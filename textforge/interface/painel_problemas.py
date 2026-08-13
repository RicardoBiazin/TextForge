"""Painel "Problemas": erros de sintaxe e avisos de formatacao.

Existe para o erro NAO virar dialogo modal. Um erro de sintaxe num XML de 4 mil
linhas precisa de duas coisas: a mensagem visivel enquanto se edita, e um clique que
leve ate' a linha. Um `QMessageBox` da' a mensagem e tira as duas.

Cada item guarda a POSICAO ABSOLUTA quando ela e' conhecida (o JSON entrega isso de
graca no `JSONDecodeError.pos`), e cai para linha/coluna quando nao e'. Com a posicao
absoluta o cursor vai direto ao caractere do erro, sem recalcular nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from textforge.formatadores.base import ErroDeSintaxe, Recusa


@dataclass(frozen=True)
class Problema:
    """Um item do painel."""

    gravidade: str                 # "erro" | "aviso" | "recusa"
    mensagem: str
    linha: int = 0                 # BASE 1; zero quando nao se aplica
    coluna: int = 0
    posicao: int | None = None     # offset absoluto em caracteres
    contexto: str = ""
    origem: str = ""               # "XML", "JSON", o nome do formatador

    @classmethod
    def de_erro(cls, erro: ErroDeSintaxe, origem: str = "") -> "Problema":
        return cls(gravidade="erro", mensagem=erro.motivo, linha=erro.linha,
                   coluna=erro.coluna, posicao=erro.posicao,
                   contexto=erro.contexto, origem=origem)

    @classmethod
    def de_recusa(cls, recusa: Recusa, origem: str = "") -> "Problema":
        # A sugestao entra na mensagem: e' o que transforma a recusa em caminho, e
        # o painel nao tem coluna separada para ela.
        texto = recusa.motivo
        if recusa.sugestao:
            texto += "  →  " + recusa.sugestao
        return cls(gravidade="recusa", mensagem=texto, origem=origem)

    @classmethod
    def de_aviso(cls, texto: str, origem: str = "") -> "Problema":
        return cls(gravidade="aviso", mensagem=texto, origem=origem)


MARCA = {"erro": "✕", "aviso": "!", "recusa": "⊘"}


class PainelProblemas(QWidget):
    problema_escolhido = Signal(int, int, object)   # linha, coluna, posicao

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tema = None

        self.cabecalho = QLabel("Nenhum problema.", self)
        topo = QHBoxLayout()
        topo.setContentsMargins(6, 2, 6, 2)
        topo.addWidget(self.cabecalho, 1)

        self.arvore = QTreeWidget(self)
        self.arvore.setHeaderLabels(["", "Mensagem", "Linha", "Trecho"])
        self.arvore.setColumnWidth(0, 26)
        self.arvore.setColumnWidth(1, 420)
        self.arvore.setColumnWidth(2, 60)
        self.arvore.setRootIsDecorated(False)
        self.arvore.setUniformRowHeights(True)
        self.arvore.itemActivated.connect(self._ao_escolher)
        self.arvore.itemClicked.connect(self._ao_escolher)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        topo_widget = QWidget(self)
        topo_widget.setLayout(topo)
        layout.addWidget(topo_widget)
        layout.addWidget(self.arvore)

    # ==================================================================

    def mostrar(self, problemas: list[Problema], origem: str = "") -> None:
        self.arvore.clear()
        erros = sum(1 for p in problemas if p.gravidade == "erro")
        avisos = len(problemas) - erros

        if not problemas:
            self.cabecalho.setText(
                f"Nenhum problema{f' em {origem}' if origem else ''}.")
            return

        partes = []
        if erros:
            partes.append(f"{erros} erro(s)")
        if avisos:
            partes.append(f"{avisos} aviso(s)")
        self.cabecalho.setText(" · ".join(partes)
                               + (f" — {origem}" if origem else ""))

        for p in problemas:
            item = QTreeWidgetItem([
                MARCA.get(p.gravidade, "·"),
                p.mensagem,
                str(p.linha) if p.linha else "",
                p.contexto.strip()[:200]])
            item.setToolTip(1, p.mensagem)
            if p.linha or p.posicao is not None:
                item.setData(0, Qt.ItemDataRole.UserRole,
                             (p.linha, p.coluna, p.posicao))
            if self._tema is not None:
                cor = {"erro": "janela.erro", "aviso": "janela.aviso"}.get(
                    p.gravidade, "janela.texto_apagado")
                item.setForeground(0, self._tema.cor(cor))
            self.arvore.addTopLevelItem(item)

    def limpar(self) -> None:
        self.arvore.clear()
        self.cabecalho.setText("Nenhum problema.")

    def primeiro_erro(self) -> tuple[int, int, object] | None:
        """Para o comando "Ir para o erro" (F8)."""
        for i in range(self.arvore.topLevelItemCount()):
            dados = self.arvore.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            if dados is not None:
                return dados
        return None

    def _ao_escolher(self, item: QTreeWidgetItem, _coluna: int = 0) -> None:
        dados = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(dados, tuple) and len(dados) == 3:
            self.problema_escolhido.emit(int(dados[0]), int(dados[1]), dados[2])

    def aplicar_tema(self, tema) -> None:
        self._tema = tema
        fundo = tema.cor("janela.campo_fundo").name()
        texto = tema.cor("janela.texto").name()
        self.arvore.setStyleSheet(
            f"QTreeWidget {{ background: {fundo}; color: {texto};"
            f" border: none; }}")
        self.cabecalho.setStyleSheet(f"color: {texto};")
