"""Leitura e gravacao de arquivo, e a assinatura que detecta alteracao externa.

Duas coisas moram aqui, e as duas existem para o TextForge nao destruir arquivo:

  `gravar_atomico`  -- escreve num temporario e TROCA. Se o processo morrer no
                       meio, o arquivo original continua intacto; nunca existe um
                       estado em que ele esta' meio escrito.
  `Assinatura`      -- como o arquivo estava quando o lemos. E' o que permite
                       recusar a gravacao quando outro programa mexeu no arquivo
                       enquanto ele estava aberto (requisito 27).

Detalhes do Windows que este modulo trata, e que um `open(...,'wb')` ingenuo nao:

  * `ReplaceFileW` em vez de `os.replace` quando o destino existe. O `os.replace`
    troca o arquivo por um NOVO, que herda a ACL da PASTA -- as permissoes
    explicitas do arquivo original, o dono e os fluxos alternativos se perdem. Num
    arquivo em pasta de rede com permissao especifica, isso e' dano real.
  * retry com espera crescente. Antivirus e o indexador de busca abrem o arquivo
    logo depois de ele ser escrito, e a troca falha com "acesso negado" por
    alguns milissegundos.
  * contingencia para pasta somente leitura. Criar o temporario ao lado do
    arquivo falha com EACCES em pasta protegida (o caso real de `Y:\\Sunset`); ai'
    grava direto, com o risco assumido e registrado no log.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import pathlib
import shutil
import time
from dataclasses import dataclass

from textforge import log_interno

log = log_interno.obter(__name__)

SUFIXO_TEMPORARIO = ".tfnew"

# Esperas entre as tentativas de troca, em segundos. A primeira e' imediata; as
# seguintes dao tempo ao antivirus e ao indexador de soltarem o handle.
ESPERAS = (0.0, 0.05, 0.15, 0.40)

# Acima disto nao calculamos sha256 na assinatura: ler 500 MB para saber se o
# arquivo mudou custa mais do que a informacao vale. Tamanho e mtime bastam.
LIMITE_PARA_HASH = 8 * 1024 * 1024

# Quanto se le' de CADA PONTA de um arquivo grande para a assinatura por
# amostra. 1 MB de cada lado custa milissegundos num SSD e pega toda reescrita
# real que um log ou um export sofrem.
AMOSTRA_DE_PONTA = 1024 * 1024

# Sinalizador do ReplaceFileW: garante que a troca chegue ao disco antes de a
# funcao retornar. Em unidade de rede, sem isto a troca pode ficar em cache.
REPLACEFILE_WRITE_THROUGH = 0x00000001

FILE_ATTRIBUTE_READONLY = 0x00000001
ATRIBUTOS_INVALIDOS = 0xFFFFFFFF        # o que GetFileAttributesW devolve no erro

# Erros do Windows que significam "alguem esta' segurando o arquivo, ou eu nao
# tenho direito de mexer nele" -- os unicos em que vale diagnosticar a causa.
ERROS_DE_ACESSO = (5, 32, 33)           # ACCESS_DENIED, SHARING_VIOLATION, LOCK


class FalhaNaTroca(OSError):
    """A troca falhou, com uma explicacao que serve para quem esta' na frente.

    Existe porque o OSError cru do Windows -- "[WinError 5] Acesso negado:
    'x.csv.tfnew' -> 'x.csv'" -- nao diz ao usuario o que fazer, e as duas
    causas comuns (arquivo somente-leitura, arquivo aberto no Excel) produzem
    exatamente a mesma mensagem. Guarda a `causa` para o log.
    """

    def __init__(self, mensagem: str, causa: OSError) -> None:
        super().__init__(mensagem)
        self.causa = causa


class AlteradoNoDisco(Exception):
    """O arquivo mudou fora do editor desde que foi lido.

    Carrega as duas assinaturas para o dialogo poder dizer O QUE mudou (tamanho?
    data?), em vez de um aviso generico.
    """

    def __init__(self, esperada: "Assinatura", encontrada: "Assinatura") -> None:
        super().__init__("o arquivo foi alterado por outro programa")
        self.esperada = esperada
        self.encontrada = encontrada


@dataclass(frozen=True)
class Assinatura:
    """Como o arquivo estava num instante."""

    existe: bool = False
    tamanho: int = 0
    mtime_ns: int = 0
    sha256: str = ""              # so' para arquivos pequenos; "" quando nao vale
    #: Hash das PONTAS de um arquivo grande (ver `AMOSTRA_DE_PONTA`). Vazio a
    #: menos que alguem peca, porque custa ler alguns MB.
    amostra: str = ""

    @classmethod
    def de_caminho(cls, caminho: pathlib.Path,
                   dados: bytes | None = None, *,
                   amostrar: bool = False) -> "Assinatura":
        """A assinatura do arquivo agora.

        `amostrar=True` calcula tambem o hash das pontas quando o arquivo e'
        grande demais para o sha256 completo. Nao e' o padrao porque o vigia
        confere TODO arquivo aberto a cada 2 segundos, e ler 2 MB por arquivo
        nesse ritmo seria caro por nada. Quem pede a amostra e' o caminho de
        GRAVACAO, que e' onde a garantia de nao sobrescrever importa.
        """
        try:
            info = caminho.stat()
        except OSError:
            return cls(existe=False)
        digest = ""
        amostra = ""
        if info.st_size <= LIMITE_PARA_HASH:
            if dados is not None:
                digest = hashlib.sha256(dados).hexdigest()
            else:
                try:
                    digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
                except OSError:
                    digest = ""
        elif amostrar:
            amostra = _hash_das_pontas(caminho, info.st_size)
        return cls(existe=True, tamanho=info.st_size,
                   mtime_ns=info.st_mtime_ns, sha256=digest, amostra=amostra)

    def compativel_com(self, outra: "Assinatura") -> bool:
        """O arquivo continua sendo o que lemos?

        Quando os dois lados tem sha256, ele decide -- e' o unico jeito de pegar
        a ferramenta que reescreve o arquivo PRESERVANDO o mtime (o `touch -r`,
        alguns geradores de codigo, e o proprio Git em certas operacoes). Sem o
        hash, cai para tamanho + mtime.
        """
        if self.existe != outra.existe:
            return False
        if not self.existe:
            return True
        if self.sha256 and outra.sha256:
            return self.sha256 == outra.sha256
        if self.amostra and outra.amostra:
            # Arquivo grande: as pontas decidem. Sem isto sobra so' tamanho +
            # mtime, e uma reescrita que preserve os dois seria INDETECTAVEL --
            # gravar por cima dela e' exatamente o que o requisito 27 proibe.
            return self.amostra == outra.amostra
        return (self.tamanho == outra.tamanho
                and self.mtime_ns == outra.mtime_ns)

    def descrever_diferenca(self, outra: "Assinatura") -> str:
        """Frase curta para o dialogo de alteracao externa."""
        if not outra.existe:
            return "o arquivo foi apagado ou renomeado"
        partes = []
        if self.tamanho != outra.tamanho:
            partes.append(f"tamanho mudou de {self.tamanho} para "
                          f"{outra.tamanho} bytes")
        if self.mtime_ns != outra.mtime_ns:
            partes.append("a data de modificacao mudou")
        mudou_por_dentro = (
            (self.sha256 and outra.sha256 and self.sha256 != outra.sha256)
            or (self.amostra and outra.amostra
                and self.amostra != outra.amostra))
        if mudou_por_dentro and not partes:
            partes.append("o conteudo mudou, mantendo o mesmo tamanho e data")
        return "; ".join(partes) or "o arquivo mudou"


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def ler_bytes(caminho: str | os.PathLike[str],
              limite: int | None = None) -> bytes:
    """Le' o arquivo inteiro. `limite` corta a leitura (usado na sondagem)."""
    alvo = pathlib.Path(caminho)
    with open(alvo, "rb") as f:
        return f.read() if limite is None else f.read(limite)


