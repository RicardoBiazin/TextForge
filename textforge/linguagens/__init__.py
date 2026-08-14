"""Provedores de linguagem (requisito 36).

Este `__init__` e' o UNICO lugar a tocar para acrescentar uma linguagem embutida:
importe o modulo e registre a instancia. O nucleo nunca importa um provedor
concreto -- ele pergunta ao `registro`.

Um plugin (ou um arquivo .json em %APPDATA%\\TextForge\\linguagens) acrescenta uma
linguagem sem tocar em nada aqui.
"""

from __future__ import annotations

from textforge.linguagens.registro import REGISTRO, registrar


def carregar_embutidos(*, forcar: bool = False) -> int:
    """Registra os provedores que vem com o programa. Devolve quantos.

    IDEMPOTENTE: chamar de novo nao faz nada. Sem essa guarda, cada chamada criaria
    instancias novas de provedor e descartaria o cache de regexes compilados delas
    -- e a funcao e' chamada tanto pelo `app.py` quanto pela janela, que garante a
    propria dependencia em vez de confiar em quem a construiu.

    Importacao tardia, dentro da funcao, por dois motivos: um erro num provedor nao
    impede o programa de abrir, e o custo de compilar os regexes de 22 linguagens
    nao entra no tempo de partida quando nenhuma delas e' usada.
    """
    if REGISTRO.embutidos_carregados and not forcar:
        return REGISTRO.embutidos_carregados
    from textforge.linguagens import (c_like, csv_, css, html, ini_, javascript,
                                      json_, markdown, php, python_, shell, sql,
                                      texto, xml_, yaml_)

    # A ordem nao importa para a resolucao (ela e' por extensao e por prioridade).
    # `php` importa `html`, que importa `javascript` e `css` -- a ordem aqui nao
    # afeta isso, mas a cadeia esta' anotada para ninguem tentar inverte-la.
    modulos = (texto, python_, json_, xml_, ini_, markdown, css, javascript,
               html, php, sql, yaml_, shell, c_like, csv_)
    quantos = 0
    for modulo in modulos:
        for provedor in modulo.PROVEDORES:
            registrar(provedor)
            quantos += 1
    REGISTRO.embutidos_carregados = quantos
    return quantos


__all__ = ["REGISTRO", "registrar", "carregar_embutidos"]
