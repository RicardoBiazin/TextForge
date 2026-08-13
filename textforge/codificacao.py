"""Deteccao de codificacao, fim de linha e binario-ou-texto.

Este e' o modulo onde um erro CORROMPE ARQUIVO DO USUARIO, e por isso ele e' mais
conservador do que precisaria ser em qualquer outro lugar do programa.

A cascata de deteccao, na ordem exata (requisito 5):

  1. BOM              -- decisivo. UTF-32 antes de UTF-16: os bytes de UTF-32-LE
                         (FF FE 00 00) COMECAM com o BOM de UTF-16-LE (FF FE), e
                         testar na ordem errada leria um arquivo UTF-32 como
                         UTF-16 cheio de caracteres nulos.
  2. binario?         -- se for, nao ha' texto a decodificar; vai para o hex.
  3. UTF-16 sem BOM   -- pela proporcao de bytes nulos em posicoes pares ou
                         impares. Vem ANTES do UTF-8 estrito porque os bytes de
                         um arquivo UTF-16 ASCII (b"n\\x00u\\x00...") sao UTF-8
                         perfeitamente valido -- U+0000 e' um caractere UTF-8
                         legitimo -- e na ordem inversa o arquivo seria lido como
                         texto cheio de caracteres nulos. O charset-normalizer
                         tambem e' fraco neste caso.
  4. UTF-8 estrito    -- uma passada, barato, e a resposta certa na esmagadora
                         maioria dos casos. Vir ANTES do charset-normalizer evita
                         que ele erre num arquivo curto com um unico acento.
                         Recusado se o resultado contiver U+0000: texto de
                         verdade nao contem nulos.
  5. declaracao no    -- <?xml encoding="...">, <meta charset>, e a linha
     proprio arquivo     `coding:` do PEP 263. So' consultada depois que o UTF-8
                         estrito falhou, porque um arquivo ASCII puro que se
                         declara latin-1 da' o mesmo resultado nos dois.
  6. charset-normalizer
  7. cp1252 com errors="replace" -- o fallback do Windows em pt-BR, que e' o que
                         um .txt, .log ou .dat legado desta maquina realmente e'.

Se o passo 7 produzir qualquer U+FFFD, `Perfil.substituicoes` fica positivo, a
barra de status mostra a codificacao em vermelho e a aba entra em SOMENTE
LEITURA. Um editor nao deve deixar salvar em cima de um arquivo que ele nao
conseguiu ler direito -- e' a forma mais rapida de destruir dados.
"""

from __future__ import annotations

import codecs
import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------

# (bytes do BOM, nome do codec para decodificar, nome canonico para exibir).
# ATENCAO A' ORDEM: UTF-32 tem de vir antes de UTF-16.
BOMS: tuple[tuple[bytes, str, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32-le", "UTF-32 LE"),
    (codecs.BOM_UTF32_BE, "utf-32-be", "UTF-32 BE"),
    (codecs.BOM_UTF8, "utf-8", "UTF-8 BOM"),
    (codecs.BOM_UTF16_LE, "utf-16-le", "UTF-16 LE"),
    (codecs.BOM_UTF16_BE, "utf-16-be", "UTF-16 BE"),
)

# Codificacoes oferecidas ao usuario, com o rotulo que aparece na interface.
# A ordem e' a de utilidade pratica nesta maquina, nao a alfabetica.
OFERECIDAS: tuple[tuple[str, str], ...] = (
    ("utf-8", "UTF-8"),
    ("utf-8-sig", "UTF-8 BOM"),
    ("utf-16-le", "UTF-16 LE"),
    ("utf-16-be", "UTF-16 BE"),
    ("cp1252", "Windows-1252"),
    ("iso-8859-1", "ISO-8859-1"),
    ("ascii", "ASCII"),
    ("cp850", "IBM850 (DOS)"),
    ("utf-32-le", "UTF-32 LE"),
)

ROTULOS = dict(OFERECIDAS)

# Assinaturas de arquivo binario conhecido. Um `.dat` que comeca com uma destas
# nao e' texto, por mais que a proporcao de bytes imprimiveis diga o contrario.
ASSINATURAS: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "ZIP / DOCX / XLSX / JAR"),
    (b"PK\x05\x06", "ZIP vazio"),
    (b"%PDF", "PDF"),
    (b"\x7fELF", "executavel ELF"),
    (b"MZ", "executavel do Windows"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"BM", "BMP"),
    (b"SQLite format 3\x00", "banco SQLite"),
    (b"\x1f\x8b", "GZIP"),
    (b"Rar!\x1a\x07", "RAR"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip"),
    (b"\xd0\xcf\x11\xe0", "documento OLE (DOC/XLS antigo)"),
    (b"\x00\x00\x01\x00", "icone do Windows"),
    (b"OggS", "OGG"),
    (b"ID3", "MP3"),
    (b"RIFF", "WAV / AVI"),
    (b"\xca\xfe\xba\xbe", "classe Java"),
)

