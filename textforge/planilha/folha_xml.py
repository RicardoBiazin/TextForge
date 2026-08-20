"""Varredura dos BYTES CRUS de uma aba (`xl/worksheets/sheetN.xml`).

Este modulo existe porque a alternativa nao serve. `ElementTree.tostring()`
reescreve o XML inteiro: renomeia prefixos de espaco de nomes, reordena
atributos, e -- o que de fato quebra -- emite `mc:Ignorable="x14ac xr xr2 xr3"`
sem declarar os prefixos `xr2` e `xr3`, porque nenhum elemento os usava. O Excel
recusa o arquivo. Uma aba de 5 MB voltaria diferente em cada byte so' por ter
sido aberta, e comparar o antes e o depois viraria impossivel.

Entao a edicao e' feita por RECORTE nos bytes: acha-se o intervalo exato da
celula, troca-se aquele pedaco, e todo o resto do arquivo continua sendo os bytes
que vieram do disco. E' o `registros_crus` do CSV, um nivel abaixo.

Varrer XML com busca de texto e' normalmente um erro. Aqui e' seguro porque o
dominio e' estreito: dentro de `<sheetData>` os unicos elementos sao `<row>` e
`<c>`, nenhum dos dois aninha em si mesmo, nao ha' comentario nem CDATA, e todo
"<" de conteudo chega escapado como "&lt;". Mesmo assim o rastreador respeita
aspas ao procurar o ">" de fechamento -- um atributo pode conter ">" sem escape,
e e' legal em XML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ASPAS = (0x22, 0x27)            # " e '
MAIOR = 0x3E                    # >

_ATRIBUTO = re.compile(rb"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


@dataclass(slots=True)
class Elemento:
    """Um `<row>` ou um `<c>` localizado nos bytes.

    inicio          indice do "<"
    fim             indice logo depois do ">" final (do "/>" ou do "</tag>")
    fim_da_abertura indice logo depois do ">" da tag de abertura
    inicio_do_fecho indice do "<" de "</tag>", ou == fim quando auto-fechada
    """

    inicio: int
    fim: int
    fim_da_abertura: int
    inicio_do_fecho: int
    atributos: dict[str, str]

    @property
    def vazia(self) -> bool:
        """Auto-fechada (`<c r="A1"/>`): nao tem conteudo nenhum."""
        return self.inicio_do_fecho == self.fim_da_abertura and \
            self.fim == self.fim_da_abertura


def fim_da_tag(dados: bytes, inicio: int) -> int:
    """Indice logo depois do ">" da tag que comeca em `inicio`."""
    indice = inicio + 1
    aspa = 0
    tamanho = len(dados)
    while indice < tamanho:
        byte = dados[indice]
        if aspa:
            if byte == aspa:
                aspa = 0
        elif byte in ASPAS:
            aspa = byte
        elif byte == MAIOR:
            return indice + 1
        indice += 1
    raise ValueError("tag sem '>' de fechamento")


def atributos(dados: bytes, inicio: int, fim: int) -> dict[str, str]:
    """Os atributos da tag de abertura, ja' decodificados."""
    achados = {}
    for casamento in _ATRIBUTO.finditer(dados, inicio, fim):
        valor = casamento.group(2)
        if valor is None:
            valor = casamento.group(3)
        achados[casamento.group(1).decode("utf-8", "replace")] = \
            desescapar(valor.decode("utf-8", "replace"))
    return achados


def proxima_tag(dados: bytes, marca: bytes, inicio: int, fim: int) -> int:
    """Proxima ocorrencia de `<tag` seguida de espaco, "/" ou ">". -1 se nao ha'.

    A conferencia do byte seguinte e' o que impede `<c` de casar com `<cols` e
    `<row` com `<rowBreaks>` -- os dois existem no mesmo arquivo, so' que fora do
    `<sheetData>`.
    """
    posicao = inicio
    while True:
        posicao = dados.find(marca, posicao, fim)
        if posicao < 0:
            return -1
        seguinte = posicao + len(marca)
        if seguinte < fim and dados[seguinte] in (0x20, 0x2F, MAIOR, 0x09,
                                                  0x0A, 0x0D):
            return posicao
        posicao = seguinte


def percorrer(dados: bytes, tag: bytes, inicio: int, fim: int):
    """Gera os `<tag>` de primeiro nivel entre `inicio` e `fim`.

    So' funciona para tag que nao aninha em si mesma, que e' o caso de `row` e
    `c`. Foi o suficiente para nao precisar de uma pilha.
    """
    abre = b"<" + tag
    fecha = b"</" + tag + b">"
    posicao = inicio
    while posicao < fim:
        comeco = proxima_tag(dados, abre, posicao, fim)
        if comeco < 0:
            return
        fim_abertura = fim_da_tag(dados, comeco)
        if dados[fim_abertura - 2:fim_abertura] == b"/>":
            elemento = Elemento(comeco, fim_abertura, fim_abertura,
                                fim_abertura,
                                atributos(dados, comeco, fim_abertura))
        else:
            fechamento = dados.find(fecha, fim_abertura, fim)
            if fechamento < 0:
                return
            elemento = Elemento(comeco, fechamento + len(fecha), fim_abertura,
                                fechamento,
                                atributos(dados, comeco, fim_abertura))
        yield elemento
        posicao = elemento.fim


def intervalo_de_sheetdata(dados: bytes) -> tuple[int, int, bool]:
    """(inicio, fim, vazio) do CONTEUDO de `<sheetData>`.

    `vazio` e' True quando a aba veio como `<sheetData/>`; nesse caso inicio e
    fim apontam para o mesmo lugar -- o ponto onde o elemento precisa ser aberto
    antes de receber a primeira linha.
    """
    comeco = proxima_tag(dados, b"<sheetData", 0, len(dados))
    if comeco < 0:
        raise ValueError("a aba nao tem <sheetData>")
    fim_abertura = fim_da_tag(dados, comeco)
    if dados[fim_abertura - 2:fim_abertura] == b"/>":
        return comeco, fim_abertura, True
    fechamento = dados.find(b"</sheetData>", fim_abertura)
    if fechamento < 0:
        raise ValueError("<sheetData> sem fechamento")
    return fim_abertura, fechamento, False


# ---------------------------------------------------------------------------
# Escape
# ---------------------------------------------------------------------------

def escapar(texto: str) -> str:
    """Texto para dentro de um no' XML.

    O "&" vem primeiro; inverter a ordem transformaria um "<" recem-escrito em
    "&amp;lt;" e o usuario veria a marcacao literal na celula.
    """
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def desescapar(texto: str) -> str:
    if "&" not in texto:
        return texto
    return (texto.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'")
            .replace("&#10;", "\n").replace("&#13;", "\r")
            .replace("&#9;", "\t").replace("&amp;", "&"))
