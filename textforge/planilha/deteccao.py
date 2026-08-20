"""O que ha' dentro do pacote .xlsx -- e o que impede de grava-lo.

Duas perguntas, as duas respondidas ANTES de qualquer leitura de valor:

1. **Onde mora cada aba?** O gravador patcheia `xl/worksheets/sheetN.xml`, e o N
   NAO acompanha a ordem das abas. Numa pasta cuja terceira aba foi apagada, a
   quarta continua sendo `sheet4.xml`. O caminho certo sai de `xl/workbook.xml`
   (nome e `r:id` de cada aba) cruzado com `xl/_rels/workbook.xml.rels`
   (`r:id` -> arquivo). Deduzir pelo indice grava numa aba errada -- e' o pior
   defeito possivel neste pacote, porque o arquivo continua valido.

2. **Este pacote pode ser gravado?** Quando a resposta e' nao, o documento abre
   em SOMENTE LEITURA com o motivo escrito. Recusar a gravar e' sempre melhor
   que gravar errado (requisito 38).

A analise e' feita sobre a lista de entradas do ZIP e sobre dois XML pequenos.
Nenhuma aba e' lida aqui.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from textforge import log_interno

log = log_interno.obter(__name__)

PARTE_WORKBOOK = "xl/workbook.xml"
PARTE_RELS = "xl/_rels/workbook.xml.rels"

NS_PLANILHA = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_PLANILHA_ESTRITO = "http://purl.oclc.org/ooxml/spreadsheetml/main"
NS_RELACAO_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_RELACAO_PACOTE = "http://schemas.openxmlformats.org/package/2006/relationships"

#: Assinatura do formato OLE, que e' o que um .xlsx CRIPTOGRAFADO realmente e':
#: um contentor OLE com o pacote ZIP cifrado dentro. Tambem e' a assinatura do
#: .xls antigo, que esta' fora de escopo pelo mesmo caminho.
ASSINATURA_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ASSINATURA_ZIP = b"PK\x03\x04"

#: Teto de bytes DESCOMPACTADOS aceitos. Um ZIP de poucos KB pode declarar
#: gigabytes de conteudo (zip bomb), e um editor que abre arquivo de origem
#: desconhecida nao pode descobrir isso alocando a memoria.
TETO_DESCOMPACTADO = 512 * 1024 * 1024


@dataclass
class AbaDoPacote:
    nome: str
    parte: str                       # "xl/worksheets/sheet1.xml"
    oculta: bool = False


@dataclass
class Pacote:
    """O resultado da inspecao."""

    e_planilha: bool = False
    #: Vazio quando da' para gravar; senao, o motivo, ja' redigido para o usuario.
    motivo_somente_leitura: str = ""
    abas: list[AbaDoPacote] = field(default_factory=list)
    data1904: bool = False
    tem_macros: bool = False
    #: Partes do ZIP que o TextForge nao entende mas PRESERVA ao gravar. Vai para
    #: a barra de status, para o usuario saber que os graficos continuam la'.
    preservadas: list[str] = field(default_factory=list)


#: Prefixos de parte que denunciam conteudo rico. Nenhum e' problema -- todos
#: sobrevivem intactos, porque o gravador so' toca na aba editada --, mas dizer
#: isso na barra de status e' o que da' confianca para o usuario salvar.
RICAS = (
    ("xl/charts/", "grafico"),
    ("xl/drawings/", "desenho"),
    ("xl/media/", "imagem"),
    ("xl/pivotCache/", "tabela dinamica"),
    ("xl/pivotTables/", "tabela dinamica"),
    ("xl/slicers/", "segmentacao"),
    ("xl/threadedComments/", "comentario"),
    ("xl/comments", "comentario"),
    ("xl/vbaProject.bin", "macro"),
)


def parece_planilha(dados: bytes) -> bool:
    """Barato o suficiente para rodar no caminho de abertura de todo arquivo."""
    if not dados.startswith(ASSINATURA_ZIP):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as pacote:
            return PARTE_WORKBOOK in pacote.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def inspecionar(dados: bytes) -> Pacote:
    """Le' a estrutura do pacote. Nunca levanta: o motivo vem no resultado."""
    pacote = Pacote()

    if dados.startswith(ASSINATURA_OLE):
        pacote.motivo_somente_leitura = (
            "planilha protegida por senha ou no formato .xls antigo")
        return pacote
    if not dados.startswith(ASSINATURA_ZIP):
        pacote.motivo_somente_leitura = "nao e' um pacote .xlsx"
        return pacote

    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as zip_:
            nomes = zip_.namelist()
            if PARTE_WORKBOOK not in nomes:
                pacote.motivo_somente_leitura = (
                    "o pacote nao tem xl/workbook.xml")
                return pacote
            pacote.e_planilha = True

            total = sum(info.file_size for info in zip_.infolist())
            if total > TETO_DESCOMPACTADO:
                pacote.motivo_somente_leitura = (
                    f"o pacote declara {total / (1024 * 1024):.0f} MB "
                    "descompactados")
                return pacote

            workbook = zip_.read(PARTE_WORKBOOK)
            rels = zip_.read(PARTE_RELS) if PARTE_RELS in nomes else b""
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        pacote.motivo_somente_leitura = f"pacote ilegivel: {exc}"
        return pacote

    if b"<!DOCTYPE" in workbook:
        # Um DTD interno permite expansao recursiva de entidades (billion
        # laughs), e o expat a executa antes de qualquer codigo nosso rodar.
        # Nenhuma planilha legitima traz DTD.
        pacote.motivo_somente_leitura = "o XML da pasta declara um DTD"
        return pacote

    if NS_PLANILHA_ESTRITO.encode() in workbook:
        pacote.motivo_somente_leitura = (
            "pacote no perfil OOXML Strict, que usa outro espaco de nomes")
        return pacote

    try:
        _ler_workbook(workbook, rels, pacote)
    except ET.ParseError as exc:
        pacote.motivo_somente_leitura = f"xl/workbook.xml invalido: {exc}"
        return pacote

    if not pacote.abas:
        pacote.motivo_somente_leitura = "a pasta nao declara nenhuma aba"
        return pacote
    if pacote.data1904:
        pacote.motivo_somente_leitura = (
            "pasta no sistema de data de 1904 (Excel para Mac antigo)")
        return pacote

    vistas: list[str] = []
    for prefixo, rotulo in RICAS:
        if any(nome.startswith(prefixo) for nome in nomes) and rotulo not in vistas:
            vistas.append(rotulo)
    pacote.preservadas = vistas
    pacote.tem_macros = "xl/vbaProject.bin" in nomes
    return pacote


