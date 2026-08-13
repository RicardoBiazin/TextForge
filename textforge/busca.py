"""Pesquisa e substituicao (requisito 8).

Duas camadas, deliberadamente separadas:

  `Criterio`      o que o usuario pediu -- texto, diferenciar maiusculas, palavra
                  inteira, expressao regular. Compila para um `re.Pattern`. Nao
                  conhece Qt nem documento.
  as funcoes      operam sobre `FonteDeTexto` (contar, listar) ou sobre um
                  `QTextDocument` (achar o proximo, substituir). Sao duas coisas
                  diferentes: contar nao precisa de cursor, substituir precisa.

DECISAO CENTRAL, e o que o `teste_busca.py` protege: as posicoes usadas aqui sao
OFFSETS DE CARACTERE compativeis com `QTextCursor.position()`. E' isso que permite
achar com `re.finditer` sobre `documento.texto()` e posicionar o cursor direto no
resultado, sem recalcular linha e coluna. Funciona porque `Documento.texto()` usa
`toRawText()`, que conta como o cursor conta -- se algum dia alguem trocar por
`toPlainText()`, os offsets passam a divergir em qualquer arquivo com nbsp.

`substituir_todos` roda dentro de UM `beginEditBlock`, e aplica as substituicoes
DE TRAS PARA A FRENTE: assim o offset de cada casamento continua valido enquanto os
anteriores nao foram tocados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from textforge import log_interno
from textforge.fonte import Achado, FonteDeTexto

log = log_interno.obter(__name__)

# Teto para "listar todas as ocorrencias". Realcar 200 mil ocorrencias criaria 200
# mil ExtraSelection e a rolagem morreria; o contador continua exato porque
# `contar` nao guarda os achados.
LIMITE_DE_OCORRENCIAS = 20_000


class CriterioInvalido(ValueError):
    """Expressao regular malformada. A mensagem e' para o usuario ver."""


@dataclass(frozen=True)
class Criterio:
    texto: str = ""
    diferenciar_maiusculas: bool = False
    palavra_inteira: bool = False
    expressao_regular: bool = False

    @property
    def vazio(self) -> bool:
        return not self.texto

    def compilar(self) -> re.Pattern[str]:
        """Monta o padrao. Levanta `CriterioInvalido` com mensagem legivel."""
        if not self.texto:
            raise CriterioInvalido("nada a procurar")

        fonte = self.texto if self.expressao_regular else re.escape(self.texto)
        if self.palavra_inteira:
            # `\b` so' funciona quando a borda e' realmente de palavra. Para um
            # termo que comeca ou termina com pontuacao ("--forca", "x="), o `\b`
            # no lugar errado impediria QUALQUER casamento -- o usuario procuraria
            # e nao acharia nada, sem entender por que. Por isso a ancora e' posta
            # so' no lado que tem caractere de palavra.
            inicio = r"\b" if self.texto[:1].isalnum() or self.texto[:1] == "_" else ""
            fim = r"\b" if self.texto[-1:].isalnum() or self.texto[-1:] == "_" else ""
            fonte = f"{inicio}(?:{fonte}){fim}"

        bandeiras = 0 if self.diferenciar_maiusculas else re.IGNORECASE
        try:
            return re.compile(fonte, bandeiras)
        except re.error as exc:
            raise CriterioInvalido(
                f"expressao regular invalida: {exc.msg}"
                + (f" (posicao {exc.pos})" if exc.pos is not None else "")
            ) from exc

    def descricao(self) -> str:
        """Resumo para a barra de status e para o painel de resultados."""
        partes = [f'"{self.texto}"']
        if self.expressao_regular:
            partes.append("regex")
        if self.diferenciar_maiusculas:
            partes.append("Aa")
        if self.palavra_inteira:
            partes.append("palavra inteira")
        return " · ".join(partes)


# ---------------------------------------------------------------------------
# Sobre FonteDeTexto: contar e listar
# ---------------------------------------------------------------------------