# Quantos bytes examinar. 8 KB decidem binario-ou-texto; 512 KB decidem qualquer
# codificacao -- e a deteccao roda ao abrir cada arquivo, entao o teto importa.
AMOSTRA_BINARIO = 8 * 1024
AMOSTRA_CODIFICACAO = 512 * 1024

# Minimo de bytes nao-ASCII para o charset-normalizer ser consultado.
#
# Medido nesta maquina: para b"cora\xe7\xe3o" (7 bytes, 2 nao-ASCII) ele responde
# "cp1006", uma pagina de codigo arabe, e o texto sai como mojibake. Com poucos
# bytes nao-ASCII varias codificacoes explicam os mesmos bytes igualmente bem, e
# o palpite dele e' ruido. Abaixo deste limite, a codificacao legada configurada
# (cp1252) e' a resposta muito mais provavel para um arquivo local.
MINIMO_NAO_ASCII_PARA_DETECTOR = 16

# Codificacoes latinas de byte unico que sao MUTUAMENTE AMBIGUAS: compartilham a
# maior parte da faixa alta e diferem em poucos caracteres, entao nenhum detector
# estatistico consegue separa-las com confianca.
#
# Medido: para texto em portugues gravado em cp1252, o charset-normalizer responde
# "cp1250" com chaos=0.0 -- ou seja, ele proprio nao ve nenhuma evidencia contra.
# A diferenca pratica e' que 0xE3 e' "a" com tilde em cp1252 e "a" com breve em
# cp1250: "coracao" viraria "coracao" com o acento errado em TODO arquivo legado
# brasileiro.
#
# Quando o detector escolhe uma destas E a codificacao legada configurada tambem
# esta' na lista, o empate e' resolvido pela CONFIGURACAO, nao pela ordem interna
# da biblioteca. E' a unica informacao real disponivel: a maquina do usuario.
LATINAS_AMBIGUAS = frozenset({
    "cp1250", "cp1252", "cp1254", "cp1257", "cp1258",
    "iso8859-1", "iso8859-2", "iso8859-3", "iso8859-4",
    "iso8859-9", "iso8859-13", "iso8859-14", "iso8859-15", "iso8859-16",
    "mac-roman", "mac-latin2", "cp850", "cp852", "cp858", "cp437",
})

# Proporcao de bytes fora do conjunto "de texto" a partir da qual consideramos
# binario. 30% e' folgado o bastante para um .dat de largura fixa em cp1252 com
# muitos acentos passar, e apertado o bastante para um dump de struct nao passar.
LIMITE_DE_BYTES_ESTRANHOS = 0.30

# Bytes que aparecem em texto de verdade: imprimiveis ASCII, os controles uteis, e
# a faixa alta inteira (que em cp1252 e latin-1 sao letras acentuadas).
BYTES_DE_TEXTO = frozenset(
    bytes(range(0x20, 0x7F)) + b"\t\n\r\f\v\b\x1b\x07" + bytes(range(0x80, 0x100)))

