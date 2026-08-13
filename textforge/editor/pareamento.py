"""Pareamento de delimitadores e de tags (requisito 14).

Duas buscas diferentes:

  `casar_delimitador`  ( ) [ ] { } -- percorre os `DadosDoBloco.pares` que o
                       realcador ja' gravou, contando o saldo. Como o realcador
                       excluiu os delimitadores dentro de string e de comentario,
                       um "(" de texto nao e' casado com um ")" de codigo.

  `casar_tag`          <div> e </div> -- percorre o texto, contando o aninhamento
                       da MESMA tag. Tag vazia (<br/>) e' ignorada, senao ela
                       consumiria o fechamento de outra.

Limite deliberado: as duas param depois de `LIMITE_DE_BLOCOS` blocos em cada
direcao. O pareamento roda a CADA movimento do cursor, e varrer um arquivo de 1
milhao de linhas para descobrir que o parentese nao tem par tornaria as setas do
teclado lentas. Sem par dentro do limite, nao se realca nada -- que e' o mesmo
resultado visual de nao existir par.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from textforge.realce.dados_do_bloco import DadosDoBloco

# Quantos blocos varrer em cada direcao. 5000 cobre qualquer funcao ou bloco XML
# de verdade; alem disso, quase certamente nao ha' par.
LIMITE_DE_BLOCOS = 5000

FECHA_DE = {"(": ")", "[": "]", "{": "}"}
ABRE_DE = {v: k for k, v in FECHA_DE.items()}

_TAG = re.compile(r"<(?P<fecha>/?)\s*(?P<nome>[A-Za-z_][\w.:-]*)"
                  r"(?P<resto>[^>]*?)(?P<vazia>/?)>")


@dataclass(frozen=True)
class Posicao:
    """Um ponto no documento: bloco (base zero) e coluna."""

    bloco: int
    coluna: int
    tamanho: int = 1


def _dados(documento, numero: int) -> DadosDoBloco | None:
    bloco = documento.findBlockByNumber(numero)
    if not bloco.isValid():
        return None
    dados = bloco.userData()
    return dados if isinstance(dados, DadosDoBloco) else None


def delimitador_em(documento, bloco: int, coluna: int
                   ) -> tuple[str, int] | None:
    """O delimitador NO cursor ou imediatamente ANTES dele.

    Olhar os dois lados e' o que faz o realce aparecer tanto ao chegar num "(" com
    a seta quanto ao acabar de digitar um ")": em cada caso o cursor esta' de um
    lado diferente do caractere.
    """
    dados = _dados(documento, bloco)
    if dados is None:
        return None
    for par in dados.pares:
        if par.posicao == coluna:
            return par.caractere, par.posicao
    for par in dados.pares:
        if par.posicao == coluna - 1:
            return par.caractere, par.posicao
    return None


def casar_delimitador(documento, bloco: int, coluna: int
                      ) -> tuple[Posicao, Posicao] | None:
    """Acha o par do delimitador junto ao cursor. None se nao houver.

    Devolve (posicao do cursor, posicao do par), sempre nessa ordem, para quem
    desenha nao precisar descobrir qual e' qual.
    """
    achado = delimitador_em(documento, bloco, coluna)
    if achado is None:
        return None
    caractere, posicao = achado
    origem = Posicao(bloco, posicao)

    if caractere in FECHA_DE:
        par = _procurar_adiante(documento, bloco, posicao, caractere,
                                FECHA_DE[caractere])
    elif caractere in ABRE_DE:
        par = _procurar_atras(documento, bloco, posicao, ABRE_DE[caractere],
                              caractere)
    else:
        return None
    return (origem, par) if par is not None else None


def _procurar_adiante(documento, bloco_inicial: int, coluna_inicial: int,
                      abre: str, fecha: str) -> Posicao | None:
    saldo = 0
    numero = bloco_inicial
    fim = min(documento.blockCount(), bloco_inicial + LIMITE_DE_BLOCOS)
    while numero < fim:
        dados = _dados(documento, numero)
        if dados is not None:
            for par in dados.pares:
                if numero == bloco_inicial and par.posicao < coluna_inicial:
                    continue
                if par.caractere == abre:
                    saldo += 1
                elif par.caractere == fecha:
                    saldo -= 1
                    if saldo == 0:
                        return Posicao(numero, par.posicao)
        numero += 1
    return None


def _procurar_atras(documento, bloco_inicial: int, coluna_inicial: int,
                    abre: str, fecha: str) -> Posicao | None:
    saldo = 0
    numero = bloco_inicial
    limite = max(0, bloco_inicial - LIMITE_DE_BLOCOS)
    while numero >= limite:
        dados = _dados(documento, numero)
        if dados is not None:
            # De tras para a frente DENTRO do bloco tambem: o par mais proximo e' o
            # que interessa.
            for par in reversed(dados.pares):
                if numero == bloco_inicial and par.posicao > coluna_inicial:
                    continue
                if par.caractere == fecha:
                    saldo += 1
                elif par.caractere == abre:
                    saldo -= 1
                    if saldo == 0:
                        return Posicao(numero, par.posicao)
        numero -= 1
    return None


# ---------------------------------------------------------------------------
# Tags XML e HTML
# ---------------------------------------------------------------------------


def tag_em(texto: str, coluna: int) -> re.Match[str] | None:
    """A tag que contem a coluna, se houver."""
    for casamento in _TAG.finditer(texto):
        if casamento.start() <= coluna <= casamento.end():
            return casamento
    return None


def casar_tag(documento, bloco: int, coluna: int
              ) -> tuple[Posicao, Posicao] | None:
    """Acha a tag correspondente (requisito 14 e 6-XML).

    Devolve as posicoes do NOME da tag nas duas pontas -- e nao dos sinais "<" e
    ">" -- porque destacar o nome e' o que deixa claro qual par foi encontrado
    quando a tag tem muitos atributos.
    """
    origem_bloco = documento.findBlockByNumber(bloco)
    if not origem_bloco.isValid():
        return None
    casamento = tag_em(origem_bloco.text(), coluna)
    if casamento is None:
        return None
    if casamento.group("vazia"):
        return None                # <br/> nao tem par
    nome = casamento.group("nome")
    origem = Posicao(bloco, casamento.start("nome"), len(nome))

    if casamento.group("fecha"):
        par = _tag_atras(documento, bloco, casamento.start(), nome)
    else:
        par = _tag_adiante(documento, bloco, casamento.end(), nome)
    return (origem, par) if par is not None else None


def _tag_adiante(documento, bloco_inicial: int, apos: int,
                 nome: str) -> Posicao | None:
    saldo = 1
    numero = bloco_inicial
    fim = min(documento.blockCount(), bloco_inicial + LIMITE_DE_BLOCOS)
    while numero < fim:
        texto = documento.findBlockByNumber(numero).text()
        for c in _TAG.finditer(texto):
            if numero == bloco_inicial and c.start() < apos:
                continue
            if c.group("nome") != nome or c.group("vazia"):
                continue
            if c.group("fecha"):
                saldo -= 1
                if saldo == 0:
                    return Posicao(numero, c.start("nome"), len(nome))
            else:
                saldo += 1
        numero += 1
    return None


def _tag_atras(documento, bloco_inicial: int, antes: int,
               nome: str) -> Posicao | None:
    saldo = 1
    numero = bloco_inicial
    limite = max(0, bloco_inicial - LIMITE_DE_BLOCOS)
    while numero >= limite:
        texto = documento.findBlockByNumber(numero).text()
        for c in reversed(list(_TAG.finditer(texto))):
            if numero == bloco_inicial and c.start() >= antes:
                continue
            if c.group("nome") != nome or c.group("vazia"):
                continue
            if c.group("fecha"):
                saldo += 1
            else:
                saldo -= 1
                if saldo == 0:
                    return Posicao(numero, c.start("nome"), len(nome))
        numero -= 1
    return None


def casar(documento, bloco: int, coluna: int) -> tuple[Posicao, Posicao] | None:
    """Tenta delimitador e depois tag. E' o que o editor chama."""
    return (casar_delimitador(documento, bloco, coluna)
            or casar_tag(documento, bloco, coluna))