def contar(fonte: FonteDeTexto, criterio: Criterio,
           cancelar=None) -> int:
    """Quantas ocorrencias existem. Nao guarda os achados, entao nao tem teto."""
    padrao = criterio.compilar()
    total = 0
    for _ in fonte.buscar(padrao, 0, cancelar):
        total += 1
    return total


def listar(fonte: FonteDeTexto, criterio: Criterio,
           limite: int = LIMITE_DE_OCORRENCIAS,
           cancelar=None) -> tuple[list[Achado], bool]:
    """(achados, houve_corte). O corte protege o realce de todas as ocorrencias."""
    padrao = criterio.compilar()
    achados: list[Achado] = []
    for achado in fonte.buscar(padrao, 0, cancelar):
        achados.append(achado)
        if len(achados) >= limite:
            return achados, True
    return achados, False


# ---------------------------------------------------------------------------
# Sobre QTextDocument: achar o proximo e substituir
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Faixa:
    """Um casamento no documento, em offsets de caractere do QTextCursor."""

    inicio: int
    fim: int
    grupos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tamanho(self) -> int:
        return self.fim - self.inicio


def _texto_do_documento(documento) -> str:
    """O texto como o CURSOR conta.

    `toRawText()` e nao `toPlainText()`: o segundo troca nbsp por espaco e
    U+2028/U+2029 por "\\n", o que ALTERA o numero de caracteres em relacao ao que
    `QTextCursor.position()` usa -- e todo offset calculado aqui apontaria para o
    lugar errado num arquivo com nbsp.
    """
    from textforge import codificacao
    return documento.toRawText().replace(
        codificacao.SEPARADOR_DE_PARAGRAFO, "\n")


def todas_no_documento(documento, criterio: Criterio,
                       limite: int = LIMITE_DE_OCORRENCIAS
                       ) -> tuple[list[Faixa], bool]:
    padrao = criterio.compilar()
    texto = _texto_do_documento(documento)
    faixas: list[Faixa] = []
    for casamento in padrao.finditer(texto):
        faixas.append(Faixa(casamento.start(), casamento.end(),
                            casamento.groups()))
        if len(faixas) >= limite:
            return faixas, True
        if casamento.end() == casamento.start():
            # Padrao que casa vazio ("x*"): sem este cuidado o finditer avancaria
            # de um em um e a lista teria um item por caractere do arquivo.
            continue
    return faixas, False


def achar(documento, criterio: Criterio, de_posicao: int = 0, *,
          para_tras: bool = False, circular: bool = True,
          limite_da_selecao: tuple[int, int] | None = None) -> Faixa | None:
    """O proximo (ou anterior) casamento a partir de `de_posicao`.

    `circular` faz a busca recomecar do inicio (ou do fim) ao chegar na ponta --
    e' o comportamento que o F3 tem em todo editor.

    `limite_da_selecao` restringe a busca a uma faixa: e' o "somente na selecao".
    """
    padrao = criterio.compilar()
    texto = _texto_do_documento(documento)

    inicio_permitido, fim_permitido = 0, len(texto)
    if limite_da_selecao is not None:
        inicio_permitido, fim_permitido = limite_da_selecao
        texto_alvo = texto[inicio_permitido:fim_permitido]
        deslocamento = inicio_permitido
    else:
        texto_alvo = texto
        deslocamento = 0

    casamentos = [
        Faixa(c.start() + deslocamento, c.end() + deslocamento, c.groups())
        for c in padrao.finditer(texto_alvo)]
    if not casamentos:
        return None

    if para_tras:
        anteriores = [f for f in casamentos if f.fim < de_posicao
                      or (f.fim == de_posicao and f.inicio < de_posicao)]
        if anteriores:
            return anteriores[-1]
        return casamentos[-1] if circular else None

    seguintes = [f for f in casamentos if f.inicio >= de_posicao]
    if seguintes:
        return seguintes[0]
    return casamentos[0] if circular else None


