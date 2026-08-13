"""Formatador de XML (requisito 6-XML e requisito 39).

Formatar, compactar, validar, e apontar linha/coluna/motivo do erro.

NUNCA usa `xml.dom.minidom.toprettyxml`. Ele insere texto em nos de TEXTO
existentes: `<nome>Ana</nome>` vira `<nome>\\n  Ana\\n</nome>`, e o conteudo do
documento MUDA. Isso e' corrupcao, nao formatacao -- e num XML de integracao o
sistema que consome o arquivo passa a receber "\\n  Ana\\n" no lugar de "Ana".

Usa `ET.indent` (Python 3.9+), que ja' pula elementos com conteudo misto, sobre a
arvore que o `seguranca.analisar_xml_seguro` produz -- com DTD e entidades
desligados.

PERDAS DO CAMINHO DA STDLIB, tratadas e nao escondidas:

  declaracao <?xml?>   capturada do original por regex e recolocada literalmente
  <!DOCTYPE>           o documento e' RECUSADO (o DTD nao pode ser expandido)
  CDATA                o documento e' RECUSADO (o ElementTree o converteria em
                       texto escapado, mudando o conteudo)
  prefixos de namespace registrados a partir do original, para nao virarem ns0:
  aspas de atributo    ' vira ", com aviso (e' semanticamente identico)

Com `lxml` instalado, `motor()` devolve "lxml" e o CDATA deixa de ser um problema.
UMA funcao decide; o resto do modulo tem duas implementacoes atras da mesma
assinatura, entao instalar lxml depois nao muda nenhuma chamada.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.parsers import expat

from textforge import log_interno, seguranca
from textforge.formatadores.base import (ErroDeSintaxe, Recusa, Resultado, Saida,
                                         unidade_de_indentacao)

log = log_interno.obter(__name__)

_DECLARACAO = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_CDATA = re.compile(r"<!\[CDATA\[")
_PREFIXO = re.compile(r"xmlns:([\w.-]+)\s*=\s*[\"']([^\"']+)[\"']")


def motor() -> str:
    """"lxml" se importavel, senao "stdlib".

    UMA funcao decide. O resto do modulo tem duas implementacoes atras da mesma
    assinatura, entao instalar o lxml depois nao muda nenhuma chamada no resto do
    programa.
    """
    try:
        import lxml.etree  # noqa: F401
    except ImportError:
        return "stdlib"
    return "lxml"


def validar(texto: str) -> ErroDeSintaxe | None:
    """None se bem-formado. Usa `expat` direto: mensagem e posicao melhores.

    A coluna sai em CARACTERES -- ver a medicao em `seguranca.posicao_do_erro`.
    """
    if not texto.strip():
        return ErroDeSintaxe(1, 1, "o documento esta' vazio", 0, "")
    analisador = expat.ParserCreate()
    # Validar NAO expande entidades: uma entidade nao declarada e' erro de sintaxe
    # legitimo, e um DTD nao pode ser processado (ver seguranca.py).
    analisador.ExternalEntityRefHandler = lambda *_a: 0
    try:
        analisador.Parse(texto, True)
    except expat.ExpatError as exc:
        linha, coluna, motivo, contexto = seguranca.posicao_do_erro(exc, texto)
        return ErroDeSintaxe(linha, coluna, motivo, None, contexto)
    except ValueError as exc:
        return ErroDeSintaxe(1, 1, str(exc), None, "")
    return None


def _registrar_namespaces(texto: str) -> None:
    """Preserva os prefixos declarados no arquivo.

    Sem isto, o ElementTree reescreve `soap:Envelope` como `ns0:Envelope`. E'
    semanticamente equivalente, mas um XML de integracao passa a nao se parecer
    com o que o outro lado espera ver, e a comparacao com o original fica inutil.
    """
    for prefixo, uri in _PREFIXO.findall(texto[:20_000]):
        try:
            ET.register_namespace(prefixo, uri)
        except (ValueError, TypeError):
            pass


def _preparar(texto: str) -> tuple[ET.Element, str, list[str]] | Saida:
    """Valida e monta a arvore. Devolve (raiz, declaracao, avisos) ou a falha."""
    try:
        seguranca.conferir_tamanho(texto)
    except seguranca.EntradaGrandeDemais as exc:
        return Recusa(str(exc), "Use uma ferramenta de linha de comando para "
                               "arquivos desse tamanho.")

    # O DOCTYPE e' checado ANTES da validacao, e a ordem importa para o usuario:
    # um documento com DTD que declara entidades produz, na validacao, um erro de
    # sintaxe sobre "entidade nao declarada" -- tecnicamente verdadeiro (nao
    # expandimos o DTD) e completamente confuso. Checando primeiro, ele recebe a
    # explicacao do DTD e o caminho de sair dela.
    if seguranca.tem_doctype(texto):
        return Recusa(
            "Este XML declara um DTD (<!DOCTYPE ...>). Por seguranca, o TextForge "
            "nao expande DTDs, e formatar sem expandir mudaria o documento.",
            "Voce pode VALIDAR o arquivo sem o DTD, ou edita-lo como texto.")

    erro = validar(texto)
    if erro is not None:
        return erro

    if _CDATA.search(texto) and motor() == "stdlib":
        return Recusa(
            "Este XML tem uma secao CDATA, e o formatador da biblioteca padrao a "
            "converteria em texto escapado -- o conteudo do arquivo MUDARIA.",
            "Instale o lxml (pip install -r requirements-extras.txt) para "
            "formatar preservando o CDATA.")

    _registrar_namespaces(texto)
    avisos: list[str] = []
    try:
        raiz = seguranca.analisar_xml_seguro(texto)
    except seguranca.ErroXmlInseguro as exc:
        return Recusa(str(exc), exc.sugestao)
    except expat.ExpatError as exc:
        linha, coluna, motivo, contexto = seguranca.posicao_do_erro(exc, texto)
        return ErroDeSintaxe(linha, coluna, motivo, None, contexto)

    casamento = _DECLARACAO.match(texto)
    declaracao = casamento.group(0).strip() if casamento else ""
    if "'" in texto and '"' not in texto[:200]:
        avisos.append("As aspas simples dos atributos foram trocadas por aspas "
                      "duplas (e' equivalente em XML).")
    return raiz, declaracao, avisos


def formatar(texto: str, opcoes: dict) -> Saida:
    """Indenta hierarquicamente (o exemplo do requisito 39)."""
    preparado = _preparar(texto)
    if not isinstance(preparado, tuple):
        return preparado
    raiz, declaracao, avisos = preparado

    unidade = unidade_de_indentacao(opcoes)
    try:
        # ET.indent JA pula elementos com conteudo misto -- e' o comportamento
        # correto: indentar `<p>texto <b>forte</b> texto</p>` mudaria o conteudo.
        ET.indent(raiz, space=unidade)
        corpo = ET.tostring(raiz, encoding="unicode")
    except Exception as exc:            # noqa: BLE001 - arvore exotica
        log.warning("falha ao formatar XML: %s", exc)
        return Recusa(f"Nao foi possivel formatar este XML ({exc}).",
                      "O arquivo nao foi alterado.")

    partes = [declaracao] if declaracao else []
    partes.append(corpo.strip())
    return Resultado("\n".join(partes) + "\n", avisos)


def compactar(texto: str, opcoes: dict) -> Saida:
    """Remove a indentacao entre tags, preservando o texto dos elementos."""
    preparado = _preparar(texto)
    if not isinstance(preparado, tuple):
        return preparado
    raiz, declaracao, avisos = preparado

    _remover_espaco_entre_tags(raiz)
    corpo = ET.tostring(raiz, encoding="unicode")
    partes = [declaracao] if declaracao else []
    partes.append(corpo.strip())
    return Resultado("".join(partes), avisos)


def _remover_espaco_entre_tags(elemento: ET.Element) -> None:
    """Apaga o espaco que E' so' indentacao, e nunca o texto de conteudo.

    A diferenca: um texto que, aparado, fica vazio era indentacao; qualquer outro e'
    conteudo do documento e fica intacto. Apagar `<nome>Ana</nome>` seria destruir
    dado.
    """
    if elemento.text is not None and not elemento.text.strip():
        elemento.text = None
    if elemento.tail is not None and not elemento.tail.strip():
        elemento.tail = None
    for filho in elemento:
        _remover_espaco_entre_tags(filho)


class FormatadorXml:
    nome = "XML"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return formatar(texto, opcoes)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return compactar(texto, opcoes)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorXml()
