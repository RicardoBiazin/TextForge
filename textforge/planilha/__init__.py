"""Leitura e gravacao de planilhas .xlsx/.xlsm (requisito 6, item Planilha).

O pacote existe por causa de UMA decisao, e ela vale a pena estar escrita logo na
porta de entrada:

    **O TextForge nunca REGRAVA uma planilha. Ele PATCHEIA a que ja' existe.**

O caminho obvio -- `openpyxl.load_workbook()` seguido de `.save()` -- perde
graficos, tabelas dinamicas, slicers, comentarios encadeados e parte da formatacao
condicional, porque openpyxl nao sabe reconstruir o que nao sabe ler. Num editor
cuja regra central e' "o que entrou tem de sair igual" (requisito 38), isso e'
destruicao silenciosa da pior especie: o usuario corrige um numero num relatorio e
descobre semanas depois que os graficos sumiram.

Por isso a divisao de trabalho aqui e' rigida:

    leitor.py     openpyxl, SO' para ler valores. Ele e' bom nisso: resolve
                  sharedStrings, strings inline, formatos de data e formulas.
    gravador.py   zipfile + patch nos BYTES CRUS da aba editada. Nao importa
                  openpyxl. Toda parte do pacote OOXML que nenhuma celula tocou
                  e' copiada como veio.
    deteccao.py   o que este gravador NAO sabe patchear -- e que por isso abre em
                  somente leitura, em vez de gravar errado.

E' o mesmo contrato de `visualizadores/tabela_csv.py` -- registro nao editado sai
identico -- aplicado um nivel acima, no pacote ZIP.
"""

from __future__ import annotations

from textforge.planilha.pasta import (Celula, Folha, Pasta, TIPO_BOOL,
                                      TIPO_DATA, TIPO_ERRO, TIPO_FORMULA,
                                      TIPO_NUMERO, TIPO_TEXTO, TIPO_VAZIO)

__all__ = ["Celula", "Folha", "Pasta", "TIPO_BOOL", "TIPO_DATA", "TIPO_ERRO",
           "TIPO_FORMULA", "TIPO_NUMERO", "TIPO_TEXTO", "TIPO_VAZIO", "abrir"]


def abrir(caminho, cfg: dict | None = None) -> Pasta:
    """Le' a planilha. Atalho para `leitor.abrir`, que e' import tardio."""
    from textforge.planilha import leitor
    return leitor.abrir(caminho, cfg)
