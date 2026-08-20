"""A planilha em modo GRADE (requisito 6, item Planilha).

Nasceu de `tabela_csv.py` e mantem as decisoes que la' se pagaram: proxy para
ordenar e filtrar sem reordenar a origem, papel proprio de ordenacao (senao "10"
vem antes de "9" em toda coluna numerica) e alinhamento a' direita para numero.

Tres diferencas, e as tres vem de a planilha nao ser texto:

1. **Nao ha' modo texto para o qual voltar.** O `.xlsx` e' um pacote ZIP; o
   `QTextDocument` da aba fica vazio e quem tem o conteudo e' este widget. Ele
   implementa `VisualizadorBinario` (ver `visualizadores/base.py`), nao
   `Visualizador`.

2. **A pasta tem varias abas.** Elas ficam num `QTabBar` embaixo, como no Excel.
   Trocar de aba troca o MODELO; a `Pasta` continua a mesma e as edicoes de todas
   as abas convivem ate' a gravacao.

3. **Nem toda celula aceita edicao.** Formula compartilhada e celula de erro sao
   travadas, e a dica de contexto diz por que -- ver `planilha/pasta.py`.

Ha' linhas e colunas VAZIAS depois do fim dos dados, de proposito: e' o que
permite acrescentar sem um botao. Elas so' entram no arquivo se receberem valor.
"""

from __future__ import annotations

from PySide6.QtCore import (QAbstractTableModel, QModelIndex,
                            QSortFilterProxyModel, Qt, Signal)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QTabBar, QTableView, QVBoxLayout,
                               QWidget)

from textforge import log_interno
from textforge.planilha import valores
from textforge.planilha.pasta import (Folha, Pasta, TIPO_DATA, TIPO_FORMULA,
                                      TIPO_NUMERO)

log = log_interno.obter(__name__)

#: Papel proprio para ORDENAR, pelo mesmo motivo que no CSV.
PAPEL_DE_ORDENACAO = Qt.ItemDataRole.UserRole + 1

#: Linhas e colunas em branco oferecidas depois do fim dos dados.
LINHAS_LIVRES = 20
COLUNAS_LIVRES = 4

#: Quantas linhas medir ao ajustar a largura das colunas.
LINHAS_PARA_MEDIR = 200


