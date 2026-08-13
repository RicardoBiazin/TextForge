"""Painel "Estrutura" (requisito 11).

Mostra a arvore que o `ProvedorDeLinguagem.estrutura()` devolve, e navega para a
linha ao clicar. Funciona para qualquer linguagem sem uma linha de codigo especifica
aqui -- e' o pagamento do contrato do requisito 36.

Duas decisoes de desempenho:

  * a arvore e' reconstruida com ATRASO (500 ms depois da ultima tecla), e nao a
    cada caractere. `ast.parse` num arquivo de 5 mil linhas leva dezenas de
    milissegundos, e fazer isso por tecla travaria a digitacao.
  * o painel oculto NAO recalcula nada. Sem isso, o custo existiria mesmo para quem
    nunca abre o painel.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QLineEdit, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from textforge import log_interno
from textforge.linguagens.base import NoDeEstrutura

log = log_interno.obter(__name__)

ATRASO_MS = 500

# Prefixo por tipo de no. Um icone de verdade exigiria um arquivo por tipo; um
# marcador de texto e' legivel, escala para qualquer linguagem nova e nao depende
# de tema.
MARCA = {
    "classe": "C",
    "funcao": "f",
    "metodo": "m",
    "secao": "§",
    "seletor": "{",
    "tag": "<>",
    "chave": "·",
    "objeto": "{}",
    "lista": "[]",
    "titulo": "#",
    "comando": ">",
    "rotulo": ":",
}


class PainelEstrutura(QWidget):
    """Arvore da estrutura do documento ativo."""

    linha_escolhida = Signal(int, int)          # linha, coluna -- BASE ZERO

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._documento = None
        self._provedor = None

        self.filtro = QLineEdit(self)
        self.filtro.setPlaceholderText("Filtrar...")
        self.filtro.setClearButtonEnabled(True)
        self.filtro.textChanged.connect(self._aplicar_filtro)

        self.arvore = QTreeWidget(self)
        self.arvore.setHeaderLabels(["Nome", "Detalhe"])
        self.arvore.setColumnWidth(0, 220)
        self.arvore.setUniformRowHeights(True)
        self.arvore.setAlternatingRowColors(False)
        self.arvore.itemActivated.connect(self._ao_escolher)
        self.arvore.itemClicked.connect(self._ao_escolher)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.filtro)
        layout.addWidget(self.arvore)

        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(ATRASO_MS)
        self._temporizador.timeout.connect(self.reconstruir)

    # ==================================================================
    # Ligacao com o documento
    # ==================================================================

    def acompanhar(self, documento) -> None:
        """Passa a mostrar a estrutura de `documento`."""
        if self._documento is documento:
            return
        if self._documento is not None:
            try:
                self._documento.qt.contentsChange.disconnect(self._agendar)
            except (RuntimeError, TypeError):
                pass
        self._documento = documento
        self._provedor = getattr(documento, "provedor", None) if documento else None
        if documento is not None:
            documento.qt.contentsChange.connect(self._agendar)
        self.reconstruir()

    def _agendar(self, *_a) -> None:
        """Reconstroi com atraso, e so' se o painel estiver visivel."""
        if self.isVisible():
            self._temporizador.start()

    def showEvent(self, evento) -> None:                    # noqa: N802 - Qt
        super().showEvent(evento)
        # Ao ficar visivel, reconstroi: enquanto oculto nada foi recalculado.
        self.reconstruir()

    # ==================================================================
    # Construcao da arvore
    # ==================================================================

    def reconstruir(self) -> None:
        self.arvore.clear()
        doc = self._documento
        if doc is None:
            return
        provedor = getattr(doc, "provedor", None)
        if provedor is None:
            self._mensagem("Nenhuma linguagem detectada.")
            return
        try:
            nos = provedor.estrutura(doc.texto())
        except Exception as exc:            # noqa: BLE001 - provedor de plugin
            # Um provedor com defeito nao pode derrubar a janela.
            log.warning("estrutura de %r falhou: %s", provedor.nome, exc)
            self._mensagem("Nao foi possivel analisar a estrutura.")
            return

        if not nos:
            self._mensagem(f"Sem estrutura para {provedor.nome}.")
            return

        self.arvore.setUpdatesEnabled(False)
        try:
            for no in nos:
                self.arvore.addTopLevelItem(self._item(no))
            # Expande so' os dois primeiros niveis: num XML de 500 tags, expandir
            # tudo produz uma lista inutilizavel.
            self.arvore.expandToDepth(1)
        finally:
            self.arvore.setUpdatesEnabled(True)
        self._aplicar_filtro(self.filtro.text())

    def _item(self, no: NoDeEstrutura) -> QTreeWidgetItem:
        marca = MARCA.get(no.tipo, "·")
        item = QTreeWidgetItem([f"{marca}  {no.rotulo}", no.detalhe])
        item.setToolTip(0, f"{no.tipo} — linha {no.linha + 1}")
        # A linha e a coluna viajam no proprio item: e' o que o clique usa.
        item.setData(0, Qt.ItemDataRole.UserRole, (no.linha, no.coluna))
        for filho in no.filhos:
            item.addChild(self._item(filho))
        return item

    def _mensagem(self, texto: str) -> None:
        item = QTreeWidgetItem([texto, ""])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.arvore.addTopLevelItem(item)

    # ==================================================================
    # Interacao
    # ==================================================================

    def _ao_escolher(self, item: QTreeWidgetItem, _coluna: int = 0) -> None:
        dados = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(dados, tuple) and len(dados) == 2:
            self.linha_escolhida.emit(int(dados[0]), int(dados[1]))

    def _aplicar_filtro(self, texto: str) -> None:
        """Esconde os itens que nao casam, mas MANTEM os pais dos que casam.

        Sem preservar os pais, filtrar num XML esconderia a tag procurada junto com
        a arvore inteira -- o filtro seria inutil.
        """
        alvo = texto.strip().lower()
        raiz = self.arvore.invisibleRootItem()
        for i in range(raiz.childCount()):
            self._filtrar_item(raiz.child(i), alvo)

    def _filtrar_item(self, item: QTreeWidgetItem, alvo: str) -> bool:
        casa = not alvo or alvo in item.text(0).lower()
        algum_filho = False
        for i in range(item.childCount()):
            if self._filtrar_item(item.child(i), alvo):
                algum_filho = True
        visivel = casa or algum_filho
        item.setHidden(not visivel)
        if alvo and algum_filho:
            item.setExpanded(True)
        return visivel

    def aplicar_tema(self, tema) -> None:
        fundo = tema.cor("janela.campo_fundo").name()
        texto = tema.cor("janela.texto").name()
        self.arvore.setStyleSheet(
            f"QTreeWidget {{ background: {fundo}; color: {texto};"
            f" border: none; }}")
