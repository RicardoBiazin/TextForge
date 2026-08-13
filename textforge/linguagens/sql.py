"""Provedor de SQL.

Duas particularidades que o generico nao cobre:

  * SQL nao diferencia maiusculas, mas o CODIGO costuma escrever as palavras
    reservadas em maiusculas. O realce e' insensivel a caixa (`select` e `SELECT`
    ficam iguais), o que e' o comportamento correto.
  * a string de SQL usa aspas SIMPLES, e o escape e' a aspa DOBRADA (`''`), nao a
    barra invertida. Um `\\'` no meio de uma string SQL nao escapa nada -- tratar
    como C faria a string parecer nao fechada e pintaria o resto do arquivo de verde.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

# Os comandos que o requisito 6 lista, mais o vocabulario que aparece em qualquer
# consulta de verdade.
COMANDOS = (
    "select from where join inner outer left right full cross on group by having "
    "order asc desc limit offset union all insert into values update set delete "
    "create alter drop truncate table view index sequence trigger procedure "
    "function database schema constraint primary foreign key unique check default "
    "references cascade grant revoke commit rollback savepoint begin transaction "
    "with recursive returning merge using upsert conflict do nothing").split()

PALAVRAS = (
    "and or not in exists between like ilike is null as case when then else end "
    "distinct count sum avg min max cast convert coalesce nullif if declare "
    "cursor fetch open close while loop for each row before after instead of "
    "exception raise return call execute immediate").split()

TIPOS = (
    "int integer smallint bigint tinyint decimal numeric float real double "
    "precision char varchar nchar nvarchar text ntext clob blob date datetime "
    "datetime2 timestamp time year boolean bool bit binary varbinary uuid json "
    "jsonb xml money serial bigserial identity").split()

CONSTANTES = "null true false current_date current_time current_timestamp".split()


class ProvedorSql(ProvedorDeLinguagem):
    nome = "SQL"
    extensoes = (".sql", ".ddl", ".dml", ".pks", ".pkb", ".prc", ".fnc", ".vw",
                 ".mysql", ".pgsql", ".tsql", ".plsql")
    comentario_de_linha = "--"
    comentario_de_bloco = ("/*", "*/")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)
    aumenta_indentacao = re.compile(r"(?i:\b(?:begin|then|loop|as)\s*$)|\(\s*$")
    diminui_indentacao = re.compile(r"(?i:^\s*(?:end|else|elsif)\b)|^\s*\)")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        # A insensibilidade a caixa vem por ESCOPO nas regras que precisam dela
        # (as listas de palavras, via `regra_de_palavras(sem_caixa=True)`), e nao
        # como bandeira do contexto: assim as regras deste contexto sao
        # componiveis com as de qualquer outro. Comentario, string e numero nao
        # dependem de caixa.
        raiz = Contexto("raiz", (
            Regra(re.compile(r"/\*"), "comentario", entrar_em="comentario"),
            Regra(re.compile(r"--.*$"), "comentario"),
            Regra(re.compile(r"#.*$"), "comentario"),      # MySQL
            # String de SQL: o escape e' a aspa DOBRADA, nao a barra invertida.
            # Tratar como C faria a string parecer nao fechada e pintaria o resto
            # do arquivo como texto literal.
            Regra(re.compile(r"'(?:[^']|'')*'"), "texto_literal"),
            # Identificador entre delimitador: "coluna", [coluna], `coluna`.
            Regra(re.compile(r'"[^"\n]*"|\[[^\]\n]*\]|`[^`\n]*`'), "variavel"),
            # Parametro de comando preparado: @nome, :nome, ?, $1.
            Regra(re.compile(r"[@:]\w+|\$\d+|\?"), "interpolacao"),
            Regra(re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), "numero"),
            r.regra_de_palavras(COMANDOS, "palavra_chave", sem_caixa=True),
            r.regra_de_palavras(PALAVRAS, "palavra_chave_2", sem_caixa=True),
            r.regra_de_palavras(TIPOS, "tipo", sem_caixa=True),
            r.regra_de_palavras(CONSTANTES, "constante", sem_caixa=True),
            Regra(re.compile(r.CHAMADA), "chamada"),
            Regra(re.compile(r"[-+*/%=<>!|]+"), "operador"),
            Regra(re.compile(r"[(),;.]"), "pontuacao"),
        ))
        comentario = Contexto("comentario", (
            Regra(re.compile(r"\*/"), "comentario", sair=True),
        ), papel_padrao="comentario")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "comentario": comentario})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="marcadores",
                            marcador_abre=re.compile(
                                r"(?i:^\s*(?:select|insert|update|delete|create"
                                r"|alter|drop|begin|with)\b)"))

    def palavras_de_autocomplete(self) -> frozenset[str]:
        # Em maiusculas: e' como se escreve palavra reservada de SQL na pratica.
        return frozenset(p.upper() for p in COMANDOS + PALAVRAS + TIPOS)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Blocos e comandos principais (requisito 11-SQL).

        Lista os comandos de topo, com o objeto quando ha' um: "CREATE TABLE
        clientes" aparece como "TABLE clientes". E' o que permite navegar num
        arquivo de migracao com dezenas de comandos.
        """
        achados: list[NoDeEstrutura] = []
        criacao = re.compile(
            r"^\s*(?P<verbo>create|alter|drop)\s+(?:or\s+replace\s+)?"
            r"(?P<objeto>table|view|index|sequence|trigger|procedure|function"
            r"|database|schema|type)\s+(?:if\s+(?:not\s+)?exists\s+)?"
            r"(?P<nome>[\w.\"\[\]`]+)", re.I)
        comando = re.compile(
            r"^\s*(?P<verbo>select|insert|update|delete|merge|with|begin"
            r"|commit|rollback|grant|revoke|truncate)\b", re.I)

        for numero, linha in enumerate(texto.split("\n")):
            sem_comentario = re.sub(r"--.*$", "", linha)
            c = criacao.match(sem_comentario)
            if c:
                achados.append(NoDeEstrutura(
                    rotulo=f"{c.group('objeto').upper()} {c.group('nome')}",
                    tipo="secao", linha=numero, coluna=c.start("verbo"),
                    detalhe=c.group("verbo").upper()))
                continue
            c = comando.match(sem_comentario)
            if c:
                achados.append(NoDeEstrutura(
                    rotulo=c.group("verbo").upper() + " "
                    + sem_comentario.strip()[len(c.group("verbo")):].strip()[:50],
                    tipo="comando", linha=numero, coluna=c.start("verbo")))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"(?i)\bselect\b[\s\S]{0,200}\bfrom\b", amostra):
            pontos += 55
        if re.search(r"(?i)\b(?:create|alter|drop)\s+(?:table|view|index)\b",
                     amostra):
            pontos += 45
        if re.search(r"(?i)\b(?:insert\s+into|update\s+\w+\s+set|delete\s+from)\b",
                     amostra):
            pontos += 40
        if re.search(r"(?m)^\s*--", amostra):
            pontos += 10
        return min(pontos, 100)

    def formatador(self):
        try:
            from textforge.formatadores import de_sql
        except ImportError:
            return None
        return getattr(de_sql, "FORMATADOR", None)


PROVEDORES = (ProvedorSql(),)
