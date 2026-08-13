"""Provedores de linguagem (requisito 36).

Este `__init__` e' o UNICO lugar a tocar para acrescentar uma linguagem embutida:
importe o modulo e registre a instancia. O nucleo nunca importa um provedor
concreto -- ele pergunta ao `registro`.

Um plugin (ou um arquivo .json em %APPDATA%\\TextForge\\linguagens) acrescenta uma
linguagem sem tocar em nada aqui.
"""

from __future__ import annotations

from textforge.linguagens.registro import REGISTRO, registrar


def carregar_embutidos() -> int:
    """Registra os provedores que vem com o programa. Devolve quantos.

    Importacao tardia, dentro da funcao, por dois motivos: um erro num provedor
    nao impede o programa de abrir, e o custo de compilar os regexes de 15
    linguagens nao entra no tempo de partida quando nenhuma delas e' usada.
    """
    from textforge.linguagens import (ini_, json_, markdown, python_, texto,
                                      xml_)

    # A ordem nao importa para a resolucao (ela e' por extensao e por prioridade),
    # mas importa para o menu Linguagem, que segue esta lista.
    modulos = (texto, python_, json_, xml_, ini_, markdown)
    quantos = 0
    for modulo in modulos:
        for provedor in modulo.PROVEDORES:
            registrar(provedor)
            quantos += 1
    return quantos


__all__ = ["REGISTRO", "registrar", "carregar_embutidos"]
