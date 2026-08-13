"""Painel de resultados de "Pesquisar em arquivos" (requisito 8).

Agrupa por ARQUIVO, e nao lista plana: uma busca com 800 ocorrencias em 30 arquivos
e' inutilizavel como lista, e navegavel como arvore. Clique duplo abre o arquivo na
linha -- que e' o requisito literal ("ao clicar no resultado, abrir diretamente
naquela linha").

Os resultados chegam em LOTES da thread de busca. O painel os acrescenta sem
reconstruir a arvore, o que mantem a interface responsiva durante uma varredura
longa.
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from textforge.busca_em_arquivos import Resultado, Resumo


class PainelResultados(QWidget):
    resultado_escolhido = Signal(str, int, int)     # caminho, linha, coluna
    cancelar_pedido = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._por_arquivo: dict[str, QTreeWidgetItem] = {}
        self._total = 0

        self.cabecalho = QLabel("", self)
        self.botao_cancelar = QToolButton(self)
        self.botao_cancelar.setText("Cancelar")
        self.botao_cancelar.setAutoRaise(True)
        self.botao_cancelar.clicked.connect(self.cancelar_pedido)
        self.botao_cancelar.hide()

        topo = QHBoxLayout()
        topo.setContentsMargins(4, 2, 4, 2)
        topo.addWidget(self.cabecalho, 1)
        topo.addWidget(self.botao_cancelar)

        self.arvore = QTreeWidget(self)
        # A segunda coluna mostra a PASTA na linha do arquivo e o TRECHO nas linhas
        # de ocorrencia -- o cabecalho diz os dois, para nao parecer erro.
        self.arvore.setHeaderLabels(["Arquivo / linha", "Pasta / trecho"])
        self.arvore.setColumnWidth(0, 240)
        self.arvore.setUniformRowHeights(True)
        self.arvore.itemActivated.connect(self._ao_escolher)
        self.arvore.itemDoubleClicked.connect(self._ao_escolher)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        topo_widget = QWidget(self)
        topo_widget.setLayout(topo)
        layout.addWidget(topo_widget)
        layout.addWidget(self.arvore)

    # ==================================================================
    # Ciclo da busca
    # ==================================================================

    def comecar(self, descricao: str, pasta: str) -> None:
        self.arvore.clear()
        self._por_arquivo.clear()
        self._total = 0
        self.cabecalho.setText(f"Procurando {descricao} em {pasta}...")
        self.botao_cancelar.show()

    def acrescentar(self, resultados: list[Resultado]) -> None:
        """Acrescenta um lote SEM reconstruir a arvore."""
        self.arvore.setUpdatesEnabled(False)
        try:
            for r in resultados:
                pai = self._pai_de(r.caminho)
                item = QTreeWidgetItem([f"linha {r.linha + 1}", r.trecho])
                item.setData(0, Qt.ItemDataRole.UserRole,
                             (str(r.caminho), r.linha, r.coluna))
                pai.addChild(item)
                self._total += 1
                pai.setText(0, f"{r.caminho.name}  ({pai.childCount()})")
        finally:
            self.arvore.setUpdatesEnabled(True)

    def _pai_de(self, caminho: pathlib.Path) -> QTreeWidgetItem:
        chave = str(caminho)
        item = self._por_arquivo.get(chave)
        if item is None:
            item = QTreeWidgetItem([caminho.name, str(caminho.parent)])
            # O item de ARQUIVO nao navega: quem navega sao os filhos (as linhas).
            item.setToolTip(0, chave)
            self.arvore.addTopLevelItem(item)
            item.setExpanded(True)
            self._por_arquivo[chave] = item
        return item

    def terminar(self, resumo: Resumo) -> None:
        self.botao_cancelar.hide()
        self.cabecalho.setText(resumo.descrever())
        if self._total == 0:
            vazio = QTreeWidgetItem(["Nenhuma ocorrencia encontrada.", ""])
            vazio.setFlags(Qt.ItemFlag.NoItemFlags)
            self.arvore.addTopLevelItem(vazio)

    def cancelado(self) -> None:
        self.botao_cancelar.hide()
        self.cabecalho.setText(
            f"Busca cancelada — {self._total} ocorrencia(s) ate' aqui.")

    def falhou(self, mensagem: str) -> None:
        self.botao_cancelar.hide()
        self.cabecalho.setText("A busca falhou.")
        item = QTreeWidgetItem([mensagem.strip().splitlines()[-1][:200], ""])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.arvore.addTopLevelItem(item)

    def progresso(self, lidos: int, pasta: str) -> None:
        self.cabecalho.setText(f"{lidos} arquivo(s) lido(s) — {pasta}")

    # ==================================================================
    # Interacao
    # ==================================================================

    def _ao_escolher(self, item: QTreeWidgetItem, _coluna: int = 0) -> None:
        dados = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(dados, tuple) and len(dados) == 3:
            self.resultado_escolhido.emit(str(dados[0]), int(dados[1]),
                                          int(dados[2]))

    def aplicar_tema(self, tema) -> None:
        fundo = tema.cor("janela.campo_fundo").name()
        texto = tema.cor("janela.texto").name()
        self.arvore.setStyleSheet(
            f"QTreeWidget {{ background: {fundo}; color: {texto};"
            f" border: none; }}")
        self.cabecalho.setStyleSheet(f"color: {texto}; padding: 2px;")
