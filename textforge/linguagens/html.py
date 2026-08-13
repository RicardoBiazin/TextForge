"""Provedor de HTML.

Aqui esta' a composicao de contextos: `<script>` entra nos contextos do JavaScript,
`<style>` nos do CSS, e nenhuma regra e' duplicada -- uma correcao no provedor de JS
vale para o HTML tambem. O mecanismo e' `regras.com_prefixo`.

`contextos_html()` recebe regras EXTRA para a raiz, e e' assim que o `php.py`
acrescenta o `<?php` sem que o HTML precise conhecer PHP (o que evitaria a
dependencia circular entre os dois modulos).

LIMITE CONHECIDO, medido e deliberado: `</script>` DENTRO de uma string
JavaScript NAO fecha o bloco aqui. O navegador fecha (o parser de HTML nao entende
JS), entao neste caso o realce divergo do navegador.

O motivo e' o funcionamento do regex: a alternancia do contexto escolhe o
casamento MAIS A' ESQUERDA, e em `var s = "</script>";` a string comeca uma coluna
antes do `</script>`. Tornar o fechamento prioritario exigiria uma busca separada
por bloco dentro do laco central do pintor -- custo permanente em todo arquivo
HTML, por uma construcao que praticamente nao aparece. Se algum dia aparecer, a
correcao e' uma lista de "regras prioritarias" no `Contexto`.

O contrario, que seria grave, NAO acontece: uma string com "<" dentro nunca vira
tag -- ha' teste para isso.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens import css as css_mod
from textforge.linguagens import javascript as js_mod
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

NOME_DE_TAG = r"[A-Za-z][\w:-]*"

# Tags que nao tem fechamento. Precisam ser conhecidas para a arvore estrutural
# nao aninhar tudo dentro de um <br> ou de um <meta>.
VAZIAS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr", "!doctype"})


def contextos_html(extras: tuple[Regra, ...] = ()) -> dict[str, Contexto]:
    """Contextos do HTML. `extras` entra no INICIO da raiz.

    O inicio importa: o `<?php` do `php.py` tem de ser testado ANTES da regra de
    tag, senao `<?php` casaria como uma tag chamada "?php".
    """
    raiz = Contexto("raiz", extras + (
        # Comentario primeiro: "<!-- <div> -->" nao tem tag dentro.
        Regra(re.compile(r"<!--"), "comentario", entrar_em="comentario"),
        Regra(re.compile(r"(?i:<!DOCTYPE[^>]*>)"), "preprocessador"),
        Regra(re.compile(r"<!\[CDATA\["), "texto_literal", entrar_em="cdata"),
        # <script> e <style> entram nos contextos da outra linguagem.
        Regra(re.compile(r"(?i:<script\b)"), "tag", entrar_em="tag_de_script"),
        Regra(re.compile(r"(?i:<style\b)"), "tag", entrar_em="tag_de_estilo"),
        Regra(re.compile(rf"</\s*(?P<html_fecha>{NOME_DE_TAG})\s*>"),
              "tag_fechamento",
              papeis_por_grupo={"html_fecha": "tag_fechamento"}),
        Regra(re.compile(rf"<\s*(?P<html_abre>{NOME_DE_TAG})"), "pontuacao",
              papeis_por_grupo={"html_abre": "tag"}, entrar_em="dentro_da_tag"),
        Regra(re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|\w+);"), "entidade"),
    ))

    dentro_da_tag = Contexto("dentro_da_tag", (
        Regra(re.compile(r"/?>"), "pontuacao", sair=True),
        Regra(re.compile(r'"[^"]*"'), "valor_atributo"),
        Regra(re.compile(r"'[^']*'"), "valor_atributo"),
        Regra(re.compile(rf"{NOME_DE_TAG}(?=\s*=)"), "atributo"),
        Regra(re.compile(r"="), "operador"),
        # Atributo booleano, sem valor: "disabled", "checked".
        Regra(re.compile(NOME_DE_TAG), "atributo"),
    ))

    # A tag de abertura do <script>: os atributos, e o ">" que entra no corpo.
    tag_de_script = Contexto("tag_de_script", (
        Regra(re.compile(r">"), "pontuacao", entrar_em="corpo_do_script"),
        Regra(re.compile(r"/>"), "pontuacao", sair=True),
        Regra(re.compile(r'"[^"]*"|\'[^\']*\''), "valor_atributo"),
        Regra(re.compile(rf"{NOME_DE_TAG}(?=\s*=)"), "atributo"),
        Regra(re.compile(r"="), "operador"),
    ))
    tag_de_estilo = Contexto("tag_de_estilo", (
        Regra(re.compile(r">"), "pontuacao", entrar_em="corpo_do_estilo"),
        Regra(re.compile(r"/>"), "pontuacao", sair=True),
        Regra(re.compile(r'"[^"]*"|\'[^\']*\''), "valor_atributo"),
        Regra(re.compile(rf"{NOME_DE_TAG}(?=\s*=)"), "atributo"),
        Regra(re.compile(r"="), "operador"),
    ))

    # O CORPO. A regra de fechamento vem PRIMEIRO, e o resto sao as regras da
    # outra linguagem: `</script>` tem de vencer qualquer regra de JS.
    contextos_js = r.com_prefixo(js_mod.contextos(), "js")
    contextos_css = r.com_prefixo(css_mod.contextos(), "css")

    # `voltar_para="raiz"`, e nao `sair=True`: entrar no corpo custou DOIS niveis
    # (tag_de_script e depois corpo_do_script), entao um `sair` simples deixaria a
    # pilha em `tag_de_script` -- e todo o HTML seguinte seria realcado como
    # atributo de tag.
    corpo_do_script = Contexto("corpo_do_script", (
        (Regra(re.compile(r"(?i:</script\s*>)"), "tag_fechamento",
               voltar_para="raiz"),)
        + contextos_js["js:raiz"].regras))
    corpo_do_estilo = Contexto("corpo_do_estilo", (
        (Regra(re.compile(r"(?i:</style\s*>)"), "tag_fechamento",
               voltar_para="raiz"),)
        + contextos_css["css:raiz"].regras))

    comentario = Contexto("comentario", (
        Regra(re.compile(r"-->"), "comentario", sair=True),
    ), papel_padrao="comentario")
    cdata = Contexto("cdata", (
        Regra(re.compile(r"\]\]>"), "texto_literal", sair=True),
    ), papel_padrao="texto_literal")

    todos = {
        "raiz": raiz, "dentro_da_tag": dentro_da_tag,
        "tag_de_script": tag_de_script, "tag_de_estilo": tag_de_estilo,
        "corpo_do_script": corpo_do_script, "corpo_do_estilo": corpo_do_estilo,
        "comentario": comentario, "cdata": cdata,
    }
    # Os contextos AUXILIARES das linguagens embutidas (comentario de bloco do JS,
    # template string, comentario do CSS) tambem precisam existir: as regras acima
    # apontam para eles.
    todos.update(contextos_js)
    todos.update(contextos_css)
    return todos


class ProvedorHtml(ProvedorDeLinguagem):
    nome = "HTML"
    extensoes = (".html", ".htm", ".xhtml", ".shtml", ".vue", ".svelte",
                 ".hbs", ".ejs", ".twig", ".jinja", ".jinja2", ".j2")
    comentario_de_bloco = ("<!--", "-->")
    comentario_de_linha = None
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    aumenta_indentacao = re.compile(r"<(?!/)[^>]*[^/]>\s*$")
    diminui_indentacao = re.compile(r"^\s*</")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is None:
            self._cache = RegrasDeRealce(inicial="raiz",
                                         contextos=contextos_html())
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        tags = ("html head body title meta link script style div span p a img "
                "ul ol li table thead tbody tr td th form input button select "
                "option textarea label h1 h2 h3 h4 h5 h6 header footer nav main "
                "section article aside pre code br hr strong em").split()
        return frozenset(tags)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """DOM simplificado (requisito 11-HTML).

        Ignora as tags vazias (<br>, <meta>, <img>) na hora de aninhar: sem isso,
        um <br> no meio da pagina faria todo o resto do documento virar filho dele.
        """
        pilha: list[NoDeEstrutura] = []
        raizes: list[NoDeEstrutura] = []
        padrao = re.compile(
            rf"<(?P<fecha>/?)\s*(?P<nome>{NOME_DE_TAG})"
            r"(?P<resto>[^>]*?)(?P<vazia>/?)>")

        for numero, linha in enumerate(texto.split("\n")):
            limpa = re.sub(r"<!--.*?-->", "", linha)
            for c in padrao.finditer(limpa):
                nome = c.group("nome")
                minusculo = nome.lower()
                if c.group("fecha"):
                    # Fecha o nivel correspondente, e nao apenas o ultimo: HTML
                    # real tem tag nao fechada, e um pop cego desalinharia a arvore
                    # do resto do documento.
                    for i in range(len(pilha) - 1, -1, -1):
                        if pilha[i].rotulo.lower() == minusculo:
                            del pilha[i:]
                            break
                    continue
                no = NoDeEstrutura(
                    rotulo=nome, tipo="tag", linha=numero,
                    coluna=c.start("nome"), detalhe=_resumo(c.group("resto")))
                if pilha:
                    pilha[-1].filhos.append(no)
                else:
                    raizes.append(no)
                if not c.group("vazia") and minusculo not in VAZIAS:
                    pilha.append(no)
                if len(pilha) > 60:
                    return raizes
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        inicio = amostra.lstrip()[:200].lower()
        if inicio.startswith("<!doctype html") or inicio.startswith("<html"):
            return 95
        pontos = 0
        if re.search(r"<(?:html|head|body)\b", amostra, re.I):
            pontos += 50
        if re.search(r"<(?:div|span|p|a|img|table|form)\b", amostra, re.I):
            pontos += 30
        if re.search(r"<(?:script|style)\b", amostra, re.I):
            pontos += 20
        return min(pontos, 100)


def _resumo(resto: str) -> str:
    """id e class primeiro: sao o que identifica o elemento na pratica."""
    partes = []
    for chave in ("id", "class"):
        c = re.search(rf'\b{chave}\s*=\s*["\']([^"\']*)', resto)
        if c:
            marca = "#" if chave == "id" else "."
            partes.append(marca + c.group(1).replace(" ", " ."))
    return " ".join(partes)


PROVEDORES = (ProvedorHtml(),)