def _expandir_substituicao(substituicao: str, criterio: Criterio) -> str:
    """Traduz `$1` para `\\1` no modo regex.

    O Notepad++ usa `\\1`, e muita gente vem de ferramenta que usa `$1`. Aceitar os
    dois evita a situacao em que o usuario substitui 500 ocorrencias por um literal
    "$1" -- um estrago silencioso e trabalhoso de desfazer.

    Fora do modo regex, nada e' interpretado: o texto vai literal.
    """
    if not criterio.expressao_regular:
        return substituicao
    return re.sub(r"(?<!\\)\$(\d+)", r"\\\1", substituicao)


def substituir_uma(documento, faixa: Faixa, substituicao: str,
                   criterio: Criterio) -> int:
    """Substitui UM casamento. Devolve o tamanho do texto inserido."""
    from PySide6.QtGui import QTextCursor

    texto = _expandir_substituicao(substituicao, criterio)
    if criterio.expressao_regular:
        padrao = criterio.compilar()
        original = _texto_do_documento(documento)[faixa.inicio:faixa.fim]
        casamento = padrao.fullmatch(original)
        if casamento is not None:
            try:
                texto = casamento.expand(texto)
            except (re.error, IndexError) as exc:
                raise CriterioInvalido(
                    f"a substituicao usa um grupo que a expressao nao tem: {exc}"
                ) from exc

    cursor = QTextCursor(documento)
    cursor.setPosition(faixa.inicio)
    cursor.setPosition(faixa.fim, QTextCursor.MoveMode.KeepAnchor)
    cursor.beginEditBlock()
    try:
        cursor.insertText(texto)
    finally:
        cursor.endEditBlock()
    return len(texto)


def substituir_todos(documento, criterio: Criterio, substituicao: str, *,
                     limite_da_selecao: tuple[int, int] | None = None) -> int:
    """Substitui todas as ocorrencias. Devolve quantas.

    Duas propriedades que o teste trava:

      * e' UM passo de desfazer, mesmo com 500 ocorrencias. Sem isso, desfazer
        exigiria 500 Ctrl+Z -- o que na pratica e' nao poder desfazer.
      * as substituicoes sao aplicadas DE TRAS PARA A FRENTE. Aplicando do inicio,
        a primeira troca deslocaria todas as posicoes seguintes e cada casamento
        seria escrito no lugar errado.
    """
    from PySide6.QtGui import QTextCursor

    padrao = criterio.compilar()
    texto = _texto_do_documento(documento)

    if limite_da_selecao is not None:
        inicio, fim = limite_da_selecao
        alvo, deslocamento = texto[inicio:fim], inicio
    else:
        alvo, deslocamento = texto, 0

    modelo = _expandir_substituicao(substituicao, criterio)
    trocas: list[tuple[int, int, str]] = []
    for casamento in padrao.finditer(alvo):
        if criterio.expressao_regular:
            try:
                novo = casamento.expand(modelo)
            except (re.error, IndexError) as exc:
                raise CriterioInvalido(
                    f"a substituicao usa um grupo que a expressao nao tem: {exc}"
                ) from exc
        else:
            novo = modelo
        trocas.append((casamento.start() + deslocamento,
                       casamento.end() + deslocamento, novo))

    if not trocas:
        return 0

    cursor = QTextCursor(documento)
    cursor.beginEditBlock()
    try:
        for comeco, termino, novo in reversed(trocas):
            cursor.setPosition(comeco)
            cursor.setPosition(termino, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(novo)
    finally:
        cursor.endEditBlock()
    log.info("substituidas %d ocorrencias", len(trocas))
    return len(trocas)


def ordinal(faixas: list[Faixa], posicao: int) -> int:
    """Qual ocorrencia (base 1) comeca em `posicao`. Zero se nenhuma.

    E' o "3 de 17" da barra de busca.
    """
    for i, faixa in enumerate(faixas, start=1):
        if faixa.inicio == posicao:
            return i
    return 0