def tamanho_de(caminho: str | os.PathLike[str]) -> int:
    try:
        return pathlib.Path(caminho).stat().st_size
    except OSError:
        return 0


def _hash_das_pontas(caminho: pathlib.Path, tamanho: int) -> str:
    """sha256 do inicio + do fim + do tamanho de um arquivo grande.

    Ler 240 MB para conferir se ele mudou custaria mais que a propria gravacao.
    As PONTAS pegam o que muda na pratica: um log ganha linhas no fim, um export
    e' regerado do zero (e o cabecalho muda), e uma edicao por outro programa
    quase sempre desloca tudo. O tamanho entra no hash para dois arquivos com as
    mesmas pontas e miolos diferentes nao colidirem de graca.

    Nao e' garantia criptografica de igualdade, e nao precisa ser: o que se quer
    e' nao sobrescrever uma alteracao externa em silencio. Uma alteracao que
    preserve tamanho, data E as duas pontas e' um caso que nenhuma heuristica
    barata pega -- e o alerta seria dado pelo tamanho ou pela data em tudo o mais.
    """
    resumo = hashlib.sha256()
    resumo.update(str(tamanho).encode())
    try:
        with open(caminho, "rb") as f:
            resumo.update(f.read(AMOSTRA_DE_PONTA))
            if tamanho > AMOSTRA_DE_PONTA * 2:
                f.seek(tamanho - AMOSTRA_DE_PONTA)
                resumo.update(f.read(AMOSTRA_DE_PONTA))
    except OSError as exc:
        log.warning("nao foi possivel amostrar %s: %s", caminho, exc)
        return ""
    return resumo.hexdigest()


