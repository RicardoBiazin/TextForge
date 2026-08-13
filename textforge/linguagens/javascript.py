"""Provedor de JavaScript e TypeScript.

Exporta `contextos()` para o `html.py` embutir JS dentro de `<script>`.

A parte delicada e' a TEMPLATE STRING (`crase`): ela atravessa linhas E contem
`${expressao}`, que e' codigo JS de novo. Isso produz uma pilha de tres niveis --
raiz > template > interpolacao -- e e' o caso que justifica o internamento da pilha
em `realce/pilha.py`.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

PALAVRAS_CHAVE = (
    "async await break case catch class const continue debugger default delete "
    "do else enum export extends finally for from function get if implements "
    "import in instanceof interface let new of package private protected public "
    "return set static super switch this throw try typeof var void while with "
    "yield as satisfies keyof infer readonly declare namespace abstract "
    "override").split()

CONSTANTES = "true false null undefined NaN Infinity".split()

TIPOS = ("string number boolean object symbol bigint any unknown never void "
         "Array Object String Number Boolean Function Promise Map Set WeakMap "
         "WeakSet Date RegExp Error JSON Math Symbol BigInt Proxy Reflect").split()

EMBUTIDAS = ("console document window fetch setTimeout setInterval "
             "clearTimeout clearInterval parseInt parseFloat isNaN encodeURI "
             "decodeURI encodeURIComponent decodeURIComponent require module "
             "exports process globalThis structuredClone").split()


def contextos() -> dict[str, Contexto]:
    """Contextos do JS/TS. Reaproveitados pelo HTML dentro de <script>."""
    raiz = Contexto("raiz", (
        Regra(re.compile(r"/\*"), "comentario", entrar_em="comentario"),
        Regra(re.compile(r"//.*$"), "comentario"),
        # A template string vem antes das outras: a crase e' um delimitador
        # proprio, e o conteudo dela nao e' codigo (exceto dentro de ${}).
        Regra(re.compile(r"`"), "texto_literal", entrar_em="template"),
        Regra(re.compile(r.texto_com_escape('"')), "texto_literal"),
        Regra(re.compile(r.texto_com_escape("'")), "texto_literal"),
        # Literal de expressao regular. O lookbehind evita confundir com divisao:
        # so' e' regex depois de "(", ",", "=", ":", "[", "!", "&", "|", "?",
        # "{", ";" ou "return".
        Regra(re.compile(r"(?<=[(,=:\[!&|?{;])\s*/(?![*/])(?:\\.|[^/\\\n])+/[gimsuy]*"),
              "regex"),
        Regra(re.compile(r"\b(?:function|class)\s+(?P<js_nome>[A-Za-z_$][\w$]*)"),
              "palavra_chave", papeis_por_grupo={"js_nome": "definicao"}),
        # Arrow function nomeada: "const f = (x) => ..." -- o nome vem antes.
        Regra(re.compile(r"\b(?:const|let|var)\s+(?P<js_var>[A-Za-z_$][\w$]*)"
                         r"(?=\s*=\s*(?:async\s+)?(?:\(|[A-Za-z_$][\w$]*\s*=>))"),
              "palavra_chave", papeis_por_grupo={"js_var": "definicao"}),
        Regra(re.compile(r"\bthis\b"), "pseudo_variavel"),
        Regra(re.compile(r"@[A-Za-z_$][\w$]*"), "decorador"),
        Regra(re.compile(r.NUMERO + r"n?"), "numero"),
        r.regra_de_palavras(CONSTANTES, "constante"),
        r.regra_de_palavras(TIPOS, "tipo"),
        r.regra_de_palavras(PALAVRAS_CHAVE, "palavra_chave"),
        r.regra_de_palavras(EMBUTIDAS, "embutida"),
        Regra(re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"), "constante"),
        Regra(re.compile(r.CHAMADA), "chamada"),
        Regra(re.compile(r"=>"), "operador"),
        Regra(re.compile(r.OPERADOR), "operador"),
        Regra(re.compile(r.PONTUACAO), "pontuacao"),
    ))
    comentario = Contexto("comentario", (
        Regra(re.compile(r"\*/"), "comentario", sair=True),
    ), papel_padrao="comentario")
    # Dentro da template string: so' o escape, o "${" e a crase de fechamento.
    template = Contexto("template", (
        Regra(re.compile(r"\\."), "escape"),
        Regra(re.compile(r"\$\{"), "interpolacao", entrar_em="interpolacao"),
        Regra(re.compile(r"`"), "texto_literal", sair=True),
    ), papel_padrao="texto_literal")
    # Dentro de ${}: e' JS de novo. Reaproveitamos as regras da raiz mais a de
    # fechamento -- e' o terceiro nivel da pilha.
    interpolacao = Contexto("interpolacao", (
        (Regra(re.compile(r"\}"), "interpolacao", sair=True),) + raiz.regras))
    return {"raiz": raiz, "comentario": comentario, "template": template,
            "interpolacao": interpolacao}


class ProvedorJavaScript(ProvedorDeLinguagem):
    nome = "JavaScript"
    extensoes = (".js", ".mjs", ".cjs", ".jsx")
    padroes_de_shebang = ("node",)
    comentario_de_linha = "//"
    comentario_de_bloco = ("/*", "*/")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    aumenta_indentacao = re.compile(r"[{\[(]\s*$")
    diminui_indentacao = re.compile(r"^\s*[}\])]")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is None:
            self._cache = RegrasDeRealce(inicial="raiz", contextos=contextos())
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(PALAVRAS_CHAVE + CONSTANTES + TIPOS + EMBUTIDAS)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Classes, funcoes, metodos e arrow functions nomeadas."""
        achados: list[NoDeEstrutura] = []
        padroes = (
            (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([\w$]+)"),
             "classe"),
            (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
                        r"function\s*\*?\s*([\w$]+)"), "funcao"),
            (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*"
                        r"(?:async\s+)?(?:\(|[\w$]+\s*=>|function)"), "funcao"),
            # Metodo de classe: "  nome(args) {" -- exclui as palavras-chave para
            # nao confundir "if (x) {" com um metodo chamado "if".
            (re.compile(r"^\s{2,}(?:async\s+|get\s+|set\s+|static\s+)*"
                        r"(?!if|for|while|switch|catch|return|function|else\b)"
                        r"([\w$]+)\s*\([^)]*\)\s*\{"), "metodo"),
        )
        for numero, linha in enumerate(texto.split("\n")):
            for padrao, tipo in padroes:
                c = padrao.match(linha)
                if c:
                    achados.append(NoDeEstrutura(
                        rotulo=c.group(1), tipo=tipo, linha=numero,
                        coluna=c.start(1)))
                    break
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"\b(?:function|const|let|var)\s+[\w$]+", amostra):
            pontos += 40
        if re.search(r"=>", amostra):
            pontos += 20
        if re.search(r"\b(?:console\.log|require\(|import\s+.*\bfrom\b)", amostra):
            pontos += 30
        if re.search(r";\s*$", amostra, re.M):
            pontos += 10
        # HTML com <script> deve ir para o provedor de HTML.
        if re.search(r"<(?:html|body|div|script)\b", amostra, re.I):
            pontos -= 45
        return max(0, min(pontos, 100))


class ProvedorTypeScript(ProvedorJavaScript):
    """TypeScript compartilha tudo com JS: a diferenca esta' nas palavras-chave,
    que ja' estao na lista comum. Um provedor separado existe para o menu
    Linguagem mostrar "TypeScript" e para as extensoes resolverem."""

    nome = "TypeScript"
    extensoes = (".ts", ".tsx", ".mts", ".cts", ".d.ts")

    def __init__(self) -> None:
        super().__init__()


PROVEDORES = (ProvedorJavaScript(), ProvedorTypeScript())
