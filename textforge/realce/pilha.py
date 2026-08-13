"""Internamento da pilha de contextos.

`QSyntaxHighlighter.setCurrentBlockState()` guarda UM inteiro por bloco. Um
contexto unico caberia; uma PILHA nao:

    HTML  ->  <script>  ->  template string  ->  ${ expressao }

sao quatro niveis, e cada um precisa saber ao que voltar. Nao ha' como empacotar
isso num int de forma geral.

A solucao (a mesma do KSyntaxHighlighting do KDE) e' internar: cada pilha distinta
recebe um numero, e o numero volta a ser pilha na leitura. O ganho colateral e'
importante: duas pilhas IGUAIS recebem o MESMO numero, e e' isso que faz o
`QSyntaxHighlighter` parar de reprocessar o resto do documento -- ele compara o
estado novo com o antigo e para quando coincidem. Um contador incremental
funcionaria como identificador, mas o realce nunca pararia de propagar.

O internador e' POR PINTOR, nunca global: a tabela morre com o documento, e os
numeros de dois documentos diferentes nunca se cruzam.
"""

from __future__ import annotations

Pilha = tuple[str, ...]


class Internador:
    """Mapeia pilha de contextos <-> int, nos dois sentidos."""

    def __init__(self) -> None:
        # O 0 e' a pilha vazia. O bloco 0 de um documento tem estado anterior -1,
        # e `pilha_de(-1)` devolve () -- ver o teste.
        self._para_id: dict[Pilha, int] = {(): 0}
        self._para_pilha: list[Pilha] = [()]

    def id_de(self, pilha: Pilha) -> int:
        ident = self._para_id.get(pilha)
        if ident is None:
            ident = len(self._para_pilha)
            self._para_id[pilha] = ident
            self._para_pilha.append(pilha)
        return ident

    def pilha_de(self, ident: int) -> Pilha:
        """Pilha de um id. Pilha vazia para id desconhecido ou negativo.

        Devolver () em vez de levantar e' deliberado: isto e' chamado de dentro do
        `highlightBlock`, e o Qt passa -1 no primeiro bloco. Uma excecao ali
        aconteceria no meio do desenho da tela.
        """
        if 0 <= ident < len(self._para_pilha):
            return self._para_pilha[ident]
        return ()

    def __len__(self) -> int:
        return len(self._para_pilha)
