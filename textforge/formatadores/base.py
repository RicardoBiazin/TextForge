"""Contrato comum dos formatadores.

Tres tipos de retorno, e a distincao importa:

  `Resultado`       deu certo. Traz o texto novo e uma lista de AVISOS -- coisas que
                    o usuario precisa saber sobre o que aconteceu, sem que a
                    operacao tenha falhado.
  `ErroDeSintaxe`   o documento nao e' valido. Traz linha, coluna, motivo e o
                    trecho, para o painel Problemas navegar ate' lá.
  `Recusa`          o documento e' valido, mas formatar PERDERIA informacao. Nao e'
                    erro do usuario nem falha nossa: e' um limite honesto.

A `Recusa` existe porque a alternativa e' pior. Um formatador de XML que engole uma
secao CDATA "porque a biblioteca nao preserva" entrega um arquivo diferente do que
o usuario abriu, e ele so' descobre quando o sistema que consome o arquivo quebra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Resultado:
    texto: str
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class ErroDeSintaxe:
    linha: int                     # BASE 1 -- vai direto para a tela
    coluna: int                    # BASE 1, em caracteres
    motivo: str
    # Offset absoluto em caracteres, quando conhecido. Com ele o cursor vai direto
    # ao ponto do erro, sem recalcular linha e coluna -- e' o caso do JSON, cujo
    # JSONDecodeError ja' traz `pos`.
    posicao: int | None = None
    contexto: str = ""             # a linha do erro, para o painel mostrar

    @property
    def ok(self) -> bool:
        return False

    def descrever(self) -> str:
        return f"Linha {self.linha}, coluna {self.coluna}: {self.motivo}"


@dataclass(frozen=True)
class Recusa:
    """O documento e' valido, mas formatar perderia informacao."""

    motivo: str
    sugestao: str = ""

    @property
    def ok(self) -> bool:
        return False

    def descrever(self) -> str:
        return self.motivo + (f" {self.sugestao}" if self.sugestao else "")


Saida = Resultado | ErroDeSintaxe | Recusa


class Formatador(Protocol):
    nome: str

    def formatar(self, texto: str, opcoes: dict) -> Saida: ...

    def compactar(self, texto: str, opcoes: dict) -> Saida: ...

    def validar(self, texto: str) -> ErroDeSintaxe | None: ...


def unidade_de_indentacao(opcoes: dict) -> str:
    """A unidade a usar, a partir das opcoes do documento.

    Respeita a indentacao DO ARQUIVO, que o `Documento` detectou. Formatar com 4
    espacos um arquivo indentado com 2 mudaria toda linha do arquivo -- um diff
    inteiro por causa de uma preferencia.
    """
    if not opcoes.get("usa_espacos", True):
        return "\t"
    return " " * max(1, int(opcoes.get("largura", 4)))