# Declaracao de codificacao dentro do proprio arquivo.
_DECL_XML = re.compile(rb"""<\?xml[^>]*?encoding\s*=\s*["']([\w.\-]+)["']""",
                       re.IGNORECASE)
_DECL_HTML = re.compile(rb"""<meta[^>]*?charset\s*=\s*["']?([\w.\-]+)""",
                        re.IGNORECASE)
_DECL_PEP263 = re.compile(rb"coding[:=]\s*([-\w.]+)")

CRLF, LF, CR = "\r\n", "\n", "\r"
ROTULO_EOL = {CRLF: "CRLF", LF: "LF", CR: "CR"}
EOL_POR_NOME = {"crlf": CRLF, "lf": LF, "cr": CR}

# U+2029, SEPARADOR DE PARAGRAFO. O Qt usa este caractere no lugar da quebra de
# linha em `QTextDocument.toRawText()` e em `QTextCursor.selectedText()`.
#
# Definido AQUI, com escape, e importado por quem precisa -- e' a unica definicao
# no programa. Escrito como "\\u2029" de proposito: o caractere literal e'
# invisivel no editor e no diff, e um literal invisivel num `replace()` e' um bug
# impossivel de ver em revisao de codigo.
SEPARADOR_DE_PARAGRAFO = " "


# ---------------------------------------------------------------------------
# Resultado da deteccao
# ---------------------------------------------------------------------------


@dataclass
class Perfil:
    """O que a deteccao descobriu sobre um arquivo."""

    codec: str = "utf-8"          # nome de codec do Python, para (de)codificar
    bom: bytes = b""              # os bytes literais do BOM, para reescrever igual
    texto: str = ""               # ja' decodificado, SEM o BOM
    binario: bool = False
    assinatura: str = ""          # "PDF", "ZIP", ... quando binario
    confianca: int = 0            # 0..100
    substituicoes: int = 0        # quantos U+FFFD entraram no texto
    como_decidiu: str = ""        # para o log e para o dialogo de propriedades

    @property
    def rotulo(self) -> str:
        """Como a codificacao aparece na barra de status."""
        if self.bom == codecs.BOM_UTF8:
            return "UTF-8 BOM"
        return ROTULOS.get(self.codec, self.codec.upper())

    @property
    def suspeito(self) -> bool:
        """True quando a leitura perdeu caracteres. Bloqueia a edicao."""
        return self.substituicoes > 0


@dataclass(frozen=True)
class Perda:
    """Um caractere que a codificacao destino nao representa."""

    linha: int                    # base 1, porque vai direto para a tela
    coluna: int                   # base 1, em caracteres
    caractere: str
    nome_unicode: str


@dataclass
class PerfilDeLinha:
    """Fim de linha e indentacao de um texto ja' decodificado."""

    fim_de_linha: str = CRLF
    misto: bool = False
    contagens: dict[str, int] = field(default_factory=dict)
    termina_com_nova_linha: bool = True

    @property
    def rotulo(self) -> str:
        return ROTULO_EOL.get(self.fim_de_linha, "CRLF")


# ---------------------------------------------------------------------------
# Binario ou texto (o caso do .dat -- requisito 7)
# ---------------------------------------------------------------------------


def assinatura_de(dados: bytes) -> str:
    for marca, nome in ASSINATURAS:
        if dados.startswith(marca):
            return nome
    return ""


def _parece_utf16_sem_bom(amostra: bytes) -> str:
    """"utf-16-le", "utf-16-be" ou "" -- pela distribuicao dos bytes nulos.

    Texto ASCII em UTF-16 tem um byte nulo a cada dois. Olhar so' "tem NUL?" faria
    esse arquivo ser classificado como binario; olhar a POSICAO dos nulos resolve.
    """
    if len(amostra) < 4:
        return ""
    pares = amostra[0::2]
    impares = amostra[1::2]
    nulos_pares = pares.count(0) / max(1, len(pares))
    nulos_impares = impares.count(0) / max(1, len(impares))
    if nulos_impares > 0.3 and nulos_pares < 0.1:
        return "utf-16-le"          # 'a' -> 61 00
    if nulos_pares > 0.3 and nulos_impares < 0.1:
        return "utf-16-be"          # 'a' -> 00 61
    return ""


