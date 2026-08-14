"""Abas: um `Documento` por aba, com as views dele (requisito 2).

Duas classes:

  `Aba`               um `QStackedWidget` com as views de UM documento. Hoje so' o
                      editor de texto; as etapas seguintes acrescentam a tabela do
                      CSV, o visualizador hexadecimal e o visor de arquivo grande.
                      A pilha existe desde ja' para que "alternar Texto <-> Tabela"
                      seja `setCurrentIndex` em vez de reconstruir a aba -- e' o
                      que preserva a pilha de desfazer na troca de modo.

  `GerenciadorAbas`   o `QTabWidget`, com o asterisco de modificado e o menu de
                      contexto inteiro do requisito 2.

Regra de identidade: uma aba por ARQUIVO, comparando por `Documento.chave()`, que
resolve o caminho e ignora a caixa. Duas abas do mesmo arquivo produziriam duas
versoes divergentes, e uma delas se perderia no primeiro salvamento.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QApplication, QMenu, QStackedWidget, QTabBar,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)

from textforge import arquivos, log_interno
from textforge.documento import Documento
from textforge.editor.widget import EditorDeTexto
from textforge.realce.pintor import Pintor

log = log_interno.obter(__name__)


class Aba(QWidget):
    """As views de um documento."""

    def __init__(self, documento: Documento, cfg: dict, tema,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.documento = documento
        self.cfg = cfg

        self.pilha = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.pilha)

        self.editor = EditorDeTexto(cfg, tema, self)
        self.editor.setDocument(documento.qt)
        self.editor.setReadOnly(documento.somente_leitura)
        # O menu de contexto do editor (requisito 20) e' montado pela janela, que
        # e' quem tem o registro de comandos. A aba so' repassa o pedido.
        self.editor.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._pedir_menu)
        if cfg.get("detectar_indentacao", True):
            self.editor.definir_indentacao(documento.indentacao)
        self.pilha.addWidget(self.editor)
        # Nome -> widget. As etapas 9 e 10 registram "tabela", "hex" e "grande"
        # aqui, e a troca de modo passa a ser uma linha.
        self._views: dict[str, QWidget] = {"texto": self.editor}

        # O realcador e' anexado ao QTextDocument, e nao ao editor: e' o documento
        # que tem o conteudo, e e' assim que um Split View (dois editores no mesmo
        # documento) compartilharia um realce so'.
        self.pintor = Pintor(documento.qt, documento.provedor, tema, cfg)
        # O editor precisa do provedor para o auto-indent (`aumenta_indentacao`).
        self.editor.provedor = documento.provedor

    def _pedir_menu(self, ponto: QPoint) -> None:
        gerenciador = self.parent()
        montar = getattr(gerenciador, "montar_menu_do_editor", None)
        if montar is None:
            return
        menu = montar(self.editor)
        if menu is not None:
            menu.exec(self.editor.viewport().mapToGlobal(ponto))

    def registrar_view(self, nome: str, widget: QWidget) -> None:
        self.remover_view(nome)
        self._views[nome] = widget
        self.pilha.addWidget(widget)

    def remover_view(self, nome: str) -> None:
        """Descarta uma view alternativa. "texto" nunca sai.

        A tabela do CSV e' DESCARTADA ao voltar para o texto, e nao guardada: o
        usuario pode editar o texto em seguida, e uma tabela viva com o conteudo
        antigo mostraria dados obsoletos na proxima troca de modo -- ou pior,
        escreveria o conteudo antigo de volta por cima do novo.
        """
        if nome == "texto":
            return
        widget = self._views.pop(nome, None)
        if widget is None:
            return
        self.pilha.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()

    def tem_view(self, nome: str) -> bool:
        return nome in self._views

    def view(self, nome: str) -> QWidget | None:
        return self._views.get(nome)

    def trocar_para(self, nome: str) -> bool:
        widget = self._views.get(nome)
        if widget is None:
            return False
        self.pilha.setCurrentWidget(widget)
        widget.setFocus()
        return True

    def view_atual(self) -> str:
        atual = self.pilha.currentWidget()
        for nome, widget in self._views.items():
            if widget is atual:
                return nome
        return "texto"

    def aplicar_tema(self, tema) -> None:
        self.editor.aplicar_tema(tema)
        self.pintor.definir_tema(tema)
        for nome, widget in self._views.items():
            if nome != "texto" and hasattr(widget, "aplicar_tema"):
                widget.aplicar_tema(tema)

    def aplicar_configuracao(self, cfg: dict) -> None:
        self.cfg = cfg
        self.editor.aplicar_configuracao(cfg)
        self.pintor.definir_configuracao(cfg)

    def definir_provedor(self, provedor) -> None:
        """Troca a linguagem desta aba."""
        self.documento.provedor = provedor
        self.editor.provedor = provedor
        self.pintor.definir_provedor(provedor)
        if provedor is not None and self.cfg.get("detectar_indentacao", True):
            # A indentacao do ARQUIVO continua mandando; o provedor so' entra
            # quando o arquivo nao revelou nada (ver `indentacao.detectar`).
            pass


class GerenciadorAbas(QTabWidget):
    documento_trocado = Signal(object)     # Aba | None
    titulo_mudou = Signal()
    # Repassados APENAS da aba ativa. A barra de status se conecta a estes, e nao
    # aos editores: com 20 abas abertas, 20 editores emitindo posicao para a mesma
    # barra seria trabalho jogado fora a cada tecla. E conectar/desconectar na
    # troca de aba, a alternativa obvia, gera RuntimeWarning do PySide na
    # primeira troca (nao havia nada conectado para desconectar).
    posicao_mudou = Signal(int, int)
    selecao_mudou = Signal(int, int)

    def __init__(self, cfg: dict, tema, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.tema = tema
        # Botao de fechar PROPRIO, em vez do `setTabsClosable(True)` do Qt: o
        # estilo Fusion desenha um X vermelho vivo em toda aba, e a folha de
        # estilo nao consegue recolorir esse icone -- so' remove-lo, o que
        # deixaria a aba sem nenhuma indicacao de fechar. Um QToolButton com "x"
        # de texto e' controlavel pelo tema.
        self.setTabsClosable(False)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabCloseRequested.connect(self.fechar)
        self.currentChanged.connect(self._ao_trocar)

        barra = self.tabBar()
        barra.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        barra.customContextMenuRequested.connect(self._menu_da_aba)
        # Meio-clique fecha a aba, como no navegador. Nao esta' no requisito, mas
        # e' o gesto que todo mundo tenta.
        barra.setUsesScrollButtons(True)
        barra.installEventFilter(self)

        # Ganchos preenchidos pela janela, que e' quem sabe perguntar ao usuario e
        # quem tem o registro de comandos. Ficam como atributos, e nao como sinais,
        # porque os dois precisam de RESPOSTA -- um sinal nao devolve valor.
        self.pode_fechar = lambda aba: True
        self.montar_menu_do_editor = lambda editor: None

    # ==================================================================
    # Consulta
    # ==================================================================

    def abas(self) -> list[Aba]:
        return [self.widget(i) for i in range(self.count())]

    def aba_atual(self) -> Aba | None:
        return self.currentWidget()

    def documento_atual(self) -> Documento | None:
        aba = self.aba_atual()
        return aba.documento if aba is not None else None

    def editor_atual(self) -> EditorDeTexto | None:
        aba = self.aba_atual()
        return aba.editor if aba is not None else None

    def indice_por_chave(self, chave: str) -> int:
        for i, aba in enumerate(self.abas()):
            if aba.documento.chave() == chave:
                return i
        return -1

    def com_pendencias(self) -> list[Aba]:
        return [a for a in self.abas() if a.documento.modificado]

    # ==================================================================
    # Abrir e fechar
    # ==================================================================

    def adicionar(self, documento: Documento, *, focar: bool = True) -> Aba:
        """Cria uma aba. Se o arquivo ja' esta' aberto, FOCA a existente.

        Reusar a aba existente nao e' comodidade: duas abas do mesmo arquivo
        divergem, e no primeiro salvamento uma das versoes se perde.
        """
        existente = self.indice_por_chave(documento.chave())
        if existente >= 0:
            self.setCurrentIndex(existente)
            log.info("arquivo ja' aberto; focando a aba existente: %s",
                     documento.nome)
            return self.widget(existente)

        aba = Aba(documento, self.cfg, self.tema, self)
        indice = self.addTab(aba, documento.titulo_da_aba)
        self.setTabToolTip(indice, str(documento.caminho or documento.nome))
        aba.editor.posicao_mudou.connect(
            lambda l, c, a=aba: self._repassar(a, self.posicao_mudou, l, c))
        aba.editor.selecao_mudou.connect(
            lambda n, l, a=aba: self._repassar(a, self.selecao_mudou, n, l))
        self._por_botao_de_fechar(indice)
        documento.qt.modificationChanged.connect(
            lambda _m, a=aba: self._atualizar_titulo(a))
        documento.metadados_mudaram.connect(
            lambda a=aba: self._atualizar_titulo(a))
        if focar:
            self.setCurrentIndex(indice)
        return aba

    def fechar(self, indice: int) -> bool:
        aba = self.widget(indice)
        if aba is None:
            return False
        if not self.pode_fechar(aba):
            return False
        self.removeTab(indice)
        # deleteLater, e nao del: o Qt pode ainda ter eventos pendentes para este
        # widget, e destrui-lo agora derrubaria o programa dentro da fila.
        aba.setParent(None)
        aba.deleteLater()
        log.info("aba fechada: %s", aba.documento.nome)
        return True

    def fechar_todas(self) -> bool:
        while self.count():
            if not self.fechar(self.count() - 1):
                return False
        return True

    def fechar_outras(self, indice: int) -> bool:
        alvo = self.widget(indice)
        for aba in list(self.abas()):
            if aba is not alvo and not self.fechar(self.indexOf(aba)):
                return False
        return True

    def fechar_a_direita(self, indice: int) -> bool:
        while self.count() > indice + 1:
            if not self.fechar(self.count() - 1):
                return False
        return True

    def duplicar(self, indice: int) -> Aba | None:
        """Abre outra aba com o MESMO conteudo, como documento independente.

        Nao compartilha o QTextDocument de proposito: "duplicar aba" serve para
        experimentar uma alteracao sem perder o original, e um documento
        compartilhado faria as duas abas mudarem juntas -- que e' o Split View,
        um recurso diferente.
        """
        aba = self.widget(indice)
        if aba is None:
            return None
        copia = Documento.novo(self.cfg)
        copia.definir_texto(aba.documento.texto())
        copia.codec = aba.documento.codec
        copia.bom = aba.documento.bom
        copia.fim_de_linha = aba.documento.fim_de_linha
        copia.indentacao = aba.documento.indentacao
        copia.rotulo_sem_titulo = f"{aba.documento.nome} (copia)"
        nova = self.adicionar(copia)
        nova.editor.setTextCursor(aba.editor.textCursor())
        return nova

    # ==================================================================
    # Titulo
    # ==================================================================

    def _atualizar_titulo(self, aba: Aba) -> None:
        indice = self.indexOf(aba)
        if indice < 0:
            return
        self.setTabText(indice, aba.documento.titulo_da_aba)
        self.setTabToolTip(indice,
                           str(aba.documento.caminho or aba.documento.nome))
        self.titulo_mudou.emit()

    def atualizar_todos_os_titulos(self) -> None:
        for aba in self.abas():
            self._atualizar_titulo(aba)

    def _por_botao_de_fechar(self, indice: int) -> None:
        botao = QToolButton(self.tabBar())
        botao.setObjectName("fecharAba")
        botao.setText("×")            # MULTIPLICATION SIGN, nao a letra "x"
        botao.setToolTip("Fechar (Ctrl+W)")
        botao.setCursor(Qt.CursorShape.ArrowCursor)
        botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        botao.setAutoRaise(True)
        botao.clicked.connect(self._fechar_pelo_botao)
        self.tabBar().setTabButton(indice, QTabBar.ButtonPosition.RightSide,
                                   botao)

    def _fechar_pelo_botao(self) -> None:
        """Descobre a qual aba o botao clicado pertence.

        Procurar em tempo de clique, em vez de guardar o indice na criacao, e'
        obrigatorio: as abas sao reordenaveis e o indice de uma aba muda quando
        outra e' fechada ou arrastada.
        """
        remetente = self.sender()
        for i in range(self.count()):
            if self.tabBar().tabButton(
                    i, QTabBar.ButtonPosition.RightSide) is remetente:
                self.fechar(i)
                return

    def _repassar(self, aba: Aba, sinal, *argumentos) -> None:
        """Repassa o sinal so' se vier da aba ATIVA."""
        if self.currentWidget() is aba:
            sinal.emit(*argumentos)

    def _ao_trocar(self, _indice: int) -> None:
        self.documento_trocado.emit(self.aba_atual())

    # ==================================================================
    # Menu de contexto da aba (requisito 2)
    # ==================================================================

    def _menu_da_aba(self, ponto: QPoint) -> None:
        indice = self.tabBar().tabAt(ponto)
        menu = self.construir_menu_da_aba(indice)
        if menu is not None:
            menu.exec(self.tabBar().mapToGlobal(ponto))

    def construir_menu_da_aba(self, indice: int) -> QMenu | None:
        """Monta o menu de contexto da aba SEM exibi-lo.

        Separado da exibicao de proposito: `QMenu.exec()` e' modal, e um metodo
        que constroi E exibe nao pode ser testado -- em modo offscreen o menu
        ficaria aberto para sempre, sem ninguem para fecha-lo. (E substituir
        `QMenu.exec` no teste nao funciona: e' um slot C++, e a atribuicao na
        classe nao muda o que o objeto realmente chama.)
        """
        if indice < 0 or indice >= self.count():
            return None
        aba = self.widget(indice)
        doc = aba.documento
        menu = QMenu(self)

        menu.addAction("Fechar", lambda: self.fechar(indice))
        acao = menu.addAction("Fechar outras",
                              lambda: self.fechar_outras(indice))
        acao.setEnabled(self.count() > 1)
        acao = menu.addAction("Fechar as abas a' direita",
                              lambda: self.fechar_a_direita(indice))
        acao.setEnabled(indice < self.count() - 1)
        menu.addSeparator()
        menu.addAction("Duplicar aba", lambda: self.duplicar(indice))
        menu.addSeparator()

        tem_arquivo = doc.caminho is not None
        acao = menu.addAction(
            "Abrir local do arquivo",
            lambda: arquivos.abrir_no_explorer(doc.caminho))
        acao.setEnabled(tem_arquivo)
        acao = menu.addAction(
            "Copiar caminho completo",
            lambda: QApplication.clipboard().setText(str(doc.caminho)))
        acao.setEnabled(tem_arquivo)
        menu.addAction("Copiar nome do arquivo",
                       lambda: QApplication.clipboard().setText(doc.nome))
        return menu

    def eventFilter(self, objeto, evento) -> bool:          # noqa: N802 - Qt
        if (objeto is self.tabBar()
                and evento.type() == evento.Type.MouseButtonRelease
                and evento.button() == Qt.MouseButton.MiddleButton):
            indice = self.tabBar().tabAt(evento.position().toPoint())
            if indice >= 0:
                self.fechar(indice)
                return True
        return super().eventFilter(objeto, evento)

    # ==================================================================
    # Aparencia
    # ==================================================================

    def aplicar_tema(self, tema) -> None:
        self.tema = tema
        # As abas sao estilizadas por folha, com as cores do tema pedidas por
        # NOME. O padrao do estilo Fusion desenha o botao de fechar como um X
        # vermelho vivo em TODA aba, o que polui a barra e briga com o requisito
        # de interface limpa -- aqui ele fica discreto e so' ganha destaque sob o
        # ponteiro.
        aba_ativa = tema.cor("janela.aba_ativa").name()
        aba_inativa = tema.cor("janela.aba_inativa").name()
        texto = tema.cor("janela.texto").name()
        apagado = tema.cor("janela.texto_apagado").name()
        borda = tema.cor("janela.borda").name()
        destaque = tema.cor("janela.destaque").name()
        erro = tema.cor("janela.erro").name()
        self.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {aba_ativa}; }}
            QTabBar {{ background: {aba_inativa}; qproperty-drawBase: 0; }}
            QTabBar::tab {{
                background: {aba_inativa}; color: {apagado};
                border: 1px solid {borda}; border-bottom: none;
                padding: 5px 10px; margin-right: 1px;
                min-width: 60px;
            }}
            QTabBar::tab:selected {{
                background: {aba_ativa}; color: {texto};
                border-top: 2px solid {destaque};
            }}
            QTabBar::tab:hover:!selected {{ color: {texto}; }}
            QTabBar QToolButton#fecharAba {{
                border: none; background: transparent; color: {apagado};
                font-size: 13px; font-weight: bold;
                padding: 0px; margin-left: 4px;
                min-width: 14px; max-width: 14px;
                min-height: 14px; max-height: 14px;
            }}
            QTabBar QToolButton#fecharAba:hover {{
                background: {erro}; color: white; border-radius: 7px;
            }}
        """)
        for aba in self.abas():
            aba.aplicar_tema(tema)

    def aplicar_configuracao(self, cfg: dict) -> None:
        self.cfg = cfg
        for aba in self.abas():
            aba.aplicar_configuracao(cfg)
