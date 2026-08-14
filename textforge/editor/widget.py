"""`EditorDeTexto`: o widget de edicao.

`QPlainTextEdit` subclassado. Ver o `__init__.py` do pacote para o porque desta
base e nao de `QTextEdit` nem de um widget totalmente proprio.

O que esta etapa entrega: numeracao de linhas, realce da linha atual, guias de
indentacao, regua de coluna, caracteres invisiveis, tabulacao configuravel,
quebra de linha, zoom, marcadores por linha e auto-indent. Realce de sintaxe,
dobras, multi-cursor e minimapa entram nas etapas seguintes -- e os ganchos para
eles ja' estao aqui (a margem ja' pula blocos invisiveis, as `selecoes` ja' sao
em camadas).

Cuidado de desempenho que orienta o arquivo inteiro: o gargalo do
`QPlainTextEdit` NAO e' o numero de linhas (aguenta centenas de milhares), e' uma
LINHA muito longa -- o `QTextLayout` tem custo quadratico dentro de um bloco. Por
isso nada aqui percorre o documento inteiro em resposta a uma tecla, e todo laco
de desenho comeca em `firstVisibleBlock()` e para na borda do viewport.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPaintEvent,
                           QPalette, QResizeEvent, QTextBlock, QTextCursor,
                           QTextFormat, QTextOption, QWheelEvent)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from textforge import log_interno
from textforge.editor import indentacao as ind
from textforge.editor.indentacao import Indentacao
from textforge.editor.margem import LARGURA_DO_MARCADOR, MargemDeLinhas
from textforge.editor.selecoes import GerenciadorDeSelecoes

log = log_interno.obter(__name__)

ZOOM_MINIMO = 6
ZOOM_MAXIMO = 48

# QTextCursor.selectedText() devolve U+2029 (SEPARADOR DE PARAGRAFO) no lugar da
# quebra de linha. Contar "\n" no resultado daria SEMPRE uma linha, por mais que
# o usuario selecionasse -- e' o erro classico desta API do Qt. Escrito como
# escape de proposito: o caractere literal e' invisivel no editor e no diff.
SEPARADOR_DE_PARAGRAFO = " "

# Simbolo do fim de linha (requisito 3). Espacos e TAB o proprio Qt desenha.
PILCROW = "¶"


class EditorDeTexto(QPlainTextEdit):
    """Editor de um documento."""

    posicao_mudou = Signal(int, int)          # linha, coluna -- BASE ZERO
    selecao_mudou = Signal(int, int)          # caracteres, linhas
    marcadores_mudaram = Signal()
    zoom_mudou = Signal(int)

    def __init__(self, cfg: dict, tema, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.tema = tema
        self.indentacao = Indentacao(
            usa_espacos=bool(cfg.get("usar_espacos", True)),
            largura=int(cfg.get("tabulacao", 4)))
        self._marcadores: set[int] = set()

        self.selecoes = GerenciadorDeSelecoes(self)
        self.margem = MargemDeLinhas(self)
        # Selecao retangular (Alt+arrastar). Ver `editor/bloco.py`.
        from textforge.editor.bloco import SelecaoEmBloco
        self.bloco = SelecaoEmBloco(self)

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameStyle(QPlainTextEdit.Shape.NoFrame)
        self.setUndoRedoEnabled(True)
        # False de proposito. Com True, o Qt permite rolar ALEM do fim do
        # documento para poder centralizar o cursor -- e num arquivo curto isso
        # empurra as primeiras linhas para fora da tela, o que parece defeito.
        # E' o comportamento do VS Code, nao o do Notepad++, e aqui o segundo e'
        # o esperado.
        self.setCenterOnScroll(False)

        self.blockCountChanged.connect(self._ajustar_margem)
        self.updateRequest.connect(self._atualizar_margem)
        self.cursorPositionChanged.connect(self._ao_mover_cursor)
        self.selectionChanged.connect(self._ao_mudar_selecao)

        self.aplicar_configuracao(cfg)
        self.aplicar_tema(tema)
        self._ajustar_margem()
        self._realcar_linha_atual()

    # ==================================================================
    # Aparencia
    # ==================================================================

    def aplicar_configuracao(self, cfg: dict) -> None:
        """Reaplica tudo o que vem da configuracao. Chamavel a qualquer momento."""
        self.cfg = cfg
        self.aplicar_fonte()
        self.definir_quebra_de_linha(bool(cfg.get("quebra_de_linha", False)))
        self.aplicar_invisiveis()
        self._realcar_linha_atual()
        self._ajustar_margem()

    def aplicar_fonte(self) -> None:
        fonte = QFont(str(self.cfg.get("fonte", "Consolas")),
                      int(self.cfg.get("fonte_tamanho", 11)))
        fonte.setFixedPitch(True)
        # StyleHint garante uma monoespacada de verdade se a fonte pedida nao
        # existir na maquina. Sem isto, um nome errado cairia numa fonte
        # proporcional e o alinhamento de colunas de um .dat de largura fixa
        # deixaria de existir -- sem nenhum aviso.
        fonte.setStyleHint(QFont.StyleHint.Monospace,
                           QFont.StyleStrategy.PreferDefault)
        self.setFont(fonte)
        self.aplicar_espacamento()
        self._aplicar_tabulacao()
        self._ajustar_margem()

    def aplicar_espacamento(self) -> None:
        """Altura da linha, como multiplo da altura natural da fonte.

        O Qt so' expoe isto por `QTextBlockFormat`, ou seja, bloco a bloco. Dois
        cuidados que isso obriga:

          * e' O(n) sobre o documento, entao so' roda quando o valor MUDA, nunca
            a cada tecla;
          * mexer em formato de bloco marca o QTextDocument como modificado. Como
            isto e' pura apresentacao, o estado de modificado e a pilha de
            desfazer sao preservados em volta da operacao. Sem isso, abrir um
            arquivo ja' o mostraria com o asterisco de "nao salvo" -- e o
            usuario acabaria salvando uma alteracao que ele nunca fez.
        """
        multiplicador = float(self.cfg.get("fonte_espacamento", 1.0))
        if abs(multiplicador - 1.0) < 0.01:
            return
        documento = self.document()
        modificado = documento.isModified()
        documento.blockSignals(True)
        try:
            from PySide6.QtGui import QTextBlockFormat
            formato = QTextBlockFormat()
            formato.setLineHeight(
                multiplicador * 100.0,
                QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            cursor = QTextCursor(documento)
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeBlockFormat(formato)
        finally:
            documento.blockSignals(False)
            documento.setModified(modificado)

    def _aplicar_tabulacao(self) -> None:
        """Largura visual do TAB, em pixels.

        `setTabStopDistance` recebe PIXELS, nao numero de espacos. Medimos com
        `QFontMetricsF` na fonte atual; um numero fixo desalinharia em qualquer
        fonte, tamanho ou DPI diferente do da maquina onde o codigo foi escrito.
        """
        metricas = QFontMetricsF(self.font())
        self.setTabStopDistance(
            metricas.horizontalAdvance(" ") * self.indentacao.largura)

    def aplicar_tema(self, tema) -> None:
        self.tema = tema
        fundo = tema.cor("editor.fundo").name()
        texto = tema.cor("editor.texto").name()
        selecao = tema.cor("editor.selecao").name()
        texto_selecao = tema.cor("editor.texto_da_selecao").name()
        self.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {fundo}; color: {texto};"
            f" selection-background-color: {selecao};"
            f" selection-color: {texto_selecao}; border: none; }}")
        # A cor do cursor piscante vem da paleta (papel Text), nao da folha de
        # estilo -- nao existe propriedade CSS para ela no Qt.
        paleta = self.palette()
        paleta.setColor(QPalette.ColorRole.Text, tema.cor("editor.cursor"))
        self.setPalette(paleta)
        self._realcar_linha_atual()
        self.margem.update()

    def definir_indentacao(self, indentacao: Indentacao) -> None:
        self.indentacao = indentacao
        self._aplicar_tabulacao()
        self.viewport().update()

    def definir_quebra_de_linha(self, ligada: bool) -> None:
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if ligada
                             else QPlainTextEdit.LineWrapMode.NoWrap)

    def aplicar_invisiveis(self) -> None:
        """Liga/desliga espacos e TAB visiveis (requisito 3).

        O Qt tem `ShowTabsAndSpaces` nativo, mas nao tem opcao separada para o
        fim de linha. Como o requisito pede os dois independentes, o CR/LF e'
        desenhado por nos em `_pintar_fim_de_linha`.
        """
        opcao = self.document().defaultTextOption()
        marcas = opcao.flags()
        if self.cfg.get("mostrar_espacos"):
            marcas |= QTextOption.Flag.ShowTabsAndSpaces
        else:
            marcas &= ~QTextOption.Flag.ShowTabsAndSpaces
        opcao.setFlags(marcas)
        self.document().setDefaultTextOption(opcao)
        self.viewport().update()

    # ==================================================================
    # Margem
    # ==================================================================

    def _ajustar_margem(self) -> None:
        self.setViewportMargins(self.margem.largura_total(), 0, 0, 0)

    def _atualizar_margem(self, retangulo: QRect, dy: int) -> None:
        if dy:
            self.margem.scroll(0, dy)
        else:
            self.margem.update(0, retangulo.y(),
                               self.margem.width(), retangulo.height())
        if retangulo.contains(self.viewport().rect()):
            self._ajustar_margem()

    def resizeEvent(self, evento: QResizeEvent) -> None:     # noqa: N802 - Qt
        super().resizeEvent(evento)
        area = self.contentsRect()
        self.margem.setGeometry(QRect(area.left(), area.top(),
                                      self.margem.largura_total(),
                                      area.height()))

    def pintar_margem(self, margem: MargemDeLinhas, evento: QPaintEvent) -> None:
        """Desenha os numeros de linha. Chamado pelo paintEvent da margem.

        Percorre APENAS os blocos visiveis, a partir de `firstVisibleBlock()`.
        Percorrer o documento inteiro aqui -- o erro classico -- tornaria a
        rolagem de um arquivo grande impraticavel.
        """
        pintor = QPainter(margem)
        pintor.fillRect(evento.rect(), self.tema.cor("editor.margem_fundo"))

        cor_normal = self.tema.cor("editor.margem_texto")
        cor_atual = self.tema.cor("editor.margem_texto_atual")
        cor_marcador = self.tema.cor("editor.marcador")
        linha_do_cursor = self.textCursor().blockNumber()
        largura_numeros = margem.largura_dos_numeros()

        pintor.setFont(self.font())
        bloco = self.firstVisibleBlock()
        numero = bloco.blockNumber()
        topo = int(self.blockBoundingGeometry(bloco)
                   .translated(self.contentOffset()).top())
        base = topo + int(self.blockBoundingRect(bloco).height())

        while bloco.isValid() and topo <= evento.rect().bottom():
            altura = max(1, base - topo)
            # Blocos invisiveis existem quando o folding entrar. Pular aqui e'
            # obrigatorio: sem isso os numeros continuariam sendo desenhados nas
            # posicoes das linhas recolhidas.
            if bloco.isVisible() and base >= evento.rect().top():
                atual = numero == linha_do_cursor
                pintor.setPen(cor_atual if atual else cor_normal)
                pintor.drawText(LARGURA_DO_MARCADOR, topo, largura_numeros,
                                altura,
                                int(Qt.AlignmentFlag.AlignRight
                                    | Qt.AlignmentFlag.AlignVCenter),
                                str(numero + 1))
                if numero in self._marcadores:
                    self._pintar_marcador(pintor, topo, altura, cor_marcador)

            bloco = bloco.next()
            topo = base
            base = topo + int(self.blockBoundingRect(bloco).height())
            numero += 1

        pintor.setPen(self.tema.cor("editor.margem_borda"))
        pintor.drawLine(margem.width() - 1, evento.rect().top(),
                        margem.width() - 1, evento.rect().bottom())

    def _pintar_marcador(self, pintor: QPainter, topo: int, altura: int,
                         cor: QColor) -> None:
        lado = max(4, min(8, altura - 4))
        pintor.setBrush(cor)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.drawEllipse(3, topo + (altura - lado) // 2, lado, lado)

    # ==================================================================
    # Desenho do texto: regua, guias e fim de linha
    # ==================================================================

    def paintEvent(self, evento: QPaintEvent) -> None:       # noqa: N802 - Qt
        # A ordem importa: regua e guias vao ATRAS do texto, e o simbolo de fim
        # de linha vai na frente. Por isso sao passadas separadas de pintura.
        if self.cfg.get("coluna_limite") or self.cfg.get(
                "mostrar_guias_de_indentacao"):
            self._pintar_fundo()
        super().paintEvent(evento)
        if self.cfg.get("mostrar_fim_de_linha"):
            self._pintar_fim_de_linha()

    def _largura_do_caractere(self) -> float:
        return QFontMetricsF(self.font()).horizontalAdvance(" ")

    # A selecao em bloco precisa das duas medidas para converter um ponto do
    # mouse em coluna. Publicas porque `editor/bloco.py` as consome.
    def largura_de_caractere(self) -> float:
        return self._largura_do_caractere()

    def deslocamento_do_texto(self) -> float:
        """x, em pixels, onde a coluna 0 comeca dentro do viewport."""
        return self.contentOffset().x()

    def _pintar_fundo(self) -> None:
        pintor = QPainter(self.viewport())
        largura_ch = self._largura_do_caractere()
        deslocamento = self.contentOffset().x()

        coluna = int(self.cfg.get("coluna_limite", 0))
        if coluna > 0:
            x = int(deslocamento + largura_ch * coluna)
            pintor.setPen(self.tema.cor("editor.coluna_limite"))
            pintor.drawLine(x, 0, x, self.viewport().height())

        if not self.cfg.get("mostrar_guias_de_indentacao"):
            return
        pintor.setPen(self.tema.cor("editor.guia_indentacao"))
        passo = max(1, self.indentacao.largura)
        bloco = self.firstVisibleBlock()
        while bloco.isValid():
            geometria = self.blockBoundingGeometry(bloco).translated(
                self.contentOffset())
            if geometria.top() > self.viewport().height():
                break
            if bloco.isVisible():
                colunas = self.indentacao.largura_visual(
                    ind.prefixo_de_indentacao(bloco.text()))
                # Guias nos niveis existentes, sem o ultimo: uma guia colada no
                # primeiro caractere do texto so' polui a tela.
                for nivel in range(passo, colunas, passo):
                    x = int(deslocamento + largura_ch * nivel)
                    pintor.drawLine(x, int(geometria.top()),
                                    x, int(geometria.bottom()) - 1)
            bloco = bloco.next()

    def _pintar_fim_de_linha(self) -> None:
        pintor = QPainter(self.viewport())
        pintor.setFont(self.font())
        pintor.setPen(self.tema.cor("editor.fim_de_linha_visivel"))
        ultimo = self.document().blockCount() - 1
        bloco = self.firstVisibleBlock()
        while bloco.isValid():
            geometria = self.blockBoundingGeometry(bloco).translated(
                self.contentOffset())
            if geometria.top() > self.viewport().height():
                break
            # O ultimo bloco nao tem quebra depois dele: desenhar o simbolo la'
            # anunciaria um fim de linha que nao existe no arquivo.
            if bloco.isVisible() and bloco.blockNumber() != ultimo:
                cursor = QTextCursor(bloco)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                retangulo = self.cursorRect(cursor)
                pintor.drawText(retangulo.right() + 1, retangulo.bottom() - 2,
                                PILCROW)
            bloco = bloco.next()

    # ==================================================================
    # Cursor, selecao e realce da linha atual
    # ==================================================================

    def _ao_mover_cursor(self) -> None:
        self._realcar_linha_atual()
        self._realcar_par()
        cursor = self.textCursor()
        # Coluna VISUAL: um TAB nao vale uma coluna, vale ate' a proxima parada
        # de tabulacao. Contar caracteres daria a coluna errada em qualquer
        # arquivo indentado com TAB -- e a barra de status mentiria.
        prefixo = cursor.block().text()[:cursor.positionInBlock()]
        self.posicao_mudou.emit(cursor.blockNumber(),
                                self.indentacao.largura_visual(prefixo))

    def _ao_mudar_selecao(self) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            self.selecao_mudou.emit(0, 0)
            return
        selecionado = cursor.selectedText()
        linhas = selecionado.count(SEPARADOR_DE_PARAGRAFO) + 1
        self.selecao_mudou.emit(len(selecionado), linhas)

    def _realcar_linha_atual(self) -> None:
        if not self.cfg.get("realcar_linha_atual", True):
            self.selecoes.limpar("linha_atual")
            return
        selecao = QTextEdit.ExtraSelection()
        selecao.format.setBackground(self.tema.cor("editor.linha_atual"))
        # FullWidthSelection faz o realce ir ate' a borda direita do viewport em
        # vez de parar no fim do texto. Sem isto, a "linha atual" fica um retalho
        # do tamanho do texto, que e' pior do que nao ter realce nenhum.
        selecao.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        cursor = self.textCursor()
        cursor.clearSelection()
        selecao.cursor = cursor
        self.selecoes.definir("linha_atual", [selecao])

    # ==================================================================
    # Pareamento (requisito 14)
    # ==================================================================

    def _realcar_par(self) -> None:
        """Destaca o delimitador ou a tag correspondente ao lado do cursor.

        Roda a CADA movimento do cursor, entao tudo aqui e' barato: os
        delimitadores vem dos `DadosDoBloco` que o realcador ja' gravou, e a busca
        tem teto de blocos (ver `pareamento.py`).
        """
        from textforge.editor import pareamento

        cursor = self.textCursor()
        try:
            par = pareamento.casar(self.document(), cursor.blockNumber(),
                                   cursor.positionInBlock())
        except Exception:            # noqa: BLE001 - nunca derrubar o cursor
            self.selecoes.limpar("pares")
            return

        if par is None:
            # Sem par: se o cursor esta' SOBRE um delimitador, marca em vermelho --
            # e' o aviso de parentese nao fechado.
            solto = pareamento.delimitador_em(
                self.document(), cursor.blockNumber(), cursor.positionInBlock())
            if solto is None:
                self.selecoes.limpar("pares")
                return
            _caractere, coluna = solto
            self.selecoes.definir("pares", [self._marcar(
                cursor.blockNumber(), coluna, 1, "editor.par_sem_par")])
            return

        origem, destino = par
        self.selecoes.definir("pares", [
            self._marcar(origem.bloco, origem.coluna, origem.tamanho,
                         "editor.par_casado"),
            self._marcar(destino.bloco, destino.coluna, destino.tamanho,
                         "editor.par_casado"),
        ])

    def _marcar(self, bloco: int, coluna: int, tamanho: int,
                cor: str) -> QTextEdit.ExtraSelection:
        selecao = QTextEdit.ExtraSelection()
        selecao.format.setForeground(self.tema.cor(cor))
        selecao.format.setFontWeight(QFont.Weight.Bold)
        alvo = self.document().findBlockByNumber(bloco)
        cursor = QTextCursor(alvo)
        cursor.setPosition(alvo.position() + coluna)
        cursor.setPosition(alvo.position() + coluna + tamanho,
                           QTextCursor.MoveMode.KeepAnchor)
        selecao.cursor = cursor
        return selecao

    def ir_para_par(self) -> bool:
        """Salta para o delimitador ou a tag correspondente (Ctrl+])."""
        from textforge.editor import pareamento

        cursor = self.textCursor()
        par = pareamento.casar(self.document(), cursor.blockNumber(),
                               cursor.positionInBlock())
        if par is None:
            return False
        _origem, destino = par
        self.ir_para_linha(destino.bloco, destino.coluna)
        return True

    # ==================================================================
    # Navegacao
    # ==================================================================

    def ir_para_linha(self, linha: int, coluna: int = 0) -> None:
        """Posiciona o cursor. `linha` e `coluna` em BASE ZERO."""
        linha = max(0, min(linha, self.document().blockCount() - 1))
        bloco = self.document().findBlockByNumber(linha)
        cursor = QTextCursor(bloco)
        if coluna > 0:
            # length() inclui o separador de bloco, dai' o -1.
            cursor.setPosition(bloco.position()
                               + min(coluna, bloco.length() - 1))
        ja_visivel = self._linha_visivel(linha)
        self.setTextCursor(cursor)
        # Centralizar SO' quando o destino estava fora da tela. Centralizar
        # sempre faz a tela pular mesmo quando a linha ja' estava a' vista, o que
        # desorienta o usuario -- e num arquivo curto joga o inicio do arquivo
        # para fora do campo de visao.
        if ja_visivel:
            self.ensureCursorVisible()
        else:
            self.centerCursor()

    def _linha_visivel(self, linha: int) -> bool:
        primeira = self.firstVisibleBlock().blockNumber()
        if linha < primeira:
            return False
        altura = self.viewport().height()
        bloco = self.firstVisibleBlock()
        while bloco.isValid():
            geometria = self.blockBoundingGeometry(bloco).translated(
                self.contentOffset())
            if geometria.top() > altura:
                return False
            if bloco.blockNumber() == linha:
                return geometria.bottom() <= altura
            bloco = bloco.next()
        return False

    def selecionar_linha(self, linha: int) -> None:
        bloco = self.document().findBlockByNumber(linha)
        if not bloco.isValid():
            return
        cursor = QTextCursor(bloco)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def bloco_em_y(self, y: int) -> QTextBlock | None:
        """Qual bloco esta' desenhado nesta altura. Usado pela margem."""
        bloco = self.firstVisibleBlock()
        while bloco.isValid():
            geometria = self.blockBoundingGeometry(bloco).translated(
                self.contentOffset())
            if geometria.top() > self.viewport().height():
                break
            if bloco.isVisible() and geometria.top() <= y <= geometria.bottom():
                return bloco
            bloco = bloco.next()
        return None

    # ==================================================================
    # Marcadores (requisito 40)
    # ==================================================================

    def alternar_marcador(self, linha: int | None = None) -> None:
        if linha is None:
            linha = self.textCursor().blockNumber()
        if linha in self._marcadores:
            self._marcadores.discard(linha)
        else:
            self._marcadores.add(linha)
        self.margem.update()
        self.marcadores_mudaram.emit()

    def marcadores(self) -> list[int]:
        return sorted(self._marcadores)

    def limpar_marcadores(self) -> None:
        if not self._marcadores:
            return
        self._marcadores.clear()
        self.margem.update()
        self.marcadores_mudaram.emit()

    def ir_para_marcador(self, adiante: bool = True) -> bool:
        """Circula pelos marcadores. False se nao houver nenhum."""
        if not self._marcadores:
            return False
        atual = self.textCursor().blockNumber()
        ordenados = sorted(self._marcadores)
        if adiante:
            alvo = next((l for l in ordenados if l > atual), ordenados[0])
        else:
            alvo = next((l for l in reversed(ordenados) if l < atual),
                        ordenados[-1])
        self.ir_para_linha(alvo)
        return True

    # ==================================================================
    # Edicao por linhas
    #
    # Regra de ouro desta secao: TODA alteracao acontece dentro de um
    # beginEditBlock/endEditBlock. Sem isso, "remover linhas duplicadas" num
    # arquivo de 5000 linhas exigiria 5000 Ctrl+Z para desfazer -- o que, na
    # pratica, e' o mesmo que nao poder desfazer.
    # ==================================================================

    def faixa_de_linhas_selecionadas(self) -> tuple[int, int]:
        """[inicio, fim) dos blocos que a selecao toca. Base zero.

        Sem selecao, e' a linha do cursor. Note o cuidado com a selecao que
        termina EXATAMENTE no inicio de uma linha: contar essa linha faria o
        usuario ver uma linha a mais sendo afetada do que ele marcou.
        """
        cursor = self.textCursor()
        if not cursor.hasSelection():
            n = cursor.blockNumber()
            return n, n + 1
        documento = self.document()
        inicio = documento.findBlock(cursor.selectionStart()).blockNumber()
        bloco_final = documento.findBlock(cursor.selectionEnd())
        fim = bloco_final.blockNumber() + 1
        if (cursor.selectionEnd() == bloco_final.position()
                and fim - 1 > inicio):
            fim -= 1
        return inicio, fim

    def _cursor_das_linhas(self, inicio: int, fim: int) -> QTextCursor:
        """Cursor cobrindo os blocos [inicio, fim), sem o separador final."""
        documento = self.document()
        primeiro = documento.findBlockByNumber(inicio)
        ultimo = documento.findBlockByNumber(max(inicio, fim - 1))
        cursor = QTextCursor(primeiro)
        cursor.setPosition(primeiro.position())
        cursor.setPosition(ultimo.position() + ultimo.length() - 1,
                           QTextCursor.MoveMode.KeepAnchor)
        return cursor

    def linhas_selecionadas(self) -> list[str]:
        inicio, fim = self.faixa_de_linhas_selecionadas()
        documento = self.document()
        return [documento.findBlockByNumber(n).text() for n in range(inicio, fim)]

    def aplicar_em_linhas(self, transformar) -> None:
        """Roda `transformar(list[str]) -> list[str]` nas linhas selecionadas.

        E' o caminho por onde passam todas as operacoes do requisito 22. A
        selecao e' recolocada sobre o resultado, para o usuario poder encadear
        duas operacoes sem selecionar de novo.
        """
        inicio, fim = self.faixa_de_linhas_selecionadas()
        antigas = self.linhas_selecionadas()
        novas = list(transformar(antigas))
        if novas == antigas:
            return
        cursor = self._cursor_das_linhas(inicio, fim)
        cursor.beginEditBlock()
        try:
            cursor.insertText("\n".join(novas))
        finally:
            cursor.endEditBlock()
        # Reselecionar o resultado: sem isto, aplicar "ordenar" e depois
        # "remover duplicadas" exigiria selecionar tudo outra vez.
        final = self._cursor_das_linhas(inicio, inicio + len(novas))
        self.setTextCursor(final)

    def aplicar_no_texto_selecionado(self, transformar) -> None:
        """Roda `transformar(str) -> str` na selecao, ou na palavra sob o cursor.

        Usado pelas conversoes de caixa e pelas de Base64/URL/HTML. Cair na
        palavra sob o cursor quando nao ha' selecao e' o que faz `camelCase`
        funcionar do jeito que se espera: posicionar e acionar.
        """
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            if not cursor.hasSelection():
                return
        original = cursor.selectedText().replace(SEPARADOR_DE_PARAGRAFO, "\n")
        novo = transformar(original)
        if novo == original:
            return
        cursor.beginEditBlock()
        try:
            cursor.insertText(novo)
        finally:
            cursor.endEditBlock()

    def duplicar_linha(self) -> None:
        from textforge.editor import operacoes_linha as ops
        self.aplicar_em_linhas(ops.duplicar)

    def excluir_linha(self) -> None:
        inicio, fim = self.faixa_de_linhas_selecionadas()
        documento = self.document()
        cursor = QTextCursor(documento.findBlockByNumber(inicio))
        cursor.beginEditBlock()
        try:
            cursor.setPosition(documento.findBlockByNumber(inicio).position())
            ultimo = documento.findBlockByNumber(max(inicio, fim - 1))
            # Levar o separador de bloco junto e' o que remove a linha de fato,
            # em vez de deixar uma linha vazia no lugar.
            destino = ultimo.position() + ultimo.length()
            cursor.setPosition(min(destino, documento.characterCount() - 1),
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        finally:
            cursor.endEditBlock()

    def mover_linha(self, para_baixo: bool) -> None:
        from textforge.editor import operacoes_linha as ops

        inicio, fim = self.faixa_de_linhas_selecionadas()
        documento = self.document()
        todas = [documento.findBlockByNumber(n).text()
                 for n in range(documento.blockCount())]
        if para_baixo:
            novas, deslocamento = ops.mover_para_baixo(todas, inicio, fim)
        else:
            novas, deslocamento = ops.mover_para_cima(todas, inicio, fim)
        if deslocamento == 0:
            return

        # Reescreve apenas a faixa afetada -- do menor indice tocado ao maior.
        # Reescrever o documento inteiro funcionaria, mas custaria um relayout
        # completo a cada Alt+Seta, o que se sente num arquivo grande.
        de = min(inicio, inicio + deslocamento)
        ate = max(fim, fim + deslocamento)
        cursor = self._cursor_das_linhas(de, ate)
        cursor.beginEditBlock()
        try:
            cursor.insertText("\n".join(novas[de:ate]))
        finally:
            cursor.endEditBlock()
        final = self._cursor_das_linhas(inicio + deslocamento,
                                       fim + deslocamento)
        self.setTextCursor(final)

    def indentar_selecao(self) -> None:
        from textforge.editor import indentacao as imod
        self.aplicar_em_linhas(
            lambda linhas: imod.indentar(linhas, self.indentacao))

    def desindentar_selecao(self) -> None:
        from textforge.editor import indentacao as imod
        self.aplicar_em_linhas(
            lambda linhas: imod.desindentar(linhas, self.indentacao))

    def converter_caixa(self, funcao) -> None:
        self.aplicar_no_texto_selecionado(funcao)

    # ==================================================================
    # Teclado
    # ==================================================================

    # ==================================================================
    # Selecao em bloco (Alt+arrastar) -- ver editor/bloco.py
    # ==================================================================

    def mousePressEvent(self, evento) -> None:               # noqa: N802 - Qt
        if (evento.button() == Qt.MouseButton.LeftButton
                and evento.modifiers() & Qt.KeyboardModifier.AltModifier):
            ponto = evento.position()
            linha, coluna = self.bloco.da_posicao(int(ponto.x()), int(ponto.y()))
            self.bloco.comecar(linha, coluna)
            # O cursor de verdade vai junto: e' ele que o Qt usa para rolar a
            # tela e para a barra de status mostrar Ln/Col.
            self.setTextCursor(self.cursorForPosition(ponto.toPoint()))
            evento.accept()
            return
        # Clique normal desfaz o bloco. Sem isto, digitar depois de clicar em
        # outro lugar ainda editaria as linhas do retangulo antigo -- o usuario
        # veria N linhas mudarem sem ter pedido.
        self.bloco.limpar()
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento) -> None:                # noqa: N802 - Qt
        if self.bloco.arrastando:
            ponto = evento.position()
            linha, coluna = self.bloco.da_posicao(int(ponto.x()), int(ponto.y()))
            self.bloco.estender(linha, coluna)
            evento.accept()
            return
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:             # noqa: N802 - Qt
        if self.bloco.arrastando:
            self.bloco.terminar()
            evento.accept()
            return
        super().mouseReleaseEvent(evento)

    def _bloco_tratou_tecla(self, evento) -> bool:
        """Teclas que agem sobre a selecao em bloco. False = trata normal."""
        if not self.bloco.ativa:
            return False
        tecla = evento.key()
        mods = evento.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        retangulo = self.bloco.retangulo

        if tecla == Qt.Key.Key_Escape:
            self.bloco.limpar()
            return True
        if ctrl and tecla in (Qt.Key.Key_C, Qt.Key.Key_X):
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.bloco.texto())
            if tecla == Qt.Key.Key_X and not self.isReadOnly():
                self.bloco.substituir("")
            return True

        # Alt+Shift+setas estende o retangulo pelo teclado, que e' o gesto de quem
        # nao quer soltar o teclado para pegar o mouse.
        if alt and shift and tecla in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                                       Qt.Key.Key_Up, Qt.Key.Key_Down):
            dl = -1 if tecla == Qt.Key.Key_Up else (
                1 if tecla == Qt.Key.Key_Down else 0)
            dc = -1 if tecla == Qt.Key.Key_Left else (
                1 if tecla == Qt.Key.Key_Right else 0)
            self.bloco.definir(
                retangulo.linha_ancora, retangulo.coluna_ancora,
                max(0, min(retangulo.linha_cursor + dl,
                           self.document().blockCount() - 1)),
                max(0, retangulo.coluna_cursor + dc))
            return True

        if self.isReadOnly():
            return False
        if tecla in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.bloco.apagar()
            return True
        # Texto digitavel: entra em TODAS as linhas do retangulo.
        texto = evento.text()
        if texto and texto.isprintable() and not ctrl:
            self.bloco.substituir(texto)
            return True
        # Qualquer outra tecla (setas sozinhas, Enter, Tab) sai do modo bloco e
        # segue o caminho normal. Tentar dar semantica retangular a tudo produz
        # comportamento que ninguem consegue prever.
        self.bloco.limpar()
        return False

    def keyPressEvent(self, evento) -> None:                 # noqa: N802 - Qt
        if self._bloco_tratou_tecla(evento):
            evento.accept()
            return

        tecla = evento.key()
        modificadores = evento.modifiers()
        sem_modificador = modificadores == Qt.KeyboardModifier.NoModifier
        so_shift = modificadores == Qt.KeyboardModifier.ShiftModifier

        # Tab / Shift+Tab com varias linhas selecionadas indenta o BLOCO, em vez
        # de substituir a selecao por um caractere de tabulacao -- que e' o
        # comportamento padrao do QPlainTextEdit e destroi a selecao do usuario.
        varias_linhas = False
        cursor = self.textCursor()
        if cursor.hasSelection():
            inicio, fim = self.faixa_de_linhas_selecionadas()
            varias_linhas = fim - inicio > 1

        if tecla == Qt.Key.Key_Tab and sem_modificador:
            if varias_linhas:
                self.indentar_selecao()
            else:
                self._inserir_tabulacao()
            evento.accept()
            return
        if tecla == Qt.Key.Key_Backtab or (tecla == Qt.Key.Key_Tab and so_shift):
            self.desindentar_selecao()
            evento.accept()
            return

        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                modificadores & Qt.KeyboardModifier.ControlModifier):
            self._enter_com_auto_indent()
            evento.accept()
            return

        if tecla == Qt.Key.Key_Backspace and sem_modificador:
            if self._backspace_de_indentacao():
                evento.accept()
                return

        super().keyPressEvent(evento)

    def _inserir_tabulacao(self) -> None:
        """Insere a unidade de indentacao, e nao um TAB literal.

        Com 'usar_espacos' ligado, digitar Tab tem de inserir espacos -- senao a
        configuracao de tabulacao valeria para reindentar mas nao para digitar, o
        que produziria arquivos com os dois misturados.
        """
        cursor = self.textCursor()
        if self.indentacao.usa_espacos:
            # Ate' a proxima parada de tabulacao, nao `largura` espacos fixos: a
            # diferenca aparece quando o cursor esta' no meio de uma coluna.
            coluna = self.indentacao.largura_visual(
                cursor.block().text()[:cursor.positionInBlock()])
            faltam = self.indentacao.largura - (coluna % self.indentacao.largura)
            cursor.insertText(" " * faltam)
        else:
            cursor.insertText("\t")

    def _enter_com_auto_indent(self) -> None:
        from textforge.editor import indentacao as imod

        cursor = self.textCursor()
        anterior = cursor.block().text()[:cursor.positionInBlock()]
        prefixo = imod.proxima_indentacao(anterior, self.indentacao,
                                          self._aumenta_indentacao())
        cursor.beginEditBlock()
        try:
            cursor.insertText("\n" + prefixo)
        finally:
            cursor.endEditBlock()

    def _aumenta_indentacao(self):
        """Padrao que indica "a proxima linha entra um nivel".

        Vem do provedor da linguagem a partir da etapa 5. Antes disso, None: sem
        provedor, o auto-indent apenas repete a indentacao da linha anterior, que
        e' o comportamento correto e seguro para um .txt ou um .log.
        """
        provedor = getattr(self, "provedor", None)
        return getattr(provedor, "aumenta_indentacao", None)

    def _backspace_de_indentacao(self) -> bool:
        """Backspace na indentacao apaga um NIVEL inteiro de espacos.

        Sem isto, sair de um nivel indentado com 4 espacos exige quatro
        Backspaces. Só age quando ha' apenas espaco em branco antes do cursor;
        no meio do texto, o Backspace continua apagando um caractere.
        """
        if not self.indentacao.usa_espacos:
            return False
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        coluna = cursor.positionInBlock()
        if coluna == 0:
            return False
        antes = cursor.block().text()[:coluna]
        if antes.strip():
            return False
        passo = self.indentacao.largura
        quantos = coluna % passo or passo
        quantos = min(quantos, coluna)
        cursor.beginEditBlock()
        try:
            for _ in range(quantos):
                cursor.deletePreviousChar()
        finally:
            cursor.endEditBlock()
        return True

    # ==================================================================
    # Zoom
    # ==================================================================

    def wheelEvent(self, evento: QWheelEvent) -> None:       # noqa: N802 - Qt
        if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ajustar_zoom(1 if evento.angleDelta().y() > 0 else -1)
            evento.accept()
            return
        super().wheelEvent(evento)

    def ajustar_zoom(self, passos: int) -> None:
        tamanho = int(self.cfg.get("fonte_tamanho", 11)) + passos
        # Os limites impedem o usuario de zerar a fonte com o Ctrl+roda e ficar
        # sem conseguir ler o proprio menu para desfazer.
        tamanho = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, tamanho))
        if tamanho == int(self.cfg.get("fonte_tamanho", 11)):
            return
        self.cfg["fonte_tamanho"] = tamanho
        self.aplicar_fonte()
        self.zoom_mudou.emit(tamanho)