def parece_binario(dados: bytes) -> bool:
    """Decide sobre os primeiros 8 KB. Ver a ordem no docstring do modulo.

    Um `.dat` de largura fixa em cp1252 passa como texto; um dump de struct com
    inteiros nao passa. E um arquivo UTF-16 sem BOM -- que e' cheio de bytes
    nulos -- tambem passa, porque a checagem de UTF-16 vem antes da de NUL.
    """
    if not dados:
        return False              # arquivo vazio e' texto vazio, nao binario
    amostra = dados[:AMOSTRA_BINARIO]

    for marca, _, _ in BOMS:
        if dados.startswith(marca):
            return False
    if _parece_utf16_sem_bom(amostra):
        return False
    if assinatura_de(dados):
        return True
    if b"\x00" in amostra:
        return True
    estranhos = sum(1 for b in amostra if b not in BYTES_DE_TEXTO)
    return estranhos / len(amostra) > LIMITE_DE_BYTES_ESTRANHOS


# ---------------------------------------------------------------------------
# Declaracao dentro do arquivo
# ---------------------------------------------------------------------------


def _codec_valido(nome: str) -> str:
    """Nome canonico do codec, ou "" se o Python nao conhece."""
    try:
        return codecs.lookup(nome).name
    except (LookupError, TypeError, ValueError):
        return ""


def codificacao_declarada(dados: bytes) -> str:
    """Le' a codificacao que o proprio arquivo anuncia. "" se nao anuncia.

    So' os primeiros 2 KB: as tres formas (declaracao XML, meta charset e a linha
    `coding:` do PEP 263) sao obrigatoriamente no inicio do arquivo, e varrer o
    arquivo todo acharia a palavra "encoding" dentro de um dado qualquer.
    """
    inicio = dados[:2048]
    for padrao in (_DECL_XML, _DECL_HTML):
        achado = padrao.search(inicio)
        if achado:
            nome = _codec_valido(achado.group(1).decode("ascii", "ignore"))
            if nome:
                return nome
    # PEP 263 vale so' nas duas primeiras linhas de um arquivo Python.
    for linha in inicio.split(b"\n", 2)[:2]:
        if linha.lstrip().startswith(b"#"):
            achado = _DECL_PEP263.search(linha)
            if achado:
                nome = _codec_valido(achado.group(1).decode("ascii", "ignore"))
                if nome:
                    return nome
    return ""


# ---------------------------------------------------------------------------
# A cascata
# ---------------------------------------------------------------------------