# ---------------------------------------------------------------------------
# Gravacao
# ---------------------------------------------------------------------------


def gravar_atomico(caminho: str | os.PathLike[str], dados: bytes,
                   *, preservar_metadados: bool = True) -> None:
    """Grava `dados` em `caminho` sem nunca deixar o arquivo pela metade.

    Escreve num temporario NA MESMA PASTA e troca. A mesma pasta e' obrigatoria:
    `os.replace` entre volumes diferentes falha, e e' comum o arquivo estar num
    mapeamento de rede enquanto o %TEMP% esta' em C:.
    """
    alvo = pathlib.Path(caminho)
    temporario = alvo.with_name(alvo.name + SUFIXO_TEMPORARIO)

    try:
        with open(temporario, "wb") as f:
            f.write(dados)
            f.flush()
            # fsync antes da troca: sem ele, um desligamento entre o write e o
            # replace pode deixar o temporario com conteudo vazio E ja' trocado.
            os.fsync(f.fileno())
    except OSError as exc:
        # Pasta somente leitura (o caso real de Y:\Sunset, que da' EACCES ao
        # criar qualquer arquivo ao lado). Gravar direto perde a atomicidade, mas
        # a alternativa e' o usuario simplesmente nao conseguir salvar.
        log.warning("nao foi possivel criar %s (%s); gravando direto",
                    temporario.name, exc)
        _gravar_direto(alvo, dados)
        return

    try:
        _trocar(temporario, alvo, preservar_metadados and alvo.exists())
    finally:
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                log.warning("o temporario %s ficou para tras", temporario)


def gravar_atomico_em_blocos(caminho: str | os.PathLike[str], produtor,
                             *, preservar_metadados: bool = True,
                             antes_de_trocar=None) -> int:
    """Como `gravar_atomico`, mas recebendo um GERADOR de blocos de bytes.

    Existe para o arquivo grande editavel. `gravar_atomico` pede todos os bytes
    de uma vez, e um arquivo de 240 MB na memoria e' exatamente o que o modo de
    arquivo grande existe para evitar -- salvar consumiria mais RAM do que abrir.

    Aqui o pico e' UM bloco. Os trechos nao editados sao copiados direto do mmap
    para o destino, sem nunca virar `str`. Ver `grande/gravacao.py`.

    `antes_de_trocar` roda com o temporario ja' gravado e o original ainda no
    lugar. E' a emenda que o arquivo grande exige no Windows: os blocos vem de um
    mmap SOBRE O DESTINO, entao ele precisa estar aberto durante a escrita e
    FECHADO na hora da troca -- um mmap vivo segura o arquivo e faz `ReplaceFileW`
    e `os.replace` falharem com acesso negado.

    Devolve quantos bytes foram escritos. A troca atomica e a devolucao do
    atributo somente-leitura sao as MESMAS de `gravar_atomico`: `_trocar` e
    `_replace_file_w` nao olham para o conteudo, entao valem sem alteracao.
    """
    alvo = pathlib.Path(caminho)
    temporario = alvo.with_name(alvo.name + SUFIXO_TEMPORARIO)
    escritos = 0

    try:
        with open(temporario, "wb") as f:
            for bloco in produtor:
                if bloco:
                    f.write(bloco)
                    escritos += len(bloco)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # Qualquer falha -- inclusive um cancelamento -- deixa o ORIGINAL
        # intacto, porque nada foi trocado ainda. O temporario e' removido para
        # nao deixar um arquivo de 240 MB pela metade ao lado do bom.
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                log.warning("o temporario %s ficou para tras", temporario)
        raise

    try:
        if antes_de_trocar is not None:
            antes_de_trocar()
        _trocar(temporario, alvo, preservar_metadados and alvo.exists())
    finally:
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                log.warning("o temporario %s ficou para tras", temporario)
    return escritos


