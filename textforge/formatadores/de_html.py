"""Formatador de HTML (requisito 6-HTML).

CONSERVADOR de proposito, e vale explicar por que: em HTML, o espaco em branco ENTRE
elementos inline e' significativo. `<span>a</span> <span>b</span>` renderiza "a b";
quebrar a linha entre eles e depois indentar produz o mesmo resultado (a quebra e' um
espaco), mas `<span>a</span><span>b</span>` renderiza "ab" -- e inserir uma quebra ali
MUDA a pagina. Um formatador que indenta tudo sem olhar quebra layout de verdade.

Por isso este formatador:

  * indenta apenas tags ESTRUTURAIS (div, section, table, ul, head, body...);
  * NAO toca em linha de conteudo misto -- texto junto com tag inline fica como esta';
  * NAO toca no interior de <pre>, <textarea>, <script> e <style>, onde o espaco e'
    conteudo (num <pre> ele e' literalmente exibido);
  * nao fecha tag que o autor deixou aberta, nem reordena atributo.

O resultado e' menos "arrumado" que o de um formatador agressivo, e nao muda o que a
pagina mostra. Para um editor de arquivos tecnicos, essa e' a troca certa.
"""

from __future__ import annotations

import re

from textforge.formatadores.base import (ErroDeSintaxe, Resultado, Saida,
                                         unidade_de_indentacao)

# Tags sem fechamento: nao abrem nivel de indentacao.
VAZIAS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr"})

# Elementos INLINE: o espaco em volta deles importa, entao nao geram indentacao.
INLINE = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "dfn", "em", "i",
    "kbd", "mark", "q", "rp", "rt", "ruby", "s", "samp", "small", "span",
    "strong", "sub", "sup", "time", "u", "var", "label", "button", "select",
    "option", "textarea", "img", "br", "input"})

# Onde o espaco em branco e' CONTEUDO e nada pode ser reindentado.
INTOCAVEIS = frozenset({"pre", "textarea", "script", "style"})

_TAG = re.compile(r"<(?P<fecha>/?)\s*(?P<nome>[A-Za-z][\w:-]*)"
                  r"(?P<resto>[^>]*?)(?P<vazia>/?)>")


def _e_estrutural(nome: str) -> bool:
    minusculo = nome.lower()
    return minusculo not in INLINE and minusculo not in VAZIAS


def formatar(texto: str, opcoes: dict) -> Saida:
    if not texto.strip():
        return Resultado(texto)

    unidade = unidade_de_indentacao(opcoes)
    saida: list[str] = []
    nivel = 0
    intocavel: str | None = None
    avisos: list[str] = []
    mistas = 0

    for linha_bruta in texto.split("\n"):
        linha = linha_bruta.strip()

        # Dentro de <pre>/<script>/<style>: a linha vai LITERAL, com a indentacao
        # original. Reindentar um <pre> mudaria o que a pagina exibe.
        if intocavel is not None:
            saida.append(linha_bruta)
            if re.search(rf"(?i:</{intocavel}\s*>)", linha_bruta):
                intocavel = None
            continue

        if not linha:
            saida.append("")
            continue

        tags = list(_TAG.finditer(linha))
        # Conteudo misto: texto FORA de tag junto com tag inline na mesma linha.
        # Mexer nisso pode mudar o espacamento renderizado.
        sem_tags = _TAG.sub("", linha).strip()
        so_inline = tags and all(not _e_estrutural(t.group("nome")) for t in tags)
        if sem_tags and (so_inline or len(tags) > 2):
            saida.append(unidade * nivel + linha)
            mistas += 1
            continue

        # Uma linha que COMECA com fechamento recua antes de ser escrita.
        primeira = tags[0] if tags else None
        if primeira and primeira.group("fecha") and _e_estrutural(
                primeira.group("nome")):
            nivel = max(0, nivel - 1)

        saida.append(unidade * nivel + linha)

        # Depois de escrever, ajusta o nivel pelo saldo da linha.
        for t in tags:
            nome = t.group("nome").lower()
            if nome in INTOCAVEIS and not t.group("fecha") and not t.group("vazia"):
                if not re.search(rf"(?i:</{nome}\s*>)", linha):
                    intocavel = nome
                continue
            if not _e_estrutural(nome) or t.group("vazia"):
                continue
            if t.group("fecha"):
                if t is not primeira:
                    nivel = max(0, nivel - 1)
            else:
                nivel += 1

    if mistas:
        avisos.append(
            f"{mistas} linha(s) com texto e tags inline juntos NAO foram "
            f"reindentadas: em HTML o espaco em volta de um elemento inline "
            f"e' significativo, e mexer nele mudaria a pagina.")
    return Resultado("\n".join(saida).rstrip() + "\n", avisos)


def compactar(texto: str, opcoes: dict) -> Saida:
    """Remove a indentacao ENTRE tags estruturais, e nada mais.

    Nao remove o espaco entre elementos inline (renderiza), nem toca em <pre>,
    <script> e <style>.
    """
    partes: list[str] = []
    intocavel: str | None = None

    for linha_bruta in texto.split("\n"):
        if intocavel is not None:
            partes.append("\n" + linha_bruta)
            if re.search(rf"(?i:</{intocavel}\s*>)", linha_bruta):
                intocavel = None
            continue

        linha = linha_bruta.strip()
        if not linha:
            continue

        for t in _TAG.finditer(linha):
            nome = t.group("nome").lower()
            if (nome in INTOCAVEIS and not t.group("fecha")
                    and not t.group("vazia")
                    and not re.search(rf"(?i:</{nome}\s*>)", linha)):
                intocavel = nome

        # Junta sem espaco quando a linha comeca e termina com tag estrutural;
        # senao preserva UM espaco, que e' o que a quebra de linha valia.
        if partes and not partes[-1].endswith(">"):
            partes.append(" ")
        partes.append(linha)

    return Resultado("".join(partes).strip() + "\n",
                     ["O espaco entre elementos inline foi preservado: em HTML "
                      "ele aparece na pagina."])


def validar(texto: str) -> ErroDeSintaxe | None:
    """Aponta tag de fechamento sem abertura correspondente.

    NAO valida HTML: o padrao permite tag nao fechada (<li>, <p>, <td>), e o
    navegador fecha sozinho. Prometer validacao completa seria enganar o usuario. O
    que se pode afirmar com certeza e' um `</div>` que fecha algo que nunca abriu.
    """
    if not texto.strip():
        return None

    pilha: list[tuple[str, int]] = []
    for numero, linha in enumerate(texto.split("\n"), start=1):
        limpa = re.sub(r"<!--.*?-->", "", linha)
        for t in _TAG.finditer(limpa):
            nome = t.group("nome").lower()
            if nome in VAZIAS or t.group("vazia"):
                continue
            if t.group("fecha"):
                if not any(n == nome for n, _ in pilha):
                    return ErroDeSintaxe(
                        numero, t.start() + 1,
                        f"</{nome}> fecha um elemento que nao foi aberto",
                        None, linha.strip()[:200])
                while pilha and pilha[-1][0] != nome:
                    pilha.pop()
                if pilha:
                    pilha.pop()
            else:
                pilha.append((nome, numero))
    return None


class FormatadorHtml:
    nome = "HTML"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return formatar(texto, opcoes)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return compactar(texto, opcoes)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorHtml()
