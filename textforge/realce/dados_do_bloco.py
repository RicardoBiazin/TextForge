"""`DadosDoBloco`: o que o realcador descobre e os outros recursos consomem.

Este e' o seam mais valioso da arquitetura. O `QSyntaxHighlighter` ja' percorre
cada bloco visivel para pintar; enquanto esta' la', ele grava aqui o nivel de
indentacao/dobra, os tokens que pintou e os pares de delimitadores. Assim:

    code folding      le' `nivel_de_dobra` e `abre_dobra`
    minimapa          le' `tokens` (2 px por linha, sem renderizar texto)
    painel Estrutura  le' `tokens` para achar classes e funcoes
    pareamento        le' `pares`
    guias de indent.  le' `nivel_de_dobra`

Nenhum deles faz uma segunda passada de parsing. Sem isto, cada recurso teria o
proprio percurso do documento, e um arquivo grande pagaria cinco vezes o mesmo
trabalho.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QTextBlockUserData


@dataclass
class Token:
    """Um trecho pintado. `inicio` e' relativo ao bloco."""

    inicio: int
    tamanho: int
    papel: str


@dataclass
class Par:
    """Um delimitador de abertura ou fechamento, para o pareamento."""

    posicao: int          # relativa ao bloco
    caractere: str
    abre: bool


class DadosDoBloco(QTextBlockUserData):
    """Anexado a cada bloco por `setCurrentBlockUserData`.

    Herda de QTextBlockUserData porque o Qt exige esse tipo -- e' ele quem cuida
    do ciclo de vida (o dado morre com o bloco). Nao usar dataclass aqui: o
    shiboken precisa do construtor do tipo base.
    """

    __slots__ = ("nivel_de_dobra", "abre_dobra", "dobrado", "tokens", "pares",
                 "pilha_ao_terminar", "vazio")

    def __init__(self) -> None:
        super().__init__()
        # Nivel de indentacao em UNIDADES da indentacao do arquivo. E' o que o
        # folding por indentacao usa, e o que as guias desenham.
        self.nivel_de_dobra: int = 0
        # True quando este bloco ABRE uma regiao dobravel (termina em ":" no
        # Python, em "{" no C, numa tag no XML).
        self.abre_dobra: bool = False
        self.dobrado: bool = False
        self.tokens: list[Token] = []
        self.pares: list[Par] = []
        # Pilha de contextos ao terminar o bloco, para diagnostico e teste.
        self.pilha_ao_terminar: tuple[str, ...] = ()
        # Linha em branco (ou so' com espaco). O folding por indentacao precisa
        # saber, porque uma linha em branco NAO encerra uma regiao.
        self.vazio: bool = False

    def papel_em(self, coluna: int) -> str:
        """Qual papel pintou esta coluna. Usado pelo autocomplete e pelos testes.

        Serve para responder "o cursor esta' dentro de uma string ou de um
        comentario?" -- que e' o que evita o autocomplete sugerir palavra-chave no
        meio de um texto literal.
        """
        for token in self.tokens:
            if token.inicio <= coluna < token.inicio + token.tamanho:
                return token.papel
        return ""
