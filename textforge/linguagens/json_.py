"""Provedor de JSON.

O detalhe que distingue um realce util de um decorativo: a CHAVE e o VALOR de
texto sao pintados de cores diferentes, apesar de os dois serem strings entre
aspas. A diferenca esta' no que vem depois -- uma chave e' seguida de ":". Sem isso,
um arquivo de configuracao fica todo de uma cor so' e nao ajuda a ler.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

# JSON nao tem comentario no padrao, mas JSONC (o dos arquivos de configuracao do
# VS Code, e de muita ferramenta) tem. Reconhecer nao faz mal: num JSON estrito o
# padrao simplesmente nao aparece.
TEXTO = r.texto_com_escape('"')


class ProvedorJson(ProvedorDeLinguagem):
    nome = "JSON"
    extensoes = (".json", ".jsonc", ".json5", ".map", ".ipynb", ".webmanifest",
                 ".jsonl", ".ndjson")
    nomes_de_arquivo = ("package.json", "tsconfig.json", "composer.json",
                        ".eslintrc", ".prettierrc", "renovate.json")
    comentario_de_linha = "//"          # JSONC
    comentario_de_bloco = ("/*", "*/")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    aumenta_indentacao = re.compile(r"[{\[]\s*$")
    diminui_indentacao = re.compile(r"^\s*[}\]]")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        raiz = Contexto("raiz", (
            Regra(re.compile(r"/\*"), "comentario", entrar_em="comentario"),
            Regra(re.compile(r"//.*$"), "comentario"),
            # A CHAVE vem antes do valor de texto: os dois sao strings, e o que os
            # distingue e' o ":" logo depois. Sem esta regra primeiro, tudo ficaria
            # com o papel de valor.
            Regra(re.compile(rf"{TEXTO}(?=\s*:)"), "chave"),
            Regra(re.compile(TEXTO), "texto_literal"),
            Regra(re.compile(r"\b(?:true|false|null)\b"), "constante"),
            Regra(re.compile(r"-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), "numero"),
            Regra(re.compile(r"[{}\[\],:]"), "pontuacao"),
        ))
        comentario = Contexto("comentario", (
            Regra(re.compile(r"\*/"), "comentario", sair=True),
        ), papel_padrao="comentario")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "comentario": comentario})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset({"true", "false", "null"})

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Arvore de objetos e propriedades (requisito 6-JSON).

        Feita com `json.loads`, que NAO avalia codigo -- e nunca com `eval` nem com
        `ast.literal_eval` como "ajuda" para JSON quase valido. Esse fallback e' a
        porta de entrada classica de execucao de codigo num editor, e o requisito 35
        o proibe.

        Arquivo invalido cai numa varredura por regex das chaves, para o painel
        continuar util enquanto o usuario digita.
        """
        import json

        try:
            dados = json.loads(texto)
        except (ValueError, RecursionError, MemoryError):
            return self._chaves_por_regex(texto)

        linhas_da_chave = self._mapear_chaves(texto)

        def percorrer(valor, rotulo: str, profundidade: int) -> NoDeEstrutura:
            linha = linhas_da_chave.get(rotulo, 0)
            if isinstance(valor, dict):
                no = NoDeEstrutura(rotulo=rotulo or "{}", tipo="objeto",
                                   linha=linha,
                                   detalhe=f"{len(valor)} propriedade(s)")
                if profundidade < 12:
                    for chave, sub in valor.items():
                        no.filhos.append(percorrer(sub, str(chave),
                                                   profundidade + 1))
                return no
            if isinstance(valor, list):
                no = NoDeEstrutura(rotulo=rotulo or "[]", tipo="lista",
                                   linha=linha, detalhe=f"{len(valor)} item(ns)")
                if profundidade < 12:
                    for i, sub in enumerate(valor[:200]):
                        no.filhos.append(percorrer(sub, f"[{i}]",
                                                   profundidade + 1))
                return no
            return NoDeEstrutura(rotulo=rotulo, tipo="chave", linha=linha,
                                 detalhe=_resumir(valor))

        raiz = percorrer(dados, "", 0)
        return raiz.filhos if raiz.filhos else [raiz]

    @staticmethod
    def _mapear_chaves(texto: str) -> dict[str, int]:
        """Chave -> primeira linha em que ela aparece.

        Aproximacao deliberada: `json.loads` nao devolve posicoes, e um parser
        proprio so' para isso nao se paga. Chave repetida em niveis diferentes
        aponta para a primeira ocorrencia, o que e' suficiente para navegar.
        """
        mapa: dict[str, int] = {}
        padrao = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:')
        for numero, linha in enumerate(texto.split("\n")):
            for casamento in padrao.finditer(linha):
                mapa.setdefault(casamento.group(1), numero)
        return mapa

    @staticmethod
    def _chaves_por_regex(texto: str) -> list[NoDeEstrutura]:
        padrao = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:')
        achados: list[NoDeEstrutura] = []
        for numero, linha in enumerate(texto.split("\n")):
            for casamento in padrao.finditer(linha):
                achados.append(NoDeEstrutura(
                    rotulo=casamento.group(1), tipo="chave", linha=numero,
                    coluna=casamento.start(1)))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        inicio = amostra.lstrip()[:1]
        if inicio not in ("{", "["):
            return 0
        import json
        try:
            json.loads(amostra)
        except ValueError:
            # Pode ser um JSON valido cortado pela amostra: a estrutura conta.
            return 55 if re.search(r'"\s*:\s*(?:"|\d|\{|\[|true|false|null)',
                                   amostra) else 20
        return 95

    def formatador(self):
        try:
            from textforge.formatadores import de_json
        except ImportError:
            return None
        return getattr(de_json, "FORMATADOR", None)


def _resumir(valor) -> str:
    if isinstance(valor, str):
        return f'"{valor[:40]}"' + ("..." if len(valor) > 40 else "")
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)[:40]


PROVEDORES = (ProvedorJson(),)
