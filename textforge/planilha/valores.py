"""Conversao entre o que o usuario digita e o que o OOXML guarda.

Tres problemas moram aqui, e nenhum e' obvio:

1. **O separador decimal.** Um editor usado em pt-BR recebe "1.234,56" e
   "1234.56" na mesma sessao. A regra e' a mesma de `analisadores/de_csv.py`:
   com os DOIS separadores presentes, o ultimo e' o decimal; com so' um, ele e'
   decimal se sobrar exatamente um e ele nao separar grupos de tres digitos.

2. **A data.** O Excel guarda data como NUMERO DE SERIE, e o que faz "45366"
   aparecer como "15/03/2024" e' o formato numerico -- que vive no estilo da
   celula, e nao na celula. Por isso o gravador escreve o serial e NAO toca no
   atributo `s`: e' o `s` que carrega o formato.

3. **O bug de 1900.** O Excel acredita que 1900 foi bissexto. A origem util e',
   portanto, 1899-12-30, e nao 1899-12-31 -- e' o desvio de um dia que acerta
   todas as datas a partir de 1900-03-01, que sao as unicas que aparecem na
   pratica. Datas anteriores a 1900-03-01 sao raras e ficariam um dia erradas;
   por isso `serial_de_data` recusa qualquer data antes disso.
"""

from __future__ import annotations

import datetime as dt
import re

#: Origem do numero de serie no sistema de data padrao. Ver o bug de 1900 acima.
ORIGEM_1900 = dt.date(1899, 12, 30)
ORIGEM_1904 = dt.date(1904, 1, 1)
#: Antes disso o bug de 1900 desloca o resultado em um dia.
PRIMEIRA_DATA_CONFIAVEL = dt.date(1900, 3, 1)

_NUMERO = re.compile(r"^[+-]?[\d.,]*\d[\d.,]*(?:[eE][+-]?\d+)?$")
_GRUPO_DE_MILHAR = re.compile(r"^\d{1,3}(?:([.,])\d{3})+$")

#: Formatos aceitos ao digitar uma data, na ordem de tentativa. O pt-BR vem
#: primeiro de proposito: "03/04/2024" e' 3 de abril para quem usa este editor.
FORMATOS_DE_DATA = (
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y",
)
FORMATOS_DE_DATA_HORA = (
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Numeros
# ---------------------------------------------------------------------------


def ler_numero(texto: str) -> float | None:
    """O texto como numero, ou None se nao for um.

    None, e nao uma excecao: quem chama esta perguntando "isto e' numero?", e o
    caso negativo e' o comum, nao o excepcional.
    """
    limpo = texto.strip()
    if not limpo or not _NUMERO.match(limpo):
        return None

    sinal = ""
    if limpo[0] in "+-":
        sinal, limpo = ("-" if limpo[0] == "-" else ""), limpo[1:]

    corpo, expoente = limpo, ""
    if "e" in corpo.lower():
        corte = corpo.lower().index("e")
        corpo, expoente = corpo[:corte], corpo[corte:]

    tem_ponto, tem_virgula = "." in corpo, "," in corpo
    if tem_ponto and tem_virgula:
        decimal = "," if corpo.rfind(",") > corpo.rfind(".") else "."
        corpo = corpo.replace("," if decimal == "." else ".", "")
        corpo = corpo.replace(decimal, ".")
    elif tem_ponto or tem_virgula:
        separador = "." if tem_ponto else ","
        # "1.234" e' mil duzentos e trinta e quatro, e nao 1,234: com um unico
        # separador seguido de exatamente tres digitos em cada grupo, ele separa
        # MILHAR. Tratar como decimal transformaria valores em outros mil vezes
        # menores -- e num arquivo financeiro isso passa despercebido.
        if _GRUPO_DE_MILHAR.match(corpo):
            corpo = corpo.replace(separador, "")
        else:
            corpo = corpo.replace(separador, ".")

    try:
        return float(sinal + corpo + expoente)
    except ValueError:
        return None


def numero_como_texto(valor: float) -> str:
    """O numero como o OOXML o quer: ponto decimal, sem separador de milhar."""
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if float(valor).is_integer() and abs(valor) < 1e15:
        return str(int(valor))
    return repr(float(valor))


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------


def ler_data(texto: str) -> dt.datetime | None:
    """O texto como data, ou None. Aceita os formatos de `FORMATOS_DE_DATA`."""
    limpo = texto.strip()
    if not limpo:
        return None
    for formato in FORMATOS_DE_DATA_HORA:
        try:
            return dt.datetime.strptime(limpo, formato)
        except ValueError:
            continue
    for formato in FORMATOS_DE_DATA:
        try:
            return dt.datetime.strptime(limpo, formato)
        except ValueError:
            continue
    return None


def data_como_texto(valor: dt.date | dt.time) -> str:
    """Como a grade exibe uma data. Sem hora quando nao ha' hora."""
    if isinstance(valor, dt.datetime):
        if (valor.hour, valor.minute, valor.second) == (0, 0, 0):
            return valor.strftime("%d/%m/%Y")
        return valor.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(valor, dt.date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, dt.time):
        return valor.strftime("%H:%M:%S")
    if isinstance(valor, dt.timedelta):
        return str(valor)
    return str(valor)


def serial_de_data(valor: dt.date, data1904: bool) -> float:
    """A data como numero de serie do Excel.

    Levanta ValueError para data anterior a 1900-03-01, onde o bug de 1900
    deslocaria o resultado -- e' preferivel recusar a gravar um dia errado.
    """
    if isinstance(valor, dt.datetime):
        dia, hora = valor.date(), valor.time()
    elif isinstance(valor, dt.date):
        dia, hora = valor, dt.time()
    else:
        raise ValueError(f"nao e' uma data: {valor!r}")

    origem = ORIGEM_1904 if data1904 else ORIGEM_1900
    if not data1904 and dia < PRIMEIRA_DATA_CONFIAVEL:
        raise ValueError("data anterior a 01/03/1900: o Excel trata 1900 como "
                         "bissexto e o numero de serie ficaria um dia errado")
    if dia < origem:
        raise ValueError(f"data anterior a origem {origem:%d/%m/%Y}")

    fracao = (hora.hour * 3600 + hora.minute * 60 + hora.second) / 86400
    return (dia - origem).days + fracao


# ---------------------------------------------------------------------------
# Referencias de celula (A1, BC27)
# ---------------------------------------------------------------------------


_REFERENCIA = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


def letra_de_coluna(coluna: int) -> str:
    """1 -> "A", 27 -> "AA". Base 1, como o proprio OOXML."""
    if coluna < 1:
        raise ValueError(f"coluna invalida: {coluna}")
    letras = ""
    while coluna:
        coluna, resto = divmod(coluna - 1, 26)
        letras = chr(ord("A") + resto) + letras
    return letras


def coluna_de_letra(letras: str) -> int:
    """"A" -> 1, "AA" -> 27."""
    coluna = 0
    for caractere in letras.upper():
        coluna = coluna * 26 + (ord(caractere) - ord("A") + 1)
    return coluna


def referencia(linha: int, coluna: int) -> str:
    """(7, 2) -> "B7"."""
    return f"{letra_de_coluna(coluna)}{linha}"


def de_referencia(texto: str) -> tuple[int, int] | None:
    """"B7" -> (7, 2). None quando nao e' uma referencia simples de celula."""
    achado = _REFERENCIA.match(texto.strip())
    if achado is None:
        return None
    return int(achado.group(2)), coluna_de_letra(achado.group(1))