def detectar(dados: bytes, preferencia: str = "cp1252") -> Perfil:
    """Descobre a codificacao e devolve o texto ja' decodificado."""
    if not dados:
        return Perfil(codec="utf-8", texto="", confianca=100,
                      como_decidiu="arquivo vazio")

    # 1. BOM -- decisivo.
    for marca, codec, _rotulo in BOMS:
        if dados.startswith(marca):
            corpo = dados[len(marca):]
            texto, trocas = _decodificar(corpo, codec)
            return Perfil(codec=codec, bom=marca, texto=texto,
                          confianca=100, substituicoes=trocas,
                          como_decidiu="BOM")

    # 2. Binario?
    if parece_binario(dados):
        return Perfil(binario=True, assinatura=assinatura_de(dados),
                      confianca=100, como_decidiu="conteudo binario")

    amostra = dados[:AMOSTRA_CODIFICACAO]

    # 3. UTF-16 sem BOM. TEM de vir antes do UTF-8 estrito: os bytes de um
    #    arquivo UTF-16 ASCII (b"n\x00u\x00...") sao UTF-8 PERFEITAMENTE VALIDO,
    #    porque U+0000 e' um caractere UTF-8 legitimo. Na ordem inversa, o teste
    #    estrito ganhava e devolvia "n\x00u\x00m..." como se fosse o conteudo.
    palpite = _parece_utf16_sem_bom(amostra)
    if palpite:
        try:
            texto = dados.decode(palpite)
        except UnicodeDecodeError:
            pass
        else:
            return Perfil(codec=palpite, texto=texto, confianca=85,
                          como_decidiu="UTF-16 sem BOM")

    # 4. UTF-8 estrito. Barato e certo na maioria dos casos.
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        # Segunda guarda contra o mesmo problema: texto de verdade praticamente
        # nunca contem U+0000. Se o "UTF-8 valido" veio cheio de nulos, ele nao e'
        # texto UTF-8 -- e' outra coisa lida errado.
        if "\x00" not in texto:
            return Perfil(codec="utf-8", texto=texto, confianca=95,
                          como_decidiu="UTF-8 estrito")

    # 5. Declaracao no proprio arquivo.
    declarada = codificacao_declarada(dados)
    if declarada:
        try:
            texto = dados.decode(declarada)
        except (UnicodeDecodeError, LookupError):
            pass                 # arquivo mente sobre a propria codificacao
        else:
            return Perfil(codec=declarada, texto=texto, confianca=90,
                          como_decidiu="declarada no arquivo")

    # 6. charset-normalizer -- SO' com amostra suficiente.
    #
    # Medido: para b"cora\xe7\xe3o" (7 bytes, 2 nao-ASCII) ele responde "cp1006",
    # uma pagina de codigo arabe, e o texto sai como mojibake. Com poucos bytes
    # nao-ASCII o palpite dele e' ruido -- varias codificacoes explicam os mesmos
    # dois bytes igualmente bem, e ele nao tem como saber qual.
    #
    # Abaixo do limite, a codificacao legada configurada (cp1252 nesta maquina)
    # e' a resposta muito mais provavel para um .txt, .log ou .dat local. Acima,
    # o detector tem dados de verdade e ganha -- e' o que faz um arquivo em
    # cirilico ou japones ser reconhecido.
    nao_ascii = sum(1 for b in amostra if b > 0x7F)
    if nao_ascii >= MINIMO_NAO_ASCII_PARA_DETECTOR:
        perfil = _tentar_detector(dados, amostra)
        if perfil is not None:
            perfil = _desempatar_latinas(perfil, dados, preferencia)
            return perfil
    elif nao_ascii:
        codec = _codec_valido(preferencia) or "cp1252"
        try:
            texto = dados.decode(codec)
        except (UnicodeDecodeError, LookupError):
            pass
        else:
            return Perfil(codec=codec, texto=texto, confianca=70,
                          como_decidiu=f"poucos bytes nao-ASCII; assumido "
                                       f"{ROTULOS.get(codec, codec)}")

    # 7. Fallback. `errors="replace"` nunca falha, e `substituicoes` conta o
    #    estrago -- e' esse numero que poe a aba em somente leitura.
    codec = _codec_valido(preferencia) or "cp1252"
    texto, trocas = _decodificar(dados, codec, tolerante=True)
    return Perfil(codec=codec, texto=texto, confianca=30 if trocas else 60,
                  substituicoes=trocas,
                  como_decidiu=f"fallback ({ROTULOS.get(codec, codec)})")


def _desempatar_latinas(perfil: Perfil, dados: bytes,
                        preferencia: str) -> Perfil:
    """Prefere a codificacao legada configurada quando o empate e' real.

    Ver `LATINAS_AMBIGUAS`. Duas condicoes, as duas necessarias:

      * a escolha do detector esta' no grupo ambiguo -- senao ele achou algo com
        evidencia de verdade (Shift-JIS, cirilico, UTF) e deve ganhar;
      * a preferida tambem esta' no grupo E decodifica os bytes sem erro -- senao
        trocar seria substituir um palpite por outro pior.
    """
    preferida = _codec_valido(preferencia)
    if not preferida or preferida == perfil.codec:
        return perfil
    if perfil.codec not in LATINAS_AMBIGUAS or preferida not in LATINAS_AMBIGUAS:
        return perfil
    try:
        texto = dados.decode(preferida)
    except (UnicodeDecodeError, LookupError):
        return perfil
    return Perfil(codec=preferida, texto=texto, confianca=perfil.confianca,
                  como_decidiu=f"latinas ambiguas ({perfil.codec} vs "
                               f"{preferida}); mantida a configurada")


