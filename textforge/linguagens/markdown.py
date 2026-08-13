"""Provedor de Markdown.

Realce de MARCACAO, nao de codigo: titulo, enfase, ligacao, lista, citacao e bloco
de codigo. O bloco de codigo cercado por ``` e' um contexto proprio, porque
atravessa linhas -- e dentro dele nada mais e' realcado, senao o `#` de um
comentario Python dentro do bloco seria pintado como titulo de Markdown.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce


class ProvedorMarkdown(ProvedorDeLinguagem):
    nome = "Markdown"
    extensoes = (".md", ".markdown", ".mdown", ".mkd", ".mdx", ".rmd")
    nomes_de_arquivo = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md",
                        "CLAUDE.md")
    comentario_de_bloco = ("<!--", "-->")
    comentario_de_linha = None
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        raiz = Contexto("raiz", (
            # A cerca de codigo vem PRIMEIRO: o conteudo dela nao e' Markdown.
            Regra(re.compile(r"^\s*```.*$"), "codigo", entrar_em="cerca"),
            Regra(re.compile(r"^\s*~~~.*$"), "codigo", entrar_em="cerca_til"),
            Regra(re.compile(r"<!--"), "comentario", entrar_em="comentario"),
            Regra(re.compile(r"^\s{0,3}#{1,6}\s.*$"), "titulo"),
            # Titulo sublinhado com === ou ---.
            Regra(re.compile(r"^\s{0,3}(?:=+|-{3,})\s*$"), "titulo"),
            Regra(re.compile(r"^\s*>.*$"), "citacao"),
            Regra(re.compile(r"^\s*(?:[-*+]|\d+\.)\s"), "lista"),
            # Codigo em linha antes de enfase: `*` dentro de `codigo` nao e' enfase.
            Regra(re.compile(r"`[^`\n]+`"), "codigo"),
            # Ligacao e imagem: o texto e o destino ganham papeis diferentes.
            Regra(re.compile(r"!?\[(?P<md_texto>[^\]\n]*)\]"
                             r"\((?P<md_alvo>[^)\n]*)\)"),
                  "pontuacao", papeis_por_grupo={"md_texto": "forte",
                                                 "md_alvo": "ligacao"}),
            Regra(re.compile(r"<https?://[^>\s]+>|https?://[^\s)>\]]+"),
                  "ligacao"),
            Regra(re.compile(r"\*\*\*[^*\n]+\*\*\*|___[^_\n]+___"), "forte"),
            Regra(re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__"), "forte"),
            Regra(re.compile(r"\*[^*\n]+\*|_[^_\n]+_"), "enfase"),
            Regra(re.compile(r"~~[^~\n]+~~"), "citacao"),
            # Tabela: a linha separadora e as barras.
            Regra(re.compile(r"^\s*\|[-:| ]+\|\s*$"), "pontuacao"),
            Regra(re.compile(r"\|"), "pontuacao"),
        ))
        cerca = Contexto("cerca", (
            Regra(re.compile(r"^\s*```\s*$"), "codigo", sair=True),
        ), papel_padrao="codigo")
        cerca_til = Contexto("cerca_til", (
            Regra(re.compile(r"^\s*~~~\s*$"), "codigo", sair=True),
        ), papel_padrao="codigo")
        comentario = Contexto("comentario", (
            Regra(re.compile(r"-->"), "comentario", sair=True),
        ), papel_padrao="comentario")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "cerca": cerca, "cerca_til": cerca_til,
            "comentario": comentario})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        # A regiao dobravel de um Markdown e' a SECAO: do titulo ao proximo do
        # mesmo nivel. Nao e' indentacao nem delimitador.
        return RegraDeDobra(modo="marcadores",
                            marcador_abre=re.compile(r"^\s{0,3}#{1,6}\s"))

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Sumario pelos titulos, aninhado pelo nivel (# > ## > ###)."""
        raizes: list[NoDeEstrutura] = []
        pilha: list[tuple[int, NoDeEstrutura]] = []
        dentro_da_cerca = False

        for numero, linha in enumerate(texto.split("\n")):
            if re.match(r"^\s*(?:```|~~~)", linha):
                dentro_da_cerca = not dentro_da_cerca
                continue
            if dentro_da_cerca:
                # Um "# comentario" dentro de bloco de codigo NAO e' titulo.
                continue
            c = re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", linha)
            if not c:
                continue
            nivel = len(c.group(1))
            no = NoDeEstrutura(rotulo=c.group(2) or "(sem titulo)",
                               tipo="titulo", linha=numero,
                               coluna=c.start(2), detalhe="#" * nivel)
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            if pilha:
                pilha[-1][1].filhos.append(no)
            else:
                raizes.append(no)
            pilha.append((nivel, no))
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"^\s{0,3}#{1,6}\s+\S", amostra, re.M):
            pontos += 45
        if re.search(r"^\s*[-*+]\s+\S", amostra, re.M):
            pontos += 20
        if re.search(r"\[[^\]]+\]\([^)]+\)", amostra):
            pontos += 25
        if "```" in amostra:
            pontos += 20
        if re.search(r"\*\*[^*]+\*\*", amostra):
            pontos += 10
        return min(pontos, 100)


PROVEDORES = (ProvedorMarkdown(),)
