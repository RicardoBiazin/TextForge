"""Formatador de SQL (requisito 6-SQL).

Usa `sqlparse`, que esta' no requirements.txt. Escrever isto a mao daria resultado
pior: indentar SQL de verdade exige entender subconsulta, CASE, JOIN encadeado e
funcao de janela, e uma heuristica por palavra-chave estraga consulta complexa.

O `sqlparse` NAO valida SQL -- nao existe "SQL invalido" para ele, porque cada banco
tem a sua gramatica. Por isso `validar` faz uma checagem estrutural minima
(parenteses e apostrofos balanceados) em vez de prometer validacao que nao pode
cumprir.
"""

from __future__ import annotations

import re

from textforge import log_interno
from textforge.formatadores.base import (ErroDeSintaxe, Recusa, Resultado, Saida,
                                         unidade_de_indentacao)

log = log_interno.obter(__name__)

# Palavras que ganham linha propria na formatacao.
QUEBRAR_ANTES = ("select", "from", "where", "group by", "order by", "having",
                 "join", "inner join", "left join", "right join", "full join",
                 "cross join", "union", "union all", "insert into", "values",
                 "update", "set", "delete from", "limit", "offset", "returning")


def _disponivel() -> bool:
    try:
        import sqlparse  # noqa: F401
    except ImportError:
        return False
    return True


def formatar(texto: str, opcoes: dict) -> Saida:
    if not texto.strip():
        return Resultado(texto)
    if not _disponivel():
        return Recusa(
            "O formatador de SQL depende do pacote 'sqlparse', que nao esta' "
            "instalado.",
            "Instale com: pip install sqlparse")

    import sqlparse

    unidade = unidade_de_indentacao(opcoes)
    try:
        novo = sqlparse.format(
            texto,
            reindent=True,
            # As palavras reservadas em MAIUSCULAS: e' a convencao universal de
            # SQL, e e' o que distingue comando de nome de coluna na leitura.
            keyword_case="upper",
            identifier_case=None,          # nao mexer no nome das colunas
            strip_comments=False,          # comentario e' conteudo
            use_space_around_operators=True,
            indent_width=len(unidade.expandtabs(4)),
            indent_tabs=unidade.startswith("\t"),
            comma_first=False,
            wrap_after=100)
    except Exception as exc:            # noqa: BLE001 - biblioteca de terceiros
        log.warning("sqlparse falhou: %s", exc)
        return Recusa(f"Nao foi possivel formatar este SQL ({exc}).",
                      "O arquivo nao foi alterado.")

    avisos = ["As palavras reservadas foram passadas para MAIUSCULAS."]
    return Resultado(novo.rstrip() + "\n", avisos)


def compactar(texto: str, opcoes: dict) -> Saida:
    """Uma linha por comando, sem indentacao."""
    if not _disponivel():
        return Recusa("O 'sqlparse' nao esta' instalado.",
                      "Instale com: pip install sqlparse")
    import sqlparse

    try:
        novo = sqlparse.format(texto, strip_whitespace=True, reindent=False,
                               keyword_case="upper", strip_comments=False)
    except Exception as exc:            # noqa: BLE001
        return Recusa(f"Nao foi possivel compactar este SQL ({exc}).")
    # Um comando por linha: "tudo numa linha so'" seria ilegivel num arquivo de
    # migracao com 40 comandos.
    return Resultado("\n".join(
        p.strip() for p in novo.split(";") if p.strip()).replace("\n", ";\n")
        + ";\n" if novo.strip() else "")


def validar(texto: str) -> ErroDeSintaxe | None:
    """Checagem ESTRUTURAL, nao sintatica.

    Nao existe "SQL invalido" em geral: cada banco tem a sua gramatica, e o
    `sqlparse` nao valida. Prometer validacao completa seria enganar o usuario --
    o que se pode afirmar com certeza e' parentese e apostrofo desbalanceados, que
    e' a causa da grande maioria dos erros de digitacao em SQL.
    """
    if not texto.strip():
        return None

    linha = 1
    coluna = 1
    profundidade = 0
    abertura: tuple[int, int] | None = None
    i = 0
    dentro_de_texto = False
    inicio_do_texto: tuple[int, int] | None = None

    while i < len(texto):
        ch = texto[i]
        if ch == "\n":
            linha += 1
            coluna = 0
        elif dentro_de_texto:
            if ch == "'":
                # Aspa DOBRADA e' o escape do SQL, e nao a barra invertida.
                if i + 1 < len(texto) and texto[i + 1] == "'":
                    i += 1
                    coluna += 1
                else:
                    dentro_de_texto = False
                    inicio_do_texto = None
        elif ch == "'":
            dentro_de_texto = True
            inicio_do_texto = (linha, coluna)
        elif ch == "-" and texto[i:i + 2] == "--":
            salto = texto.find("\n", i)
            if salto < 0:
                break
            i = salto
            continue
        elif ch == "/" and texto[i:i + 2] == "/*":
            fim = texto.find("*/", i)
            if fim < 0:
                return ErroDeSintaxe(linha, coluna,
                                     "comentario /* nao foi fechado", i, "")
            trecho = texto[i:fim]
            linha += trecho.count("\n")
            i = fim + 2
            coluna = 1
            continue
        elif ch == "(":
            profundidade += 1
            if abertura is None:
                abertura = (linha, coluna)
        elif ch == ")":
            profundidade -= 1
            if profundidade < 0:
                return ErroDeSintaxe(
                    linha, coluna, "parentese ')' sem abertura correspondente",
                    i, texto.split("\n")[linha - 1] if linha <= len(
                        texto.split("\n")) else "")
            if profundidade == 0:
                abertura = None
        i += 1
        coluna += 1

    if dentro_de_texto and inicio_do_texto is not None:
        l, c = inicio_do_texto
        return ErroDeSintaxe(l, c, "apostrofo de string nao foi fechado", None,
                             "")
    if profundidade > 0 and abertura is not None:
        l, c = abertura
        return ErroDeSintaxe(
            l, c, f"parentese '(' sem fechamento ({profundidade} aberto(s))",
            None, "")
    return None


class FormatadorSql:
    nome = "SQL"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return formatar(texto, opcoes)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return compactar(texto, opcoes)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorSql()
