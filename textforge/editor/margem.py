"""A margem a' esquerda do editor: numeros de linha, marcadores e dobras.

E' um `QWidget` comum posicionado sobre a area de `viewport margins` do
`QPlainTextEdit`. O desenho e' feito aqui, mas quem sabe quais blocos estao
visiveis e' o editor -- por isso o `paintEvent` delega a ele. E' a estrutura do
exemplo oficial "Code Editor" do Qt, com as colunas extras que o TextForge
precisa.

Colunas, da esquerda para a direita:

    [marcador] [numero da linha] [alteracao] [dobra]

A coluna de dobra e a de alteracao ja' existem em largura, mesmo antes de a
etapa que as usa chegar: reservar o espaco agora evita que o texto do editor
"pule" horizontalmente quando o recurso for ligado.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QMouseEvent, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

# Larguras fixas, em pixels, das colunas que nao dependem do numero de digitos.
LARGURA_DO_MARCADOR = 14
LARGURA_DA_ALTERACAO = 4
LARGURA_DA_DOBRA = 14
FOLGA = 8


class MargemDeLinhas(QWidget):
    def __init__(self, editor) -> None:      # EditorDeTexto
        super().__init__(editor)
        self._editor = editor
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.mostrar_dobras = False          # ligado na etapa de folding

    # -- geometria ---------------------------------------------------------

    def largura_dos_numeros(self) -> int:
        """Largura do campo numerico, em pixels, pelo numero de digitos.

        Recalculada a cada mudanca de contagem de blocos: um arquivo que passa
        de 99 para 100 linhas precisa de mais um digito, e sem isto o numero
        ficaria cortado.
        """
        digitos = max(2, len(str(max(1, self._editor.blockCount()))))
        return self._editor.fontMetrics().horizontalAdvance("9") * digitos

    def sizeHint(self) -> QSize:             # noqa: N802 - Qt
        return QSize(self.largura_total(), 0)

    def largura_total(self) -> int:
        total = (LARGURA_DO_MARCADOR + self.largura_dos_numeros()
                 + LARGURA_DA_ALTERACAO + FOLGA)
        if self.mostrar_dobras:
            total += LARGURA_DA_DOBRA
        return total

    # -- eventos -----------------------------------------------------------

    def paintEvent(self, evento: QPaintEvent) -> None:      # noqa: N802 - Qt
        self._editor.pintar_margem(self, evento)

    def mousePressEvent(self, evento: QMouseEvent) -> None:  # noqa: N802 - Qt
        """Clique na margem seleciona a linha; na area do marcador, alterna-o."""
        if evento.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(evento)
            return
        bloco = self._editor.bloco_em_y(int(evento.position().y()))
        if bloco is None:
            return
        if evento.position().x() < LARGURA_DO_MARCADOR:
            self._editor.alternar_marcador(bloco.blockNumber())
        else:
            self._editor.selecionar_linha(bloco.blockNumber())

    def wheelEvent(self, evento: QWheelEvent) -> None:       # noqa: N802 - Qt
        # Rolar com o ponteiro sobre a margem tem de rolar o texto. Sem isto a
        # roda simplesmente nao faz nada quando o ponteiro esta' sobre os
        # numeros, o que parece um travamento.
        self._editor.wheelEvent(evento)