def _tentar_detector(dados: bytes, amostra: bytes) -> Perfil | None:
    """O palpite do charset-normalizer, ou None se ele nao ajudar."""
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return None
    else:
        try:
            melhor = from_bytes(amostra).best()
        except Exception:        # noqa: BLE001 - biblioteca de terceiros
            melhor = None
        if melhor is not None and melhor.encoding:
            codec = _codec_valido(melhor.encoding)
            if codec:
                try:
                    texto = dados.decode(codec)
                except (UnicodeDecodeError, LookupError):
                    pass
                else:
                    # `chaos` mede quanto o resultado parece improvavel. Sai como
                    # confianca para a interface poder graduar o aviso.
                    caos = float(getattr(melhor, "chaos", 0.0) or 0.0)
                    return Perfil(codec=codec, texto=texto,
                                  confianca=max(40, int(80 - caos * 100)),
                                  como_decidiu="charset-normalizer")
    return None


def _decodificar(dados: bytes, codec: str,
                 *, tolerante: bool = True) -> tuple[str, int]:
    """Decodifica e conta os U+FFFD que a tolerancia introduziu."""
    if not tolerante:
        return dados.decode(codec), 0
    texto = dados.decode(codec, errors="replace")
    return texto, texto.count("�")


# ---------------------------------------------------------------------------
# Fim de linha (requisito 4)
# ---------------------------------------------------------------------------


def detectar_fim_de_linha(texto: str,
                          padrao: str = CRLF) -> PerfilDeLinha:
    """Conta os tres tipos e escolhe o DOMINANTE.

    Nao "conserta" arquivo misto: guarda `misto=True`, mantem o dominante ao
    salvar e avisa na barra de status. Normalizar em silencio um arquivo com fins
    de linha misturados reescreveria linhas que o usuario nao tocou -- proibido
    pelo requisito 38.
    """
    if not texto:
        return PerfilDeLinha(fim_de_linha=padrao, misto=False,
                             contagens={}, termina_com_nova_linha=False)

    crlf = texto.count(CRLF)
    # \r e \n que NAO fazem parte de um par \r\n.
    lf = texto.count(LF) - crlf
    cr = texto.count(CR) - crlf

    contagens = {k: v for k, v in ((CRLF, crlf), (LF, lf), (CR, cr)) if v}
    if not contagens:
        return PerfilDeLinha(fim_de_linha=padrao, misto=False, contagens={},
                             termina_com_nova_linha=False)

    dominante = max(contagens.items(), key=lambda par: par[1])[0]
    return PerfilDeLinha(fim_de_linha=dominante,
                         misto=len(contagens) > 1,
                         contagens=contagens,
                         termina_com_nova_linha=texto.endswith(("\n", "\r")))


_QUALQUER_EOL = re.compile(r"\r\n|\n|\r")


def separar_linhas_com_eol(texto: str) -> tuple[list[str], list[str]]:
    """Separa em (linhas sem terminador, terminador que seguia cada linha).

    O terminador da ULTIMA linha e' "" quando o arquivo nao termina com quebra.
    Guardar isto e' o que permite reproduzir um arquivo de fins de linha MISTOS
    exatamente como ele veio, em vez de normalizar todas as quebras para a
    dominante -- que seria alterar linhas que o usuario nao tocou.
    """
    linhas: list[str] = []
    terminadores: list[str] = []
    posicao = 0
    for achado in _QUALQUER_EOL.finditer(texto):
        linhas.append(texto[posicao:achado.start()])
        terminadores.append(achado.group(0))
        posicao = achado.end()
    linhas.append(texto[posicao:])
    terminadores.append("")
    return linhas, terminadores