class ModeloPlanilha(QAbstractTableModel):
    """Uma aba da pasta. Le' de `Folha`, escreve por `Pasta.definir`."""

    mudou = Signal()

    def __init__(self, pasta: Pasta, folha: Folha, parent=None) -> None:
        super().__init__(parent)
        self.pasta = pasta
        self.folha = folha

    # ==================================================================
    # QAbstractTableModel
    # ==================================================================

    def rowCount(self, parent=QModelIndex()) -> int:         # noqa: N802 - Qt
        if parent.isValid():
            return 0
        return self.folha.linhas + LINHAS_LIVRES

    def columnCount(self, parent=QModelIndex()) -> int:      # noqa: N802 - Qt
        if parent.isValid():
            return 0
        return self.folha.colunas + COLUNAS_LIVRES

    def data(self, index: QModelIndex,                       # noqa: N802 - Qt
             role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        celula = self.folha.celula(index.row() + 1, index.column() + 1)

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return celula.texto
        if role == PAPEL_DE_ORDENACAO:
            return celula.ordenacao
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if celula.tipo in (TIPO_NUMERO, TIPO_DATA):
                return int(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._dica(celula)
        return None

    @staticmethod
    def _dica(celula) -> str | None:
        """O que a celula esconde: o valor calculado, ou por que esta' travada."""
        partes = []
        if celula.tipo == TIPO_FORMULA and celula.cache:
            partes.append(f"Valor calculado pelo Excel: {celula.cache}")
        if celula.travada:
            partes.append("Celula somente leitura: formula compartilhada ou "
                          "erro do Excel.")
        return "\n".join(partes) or None

    def setData(self, index: QModelIndex, valor,             # noqa: N802 - Qt
                role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        if self.pasta.definir(self.folha, index.row() + 1, index.column() + 1,
                              str(valor)):
            # O `dataChanged` sozinho nao basta quando a edicao ampliou a aba:
            # o modelo passou a ter mais linhas, e a view precisa saber disso.
            self.layoutChanged.emit()
            self.dataChanged.emit(index, index, [role])
            self.mudou.emit()
            return True
        return False

    def flags(self, index: QModelIndex):                     # noqa: N802 - Qt
        base = super().flags(index)
        if not index.isValid():
            return base
        if not self.folha.editavel or self.pasta.somente_leitura:
            return base
        if not self.folha.celula(index.row() + 1,
                                 index.column() + 1).editavel:
            return base
        return base | Qt.ItemFlag.ItemIsEditable

    def headerData(self, secao: int, orientacao,             # noqa: N802 - Qt
                   role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        # As mesmas coordenadas do Excel: "A", "B", "AA" nas colunas e o numero
        # REAL da linha na vertical. Um usuario que veio de uma mensagem de erro
        # citando "B7" precisa achar B7 aqui.
        if orientacao == Qt.Orientation.Horizontal:
            return valores.letra_de_coluna(secao + 1)
        return str(secao + 1)


class VisualizadorPlanilha(QWidget):
    """A grade, a barra de abas da pasta e o filtro."""

    conteudo_mudou = Signal()

    editavel = True                 # ver visualizadores/base.py

    def __init__(self, pasta: Pasta, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pasta = pasta
        self.editavel = not pasta.somente_leitura

        self.tabela = QTableView(self)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSortingEnabled(True)
        self.tabela.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectItems)
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)

        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(PAPEL_DE_ORDENACAO)
        self.tabela.setModel(self.proxy)

        self.filtro = QLineEdit(self)
        self.filtro.setPlaceholderText("Filtrar linhas...")
        self.filtro.setClearButtonEnabled(True)
        self.filtro.textChanged.connect(self.proxy.setFilterFixedString)

        self.rotulo = QLabel(self._resumo(), self)

        self.barra_de_abas = QTabBar(self)
        self.barra_de_abas.setExpanding(False)
        self.barra_de_abas.setDrawBase(False)
        for folha in pasta.folhas:
            indice = self.barra_de_abas.addTab(folha.nome)
            if folha.oculta:
                self.barra_de_abas.setTabToolTip(
                    indice, "Aba oculta na planilha original")
            elif not folha.editavel:
                self.barra_de_abas.setTabToolTip(
                    indice, folha.motivo_somente_leitura)
        self.barra_de_abas.currentChanged.connect(self._trocar_de_folha)

        topo = QHBoxLayout()
        topo.setContentsMargins(4, 2, 4, 2)
        topo.addWidget(self.rotulo)
        topo.addStretch(1)
        topo.addWidget(self.filtro, 2)
        cabecalho = QWidget(self)
        cabecalho.setLayout(topo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(cabecalho)
        layout.addWidget(self.tabela)
        layout.addWidget(self.barra_de_abas)

        self.modelo: ModeloPlanilha | None = None
        if pasta.folhas:
            self._trocar_de_folha(0)

    def _resumo(self) -> str:
        partes = [f"{len(self.pasta.folhas)} aba(s)"]
        if self.pasta.preservadas:
            partes.append("preservado: " + ", ".join(self.pasta.preservadas))
        if self.pasta.somente_leitura:
            partes.append(f"somente leitura — {self.pasta.aviso}")
        return " · ".join(partes)

    # ==================================================================
    # Abas da pasta
    # ==================================================================

    def _trocar_de_folha(self, indice: int) -> None:
        """Troca o MODELO, e nao a pasta.

        As edicoes feitas nas outras abas continuam vivas na `Pasta`: sao dela, e
        nao do modelo. E' o que permite corrigir uma celula em tres abas e salvar
        uma vez so'.
        """
        if not 0 <= indice < len(self.pasta.folhas):
            return
        anterior = self.modelo
        self.modelo = ModeloPlanilha(self.pasta, self.pasta.folhas[indice], self)
        self.modelo.mudou.connect(self.conteudo_mudou)
        self.proxy.setSourceModel(self.modelo)
        if anterior is not None:
            anterior.deleteLater()
        # A ordenacao nao segue de uma aba para outra: a coluna 3 de uma aba nao
        # tem relacao nenhuma com a coluna 3 da outra.
        self.proxy.sort(-1)
        self._ajustar_larguras()

    def folha_atual(self) -> Folha | None:
        return self.modelo.folha if self.modelo is not None else None

    def _ajustar_larguras(self) -> None:
        """Mede so' as primeiras linhas, como no CSV: medir todas trava a aba."""
        cabecalho = self.tabela.horizontalHeader()
        cabecalho.setResizeContentsPrecision(LINHAS_PARA_MEDIR)
        self.tabela.resizeColumnsToContents()
        for coluna in range(self.proxy.columnCount()):
            largura = self.tabela.columnWidth(coluna)
            self.tabela.setColumnWidth(coluna, max(70, min(largura, 320)))

    # ==================================================================
    # Contrato de VisualizadorBinario
    # ==================================================================

    def para_bytes(self) -> bytes:
        return self.pasta.bytes_para_salvar()

    @property
    def alterado(self) -> bool:
        return self.pasta.alterado

    def confirmar_gravacao(self) -> None:
        self.pasta.confirmar_gravacao()

    # ==================================================================
    # Acoes
    # ==================================================================

    def copiar(self) -> None:
        """Copia a selecao como TSV, na ordem da TELA.

        TAB porque o destino de um Ctrl+C aqui e' quase sempre outra planilha, e
        planilha cola TSV direto em colunas.
        """
        indices = self.tabela.selectionModel().selectedIndexes()
        if not indices:
            return
        por_linha: dict[int, dict[int, str]] = {}
        for indice in indices:
            por_linha.setdefault(indice.row(), {})[indice.column()] = \
                str(indice.data() or "")
        linhas = []
        for linha in sorted(por_linha):
            colunas = por_linha[linha]
            linhas.append("\t".join(colunas[c] for c in sorted(colunas)))
        QApplication.clipboard().setText("\n".join(linhas))

    def selecionar_tudo(self) -> None:
        self.tabela.selectAll()

    def ir_para_linha(self, linha: int) -> None:
        """`linha` em BASE ZERO, como no resto do nucleo."""
        if self.modelo is None:
            return
        origem = self.modelo.index(max(0, linha), 0)
        self.tabela.setCurrentIndex(self.proxy.mapFromSource(origem))

    def aplicar_tema(self, tema) -> None:
        fundo = tema.cor("editor.fundo").name()
        texto = tema.cor("editor.texto").name()
        grade = tema.cor("editor.margem_borda").name()
        selecao = tema.cor("editor.selecao").name()
        self.tabela.setStyleSheet(f"""
            QTableView {{
                background: {fundo}; color: {texto};
                gridline-color: {grade}; border: none;
                selection-background-color: {selecao};
            }}
            QHeaderView::section {{
                background: {tema.cor('janela.aba_inativa').name()};
                color: {texto}; border: 1px solid {grade}; padding: 3px;
            }}
        """)
        self.barra_de_abas.setStyleSheet(f"""
            QTabBar::tab {{
                background: {tema.cor('janela.aba_inativa').name()};
                color: {texto}; border: 1px solid {grade};
                padding: 3px 10px;
            }}
            QTabBar::tab:selected {{ background: {fundo}; }}
        """)
        self.rotulo.setStyleSheet(f"color: {texto}; padding: 2px 6px;")
