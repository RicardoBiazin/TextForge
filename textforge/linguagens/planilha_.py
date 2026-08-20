"""Planilha (.xlsx, .xlsm) -- requisito 6, item Planilha.

Este provedor e' quase todo declaracao. Ele existe por dois motivos, e o realce
nao e' nenhum dos dois:

1. `visualizador_preferido()` devolve "planilha" -- e' assim que o formato pede a
   grade sem que o gerenciador de abas conheca .xlsx.
2. A barra de status passa a dizer "Planilha" em vez de "Texto".

`regras()` devolve o conjunto VAZIO porque nao existe texto para realcar: um
.xlsx e' um pacote ZIP, o `QTextDocument` da aba fica vazio, e o conteudo vive na
`Pasta` (ver `textforge/planilha/`). O realcador chega a ser criado -- toda aba
tem um --, e um conjunto vazio e' o que o faz nao pintar nada em vez de estourar.

E nao ha' `detectar_por_conteudo`: a amostra que o registro passa e' TEXTO
decodificado, e um pacote ZIP nunca chega ate' ali. A deteccao de verdade e'
feita nos bytes, por `planilha/deteccao.parece_planilha`, antes de o documento
tentar decodificar qualquer coisa.
"""

from __future__ import annotations

from textforge.linguagens.base import ProvedorDeLinguagem, RegraDeDobra
from textforge.realce.regras import Contexto, RegrasDeRealce


class ProvedorPlanilha(ProvedorDeLinguagem):
    nome = "Planilha"
    extensoes = (".xlsx", ".xlsm")
    # Nenhum comentario e nenhum par para fechar: nao ha' o que comentar numa
    # celula, e digitar aspas numa celula e' digitar aspas, nao abrir um par.
    comentario_de_linha = None
    pares_para_fechar = ()

    def regras(self, tema) -> RegrasDeRealce:
        return RegrasDeRealce(inicial="raiz",
                              contextos={"raiz": Contexto("raiz", ())})

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="nenhum")

    def visualizador_preferido(self) -> str:
        return "planilha"


PROVEDORES = (ProvedorPlanilha(),)
