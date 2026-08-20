"""O contrato de um visualizador alternativo.

Um visualizador e' uma view do MESMO documento numa forma diferente do texto: a
grade do CSV hoje, o hexadecimal e o visor de arquivo grande depois. Ele nao e' dono
do conteudo -- recebe o texto ao ser criado e devolve o texto quando o usuario
volta ao modo texto.

Duas exigencias, e sao as que valem para todos:

`para_texto()` SEM edicao devolve a entrada IDENTICA. Um visualizador que
reconstroi o conteudo a partir da propria estrutura interna altera o arquivo so' por
ter sido aberto -- e num arquivo de integracao isso e' destruicao silenciosa
(requisito 38). Quem nao consegue garantir isso declara `editavel = False` e a
janela nao escreve nada de volta.

`alterado` diz se ha' o que escrever de volta. E' o que permite alternar Texto <->
Tabela dez vezes sem sujar a pilha de desfazer nem marcar o documento como
modificado.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Visualizador(Protocol):
    """O que a janela espera de qualquer view alternativa."""

    #: False para os visualizadores somente-leitura (hex, arquivo grande).
    editavel: bool

    def para_texto(self) -> str:
        """O conteudo de volta como texto. Sem edicao, identico a' entrada."""

    @property
    def alterado(self) -> bool:
        """Houve edicao desde a criacao?"""

    def aplicar_tema(self, tema) -> None:
        """Pinta com as cores do tema, pedidas por NOME."""


@runtime_checkable
class VisualizadorBinario(Protocol):
    """A mesma ideia, para o conteudo que NAO e' texto.

    A planilha e' o primeiro caso: um `.xlsx` e' um pacote ZIP, e nao ha' texto
    para o qual voltar -- o `QTextDocument` da aba fica vazio e quem tem o
    conteudo e' o visualizador. Por isso `para_bytes()` no lugar de
    `para_texto()`, e por isso a aba nao oferece o alternador Texto <-> Tabela.

    A garantia central e' a MESMA, so' que um nivel abaixo: **sem edicao,
    `para_bytes()` devolve os bytes de entrada identicos** -- nem sequer
    recomprimidos. Um visualizador que remonta o arquivo a partir da propria
    estrutura interna perde tudo o que ele nao entendeu (num `.xlsx`: graficos,
    macros, tabelas dinamicas), e faz isso so' por ter sido aberto.
    """

    editavel: bool

    def para_bytes(self) -> bytes:
        """O conteudo de volta. Sem edicao, identico a' entrada."""

    @property
    def alterado(self) -> bool:
        """Houve edicao desde a criacao?"""

    def aplicar_tema(self, tema) -> None:
        """Pinta com as cores do tema, pedidas por NOME."""