def espaco_livre(caminho: str | os.PathLike[str]) -> int:
    """Bytes livres na unidade onde o arquivo mora. -1 quando nao da' para saber.

    O temporario da gravacao atomica nasce NA MESMA PASTA do destino, entao
    salvar um arquivo de 240 MB exige 240 MB livres ali -- e descobrir isso
    depois de escrever 200 MB e' o pior momento possivel.
    """
    try:
        alvo = pathlib.Path(caminho)
        pasta = alvo.parent if alvo.parent.exists() else pathlib.Path(".")
        return shutil.disk_usage(pasta).free
    except OSError as exc:
        log.warning("nao foi possivel medir o espaco livre de %s: %s",
                    caminho, exc)
        return -1


def _gravar_direto(alvo: pathlib.Path, dados: bytes) -> None:
    with open(alvo, "wb") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())


def _trocar(temporario: pathlib.Path, destino: pathlib.Path,
            usar_replacefile: bool) -> None:
    """Troca o temporario pelo destino, com retry.

    Tira o atributo somente-leitura do destino antes de trocar e o devolve
    depois: NEM `ReplaceFileW` NEM `os.replace` conseguem substituir um arquivo
    marcado como somente-leitura -- os dois falham com "acesso negado", e o
    arquivo termina com o mesmo atributo que tinha, de um jeito ou de outro.
    """
    atributos = _atributos(destino)
    tirou_somente_leitura = False
    if atributos >= 0 and atributos & FILE_ATTRIBUTE_READONLY:
        tirou_somente_leitura = _definir_atributos(
            destino, atributos & ~FILE_ATTRIBUTE_READONLY)
        log.info("%s esta' somente-leitura; atributo removido para a troca "
                 "(sera' devolvido em seguida)", destino.name)

    try:
        ultimo: OSError | None = None
        for espera in ESPERAS:
            if espera:
                time.sleep(espera)
            try:
                if usar_replacefile and _replace_file_w(temporario, destino):
                    return
                os.replace(temporario, destino)
                return
            except OSError as exc:
                ultimo = exc
                log.debug("troca falhou (%s); tentando de novo", exc)
        assert ultimo is not None
        # Diagnostica AQUI, ainda com o atributo removido: com ele de volta,
        # a sondagem de arquivo travado daria falso positivo em todo arquivo
        # somente-leitura.
        raise FalhaNaTroca(_explicar_falha(destino, ultimo), ultimo)
    finally:
        if tirou_somente_leitura:
            _definir_atributos(destino, atributos)


def _atributos(caminho: pathlib.Path) -> int:
    """Atributos Windows do arquivo; -1 quando nao da' para saber."""
    if os.name != "nt":
        return -1
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):
        return -1
    kernel32.GetFileAttributesW.restype = ctypes.c_uint32
    valor = kernel32.GetFileAttributesW(ctypes.c_wchar_p(str(caminho)))
    return -1 if valor == ATRIBUTOS_INVALIDOS else int(valor)


def _definir_atributos(caminho: pathlib.Path, valor: int) -> bool:
    if os.name != "nt" or valor < 0:
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):
        return False
    return bool(kernel32.SetFileAttributesW(ctypes.c_wchar_p(str(caminho)),
                                            ctypes.c_uint32(valor)))


def _travado_por_outro_programa(destino: pathlib.Path) -> bool:
    """Alguem esta' segurando o arquivo?

    Abrir para escrita e' a sondagem honesta: o Excel abre .csv sem permitir
    escrita nem exclusao, entao o `open` falha enquanto a planilha estiver
    aberta. Nao usa `os.access`, que no Windows olha so' o atributo e mente.
    """
    try:
        with open(destino, "r+b"):
            return False
    except OSError:
        return True


