"""Provedor de CSS, SCSS, SASS e LESS.

Exporta `contextos()` para o `html.py` embutir CSS dentro de `<style>`. E' por isso
que a construcao dos contextos e' uma funcao de modulo, e nao um metodo: quem
embute precisa dos contextos sem instanciar o provedor.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

# @media, @import, @keyframes... e as diretivas do SCSS.
DIRETIVAS = ("media import charset keyframes font-face supports namespace page "
             "mixin include extend function return if else each for while use "
             "forward at-root content debug warn error").split()

CONSTANTES = ("none inherit initial unset auto transparent currentColor "
              "important true false null").split()

UNIDADES = r"(?:px|em|rem|%|vh|vw|vmin|vmax|pt|pc|cm|mm|in|ex|ch|fr|s|ms|deg|rad|turn)"


def contextos() -> dict[str, Contexto]:
    """Contextos do CSS. Reaproveitados pelo HTML dentro de <style>."""
    raiz = Contexto("raiz", (
        Regra(re.compile(r"/\*"), "comentario", entrar_em="comentario"),
        # O SCSS aceita "//" de comentario; no CSS puro nao aparece.
        Regra(re.compile(r"//.*$"), "comentario"),
        Regra(re.compile(r.texto_com_escape('"')), "texto_literal"),
        Regra(re.compile(r.texto_com_escape("'")), "texto_literal"),
        # @media, @import: a diretiva inteira ganha papel de preprocessador.
        Regra(re.compile(r"@" + r.alternativa_de_palavras(DIRETIVAS,
                                                          limite=False)),
              "preprocessador"),
        # Cor hexadecimal antes do numero: #fff nao e' um numero.
        Regra(re.compile(r"#[0-9a-fA-F]{3,8}\b"), "constante"),
        # Variavel: --minha-cor (CSS), $minha-cor (SCSS), @minha-cor (LESS).
        Regra(re.compile(r"--[\w-]+|\$[\w-]+"), "variavel"),
        # A PROPRIEDADE e' o que vem antes do ":" -- e' o que distingue
        # "color: red" de um seletor. Sem esta regra, propriedade e seletor
        # ficariam da mesma cor e o CSS nao ajudaria a ler.
        Regra(re.compile(r"\b(?P<css_prop>[a-zA-Z-]+)(?=\s*:)"), "chave",
              papeis_por_grupo={"css_prop": "chave"}),
        # Pseudo-classe e pseudo-elemento.
        Regra(re.compile(r"::?[a-zA-Z-]+(?:\([^)\n]*\))?"), "palavra_chave_2"),
        # Seletor de classe e de id.
        Regra(re.compile(r"\.[-_a-zA-Z][-\w]*"), "tipo"),
        Regra(re.compile(r"#[-_a-zA-Z][-\w]*"), "tipo"),
        Regra(re.compile(r"\[[^\]\n]*\]"), "atributo"),
        Regra(re.compile(r"!important\b"), "aviso"),
        r.regra_de_palavras(CONSTANTES, "constante"),
        Regra(re.compile(r"-?\d*\.?\d+" + UNIDADES + r"?"), "numero"),
        Regra(re.compile(r"\b[a-zA-Z-]+(?=\s*\()"), "chamada"),
        Regra(re.compile(r"[{}:;,]"), "pontuacao"),
    ))
    comentario = Contexto("comentario", (
        Regra(re.compile(r"\*/"), "comentario", sair=True),
    ), papel_padrao="comentario")
    return {"raiz": raiz, "comentario": comentario}


class ProvedorCss(ProvedorDeLinguagem):
    nome = "CSS"
    extensoes = (".css", ".scss", ".sass", ".less", ".styl", ".pcss")
    comentario_de_linha = "//"          # SCSS/LESS; no CSS puro use o de bloco
    comentario_de_bloco = ("/*", "*/")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    aumenta_indentacao = re.compile(r"\{\s*$")
    diminui_indentacao = re.compile(r"^\s*\}")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is None:
            self._cache = RegrasDeRealce(inicial="raiz", contextos=contextos())
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(CONSTANTES) | {f"@{d}" for d in DIRETIVAS}

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Seletores e blocos @ (requisito 11-CSS).

        Pega o que vem antes do primeiro "{" da linha. NAO exige que a linha
        TERMINE no "{": a regra de uma linha (".a { color: red; }") e' comum em CSS
        de verdade, e exigir o fim da linha a deixaria fora do painel.

        Uma regra em varias linhas ("h1,\\nh2 {") aponta para a linha da abertura,
        o que basta para navegar.
        """
        achados: list[NoDeEstrutura] = []
        for numero, linha in enumerate(texto.split("\n")):
            sem_comentario = re.sub(r"/\*.*?\*/", "", linha)
            sem_comentario = re.sub(r"//.*$", "", sem_comentario)
            c = re.match(r"^\s*(?P<sel>[^{};]+?)\s*\{", sem_comentario)
            if not c:
                continue
            seletor = c.group("sel").strip()
            if not seletor:
                continue
            achados.append(NoDeEstrutura(
                rotulo=seletor[:70],
                tipo="secao" if seletor.startswith("@") else "seletor",
                linha=numero, coluna=c.start("sel")))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"[.#]?[\w-]+\s*\{[^}]*[\w-]+\s*:\s*[^;}]+;", amostra):
            pontos += 60
        if re.search(r"@(?:media|import|keyframes)\b", amostra):
            pontos += 25
        if re.search(r"#[0-9a-fA-F]{3,6}\b", amostra):
            pontos += 10
        if re.search(r"\b\d+(?:px|em|rem|%)\b", amostra):
            pontos += 15
        return min(pontos, 100)


PROVEDORES = (ProvedorCss(),)