def _ler_workbook(workbook: bytes, rels: bytes, pacote: Pacote) -> None:
    raiz = ET.fromstring(workbook)

    propriedades = raiz.find(f"{{{NS_PLANILHA}}}workbookPr")
    if propriedades is not None:
        pacote.data1904 = propriedades.get("date1904", "0") in ("1", "true")

    alvos = _alvos_das_relacoes(rels)
    abas = raiz.find(f"{{{NS_PLANILHA}}}sheets")
    if abas is None:
        return
    for indice, aba in enumerate(abas, start=1):
        identificador = aba.get(f"{{{NS_RELACAO_DOC}}}id", "")
        alvo = alvos.get(identificador, "")
        if not alvo:
            # Sem relacao declarada nao ha' como saber qual arquivo e' esta aba.
            # O palpite `sheet{indice}.xml` e' exatamente o erro que este modulo
            # existe para evitar, entao a aba entra sem parte e o leitor a marca
            # como somente leitura.
            log.warning("aba %r sem relacao %r", aba.get("name"), identificador)
        pacote.abas.append(AbaDoPacote(
            nome=aba.get("name", f"Planilha{indice}"),
            parte=alvo,
            oculta=aba.get("state", "visible") != "visible"))


def _alvos_das_relacoes(rels: bytes) -> dict[str, str]:
    """`r:id` -> caminho da parte, ja' normalizado para dentro do ZIP."""
    if not rels or b"<!DOCTYPE" in rels:
        return {}
    try:
        raiz = ET.fromstring(rels)
    except ET.ParseError:
        return {}

    alvos: dict[str, str] = {}
    for relacao in raiz.findall(f"{{{NS_RELACAO_PACOTE}}}Relationship"):
        if relacao.get("TargetMode") == "External":
            continue
        alvo = relacao.get("Target", "")
        if not alvo:
            continue
        # Um Target absoluto ("/xl/worksheets/sheet1.xml") ja' e' o caminho no
        # pacote; um relativo ("worksheets/sheet1.xml") e' relativo a "xl/",
        # que e' a pasta do workbook.xml.
        caminho = (alvo.lstrip("/") if alvo.startswith("/")
                   else posixpath.normpath(posixpath.join("xl", alvo)))
        alvos[relacao.get("Id", "")] = caminho.replace("\\", "/")
    return alvos
