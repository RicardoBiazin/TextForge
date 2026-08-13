"""Provedor de Python.

O nome do modulo termina em "_" para nao sombrear a stdlib. Um `import json` de
dentro de `textforge/linguagens/json.py` acharia o proprio arquivo, e o mesmo vale
para `python`, `xml` e `ini`.

Este e' o provedor de REFERENCIA: escrito com `Contexto`/`Regra` na mao, e nao com
`ProvedorGenerico`, porque Python tem duas coisas que o generico nao cobre --
strings triplas, que atravessam linhas, e uma arvore estrutural de verdade via
`ast`.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

PALAVRAS_CHAVE = (
    "False None True and as assert async await break class continue def del elif "
    "else except finally for from global if import in is lambda nonlocal not or "
    "pass raise return try while with yield match case").split()

# Nao sao palavras reservadas, mas sao o vocabulario que o programador reconhece
# como "do Python". Ficam num papel proprio para poderem ter cor diferente.
EMBUTIDAS = (
    "abs all any bin bool bytearray bytes callable chr classmethod compile "
    "complex delattr dict dir divmod enumerate eval exec filter float format "
    "frozenset getattr globals hasattr hash help hex id input int isinstance "
    "issubclass iter len list locals map max memoryview min next object oct open "
    "ord pow print property range repr reversed round set setattr slice sorted "
    "staticmethod str sum super tuple type vars zip").split()

EXCECOES = (
    "BaseException Exception ArithmeticError AssertionError AttributeError "
    "EOFError FileExistsError FileNotFoundError ImportError IndexError KeyError "
    "KeyboardInterrupt LookupError MemoryError NameError NotImplementedError "
    "OSError OverflowError PermissionError RecursionError RuntimeError StopIteration "
    "SyntaxError SystemExit TypeError UnicodeDecodeError UnicodeEncodeError "
    "ValueError ZeroDivisionError").split()

# Prefixos de string do Python: r, b, u, f, rb, br, fr, rf...
PREFIXO_DE_TEXTO = r"(?:[rRbBuUfF]{0,2})"


class ProvedorPython(ProvedorDeLinguagem):
    nome = "Python"
    extensoes = (".py", ".pyw", ".pyi", ".pyx")
    nomes_de_arquivo = ("SConstruct", "SConscript")
    padroes_de_shebang = ("python",)
    comentario_de_linha = "#"
    comentario_de_bloco = None       # Python nao tem; o Ctrl+/ usa o de linha
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)
    # Linha que abre bloco: termina em ":" (com comentario opcional depois).
    aumenta_indentacao = re.compile(r":\s*(?:#.*)?$")
    diminui_indentacao = re.compile(
        r"^\s*(?:return|raise|pass|break|continue|else\b|elif\b|except\b"
        r"|finally\b|case\b)")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        # ORDEM CRITICA: a string tripla vem ANTES da simples. Numa alternancia o
        # Python para no primeiro ramo que casa, e `""` (string vazia) casaria os
        # dois primeiros caracteres de `"""`, deixando o resto do docstring como
        # codigo.
        raiz = Contexto("raiz", (
            Regra(re.compile(PREFIXO_DE_TEXTO + '"""'), "texto_literal",
                  entrar_em="tres_aspas"),
            Regra(re.compile(PREFIXO_DE_TEXTO + "'''"), "texto_literal",
                  entrar_em="tres_apostrofos"),
            Regra(re.compile(PREFIXO_DE_TEXTO + r.texto_com_escape('"')),
                  "texto_literal"),
            Regra(re.compile(PREFIXO_DE_TEXTO + r.texto_com_escape("'")),
                  "texto_literal"),
            Regra(re.compile(r"#.*$"), "comentario"),
            Regra(re.compile(r"@[A-Za-z_][\w.]*"), "decorador"),
            Regra(re.compile(r.NUMERO), "numero"),
            # "def nome" / "class Nome": o nome ganha papel proprio.
            Regra(re.compile(r"\b(?:async\s+)?(?:def|class)\s+(?P<py_nome>\w+)"),
                  "palavra_chave", papeis_por_grupo={"py_nome": "definicao"}),
            Regra(re.compile(r"\bself\b|\bcls\b"), "pseudo_variavel"),
            r.regra_de_palavras(PALAVRAS_CHAVE, "palavra_chave"),
            r.regra_de_palavras(EXCECOES, "tipo"),
            r.regra_de_palavras(EMBUTIDAS, "embutida"),
            Regra(re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"), "constante"),
            Regra(re.compile(r.CHAMADA), "chamada"),
            Regra(re.compile(r.OPERADOR), "operador"),
            Regra(re.compile(r.PONTUACAO), "pontuacao"),
        ))

        # Nos contextos de string tripla, o unico papel do interior e'
        # "texto_literal", e a saida e' o delimitador correspondente. O escape
        # tambem e' reconhecido, senao um `\"""` fecharia a string cedo.
        tres_aspas = Contexto("tres_aspas", (
            Regra(re.compile(r"\\."), "escape"),
            Regra(re.compile('"""'), "texto_literal", sair=True),
        ), papel_padrao="texto_literal")
        tres_apostrofos = Contexto("tres_apostrofos", (
            Regra(re.compile(r"\\."), "escape"),
            Regra(re.compile("'''"), "texto_literal", sair=True),
        ), papel_padrao="texto_literal")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "tres_aspas": tres_aspas,
            "tres_apostrofos": tres_apostrofos})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="indentacao")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(PALAVRAS_CHAVE + EMBUTIDAS + EXCECOES)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Arvore de classes, funcoes e metodos via `ast`.

        `ast.parse` NAO executa nada -- monta a arvore sintatica e para. E' a forma
        legitima de analisar um `.py`, e nao viola o requisito 35 (que proibe
        `eval`, `exec` e `compile`).

        Arquivo com erro de sintaxe e' o caso COMUM num editor: o usuario esta'
        digitando. O fallback por regex garante que o painel Estrutura continue
        util enquanto o codigo esta' incompleto.
        """
        import ast

        try:
            arvore = ast.parse(texto)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return self._estrutura_por_regex(texto)

        def percorrer(no, dentro_de_classe: bool) -> list[NoDeEstrutura]:
            saida: list[NoDeEstrutura] = []
            for filho in getattr(no, "body", ()):
                if isinstance(filho, ast.ClassDef):
                    saida.append(NoDeEstrutura(
                        rotulo=filho.name, tipo="classe",
                        linha=filho.lineno - 1, coluna=filho.col_offset,
                        detalhe=_bases(filho),
                        filhos=percorrer(filho, True)))
                elif isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    saida.append(NoDeEstrutura(
                        rotulo=filho.name,
                        tipo="metodo" if dentro_de_classe else "funcao",
                        linha=filho.lineno - 1, coluna=filho.col_offset,
                        detalhe=_assinatura(filho),
                        filhos=percorrer(filho, False)))
            return saida

        return percorrer(arvore, False)

    @staticmethod
    def _estrutura_por_regex(texto: str) -> list[NoDeEstrutura]:
        padrao = re.compile(
            r"^(?P<recuo>\s*)(?:async\s+)?(?P<tipo>def|class)\s+(?P<nome>\w+)")
        achados: list[NoDeEstrutura] = []
        for numero, linha in enumerate(texto.split("\n")):
            casamento = padrao.match(linha)
            if not casamento:
                continue
            tipo = "classe" if casamento.group("tipo") == "class" else "funcao"
            if tipo == "funcao" and casamento.group("recuo"):
                tipo = "metodo"
            achados.append(NoDeEstrutura(
                rotulo=casamento.group("nome"), tipo=tipo, linha=numero,
                coluna=casamento.start("nome")))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"^\s*(?:async\s+)?def\s+\w+\s*\(", amostra, re.M):
            pontos += 55
        if re.search(r"^\s*class\s+\w+", amostra, re.M):
            pontos += 25
        if re.search(r"^\s*(?:import|from)\s+\w", amostra, re.M):
            pontos += 25
        if "__name__" in amostra or "self." in amostra:
            pontos += 10
        if re.search(r"^\s*#!.*python", amostra):
            pontos += 40
        return min(pontos, 100)

    def formatador(self):
        # Os formatadores entram na etapa 8. Import tardio e tolerante para o
        # provedor funcionar antes disso -- e para o `black`, que e' opcional, nao
        # ser exigido na partida.
        try:
            from textforge.formatadores import de_python
        except ImportError:
            return None
        return getattr(de_python, "FORMATADOR", None)


def _assinatura(no) -> str:
    import ast

    partes = [a.arg for a in no.args.args]
    if no.args.vararg:
        partes.append("*" + no.args.vararg.arg)
    for a in no.args.kwonlyargs:
        partes.append(a.arg)
    if no.args.kwarg:
        partes.append("**" + no.args.kwarg.arg)
    devolve = ""
    if no.returns is not None:
        try:
            devolve = " -> " + ast.unparse(no.returns)
        except Exception:            # noqa: BLE001 - anotacao exotica
            devolve = ""
    return f"({', '.join(partes)}){devolve}"


def _bases(no) -> str:
    import ast

    nomes = []
    for base in no.bases:
        try:
            nomes.append(ast.unparse(base))
        except Exception:            # noqa: BLE001
            pass
    return f"({', '.join(nomes)})" if nomes else ""


PROVEDORES = (ProvedorPython(),)