def _explicar_falha(destino: pathlib.Path, erro: OSError) -> str:
    """Transforma o erro do Windows numa frase que diz o que fazer."""
    if getattr(erro, "winerror", None) not in ERROS_DE_ACESSO:
        return str(erro)
    nome = destino.name
    if _travado_por_outro_programa(destino):
        return (f"'{nome}' esta' aberto em outro programa, que nao deixa "
                f"substitui-lo. O Excel faz isso com .csv enquanto a planilha "
                f"estiver aberta. Feche o arquivo la' e salve de novo."
                f"\n\n"
                f"O que voce escreveu NAO foi perdido: continua aqui na aba.")
    atributos = _atributos(destino)
    if atributos >= 0 and atributos & FILE_ATTRIBUTE_READONLY:
        return (f"'{nome}' esta' marcado como somente leitura e o Windows nao "
                f"deixou remover o atributo. Tire a marca nas propriedades do "
                f"arquivo, ou salve com outro nome.")
    return (f"O Windows negou a substituicao de '{nome}'. Em geral e' falta de "
            f"permissao na pasta, ou um antivirus segurando o arquivo."
            f"\n\n"
            f"Detalhe tecnico: {erro}")


def _replace_file_w(temporario: pathlib.Path, destino: pathlib.Path) -> bool:
    """`ReplaceFileW` do Windows. False se nao estiver disponivel.

    Existe justamente para trocar o CONTEUDO de um arquivo preservando dono,
    ACL, atributos e fluxos alternativos -- que e' o que `os.replace` perde,
    porque para o sistema de arquivos ele cria um arquivo novo no lugar.

    Falha aqui nao e' fatal: quem chama cai para `os.replace`. E' melhor salvar
    perdendo a ACL do que nao salvar.
    """
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):
        return False
    ok = kernel32.ReplaceFileW(ctypes.c_wchar_p(str(destino)),
                               ctypes.c_wchar_p(str(temporario)),
                               None, REPLACEFILE_WRITE_THROUGH, None, None)
    if not ok:
        erro = ctypes.get_last_error()
        log.debug("ReplaceFileW falhou (erro %d); caindo para os.replace", erro)
        return False
    return True


def gravar_conferindo(caminho: str | os.PathLike[str], dados: bytes,
                      esperada: Assinatura | None,
                      *, forcar: bool = False) -> Assinatura:
    """Grava SO' se o arquivo no disco ainda for o que lemos (requisito 27).

    Levanta `AlteradoNoDisco` quando outro programa mexeu no arquivo. Quem chama
    mostra o dialogo Recarregar / Manter o meu / Comparar e, se o usuario
    escolher manter, chama de novo com `forcar=True`.

    NUNCA sobrescreve em silencio: essa e' a regra do requisito 27, e e' o motivo
    de esta funcao existir em vez de um `gravar_atomico` direto.
    """
    alvo = pathlib.Path(caminho)
    if not forcar and esperada is not None:
        agora = Assinatura.de_caminho(alvo)
        if not esperada.compativel_com(agora):
            raise AlteradoNoDisco(esperada, agora)
    gravar_atomico(alvo, dados)
    return Assinatura.de_caminho(alvo, dados)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def pasta_aceita_escrita(pasta: str | os.PathLike[str]) -> bool:
    """Testa escrita DE VERDADE, criando e apagando um arquivo.

    `os.access(W_OK)` mente no Windows: ele olha o atributo somente-leitura e
    ignora a ACL, entao devolve True em pasta onde a escrita vai falhar. A unica
    resposta confiavel e' tentar -- foi a licao do `Y:\\Sunset`.
    """
    destino = pathlib.Path(pasta)
    sonda = destino / ".textforge-teste-de-escrita"
    try:
        sonda.write_bytes(b"")
        sonda.unlink()
        return True
    except OSError:
        return False


def abrir_no_explorer(caminho: str | os.PathLike[str]) -> bool:
    """Abre o Explorer com o arquivo selecionado.

    Usa `explorer.exe /select,` -- e nao `os.startfile`, que ABRIRIA o arquivo no
    programa associado a ele. Num editor, "abrir local do arquivo" que executa o
    arquivo seria exatamente o que o requisito 35 proibe.
    """
    if os.name != "nt":
        return False
    import subprocess
    alvo = pathlib.Path(caminho)
    try:
        # Sem shell=True e com a lista de argumentos: o caminho vem do usuario e
        # nao pode ser interpretado pelo shell.
        subprocess.Popen(["explorer.exe", f"/select,{alvo}"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except OSError as exc:
        log.warning("nao foi possivel abrir o Explorer em %s: %s", alvo, exc)
        return False
