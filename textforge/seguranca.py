"""Analise segura de XML e tetos de entrada (requisito 35).

Modelo de ameaca em uma linha: **o TextForge abre arquivos nao confiaveis que por
acaso sao formatos com poder de expansao ou de referencia externa.** Tudo aqui
decorre de "um arquivo e' dado, sempre".

MEDIDO NESTA MAQUINA (Python 3.13.7), e nao suposto:

  * `ET.fromstring` NAO resolve entidade externa: levanta ParseError com "undefined
    entity". Ou seja, XXE por `<!ENTITY x SYSTEM "file:///...">` nao funciona pelo
    ElementTree. Mas apoiar-se nisso seria fragil -- `xml.sax` e `lxml` RESOLVEM.
  * `ET.fromstring` EXPANDE entidade interna. Um billion-laughs de quatro niveis
    produziu 10.000 caracteres a partir de ~200 bytes de arquivo; com dois niveis a
    mais sao gigabytes. E' negacao de servico real, e e' o motivo principal deste
    modulo existir.
  * `ET.XMLParser` NAO expoe `.parser`. A receita comum de "endurecer os handlers do
    expat atraves do ElementTree" falha com AttributeError. Confirmado no 3.13; o
    mesmo vale no 3.14.

Por isso `analisar_xml_seguro` monta o proprio analisador sobre o `expat`, com os
handlers de DOCTYPE e de entidade RECUSANDO, e alimenta um `TreeBuilder` do
ElementTree para o resultado ser uma arvore normal.

RECUSAR TEM DE SER INFORMATIVO, nao um beco sem saida. Quem chama recebe
`ErroXmlInseguro` com uma mensagem que diz o que ha' no arquivo e o que se pode
fazer -- a interface oferece "Validar sem o DTD" e "Ver como texto".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.parsers import expat

from textforge import log_interno

log = log_interno.obter(__name__)

# Teto de aninhamento. Um XML de 200 MB profundamente aninhado mata o processo por
# recursao mesmo com as entidades desligadas.
PROFUNDIDADE_MAXIMA = 5000

# Teto de entrada para operacoes que constroem arvore. Alem disso a operacao e'
# recusada com aviso, em vez de consumir a memoria da maquina.
LIMITE_DE_ENTRADA_MB = 64

# Teto de digitos de um literal inteiro em JSON. O proprio Python levanta
# ValueError acima de 4300 digitos; capturamos para virar mensagem, nao traceback.
LIMITE_DE_DIGITOS = 4300


class ErroXmlInseguro(ValueError):
    """XML com construcao que nao vamos processar.

    `sugestao` e' o que a interface oferece ao usuario -- e' o que transforma a
    recusa em caminho, e nao em parede.
    """

    def __init__(self, mensagem: str, sugestao: str = "") -> None:
        super().__init__(mensagem)
        self.sugestao = sugestao


class EntradaGrandeDemais(ValueError):
    pass


def conferir_tamanho(texto: str, limite_mb: int = LIMITE_DE_ENTRADA_MB) -> None:
    """Levanta `EntradaGrandeDemais` acima do teto."""
    # Aproximacao por caractere e' suficiente e barata: codificar 64 MB so' para
    # medir custaria mais que a checagem vale.
    if len(texto) > limite_mb * 1024 * 1024:
        raise EntradaGrandeDemais(
            f"o documento tem mais de {limite_mb} MB. Formatar ou validar um "
            f"arquivo desse tamanho consumiria a memoria da maquina.")


def _recusar(mensagem: str, sugestao: str = ""):
    def handler(*_args, **_kwargs):
        raise ErroXmlInseguro(mensagem, sugestao)
    return handler


def tem_doctype(texto: str) -> bool:
    """O documento declara DOCTYPE? Barato, para a interface decidir antes."""
    inicio = texto[:4096].lstrip()
    return "<!DOCTYPE" in inicio or "<!doctype" in inicio


def remover_doctype(texto: str) -> str:
    """Devolve uma COPIA sem o DOCTYPE.

    E' o caminho "Validar sem o DTD": seguro (nada e' expandido) e e' o que o
    usuario quer de fato quando o arquivo tem um DTD que ele nao controla.

    Nao usa regex sobre o arquivo inteiro: o DOCTYPE pode conter "]>" dentro de um
    comentario, e um regex ganancioso cortaria conteudo. A varredura conta os
    colchetes.
    """
    inicio = texto.find("<!DOCTYPE")
    if inicio < 0:
        inicio = texto.find("<!doctype")
    if inicio < 0:
        return texto

    profundidade = 0
    i = inicio
    while i < len(texto):
        ch = texto[i]
        if ch == "[":
            profundidade += 1
        elif ch == "]":
            profundidade -= 1
        elif ch == ">" and profundidade <= 0:
            return texto[:inicio] + texto[i + 1:]
        i += 1
    return texto[:inicio]


def analisar_xml_seguro(texto: str, *,
                        profundidade_maxima: int = PROFUNDIDADE_MAXIMA,
                        limite_mb: int = LIMITE_DE_ENTRADA_MB) -> ET.Element:
    """Le' XML sem DTD, sem entidades, sem rede e sem disco.

    Levanta:
      `ErroXmlInseguro`      DOCTYPE, declaracao de entidade ou entidade externa
      `EntradaGrandeDemais`  documento acima do teto
      `expat.ExpatError`     XML malformado (a mensagem tem linha e coluna)

    NAO usa `ET.fromstring`: ele expande entidade interna, e e' por ai' que o
    billion-laughs entra. E nao da' para endurecer o analisador dele por fora --
    `ET.XMLParser` nao expoe `.parser` (medido).
    """
    conferir_tamanho(texto, limite_mb)

    # `insert_comments`/`insert_pis` fazem o TreeBuilder aceitar comentario e
    # instrucao de processamento como nos da arvore -- um formatador que os
    # descartasse estaria alterando o documento.
    construtor = ET.TreeBuilder(insert_comments=True, insert_pis=True)
    analisador = expat.ParserCreate()

    analisador.StartDoctypeDeclHandler = _recusar(
        "Este XML declara um DTD (<!DOCTYPE ...>). Por seguranca, o TextForge nao "
        "expande DTDs: um DTD pode ler arquivos do seu disco ou consumir toda a "
        "memoria da maquina.",
        "Voce pode validar o documento SEM o DTD, ou ver o arquivo como texto.")
    analisador.EntityDeclHandler = _recusar(
        "Este XML declara entidades. Expandi-las pode multiplicar o conteudo em "
        "gigabytes (o ataque conhecido como 'billion laughs').",
        "Voce pode validar o documento sem as entidades, ou ver como texto.")
    analisador.UnparsedEntityDeclHandler = _recusar(
        "Este XML declara uma entidade nao analisada, que aponta para um recurso "
        "externo.",
        "Voce pode ver o arquivo como texto.")
    # Devolver 0 aborta a resolucao da entidade externa: nada e' buscado no disco
    # nem na rede.
    analisador.ExternalEntityRefHandler = lambda *_a: 0

    profundidade = [0]

    def inicio(tag, atributos):
        profundidade[0] += 1
        if profundidade[0] > profundidade_maxima:
            raise ErroXmlInseguro(
                f"o documento passa de {profundidade_maxima} niveis de "
                f"aninhamento.",
                "Um XML tao aninhado normalmente indica arquivo gerado com "
                "defeito.")
        construtor.start(tag, atributos)

    def fim(tag):
        profundidade[0] -= 1
        construtor.end(tag)

    def comentario(dados: str) -> None:
        # SO' dentro do elemento raiz. Um comentario no PROLOGO (antes da raiz) nao
        # e' filho de ninguem, e entrega-lo ao TreeBuilder o transformaria num
        # segundo elemento de topo -- o que faz o analisador falhar com "multiple
        # elements on top level". O `ET.fromstring` da stdlib tambem os descarta.
        if profundidade[0] > 0:
            construtor.comment(dados)

    def instrucao(alvo: str, dados: str) -> None:
        if profundidade[0] > 0:
            construtor.pi(alvo, dados)

    analisador.StartElementHandler = inicio
    analisador.EndElementHandler = fim
    analisador.CharacterDataHandler = construtor.data
    analisador.CommentHandler = comentario
    analisador.ProcessingInstructionHandler = instrucao

    analisador.Parse(texto, True)
    return construtor.close()


# ---------------------------------------------------------------------------
# Posicao de erro
# ---------------------------------------------------------------------------


def posicao_do_erro(erro: expat.ExpatError,
                    texto: str) -> tuple[int, int, str, str]:
    """(linha base 1, coluna base 1, motivo, conteudo da linha) de um ExpatError.

    MEDIDO nesta maquina, e ao contrario do que se costuma supor: quando a entrada
    e' `str`, o `pyexpat` reporta a coluna em CARACTERES, nao em bytes do UTF-8.
    Verificado com prefixos de 0, 2 e 6 acentos, onde bytes e caracteres divergem
    em ate' 6 posicoes -- o offset acompanhou os CARACTERES nos tres casos.

    Por isso NAO ha' conversao aqui. Aplicar a correcao byte->caractere que a
    documentacao informal recomenda deslocaria a coluna para tras em todo XML
    acentuado, ou seja, introduziria exatamente o defeito que ela promete corrigir.
    """
    linhas = texto.split("\n")
    numero = max(1, erro.lineno)
    conteudo = linhas[numero - 1] if numero - 1 < len(linhas) else ""
    coluna = max(1, (erro.offset or 0) + 1)
    try:
        motivo = expat.ErrorString(erro.code)
    except Exception:            # noqa: BLE001 - codigo desconhecido
        motivo = str(erro)
    return numero, coluna, traduzir(motivo), conteudo


MENSAGENS = {
    "not well-formed (invalid token)": "caractere invalido nesta posicao",
    "no element found": "o documento esta' vazio ou incompleto",
    "mismatched tag": "a tag de fechamento nao corresponde a' de abertura",
    "junk after document element": "ha' conteudo depois do elemento raiz "
                                   "(um XML tem UM elemento raiz)",
    "unclosed token": "uma tag ou string nao foi fechada",
    "undefined entity": "entidade nao declarada (&nome;)",
    "duplicate attribute": "o mesmo atributo aparece duas vezes na tag",
    "syntax error": "erro de sintaxe",
    "unclosed CDATA section": "uma secao CDATA nao foi fechada",
    "reference to invalid character number": "referencia a um caractere invalido",
    "XML or text declaration not at start of entity":
        "a declaracao <?xml ...?> tem de ser a PRIMEIRA coisa do arquivo",
    "encoding specified in XML declaration is incorrect":
        "a codificacao declarada nao corresponde ao conteudo",
}


def traduzir(motivo: str) -> str:
    """Mensagem do expat em portugues, quando conhecida.

    A mensagem original vai entre parenteses: quem procurar o texto em ingles na
    internet ainda precisa dele.
    """
    for chave, traducao in MENSAGENS.items():
        if motivo.startswith(chave):
            return f"{traducao} ({motivo})"
    return motivo
