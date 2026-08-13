"""Formatador de CSS (requisito 6-CSS).

Escrito a mao, e nao com dependencia: a estrutura do CSS e' rasa (seletor, chaves,
`propriedade: valor;`) e um formatador de 100 linhas cobre praticamente todo arquivo
real. Nao vale trazer uma dependencia nova para isso.

O que ele NAO tenta fazer, e por que: nao reordena propriedades (a ordem tem
significado em CSS -- a ultima declaracao vence), nao normaliza cores nem unidades
(`#FFF` e `#ffffff` sao equivalentes para o navegador, mas trocar um pelo outro e'
alterar o arquivo sem que ninguem tenha pedido), e nao junta seletores.

O cuidado central e' o mesmo dos outros formatadores: STRING e COMENTARIO sao
conteudo. O separador `;` ou `{` dentro de `content: "a;b"` nao e' pontuacao, e
quebrar linha ali produziria CSS quebrado. Por isso a varredura e' caractere a
caractere, com estado, e nao um `split(";")`.
"""

from __future__ import annotations

import re

from textforge.formatadores.base import (ErroDeSintaxe, Recusa, Resultado, Saida,
                                         unidade_de_indentacao)


def _fatiar(texto: str) -> list[tuple[str, str]]:
    """Quebra o CSS em pedacos (tipo, conteudo), respeitando string e comentario.

    Tipos: "abre", "fecha", "declaracao", "comentario", "arroba".
    """
    pedacos: list[tuple[str, str]] = []
    atual: list[str] = []
    i = 0
    n = len(texto)

    def despejar(tipo: str) -> None:
        conteudo = "".join(atual).strip()
        atual.clear()
        if conteudo:
            pedacos.append((tipo, conteudo))

    while i < n:
        ch = texto[i]

        if ch == "/" and texto[i:i + 2] == "/*":
            fim = texto.find("*/", i + 2)
            if fim < 0:
                atual.append(texto[i:])
                break
            despejar("declaracao")
            pedacos.append(("comentario", texto[i:fim + 2]))
            i = fim + 2
            continue

        if ch in ('"', "'"):
            # A string vai inteira para o pedaco atual: o ";" e o "{" de dentro
            # dela NAO sao pontuacao.
            fim = i + 1
            while fim < n:
                if texto[fim] == "\\":
                    fim += 2
                    continue
                if texto[fim] == ch:
                    break
                fim += 1
            atual.append(texto[i:fim + 1])
            i = fim + 1
            continue

        if ch == "{":
            despejar("abre")
            i += 1
            continue
        if ch == "}":
            despejar("declaracao")
            pedacos.append(("fecha", "}"))
            i += 1
            continue
        if ch == ";":
            despejar("declaracao")
            i += 1
            continue

        atual.append(ch)
        i += 1

    despejar("declaracao")
    return pedacos


def formatar(texto: str, opcoes: dict) -> Saida:
    if not texto.strip():
        return Resultado(texto)

    erro = validar(texto)
    if erro is not None:
        return erro

    unidade = unidade_de_indentacao(opcoes)
    linhas: list[str] = []
    nivel = 0

    for tipo, conteudo in _fatiar(texto):
        recuo = unidade * nivel
        if tipo == "comentario":
            linhas.append(recuo + conteudo)
        elif tipo == "abre":
            # Seletor de varias linhas ("h1,\n h2 {") vira uma linha por seletor:
            # e' como CSS de verdade e' escrito.
            seletores = [s.strip() for s in conteudo.split(",") if s.strip()]
            if len(seletores) > 1:
                for s in seletores[:-1]:
                    linhas.append(f"{recuo}{s},")
                linhas.append(f"{recuo}{seletores[-1]} {{")
            else:
                linhas.append(f"{recuo}{conteudo} {{")
            nivel += 1
        elif tipo == "fecha":
            nivel = max(0, nivel - 1)
            linhas.append(unidade * nivel + "}")
        else:
            # `propriedade:valor` ganha um espaco depois dos dois-pontos, mas a
            # divisao e' no PRIMEIRO ":" -- um valor como `url(http://x)` tem
            # dois-pontos dentro.
            nome, sep, valor = conteudo.partition(":")
            if sep:
                linhas.append(f"{recuo}{nome.strip()}: {valor.strip()};")
            else:
                linhas.append(f"{recuo}{conteudo};")

    return Resultado("\n".join(linhas) + "\n")


