"""Conversao de caixa (requisito 40).

Funcoes puras `str -> str`. As tres primeiras sao triviais; as quatro de
identificador (camel, Pascal, snake, kebab) exigem SEPARAR PALAVRAS antes, e e'
ai' que a maioria das implementacoes erra.

O separador aqui trata os quatro casos que aparecem em codigo de verdade:

    "numero_guia"   -> ["numero", "guia"]     (sublinhado)
    "numero-guia"   -> ["numero", "guia"]     (hifen)
    "numeroGuia"    -> ["numero", "Guia"]     (transicao minuscula->maiuscula)
    "numeroXMLGuia" -> ["numero", "XML", "Guia"]  (fim de uma sigla)

O ultimo e' o que separa uma implementacao usavel de uma que estraga nomes:
`numeroXMLGuia` virando `numero_x_m_l_guia` e' o resultado tipico de quem usa
apenas a regra da transicao simples.
"""

from __future__ import annotations

import re

# Divide em: sigla seguida de palavra capitalizada (XMLGuia -> XML | Guia),
# palavra capitalizada, sigla inteira, sequencia de minusculas, ou numero.
_PALAVRAS = re.compile(
    r"[A-Z]+(?=[A-Z][a-z])"     # sigla antes de palavra: o "XML" de XMLGuia
    r"|[A-Z]?[a-z]+"            # Guia, guia
    r"|[A-Z]+"                  # sigla no fim: o "XML" de guiaXML
    r"|\d+"                     # numeros formam palavra propria
)


def separar_palavras(texto: str) -> list[str]:
    """Quebra um identificador nas palavras que o compoem."""
    partes: list[str] = []
    # Sublinhado, hifen, espaco e ponto sao separadores explicitos.
    for pedaco in re.split(r"[\s_\-.]+", texto):
        if pedaco:
            partes.extend(_PALAVRAS.findall(pedaco))
    return partes


# ---------------------------------------------------------------------------
# Caixa simples
# ---------------------------------------------------------------------------


def maiusculas(texto: str) -> str:
    return texto.upper()


def minusculas(texto: str) -> str:
    return texto.lower()


def titulo(texto: str) -> str:
    """Primeira letra de cada palavra em maiuscula.

    NAO usa `str.title()`: ele transforma "don't" em "Don'T" e "arquivo.txt" em
    "Arquivo.Txt", porque considera o apostrofo e o ponto como separadores de
    palavra. A regex abaixo so' quebra em espaco em branco de verdade.
    """
    return re.sub(r"(\S+)",
                  lambda m: m.group(1)[0].upper() + m.group(1)[1:],
                  texto)


def alternar(texto: str) -> str:
    """Inverte a caixa de cada letra. Serve para consertar um CAPS LOCK esquecido."""
    return texto.swapcase()


# ---------------------------------------------------------------------------
# Caixa de identificador
# ---------------------------------------------------------------------------


def camel(texto: str) -> str:
    palavras = separar_palavras(texto)
    if not palavras:
        return texto
    return palavras[0].lower() + "".join(p.capitalize() for p in palavras[1:])


def pascal(texto: str) -> str:
    palavras = separar_palavras(texto)
    if not palavras:
        return texto
    return "".join(p.capitalize() for p in palavras)


def snake(texto: str) -> str:
    palavras = separar_palavras(texto)
    if not palavras:
        return texto
    return "_".join(p.lower() for p in palavras)


def snake_maiusculo(texto: str) -> str:
    """CONSTANTE_ASSIM. Comum em .env e em arquivo de configuracao."""
    palavras = separar_palavras(texto)
    if not palavras:
        return texto
    return "_".join(p.upper() for p in palavras)


def kebab(texto: str) -> str:
    palavras = separar_palavras(texto)
    if not palavras:
        return texto
    return "-".join(p.lower() for p in palavras)


# Nome do comando em `acoes.py` -> funcao. E' o que permite o widget aplicar a
# conversao sem um `if` por caso.
POR_COMANDO = {
    "caixa.maiusculas": maiusculas,
    "caixa.minusculas": minusculas,
    "caixa.titulo": titulo,
    "caixa.camel": camel,
    "caixa.pascal": pascal,
    "caixa.snake": snake,
}
