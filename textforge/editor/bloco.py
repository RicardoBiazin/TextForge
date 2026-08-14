"""Selecao em BLOCO (retangular / por coluna) no editor.

Alt+arrastar marca um retangulo; digitar altera todas as linhas na mesma coluna;
Ctrl+C copia so' o retangulo. E' o "modo coluna" do Notepad++, e o uso real e' um
arquivo de largura fixa ou uma lista onde se quer mexer numa coluna so'.

O `QPlainTextEdit` nao tem nada disso, entao a selecao mora AQUI, como quatro
numeros (linha e coluna da ancora, linha e coluna do cursor), e nao no QTextCursor.
O cursor do Qt continua existindo e marcando a posicao "de verdade"; o retangulo e'
desenhado por cima com `ExtraSelection`, uma por linha.

**AS COLUNAS SAO VISUAIS, e nao indices de caractere.** Num arquivo indentado com
TAB, um TAB ocupa ate' a proxima parada de tabulacao; contar caracteres produziria
um retangulo torto na tela -- justamente no tipo de arquivo em que a selecao por
coluna serve para alguma coisa. `_coluna_visual` e `_posicao_da_coluna` fazem as
duas conversoes, usando a mesma `Indentacao` que o resto do editor.

CONSEQUENCIA DECLARADA: um TAB que COMECA antes da coluna alvo e a atravessa fica de
fora do retangulo -- ele pertence ao lado esquerdo. A regra vale igual para o inicio
e para o fim, entao os dois lados concordam e o TAB nunca e' partido. Parti-lo
exigiria troca-lo por espacos, ou seja, alterar bytes que o usuario nao pediu para
alterar (requisito 38).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit


@dataclass
class Retangulo:
    """A selecao em bloco, em linhas e COLUNAS VISUAIS, base zero."""

    linha_ancora: int = 0
    coluna_ancora: int = 0
    linha_cursor: int = 0
    coluna_cursor: int = 0

    @property
    def primeira_linha(self) -> int:
        return min(self.linha_ancora, self.linha_cursor)

    @property
    def ultima_linha(self) -> int:
        return max(self.linha_ancora, self.linha_cursor)

    @property
    def coluna_inicial(self) -> int:
        return min(self.coluna_ancora, self.coluna_cursor)

    @property
    def coluna_final(self) -> int:
        return max(self.coluna_ancora, self.coluna_cursor)

    @property
    def linhas(self) -> int:
        return self.ultima_linha - self.primeira_linha + 1

    @property
    def largura(self) -> int:
        return self.coluna_final - self.coluna_inicial

    @property
    def vazio(self) -> bool:
        """Largura zero. NAO e' inutil: um retangulo de largura zero e' um
        cursor por linha, e e' assim que se digita um prefixo em N linhas."""
        return self.largura == 0

    def descrever(self) -> str:
        return (f"bloco {self.linhas}x{self.largura} "
                f"(col {self.coluna_inicial + 1}-{self.coluna_final + 1})")


