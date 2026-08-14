"""CSV e TSV (requisito 6, item CSV).

Este provedor existe por tres motivos, e o realce e' o menor deles:

1. `visualizador_preferido()` devolve "tabela" -- e' assim que o CSV pede o modo
   grade sem que o gerenciador de abas conheca CSV.
2. A barra de status passa a dizer "CSV" em vez de "Texto".
3. O realce das ASPAS, que e' o unico realce util num CSV.

O que este provedor NAO faz, de proposito: colorir o delimitador. O delimitador so'
e' conhecido depois de analisar o arquivo (ver `analisadores/de_csv.py`), e as
regras de realce sao compiladas antes de haver arquivo. Colorir o conjunto todo
(`,;\\t|`) seria pior que nao colorir: num CSV brasileiro separado por ";", a
virgula DECIMAL de cada valor apareceria pintada como separador, sugerindo uma
divisao de coluna que nao existe.

O campo entre aspas, ao contrario, e' o que de fato da' problema num CSV -- e ele
pode atravessar linhas. Por isso e' um CONTEXTO, e nao um regex de uma linha: uma
aspa aberta na linha 3 e fechada na 5 pinta as tres, e o usuario ve na hora que o
arquivo tem um campo multi-linha (ou que esqueceu de fechar uma aspa, que e' o
mesmo desenho e o mesmo diagnostico).
"""

from __future__ import annotations

import re

from textforge.linguagens.base import ProvedorDeLinguagem, RegraDeDobra
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce


class ProvedorCsv(ProvedorDeLinguagem):
    nome = "CSV"
    extensoes = (".csv", ".tsv", ".psv")
    # Nenhum comentario: o "#" numa linha de CSV e' dado, e comentar uma linha
    # com Ctrl+/ corromperia o arquivo em vez de desativar a linha.
    comentario_de_linha = None
    # Nenhum par para fechar automaticamente. Digitar `"` num CSV e' abrir um
    # campo entre aspas -- o editor fechar sozinho inseriria um campo vazio no
    # meio do dado.
    pares_para_fechar = ()

    def regras(self, tema) -> RegrasDeRealce:
        return RegrasDeRealce(
            inicial="raiz",
            contextos={
                "raiz": Contexto("raiz", (
                    Regra(re.compile(r'"'), "texto_literal",
                          entrar_em="campo"),
                )),
                # `papel_padrao` pinta TODO o interior do campo, e nao so' as
                # aspas -- e' o que torna visivel onde o campo comeca e acaba.
                "campo": Contexto("campo", (
                    # A aspa DOBRADA e' o escape do CSV: tem de ser testada antes
                    # da aspa simples, senao `""` fecharia e reabriria o campo.
                    Regra(re.compile(r'""'), "escape"),
                    Regra(re.compile(r'"'), "texto_literal", sair=True),
                ), papel_padrao="texto_literal"),
            })

    def dobras(self) -> RegraDeDobra:
        # Um CSV nao tem hierarquia: dobrar por indentacao acharia regiao onde nao
        # ha' nenhuma, so' porque uma linha comeca com espaco dentro de um campo.
        return RegraDeDobra(modo="nenhum")

    def visualizador_preferido(self) -> str:
        return "tabela"

    def detectar_por_conteudo(self, amostra: str) -> int:
        """Consultado so' quando a extensao nao decidiu -- um `.dat` tabular.

        Delega ao analisador, que ja' pontua pela CONSISTENCIA das contagens. A
        nota fica em 60: passa do corte de 50 do registro, mas perde de qualquer
        provedor que reconheca a propria sintaxe com certeza.
        """
        from textforge.analisadores import de_csv
        try:
            return 60 if de_csv.parece_csv(amostra) else 0
        except Exception:                       # noqa: BLE001 - nunca derrubar
            return 0


PROVEDORES = (ProvedorCsv(),)