def juntar_linhas_com_eol(linhas: list[str], terminadores: list[str]) -> str:
    """O inverso de `separar_linhas_com_eol`."""
    partes: list[str] = []
    for i, linha in enumerate(linhas):
        partes.append(linha)
        partes.append(terminadores[i] if i < len(terminadores) else "")
    return "".join(partes)


def para_lf(texto: str) -> str:
    """Normaliza para \\n. E' a forma que o QTextDocument usa internamente."""
    return texto.replace(CRLF, LF).replace(CR, LF)


def de_lf(texto: str, fim_de_linha: str) -> str:
    """Re-expande \\n para o fim de linha original, na hora de salvar."""
    if fim_de_linha == LF:
        return texto
    return texto.replace(LF, fim_de_linha)


# ---------------------------------------------------------------------------
# Conversao destrutiva (requisito 5)
# ---------------------------------------------------------------------------


def conferir_conversao(texto: str, codec: str,
                       teto: int = 200) -> list[Perda]:
    """Quais caracteres o codec destino NAO representa, e onde.

    Detalhe que quase toda implementacao erra: `UnicodeEncodeError` reporta
    apenas a PRIMEIRA sequencia problematica de cada chamada. Reencodar a partir
    de `exc.end` ate' o fim da linha e' o que faz a lista sair completa, em vez
    de mostrar so' o primeiro acento de cada linha.

    Para em `teto` achados: a lista serve para o usuario DECIDIR, nao para ser um
    relatorio completo de um arquivo inteiro em japones.
    """
    try:
        codificador = codecs.lookup(codec)
    except LookupError:
        return []

    perdas: list[Perda] = []
    for numero, linha in enumerate(texto.split(LF), start=1):
        inicio = 0
        while inicio < len(linha):
            try:
                codificador.encode(linha[inicio:], "strict")
            except UnicodeEncodeError as exc:
                for passo, ch in enumerate(
                        linha[inicio + exc.start:inicio + exc.end]):
                    perdas.append(Perda(
                        linha=numero,
                        coluna=inicio + exc.start + passo + 1,
                        caractere=ch,
                        nome_unicode=unicodedata.name(
                            ch, f"U+{ord(ch):04X}")))
                    if len(perdas) >= teto:
                        return perdas
                inicio += exc.end
            except (ValueError, TypeError):
                return perdas
            else:
                break
    return perdas


def resumir_perdas(perdas: list[Perda]) -> str:
    """Uma linha por caractere distinto, com quantas vezes ele aparece.

    O dialogo mostra a tabela completa; este resumo e' para o log e para o titulo
    do aviso -- 200 linhas de "E ACUTE" nao ajudam ninguem a decidir.
    """
    if not perdas:
        return ""
    contagem: dict[str, int] = {}
    for p in perdas:
        contagem[p.caractere] = contagem.get(p.caractere, 0) + 1
    partes = [f"{ch!r} ({n}x)" for ch, n in
              sorted(contagem.items(), key=lambda par: -par[1])[:6]]
    if len(contagem) > 6:
        partes.append(f"e mais {len(contagem) - 6}")
    return ", ".join(partes)


def pode_converter(texto: str, codec: str) -> bool:
    """Atalho barato para "cabe inteiro nesta codificacao?"."""
    try:
        texto.encode(codec, errors="strict")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def codificar(texto: str, codec: str, bom: bytes = b"",
              *, substituir: bool = False) -> bytes:
    """Texto -> bytes, reescrevendo o BOM original literalmente.

    O BOM NAO e' deduzido do nome do codec: e' reproduzido exatamente como veio
    do arquivo. Um arquivo UTF-8 sem BOM tem de continuar sem BOM, e um com BOM
    tem de continuar com o mesmo BOM -- deduzir daria a um `utf-8-sig`
    reconstruido um BOM que talvez nao existisse.
    """
    erros = "replace" if substituir else "strict"
    return bom + texto.encode(codec, errors=erros)