class SelecaoEmBloco:
    """Mantem e aplica a selecao retangular de UM editor."""

    CAMADA = "bloco"

    def __init__(self, editor) -> None:      # EditorDeTexto
        self._editor = editor
        self.retangulo: Retangulo | None = None
        self._arrastando = False

    # ==================================================================
    # Conversao entre coluna VISUAL e posicao no bloco
    # ==================================================================

    def _largura_do_tab(self) -> int:
        return max(1, self._editor.indentacao.largura)

    def coluna_visual(self, texto: str, posicao: int) -> int:
        """Coluna na tela do caractere `posicao` de `texto`."""
        largura = self._largura_do_tab()
        coluna = 0
        for ch in texto[:posicao]:
            coluna += largura - (coluna % largura) if ch == "\t" else 1
        return coluna

    def posicao_da_coluna(self, texto: str, coluna: int) -> int:
        """Indice do PRIMEIRO caractere que comeca na coluna visual `coluna` ou
        depois dela.

        Essa e' a regra exata, e ela decide o caso do TAB: um TAB que COMECA antes
        da coluna alvo e a atravessa fica de fora -- ele pertence ao lado
        esquerdo. Vale igual para o inicio e para o fim do retangulo, entao os dois
        lados concordam e o TAB nunca e' partido ao meio.

        Alem do fim da linha, devolve o comprimento dela: o retangulo pode passar
        do fim, e essas linhas simplesmente contribuem com vazio.
        """
        largura = self._largura_do_tab()
        atual = 0
        for i, ch in enumerate(texto):
            if atual >= coluna:
                return i
            atual += largura - (atual % largura) if ch == "\t" else 1
        return len(texto)

    # ==================================================================
    # Definir a selecao
    # ==================================================================

    @property
    def ativa(self) -> bool:
        return self.retangulo is not None

    def comecar(self, linha: int, coluna: int) -> None:
        self.retangulo = Retangulo(linha, coluna, linha, coluna)
        self._arrastando = True
        self._pintar()

    def estender(self, linha: int, coluna: int) -> None:
        if self.retangulo is None:
            return
        self.retangulo.linha_cursor = max(0, linha)
        self.retangulo.coluna_cursor = max(0, coluna)
        self._pintar()

    def terminar(self) -> None:
        self._arrastando = False

    @property
    def arrastando(self) -> bool:
        return self._arrastando

    def limpar(self) -> None:
        if self.retangulo is None:
            return
        self.retangulo = None
        self._arrastando = False
        self._editor.selecoes.limpar(self.CAMADA)

    def definir(self, linha_ancora: int, coluna_ancora: int,
                linha_cursor: int, coluna_cursor: int) -> None:
        """Define o retangulo direto. Usado pelo teclado e pelos testes."""
        self.retangulo = Retangulo(linha_ancora, coluna_ancora,
                                   linha_cursor, coluna_cursor)
        self._pintar()

    def da_posicao(self, x: int, y: int) -> tuple[int, int]:
        """(linha, coluna visual) do ponto do viewport."""
        cursor = self._editor.cursorForPosition(_ponto(x, y))
        linha = cursor.blockNumber()
        texto = cursor.block().text()
        coluna = self.coluna_visual(texto, cursor.positionInBlock())
        # Alem do fim da linha o `cursorForPosition` gruda no ultimo caractere.
        # Para a selecao em bloco isso e' errado: arrastar para a direita numa
        # linha curta tem de continuar avancando a coluna, senao o retangulo
        # encolhe ao passar por uma linha vazia.
        largura_ch = self._editor.largura_de_caractere()
        if largura_ch > 0:
            do_ponto = int((x - self._editor.deslocamento_do_texto())
                           / largura_ch)
            coluna = max(coluna, max(0, do_ponto))
        return linha, coluna

    # ==================================================================
    # Conteudo
    # ==================================================================

    def _faixas(self) -> list[tuple[int, int, int]]:
        """(numero do bloco, posicao inicial, posicao final) por linha."""
        if self.retangulo is None:
            return []
        doc = self._editor.document()
        saida = []
        for numero in range(self.retangulo.primeira_linha,
                            self.retangulo.ultima_linha + 1):
            bloco = doc.findBlockByNumber(numero)
            if not bloco.isValid():
                continue
            texto = bloco.text()
            inicio = self.posicao_da_coluna(texto, self.retangulo.coluna_inicial)
            fim = self.posicao_da_coluna(texto, self.retangulo.coluna_final)
            saida.append((numero, inicio, max(inicio, fim)))
        return saida

    def texto(self) -> str:
        """O conteudo do retangulo, uma linha por linha.

        Linha curta demais contribui com string vazia, e NAO e' pulada: manter a
        contagem de linhas e' o que permite colar o bloco em outro lugar e ele cair
        nas linhas certas.
        """
        doc = self._editor.document()
        partes = []
        for numero, inicio, fim in self._faixas():
            partes.append(doc.findBlockByNumber(numero).text()[inicio:fim])
        return "\n".join(partes)

    # ==================================================================
    # Edicao
    # ==================================================================

    def substituir(self, novo: str) -> None:
        """Troca o conteudo do retangulo por `novo` em TODAS as linhas.

        Tudo dentro de um `beginEditBlock`: um Ctrl+Z desfaz a alteracao das N
        linhas de uma vez, e nao uma linha por vez.

        As linhas sao percorridas DE BAIXO PARA CIMA. Editar de cima para baixo
        mudaria o comprimento das linhas de cima e deslocaria as posicoes ja'
        calculadas das de baixo -- o classico defeito de editar uma lista enquanto
        se itera sobre ela.
        """
        if self.retangulo is None:
            return
        doc = self._editor.document()
        faixas = self._faixas()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        try:
            for numero, inicio, fim in reversed(faixas):
                bloco = doc.findBlockByNumber(numero)
                if not bloco.isValid():
                    continue
                # Linha mais curta que a coluna inicial: completa com espacos
                # ate' la', senao o texto novo grudaria no fim da linha e sairia
                # de coluna. Nao ha' como inserir "na coluna 40" de uma linha que
                # tem 10 caracteres sem preencher o meio.
                texto = bloco.text()
                falta = self.retangulo.coluna_inicial - self.coluna_visual(
                    texto, len(texto))
                enchimento = " " * falta if falta > 0 and novo else ""
                cursor.setPosition(bloco.position() + inicio)
                if fim > inicio:
                    cursor.setPosition(bloco.position() + fim,
                                       QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(enchimento + novo)
        finally:
            cursor.endEditBlock()

        # Depois de editar, o retangulo vira uma coluna so' -- do outro lado do
        # texto inserido, como acontece ao digitar sobre uma selecao normal.
        coluna = self.retangulo.coluna_inicial + len(novo)
        self.definir(self.retangulo.primeira_linha, coluna,
                     self.retangulo.ultima_linha, coluna)

    def substituir_por_linha(self, novas: list[str]) -> None:
        """Um texto DIFERENTE para cada linha do retangulo -- o "colar em coluna".

        Mesmas regras de `substituir`: tudo num unico passo de desfazer, de baixo
        para cima, e linha curta completada com espacos ate' a coluna.
        """
        if self.retangulo is None:
            return
        doc = self._editor.document()
        faixas = self._faixas()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        try:
            for indice in range(len(faixas) - 1, -1, -1):
                numero, inicio, fim = faixas[indice]
                novo = novas[indice] if indice < len(novas) else ""
                bloco = doc.findBlockByNumber(numero)
                if not bloco.isValid():
                    continue
                texto = bloco.text()
                falta = self.retangulo.coluna_inicial - self.coluna_visual(
                    texto, len(texto))
                enchimento = " " * falta if falta > 0 and novo else ""
                cursor.setPosition(bloco.position() + inicio)
                if fim > inicio:
                    cursor.setPosition(bloco.position() + fim,
                                       QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(enchimento + novo)
        finally:
            cursor.endEditBlock()
        self.limpar()

    def apagar(self) -> None:
        if self.retangulo is None:
            return
        if self.retangulo.vazio:
            # Largura zero: Backspace apaga o caractere ANTES da coluna, em cada
            # linha. Sem isto, Backspace num "cursor por linha" nao faria nada.
            if self.retangulo.coluna_inicial == 0:
                return
            self.definir(self.retangulo.primeira_linha,
                         self.retangulo.coluna_inicial - 1,
                         self.retangulo.ultima_linha,
                         self.retangulo.coluna_inicial)
        self.substituir("")

    # ==================================================================
    # Desenho
    # ==================================================================

    def _pintar(self) -> None:
        doc = self._editor.document()
        tema = self._editor.tema
        selecoes: list[QTextEdit.ExtraSelection] = []
        for numero, inicio, fim in self._faixas():
            bloco = doc.findBlockByNumber(numero)
            selecao = QTextEdit.ExtraSelection()
            selecao.format.setBackground(tema.cor("editor.selecao"))
            selecao.format.setForeground(tema.cor("editor.texto_da_selecao"))
            cursor = QTextCursor(doc)
            cursor.setPosition(bloco.position() + inicio)
            # Largura zero ainda produz uma marca de 1 caractere, para o usuario
            # ver ONDE os cursores estao antes de digitar.
            alvo = fim if fim > inicio else min(inicio + 1, len(bloco.text()))
            cursor.setPosition(bloco.position() + alvo,
                               QTextCursor.MoveMode.KeepAnchor)
            selecao.cursor = cursor
            selecoes.append(selecao)
        self._editor.selecoes.definir(self.CAMADA, selecoes)


def _ponto(x: int, y: int):
    from PySide6.QtCore import QPoint
    return QPoint(int(x), int(y))
