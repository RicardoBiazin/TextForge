"""Texto sem formatacao: o fallback do registro.

Nao realca nada, de proposito. Um `.txt`, um `.log` ou um `.dat` nao tem sintaxe, e
inventar realce para eles produziria cor aleatoria sobre dados -- pior que nenhuma
cor. O que este provedor ainda entrega, e que importa:

  * comentario de linha "#" para o Ctrl+/ funcionar em arquivo de anotacao;
  * dobra por indentacao, que serve a qualquer texto indentado;
  * autocomplete pelas palavras do proprio arquivo (a etapa de autocomplete usa as
    palavras do documento, nao a lista do provedor).
"""

from __future__ import annotations

from textforge.linguagens.base import ProvedorDeLinguagem, RegraDeDobra
from textforge.realce.regras import Contexto, RegrasDeRealce


class ProvedorDeTexto(ProvedorDeLinguagem):
    nome = "Texto"
    extensoes = (".txt", ".text", ".log", ".dat", ".nfo", ".asc", ".me")
    nomes_de_arquivo = ("LICENSE", "LICENCA", "COPYING", "AUTHORS", "NOTICE",
                        "CHANGELOG", "TODO")
    comentario_de_linha = "#"

    def regras(self, tema) -> RegrasDeRealce:
        # Um contexto sem regras: o pintor devolve o bloco sem tocar em nada.
        return RegrasDeRealce(inicial="raiz",
                              contextos={"raiz": Contexto("raiz", ())})

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="indentacao")


PROVEDORES = (ProvedorDeTexto(),)
