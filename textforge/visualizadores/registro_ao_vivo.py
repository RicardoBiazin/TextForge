"""Acompanhar um log ao vivo (requisito 26).

Um `QPlainTextEdit` somente leitura com `setMaximumBlockCount()`. Essa unica
chamada resolve dois problemas de uma vez:

  * `appendPlainText` passa a ser O(1) -- o Qt descarta o bloco mais antigo em vez
    de relayoutar o documento inteiro a cada linha;
  * a memoria ganha teto automatico. Um log que cresce por horas nao pode fazer o
    editor crescer junto ate' o processo morrer.

O PONTO DE INTERFACE QUE DEFINE ESTA VIEW: o rolamento automatico so' acontece
quando o usuario JA esta' no fim. Se ele rolou para cima para ler uma mensagem de
erro, cada linha nova o puxaria de volta para o rodape -- e ler um log que recebe
10 linhas por segundo viraria impossivel. A barra de rolagem e' consultada ANTES de
inserir e restaurada depois.

A linha PARCIAL (o pedaco ainda sem "\\n") aparece separada, em cinza, e nao no
corpo do log: promove-la a linha faria uma mensagem partida ao meio virar duas
linhas erradas no historico.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from textforge import log_interno
from textforge.vigia import Acompanhador

log = log_interno.obter(__name__)

# Folga em pixels para considerar que o usuario esta' "no fim". Sem ela, um pixel
# de diferenca (que acontece o tempo todo por arredondamento de altura de linha)
# desligaria o rolamento automatico sem o usuario ter feito nada.
FOLGA_DO_FIM = 4


class VisualizadorAoVivo(QWidget):
    """A view de acompanhamento de um arquivo."""

    editavel = False                    # ver visualizadores/base.py

    estado_mudou = Signal(bool)         # True = acompanhando, False = pausado

    def __init__(self, caminho, codec: str, cfg: dict, tema,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.caminho = caminho
        self._recebidas = 0

        self.texto = QPlainTextEdit(self)
        self.texto.setReadOnly(True)
        self.texto.setUndoRedoEnabled(False)
        self.texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.texto.setMaximumBlockCount(
            max(100, int(cfg.get("tail_linhas_maximas", 5000))))

        self.parcial = QLabel("", self)
        self.parcial.setObjectName("linhaParcial")
        self.parcial.hide()

        self.botao = QToolButton(self)
        self.botao.setAutoRaise(True)
        self.botao.clicked.connect(self.alternar)

        limpar = QToolButton(self)
        limpar.setText("Limpar")
        limpar.setToolTip("Esvazia a tela. O arquivo NAO e' alterado.")
        limpar.setAutoRaise(True)
        limpar.clicked.connect(self.limpar)

        self.rolar = QCheckBox("Rolar automaticamente", self)
        self.rolar.setChecked(True)
        self.rolar.setToolTip(
            "Desmarque para ficar parado numa parte do log. Rolar para cima com o "
            "mouse tambem segura a tela enquanto voce nao voltar ao fim.")

        self.contador = QLabel("", self)

        barra = QHBoxLayout()
        barra.setContentsMargins(6, 3, 6, 3)
        barra.addWidget(self.botao)
        barra.addWidget(limpar)
        barra.addWidget(self.rolar)
        barra.addStretch(1)
        barra.addWidget(self.contador)
        self.topo = QWidget(self)
        self.topo.setLayout(barra)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.topo)
        layout.addWidget(self.texto, 1)
        layout.addWidget(self.parcial)

        self.acompanhador = Acompanhador(
            caminho, codec,
            intervalo_ms=int(cfg.get("tail_intervalo_ms", 500)),
            linhas_de_contexto=int(cfg.get("tail_linhas_de_contexto", 200)),
            parent=self)
        self.acompanhador.linhas_novas.connect(self.acrescentar)
        self.acompanhador.parcial.connect(self.definir_parcial)
        self.acompanhador.recomecou.connect(self._ao_recomecar)
        self.acompanhador.erro.connect(self._ao_falhar)

        self.aplicar_configuracao(cfg)
        self.aplicar_tema(tema)
        self._atualizar_botao()

    # ==================================================================
    # Ciclo de vida
    # ==================================================================

    def iniciar(self) -> None:
        if not self.acompanhador.isRunning():
            self.acompanhador.start()
        self._atualizar_botao()

    def encerrar(self) -> None:
        """Para a thread. Idempotente, e chamada ao trocar de view ou fechar."""
        if self.acompanhador.isRunning():
            if not self.acompanhador.encerrar(3000):
                log.warning("acompanhador de %s nao saiu em 3 s", self.caminho)
        self._atualizar_botao()

    def alternar(self) -> None:
        if self.acompanhador.pausado:
            self.acompanhador.retomar()
        else:
            self.acompanhador.pausar()
        self._atualizar_botao()
        self.estado_mudou.emit(not self.acompanhador.pausado)

    @property
    def pausado(self) -> bool:
        return self.acompanhador.pausado

    def _atualizar_botao(self) -> None:
        pausado = self.acompanhador.pausado
        self.botao.setText("Retomar" if pausado else "Pausar")
        self.botao.setToolTip(
            "Continua de onde parou -- nenhuma linha do intervalo se perde."
            if pausado else
            "Para de consumir o arquivo. O que chegar durante a pausa aparece ao "
            "retomar.")
        self._atualizar_contador()

    def _atualizar_contador(self) -> None:
        estado = "pausado" if self.acompanhador.pausado else "acompanhando"
        self.contador.setText(
            f"{self._recebidas:,} linhas · {estado}".replace(",", "."))

    # ==================================================================
    # Recebimento
    # ==================================================================

    def acrescentar(self, linhas: list) -> None:
        """Insere um LOTE. Uma insercao so', e nao uma por linha.

        Um processo que despeja 5 mil linhas de uma vez faria 5 mil relayouts se
        cada linha fosse inserida sozinha.
        """
        if not linhas:
            return
        barra = self.texto.verticalScrollBar()
        # Consultado ANTES de inserir: depois, o maximo ja' mudou.
        estava_no_fim = barra.value() >= barra.maximum() - FOLGA_DO_FIM

        cursor = self.texto.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # `insertText` com o texto ja' junto, em vez de N `appendPlainText`.
        # A quebra vai NA FRENTE quando ja' ha' conteudo, para nao deixar uma
        # linha em branco no fim do documento.
        prefixo = "\n" if self.texto.blockCount() > 1 or cursor.position() else ""
        cursor.insertText(prefixo + "\n".join(str(l) for l in linhas))
        self._recebidas += len(linhas)

        if estava_no_fim and self.rolar.isChecked():
            barra.setValue(barra.maximum())
        else:
            # O usuario esta' lendo mais acima: a posicao e' preservada. Sem isto,
            # cada linha nova o jogaria para o rodape e ler um log ativo seria
            # impossivel.
            barra.setValue(min(barra.value(), barra.maximum()))
        self._atualizar_contador()

    def definir_parcial(self, texto: str) -> None:
        self.parcial.setText(texto)
        self.parcial.setVisible(bool(texto))

    def limpar(self) -> None:
        """Esvazia a TELA. O arquivo nao e' tocado, e o offset nao volta."""
        self.texto.clear()
        self._recebidas = 0
        self.definir_parcial("")
        self._atualizar_contador()

    def _ao_recomecar(self) -> None:
        """O arquivo foi truncado ou rotacionado."""
        self.limpar()
        self.texto.appendPlainText(
            "--- o arquivo foi truncado ou rotacionado; "
            "a leitura recomecou do inicio ---")
        self._recebidas = 0
        self._atualizar_contador()

    def _ao_falhar(self, mensagem: str) -> None:
        log.warning("acompanhamento de %s: %s", self.caminho, mensagem)
        self.texto.appendPlainText(f"--- erro ao ler o arquivo: {mensagem} ---")

    # ==================================================================
    # Aparencia
    # ==================================================================

    def aplicar_configuracao(self, cfg: dict) -> None:
        self.cfg = cfg
        fonte = QFont(str(cfg.get("fonte", "Consolas")),
                      int(cfg.get("fonte_tamanho", 11)))
        fonte.setFixedPitch(True)
        fonte.setStyleHint(QFont.StyleHint.Monospace,
                           QFont.StyleStrategy.PreferDefault)
        self.texto.setFont(fonte)
        self.parcial.setFont(fonte)
        self.texto.setMaximumBlockCount(
            max(100, int(cfg.get("tail_linhas_maximas", 5000))))

    def aplicar_tema(self, tema) -> None:
        fundo = tema.cor("editor.fundo").name()
        texto = tema.cor("editor.texto").name()
        apagado = tema.cor("janela.texto_apagado").name()
        self.texto.setStyleSheet(
            f"QPlainTextEdit {{ background: {fundo}; color: {texto};"
            f" border: none; selection-background-color:"
            f" {tema.cor('editor.selecao').name()}; }}")
        self.parcial.setStyleSheet(
            f"QLabel#linhaParcial {{ background: {fundo}; color: {apagado};"
            " padding: 0px 4px 2px 4px; font-style: italic; }}")
        self.topo.setStyleSheet(
            f"background: {tema.cor('janela.campo_fundo').name()};"
            f" border-bottom: 1px solid {tema.cor('janela.borda').name()};")
        for widget in (self.contador, self.rolar):
            widget.setStyleSheet(
                f"color: {tema.cor('janela.texto').name()};"
                " background: transparent; border: none;")

    def setFocus(self) -> None:                               # noqa: N802 - Qt
        self.texto.setFocus(Qt.FocusReason.OtherFocusReason)