def compactar(texto: str, opcoes: dict) -> Saida:
    if not texto.strip():
        return Resultado(texto)
    erro = validar(texto)
    if erro is not None:
        return erro

    partes: list[str] = []
    for tipo, conteudo in _fatiar(texto):
        if tipo == "comentario":
            continue          # comentario nao sobrevive ao compactar, por definicao
        if tipo == "abre":
            partes.append(re.sub(r"\s*,\s*", ",", conteudo.strip()) + "{")
        elif tipo == "fecha":
            # Remove o ";" antes do "}": e' opcional e ocupa espaco.
            if partes and partes[-1].endswith(";"):
                partes[-1] = partes[-1][:-1]
            partes.append("}")
        else:
            nome, sep, valor = conteudo.partition(":")
            if sep:
                partes.append(f"{nome.strip()}:{valor.strip()};")
            else:
                partes.append(conteudo.strip() + ";")
    return Resultado("".join(partes) + "\n",
                     ["Os comentarios foram removidos na compactacao."])


def validar(texto: str) -> ErroDeSintaxe | None:
    """Checa apenas o balanceamento de chaves e de comentarios.

    CSS nao tem sintaxe estrita como XML: o navegador ignora declaracao que nao
    entende, e o proprio padrao manda ignorar. Prometer "validar CSS" seria enganar
    o usuario -- o que se pode afirmar com certeza e' chave e comentario nao
    fechados, que e' a causa da grande maioria dos problemas reais.
    """
    if not texto.strip():
        return None

    linha = 1
    coluna = 1
    profundidade = 0
    aberturas: list[tuple[int, int]] = []
    i = 0
    n = len(texto)

    while i < n:
        ch = texto[i]
        if ch == "\n":
            linha += 1
            coluna = 0
        elif ch == "/" and texto[i:i + 2] == "/*":
            fim = texto.find("*/", i + 2)
            if fim < 0:
                return ErroDeSintaxe(linha, coluna,
                                     "comentario /* nao foi fechado", i, "")
            trecho = texto[i:fim]
            linha += trecho.count("\n")
            i = fim + 2
            coluna = 1
            continue
        elif ch in ('"', "'"):
            fim = i + 1
            while fim < n:
                if texto[fim] == "\\":
                    fim += 2
                    continue
                if texto[fim] == ch or texto[fim] == "\n":
                    break
                fim += 1
            if fim >= n or texto[fim] == "\n":
                return ErroDeSintaxe(linha, coluna,
                                     f"string {ch} nao foi fechada nesta linha",
                                     i, texto.split("\n")[linha - 1])
            i = fim + 1
            coluna += fim - i
            continue
        elif ch == "{":
            profundidade += 1
            aberturas.append((linha, coluna))
        elif ch == "}":
            profundidade -= 1
            if profundidade < 0:
                return ErroDeSintaxe(linha, coluna,
                                     "chave '}' sem abertura correspondente", i,
                                     texto.split("\n")[linha - 1])
            aberturas.pop()
        i += 1
        coluna += 1

    if profundidade > 0 and aberturas:
        l, c = aberturas[0]
        return ErroDeSintaxe(l, c,
                             f"chave '{{' sem fechamento ({profundidade} "
                             f"aberta(s))", None, "")
    return None


class FormatadorCss:
    nome = "CSS"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return formatar(texto, opcoes)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return compactar(texto, opcoes)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorCss()
