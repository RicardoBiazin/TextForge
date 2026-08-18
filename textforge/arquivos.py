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

    @classmethod
    def de_caminho(cls, caminho: pathlib.Path,
                   dados: bytes | None = None) -> "Assinatura":
        try:
            info = caminho.stat()
        except OSError:
            return cls(existe=False)
        digest = ""
        if info.st_size <= LIMITE_PARA_HASH:
            if dados is not None:
                digest = hashlib.sha256(dados).hexdigest()
            else:
                try:
                    digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
                except OSError:
                    digest = ""
        return cls(existe=True, tamanho=info.st_size,
                   mtime_ns=info.st_mtime_ns, sha256=digest)

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
        if (self.sha256 and outra.sha256 and self.sha256 != outra.sha256
                and not partes):
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
