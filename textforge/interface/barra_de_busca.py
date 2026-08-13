"""Barra de busca e substituicao, EMBUTIDA na janela.

Nao e' um dialogo modal, de proposito. Um dialogo de busca modal tapa o texto que o
usuario esta' procurando e impede editar enquanto esta' aberto -- e' o padrao antigo
do Bloco de Notas, e todo editor moderno abandonou.

O contador "3 de 17" e o realce de TODAS as ocorrencias sao atualizados enquanto o
usuario digita, com atraso curto: buscar a cada tecla num arquivo de 200 mil linhas
tornaria a digitacao na propria caixa de busca lenta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                               QToolButton, QVBoxLayout, QWidget)

from textforge.busca import Criterio

ATRASO_MS = 200


class BarraDeBusca(QWidget):
    """Barra de Localizar / Substituir."""

    procurar = Signal(object, bool)          # Criterio, para_tras
    procurar_incremental = Signal(object)    # Criterio -- atualiza contador/realce
    substituir_atual = Signal(object, str)   # Criterio, substituicao
    substituir_tudo = Signal(object, str, bool)   # Criterio, subst., so' selecao
    fechada = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("barraDeBusca")

        # -- linha 1: localizar --------------------------------------------
        self.campo = QLineEdit(self)
        self.campo.setPlaceholderText("Localizar")
        self.campo.setClearButtonEnabled(True)
        self.campo.textChanged.connect(self._agendar)
        self.campo.returnPressed.connect(lambda: self._disparar(False))

        self.contador = QLabel("", self)
        self.contador.setMinimumWidth(90)
        self.contador.setAlignment(Qt.AlignmentFlag.AlignRight
                                   | Qt.AlignmentFlag.AlignVCenter)

        anterior = self._botao("‹", "Localizar anterior (Shift+F3)",
                               lambda: self._disparar(True))
        proximo = self._botao("›", "Localizar proximo (F3)",
                              lambda: self._disparar(False))

        self.caixa_maiusculas = QCheckBox("Aa", self)
        self.caixa_maiusculas.setToolTip("Diferenciar maiusculas de minusculas")
        self.caixa_palavra = QCheckBox("ab|", self)
        self.caixa_palavra.setToolTip("Palavra inteira")
        self.caixa_regex = QCheckBox(".*", self)
        self.caixa_regex.setToolTip("Expressao regular")
        for caixa in (self.caixa_maiusculas, self.caixa_palavra,
                      self.caixa_regex):
            caixa.toggled.connect(self._agendar)

        fechar = self._botao("×", "Fechar (Esc)", self.esconder)

        linha1 = QHBoxLayout()
        linha1.setContentsMargins(4, 2, 4, 2)
        linha1.setSpacing(4)
        linha1.addWidget(self.campo, 1)
        linha1.addWidget(self.contador)
        linha1.addWidget(anterior)
        linha1.addWidget(proximo)
        linha1.addWidget(self.caixa_maiusculas)
        linha1.addWidget(self.caixa_palavra)
        linha1.addWidget(self.caixa_regex)
        linha1.addWidget(fechar)

        # -- linha 2: substituir (escondida no modo Localizar) --------------
        self.campo_substituir = QLineEdit(self)
        self.campo_substituir.setPlaceholderText("Substituir por")
        self.campo_substituir.returnPressed.connect(self._substituir_atual)

        botao_um = self._botao("Substituir", "", self._substituir_atual, largo=True)
        botao_todos = self._botao("Todos", "Substituir todas as ocorrencias",
                                  self._substituir_todos, largo=True)
        self.caixa_selecao = QCheckBox("Na selecao", self)
        self.caixa_selecao.setToolTip(
            "Substituir apenas dentro do texto selecionado")

        self.linha_substituir = QWidget(self)
        linha2 = QHBoxLayout(self.linha_substituir)
        linha2.setContentsMargins(4, 0, 4, 2)
        linha2.setSpacing(4)
        linha2.addWidget(self.campo_substituir, 1)
        linha2.addWidget(botao_um)
        linha2.addWidget(botao_todos)
        linha2.addWidget(self.caixa_selecao)

        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        principal.setSpacing(0)
        linha1_widget = QWidget(self)
        linha1_widget.setLayout(linha1)
        principal.addWidget(linha1_widget)
        principal.addWidget(self.linha_substituir)

        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(ATRASO_MS)
        self._temporizador.timeout.connect(self._emitir_incremental)

        self.linha_substituir.hide()
        self.hide()

    def _botao(self, texto: str, dica: str, acao, *,
               largo: bool = False) -> QToolButton:
        botao = QToolButton(self)
        botao.setText(texto)
        botao.setToolTip(dica)
        botao.setAutoRaise(True)
        botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if not largo:
            botao.setFixedWidth(22)
        botao.clicked.connect(acao)
        return botao

    # ==================================================================
    # Estado
    # ==================================================================

    def criterio(self) -> Criterio:
        return Criterio(
            texto=self.campo.text(),
            diferenciar_maiusculas=self.caixa_maiusculas.isChecked(),
            palavra_inteira=self.caixa_palavra.isChecked(),
            expressao_regular=self.caixa_regex.isChecked())

    def mostrar(self, *, com_substituicao: bool = False,
                texto_inicial: str = "") -> None:
        """Abre a barra. `texto_inicial` vem da selecao do editor."""
        self.linha_substituir.setVisible(com_substituicao)
        if texto_inicial:
            self.campo.setText(texto_inicial)
        self.show()
        self.campo.setFocus()
        self.campo.selectAll()
        self._emitir_incremental()

    def esconder(self) -> None:
        self.hide()
        self.fechada.emit()

    def definir_contador(self, atual: int, total: int, *,
                         erro: str = "") -> None:
        """Atualiza o "3 de 17", ou mostra o erro da expressao regular."""
        if erro:
            self.contador.setText("regex invalida")
            self.contador.setToolTip(erro)
            self.campo.setToolTip(erro)
            return
        self.contador.setToolTip("")
        self.campo.setToolTip("")
        if not self.campo.text():
            self.contador.setText("")
        elif total == 0:
            self.contador.setText("nenhum")
        elif atual > 0:
            self.contador.setText(f"{atual} de {total}")
        else:
            self.contador.setText(f"{total} achado(s)")

    # ==================================================================
    # Eventos
    # ==================================================================

    def _agendar(self) -> None:
        self._temporizador.start()

    def _emitir_incremental(self) -> None:
        self.procurar_incremental.emit(self.criterio())

    def _disparar(self, para_tras: bool) -> None:
        self._temporizador.stop()
        self.procurar.emit(self.criterio(), para_tras)

    def _substituir_atual(self) -> None:
        self.substituir_atual.emit(self.criterio(),
                                   self.campo_substituir.text())

    def _substituir_todos(self) -> None:
        self.substituir_tudo.emit(self.criterio(),
                                  self.campo_substituir.text(),
                                  self.caixa_selecao.isChecked())

    def keyPressEvent(self, evento: QKeyEvent) -> None:      # noqa: N802 - Qt
        tecla = evento.key()
        if tecla == Qt.Key.Key_Escape:
            self.esconder()
            evento.accept()
            return
        # Shift+Enter procura para tras: e' o gesto esperado, e evita ter de sair
        # do campo para clicar no botao.
        if (tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and evento.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._disparar(True)
            evento.accept()
            return
        super().keyPressEvent(evento)

    def aplicar_tema(self, tema) -> None:
        fundo = tema.cor("janela.aba_inativa").name()
        borda = tema.cor("janela.borda").name()
        texto = tema.cor("janela.texto").name()
        campo = tema.cor("janela.campo_fundo").name()
        self.setStyleSheet(f"""
            QWidget#barraDeBusca {{
                background: {fundo};
                border-top: 1px solid {borda};
            }}
            QWidget#barraDeBusca QLineEdit {{
                background: {campo}; color: {texto};
                border: 1px solid {borda}; padding: 2px 4px;
            }}
            QWidget#barraDeBusca QLabel,
            QWidget#barraDeBusca QCheckBox {{ color: {texto}; }}
            QWidget#barraDeBusca QToolButton {{ color: {texto}; }}
        """)
