"""Provedor de XML.

E' o formato mais importante para este usuario (XML de integracao), entao o realce
distingue seis coisas em vez de duas: nome da tag, tag de fechamento, atributo,
valor do atributo, entidade e comentario. Contextos separados para comentario,
CDATA e prologo, porque os tres atravessam linhas.

A arvore estrutural usa `expat` com as entidades e o DTD DESLIGADOS -- ver
`seguranca.py` na etapa 8. Aqui a estrutura e' extraida por varredura de tags, o
que e' seguro por construcao: nada e' expandido, nada e' resolvido, nenhuma
entidade externa e' buscada.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

NOME_DE_TAG = r"[A-Za-z_][\w.\-]*(?::[A-Za-z_][\w.\-]*)?"


class ProvedorXml(ProvedorDeLinguagem):
    nome = "XML"
    extensoes = (".xml", ".xsd", ".xsl", ".xslt", ".rss", ".atom", ".svg",
                 ".plist", ".csproj", ".vbproj", ".props", ".targets", ".nuspec",
                 ".resx", ".config", ".xaml", ".kml", ".gpx", ".wsdl", ".pom")
    nomes_de_arquivo = ("web.config", "app.config", "pom.xml", "AndroidManifest.xml")
    comentario_de_bloco = ("<!--", "-->")
    comentario_de_linha = None
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)
    # Abre bloco quando a linha termina com uma tag de abertura nao fechada.
    aumenta_indentacao = re.compile(r"<(?!/)[^>]*[^/]>\s*$")
    diminui_indentacao = re.compile(r"^\s*</")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        # O comentario vem PRIMEIRO: "<!-- <tag> -->" nao pode ter a tag realcada.
        raiz = Contexto("raiz", (
            Regra(re.compile(r"<!--"), "comentario", entrar_em="comentario"),
            Regra(re.compile(r"<!\[CDATA\["), "texto_literal", entrar_em="cdata"),
            Regra(re.compile(r"<\?"), "preprocessador", entrar_em="prologo"),
            # Flag com ESCOPO, e nao re.IGNORECASE na regra: as regras de um
            # contexto entram todas no mesmo regex combinado, e um regex tem um
            # conjunto de bandeiras so'. Aqui a insensibilidade vale apenas para
            # este trecho.
            Regra(re.compile(r"(?i:<!DOCTYPE)"), "preprocessador",
                  entrar_em="prologo"),
            Regra(re.compile(rf"</\s*(?P<fecha>{NOME_DE_TAG})\s*>"),
                  "tag_fechamento", papeis_por_grupo={"fecha": "tag_fechamento"}),
            Regra(re.compile(rf"<\s*(?P<abre>{NOME_DE_TAG})"), "pontuacao",
                  papeis_por_grupo={"abre": "tag"}, entrar_em="dentro_da_tag"),
            Regra(re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|\w+);"), "entidade"),
        ))

        # Dentro de "<tag ...>" so' existem atributos. Contexto proprio porque uma
        # tag com muitos atributos costuma ocupar varias linhas.
        dentro_da_tag = Contexto("dentro_da_tag", (
            Regra(re.compile(r"/?>"), "pontuacao", sair=True),
            Regra(re.compile(r'"[^"]*"'), "valor_atributo"),
            Regra(re.compile(r"'[^']*'"), "valor_atributo"),
            Regra(re.compile(rf"{NOME_DE_TAG}(?=\s*=)"), "atributo"),
            Regra(re.compile(r"="), "operador"),
        ))

        comentario = Contexto("comentario", (
            Regra(re.compile(r"-->"), "comentario", sair=True),
        ), papel_padrao="comentario")

        cdata = Contexto("cdata", (
            Regra(re.compile(r"\]\]>"), "texto_literal", sair=True),
        ), papel_padrao="texto_literal")

        prologo = Contexto("prologo", (
            Regra(re.compile(r"\?>|>"), "preprocessador", sair=True),
            Regra(re.compile(r'"[^"]*"|\'[^\']*\''), "valor_atributo"),
            Regra(re.compile(rf"{NOME_DE_TAG}(?=\s*=)"), "atributo"),
        ), papel_padrao="preprocessador")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "dentro_da_tag": dentro_da_tag,
            "comentario": comentario, "cdata": cdata, "prologo": prologo})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Arvore de tags (requisito 11-XML), por varredura.

        Varredura de tags, e nao um parser: e' seguro por construcao (nada e'
        expandido, nenhuma entidade externa e' buscada) e funciona em XML
        INCOMPLETO, que e' o estado normal de um arquivo sendo editado. Um parser
        de verdade recusaria o documento e o painel ficaria vazio justamente quando
        e' mais util.
        """
        pilha: list[NoDeEstrutura] = []
        raizes: list[NoDeEstrutura] = []
        padrao = re.compile(
            r"<(?P<fecha>/?)\s*(?P<nome>" + NOME_DE_TAG + r")"
            r"(?P<resto>[^>]*?)(?P<vazia>/?)>")

        for numero, linha in enumerate(texto.split("\n")):
            # Comentario e CDATA sao removidos ANTES da varredura: uma tag
            # comentada nao esta' na estrutura do documento.
            limpa = re.sub(r"<!--.*?-->", "", linha)
            limpa = re.sub(r"<!\[CDATA\[.*?\]\]>", "", limpa)
            for c in padrao.finditer(limpa):
                nome = c.group("nome")
                if c.group("fecha"):
                    if pilha:
                        pilha.pop()
                    continue
                no = NoDeEstrutura(rotulo=nome, tipo="tag", linha=numero,
                                   coluna=c.start("nome"),
                                   detalhe=_atributos(c.group("resto")))
                if pilha:
                    pilha[-1].filhos.append(no)
                else:
                    raizes.append(no)
                if not c.group("vazia"):
                    pilha.append(no)
                if len(pilha) > 60:
                    # XML absurdamente aninhado: para de descer em vez de consumir
                    # memoria sem limite.
                    return raizes
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        inicio = amostra.lstrip()[:120]
        if inicio.startswith("<?xml"):
            return 95
        pontos = 0
        if re.search(rf"<{NOME_DE_TAG}[^>]*>", amostra):
            pontos += 45
        if re.search(rf"</{NOME_DE_TAG}\s*>", amostra):
            pontos += 30
        if inicio.startswith("<"):
            pontos += 15
        # HTML tem tags tambem: deixa o provedor de HTML ganhar quando for o caso.
        if re.search(r"<(?:html|body|div|span|script)\b", amostra, re.I):
            pontos -= 40
        return max(0, min(pontos, 100))

    def formatador(self):
        try:
            from textforge.formatadores import de_xml
        except ImportError:
            return None
        return getattr(de_xml, "FORMATADOR", None)


def _atributos(resto: str) -> str:
    """Resumo dos atributos, para a coluna de detalhe do painel."""
    nomes = re.findall(rf"({NOME_DE_TAG})\s*=", resto)
    return " ".join(nomes[:4]) + (" ..." if len(nomes) > 4 else "")


PROVEDORES = (ProvedorXml(),)
