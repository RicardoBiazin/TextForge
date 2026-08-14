"""CSV em modo TABELA (requisito 6-CSV).

A decisao que define este arquivo: **regenerar o CSV inteiro com `csv.writer`
ALTERA o arquivo mesmo sem nenhuma edicao.** O `QUOTE_MINIMAL` transforma `"abc"`
em `abc`, `1,50` pode virar `"1,50"`, e o espaco depois do delimitador some. Num
arquivo de integracao isso e' destruicao silenciosa, e torna qualquer comparacao
com o original inutil.

Por isso o modelo guarda TRES coisas:

    registros_crus   o texto de cada registro, VERBATIM, como veio do arquivo
    campos           o registro ja' analisado -- LAZY, so' o que a tela pediu
    sujas            os indices dos registros que o usuario editou

Ao voltar para texto: registro nao sujo sai IDENTICO; registro sujo e' reescrito com
`csv.writer`. Sem nenhuma edicao, `para_texto()` devolve a entrada byte a byte -- e'
o teste central desta etapa.

O parse LAZY resolve a outra metade: abrir um CSV de 200 mil registros analisa as
~40 linhas visiveis, e nao 200 mil.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QTableView, QToolButton, QVBoxLayout, QWidget)

from textforge import log_interno
from textforge.analisadores import de_csv
from textforge.analisadores.de_csv import Dialeto

log = log_interno.obter(__name__)

# Quantas linhas medir ao ajustar a largura das colunas. Medir todas num CSV de
# 200 mil registros travaria a abertura por dezenas de segundos.
LINHAS_PARA_MEDIR = 200

# Papel proprio para ORDENAR. O papel de exibicao devolve o texto do campo, e
# ordenar por ele poria "10" antes de "9" em toda coluna numerica.
PAPEL_DE_ORDENACAO = Qt.ItemDataRole.UserRole + 1


class ModeloCsv(QAbstractTableModel):
    """Tabela sobre um CSV, preservando byte a byte o que nao foi editado."""

    mudou = Signal()

    def __init__(self, texto: str, dialeto: Dialeto, parent=None) -> None:
        super().__init__(parent)
        self.dialeto = dialeto
        self.registros_crus: list[str] = de_csv.dividir_registros(texto, dialeto)
        self.campos: list[list[str] | None] = [None] * len(self.registros_crus)
        self.sujas: set[int] = set()

        self._cabecalho: list[str] = []
        if dialeto.tem_cabecalho and self.registros_crus:
            self._cabecalho = de_csv.campos_de(self.registros_crus[0], dialeto)
        self.colunas = max(dialeto.colunas, len(self._cabecalho), 1)

        # Um arquivo que termina com quebra de linha produz um ultimo registro
        # VAZIO. Ele nao e' uma linha de dados -- mostra-lo como linha editavel
        # confundiria, e edita-lo criaria conteudo onde havia so' a quebra final.
        self._tem_vazio_final = (len(self.registros_crus) > 1
                                 and self.registros_crus[-1] == "")

    # ==================================================================
    # Mapeamento entre linha da TABELA e registro do ARQUIVO
    # ==================================================================

    @property
    def _primeiro_de_dados(self) -> int:
        return 1 if self.dialeto.tem_cabecalho else 0

    def _fisico(self, linha_da_tabela: int) -> int:
        return linha_da_tabela + self._primeiro_de_dados

    def _indices_de_dados(self) -> range:
        """Os registros que sao DADOS, incluindo o cabecalho.

        Exclui o registro vazio final -- o que existe so' porque o arquivo termina
        com quebra de linha. Inserir uma coluna nele o transformaria de "nada" em
        ";;", e remover a ultima coluna o transformaria em `""`; nos dois casos o
        arquivo ganharia uma linha de dados que nunca existiu.
        """
        fim = len(self.registros_crus) - (1 if self._tem_vazio_final else 0)
        return range(max(0, fim))

    def _campos(self, fisico: int) -> list[str]:
        """Parse LAZY de UM registro, com cache."""
        if not 0 <= fisico < len(self.registros_crus):
            return []
        if self.campos[fisico] is None:
            self.campos[fisico] = de_csv.campos_de(self.registros_crus[fisico],
                                                   self.dialeto)
        return self.campos[fisico]

    # ==================================================================
    # QAbstractTableModel
    # ==================================================================

    def rowCount(self, parent=QModelIndex()) -> int:        # noqa: N802 - Qt
        if parent.isValid():
            return 0
        total = len(self.registros_crus) - self._primeiro_de_dados
        if self._tem_vazio_final:
            total -= 1
        return max(0, total)

    def columnCount(self, parent=QModelIndex()) -> int:     # noqa: N802 - Qt
        return 0 if parent.isValid() else self.colunas

    def data(self, index: QModelIndex,                      # noqa: N802 - Qt
             role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            campos = self._campos(self._fisico(index.row()))
            if index.column() < len(campos):
                return campos[index.column()]
            return ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            campos = self._campos(self._fisico(index.row()))
            if index.column() < len(campos) and de_csv.e_numero(
                    campos[index.column()]):
                return int(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        if role == PAPEL_DE_ORDENACAO:
            campos = self._campos(self._fisico(index.row()))
            if index.column() >= len(campos):
                return ""
            return de_csv.chave_de_ordenacao(campos[index.column()], self.dialeto)
        return None

    def setData(self, index: QModelIndex, valor,            # noqa: N802 - Qt
                role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        fisico = self._fisico(index.row())
        campos = list(self._campos(fisico))
        # Registro com menos campos que a tabela: completa antes de escrever, em
        # vez de estourar IndexError.
        if len(campos) <= index.column():
            campos += [""] * (index.column() + 1 - len(campos))
        novo = str(valor)
        if campos[index.column()] == novo:
            return False
        campos[index.column()] = novo
        self.campos[fisico] = campos
        self.sujas.add(fisico)
        self.dataChanged.emit(index, index, [role])
        self.mudou.emit()
        return True

    def headerData(self, secao: int, orientacao,            # noqa: N802 - Qt
                   role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientacao == Qt.Orientation.Horizontal:
            if secao < len(self._cabecalho) and self._cabecalho[secao].strip():
                return self._cabecalho[secao]
            # Sem cabecalho, numera as colunas: e' mais util que deixar em branco.
            return f"Coluna {secao + 1}"
        return str(self._fisico(secao) + 1)

    def flags(self, index: QModelIndex):                    # noqa: N802 - Qt
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable)

    # ==================================================================
    # Linhas e colunas
    # ==================================================================

    def inserir_linha(self, depois_de: int) -> None:
        fisico = self._fisico(max(0, depois_de)) + 1
        posicao = max(0, depois_de + 1)
        self.beginInsertRows(QModelIndex(), posicao, posicao)
        try:
            vazio = self.dialeto.delimitador * (self.colunas - 1)
            self.registros_crus.insert(fisico, vazio)
            self.campos.insert(fisico, [""] * self.colunas)
            # Os indices sujos DEPOIS do ponto de insercao andam junto: sem isto,
            # a linha errada seria reescrita ao voltar para texto.
            self.sujas = {i + 1 if i >= fisico else i for i in self.sujas}
            self.sujas.add(fisico)
        finally:
            self.endInsertRows()
        self.mudou.emit()

    def remover_linha(self, linha: int) -> None:
        if not 0 <= linha < self.rowCount():
            return
        fisico = self._fisico(linha)
        self.beginRemoveRows(QModelIndex(), linha, linha)
        try:
            del self.registros_crus[fisico]
            del self.campos[fisico]
            self.sujas = {i - 1 if i > fisico else i
                          for i in self.sujas if i != fisico}
        finally:
            self.endRemoveRows()
        self.mudou.emit()

    def inserir_coluna(self, depois_de: int) -> None:
        posicao = max(0, min(depois_de + 1, self.colunas))
        self.beginInsertColumns(QModelIndex(), posicao, posicao)
        try:
            # Inserir coluna toca TODAS as linhas: todas passam a sujas, e todas
            # serao reescritas. Nao ha' como preservar o quoting original de um
            # registro cuja estrutura mudou.
            for fisico in self._indices_de_dados():
                campos = list(self._campos(fisico))
                campos += [""] * max(0, posicao - len(campos))
                campos.insert(posicao, "")
                self.campos[fisico] = campos
                self.sujas.add(fisico)
            if self._cabecalho:
                self._cabecalho.insert(min(posicao, len(self._cabecalho)), "")
            self.colunas += 1
        finally:
            self.endInsertColumns()
        self.mudou.emit()

    def remover_coluna(self, coluna: int) -> None:
        if not 0 <= coluna < self.colunas or self.colunas <= 1:
            return
        self.beginRemoveColumns(QModelIndex(), coluna, coluna)
        try:
            for fisico in self._indices_de_dados():
                campos = list(self._campos(fisico))
                if coluna < len(campos):
                    del campos[coluna]
                    self.campos[fisico] = campos
                    self.sujas.add(fisico)
            if coluna < len(self._cabecalho):
                del self._cabecalho[coluna]
            self.colunas -= 1
        finally:
            self.endRemoveColumns()
        self.mudou.emit()

    # ==================================================================
    # Volta para texto
    # ==================================================================

    @property
    def alterado(self) -> bool:
        return bool(self.sujas)

    def para_texto(self) -> str:
        """O CSV de volta.

        SEM nenhuma edicao, devolve a entrada byte a byte -- inclusive as aspas
        desnecessarias, os espacos depois do delimitador e o quoting exatamente como
        estava. E' a garantia central deste modulo.
        """
        if not self.sujas:
            return "\n".join(self.registros_crus)

        saida = list(self.registros_crus)
        for fisico in sorted(self.sujas):
            if 0 <= fisico < len(saida):
                campos = self.campos[fisico] or []
                saida[fisico] = de_csv.montar_registro(campos, self.dialeto)
        return "\n".join(saida)

    def confirmar_gravacao(self) -> None:
        """O texto do documento passou a ser o que a tabela mostra.

        Promove os registros sujos a CRUS e zera a lista de sujos. Sem esta
        promocao, `sujas.clear()` sozinho faria a proxima chamada a `para_texto()`
        emitir o registro CRU ORIGINAL das linhas ja' gravadas -- ou seja, salvar
        uma vez e editar outra celula reverteria a primeira edicao em silencio.
        """
        for fisico in sorted(self.sujas):
            if 0 <= fisico < len(self.registros_crus):
                campos = self.campos[fisico] or []
                self.registros_crus[fisico] = de_csv.montar_registro(
                    campos, self.dialeto)
        self.sujas.clear()


# ---------------------------------------------------------------------------
# O widget
# ---------------------------------------------------------------------------


class VisualizadorCsv(QWidget):
    """A grade, com filtro e os botoes de linha e coluna."""

    conteudo_mudou = Signal()
    voltar_para_texto = Signal()

    editavel = True                 # ver visualizadores/base.py

    def __init__(self, texto: str, dialeto: Dialeto,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import QSortFilterProxyModel

        self.modelo = ModeloCsv(texto, dialeto, self)
        self.modelo.mudou.connect(self.conteudo_mudou)

        # O proxy ordena e filtra SEM reordenar os dados de origem: a ordem do
        # arquivo e' preservada, e voltar para texto nao embaralha nada.
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.modelo)
        self.proxy.setFilterKeyColumn(-1)          # filtra por qualquer coluna
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(PAPEL_DE_ORDENACAO)

        self.tabela = QTableView(self)
        self.tabela.setModel(self.proxy)
        self.tabela.setSortingEnabled(True)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectItems)
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.tabela.horizontalHeader().setStretchLastSection(True)

        self.filtro = QLineEdit(self)
        self.filtro.setPlaceholderText("Filtrar registros...")
        self.filtro.setClearButtonEnabled(True)
        self.filtro.textChanged.connect(self.proxy.setFilterFixedString)

        self.rotulo = QLabel(dialeto.descrever(), self)

        barra = QHBoxLayout()
        barra.setContentsMargins(4, 2, 4, 2)
        barra.addWidget(self.rotulo)
        barra.addStretch(1)
        barra.addWidget(self.filtro, 2)
        for texto_botao, dica, acao in (
                ("+ linha", "Inserir linha abaixo da atual", self.inserir_linha),
                ("− linha", "Remover a linha atual", self.remover_linha),
                ("+ coluna", "Inserir coluna a' direita", self.inserir_coluna),
                ("− coluna", "Remover a coluna atual", self.remover_coluna)):
            botao = QToolButton(self)
            botao.setText(texto_botao)
            botao.setToolTip(dica)
            botao.setAutoRaise(True)
            botao.clicked.connect(acao)
            barra.addWidget(botao)

        voltar = QToolButton(self)
        voltar.setText("Modo texto")
        voltar.setToolTip("Voltar para o texto (as alteracoes sao aplicadas)")
        voltar.setAutoRaise(True)
        voltar.clicked.connect(self.voltar_para_texto)
        barra.addWidget(voltar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        topo = QWidget(self)
        topo.setLayout(barra)
        layout.addWidget(topo)
        layout.addWidget(self.tabela)

        self._ajustar_larguras()

    def _ajustar_larguras(self) -> None:
        """Mede so' as primeiras linhas.

        `resizeColumnsToContents` mede TODAS as linhas do modelo. Num CSV de 200
        mil registros isso trava a abertura por dezenas de segundos -- e ainda
        forcaria o parse de todos eles, anulando o ganho do parse lazy.
        """
        cabecalho = self.tabela.horizontalHeader()
        cabecalho.setResizeContentsPrecision(LINHAS_PARA_MEDIR)
        self.tabela.resizeColumnsToContents()
        for coluna in range(self.modelo.columnCount()):
            largura = self.tabela.columnWidth(coluna)
            self.tabela.setColumnWidth(coluna, max(70, min(largura, 320)))

    # -- acoes -------------------------------------------------------------

    def _linha_atual(self) -> int:
        indice = self.tabela.currentIndex()
        if not indice.isValid():
            return self.modelo.rowCount() - 1
        return self.proxy.mapToSource(indice).row()

    def _coluna_atual(self) -> int:
        indice = self.tabela.currentIndex()
        return self.proxy.mapToSource(indice).column() if indice.isValid() else 0

    def inserir_linha(self) -> None:
        self.modelo.inserir_linha(self._linha_atual())

    def remover_linha(self) -> None:
        self.modelo.remover_linha(self._linha_atual())

    def inserir_coluna(self) -> None:
        self.modelo.inserir_coluna(self._coluna_atual())
        self._ajustar_larguras()

    def remover_coluna(self) -> None:
        self.modelo.remover_coluna(self._coluna_atual())
        self._ajustar_larguras()

    def para_texto(self) -> str:
        return self.modelo.para_texto()

    @property
    def alterado(self) -> bool:
        return self.modelo.alterado

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
        self.rotulo.setStyleSheet(f"color: {texto}; padding: 2px 6px;")
