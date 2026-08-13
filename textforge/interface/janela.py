"""Janela principal.

Etapa 1: barra de menu inteira gerada do registro de comandos, barra de
ferramentas, barra de status, tema claro/escuro/seguir Windows, zoom e geometria
lembrada. As abas e o editor entram nas etapas 2 e 4.

O que esta janela NAO faz de proposito: ela nao contem regra de negocio. Abrir
arquivo, detectar encoding e formatar sao dos modulos do nucleo; aqui so' se
liga o comando a' funcao e se mostra o resultado.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QMainWindow, QMessageBox, QToolBar, QWidget

from textforge import (APP, AUTOR, VERSAO, arquivos, codificacao, configuracao,
                       log_interno, recursos)
from textforge.documento import Documento
from textforge.editor.indentacao import Indentacao
from textforge.editor.widget import EditorDeTexto
from textforge.interface import dialogos
from textforge.interface import tema as tema_mod
from textforge.interface.barra_de_status import BarraDeStatus
from textforge.interface.menus import Vinculos
from textforge.vigia import Vigia

log = log_interno.obter(__name__)

# Filtro do dialogo de abrir/salvar. A primeira entrada e' a mais util no dia a
# dia; "Todos os arquivos" existe porque um editor de arquivos tecnicos vai ser
# usado em extensao que ninguem previu.
FILTRO_DE_ARQUIVOS = ";;".join([
    "Arquivos de texto e codigo (*.txt *.log *.dat *.csv *.ini *.cfg *.conf"
    " *.env *.json *.xml *.yaml *.yml *.md *.py *.php *.js *.ts *.html *.htm"
    " *.css *.scss *.sql *.bat *.cmd *.ps1 *.sh *.java *.c *.cpp *.h *.cs"
    " *.go *.rs)",
    "Texto (*.txt *.log *.dat)",
    "Dados (*.csv *.json *.xml *.yaml *.yml)",
    "Configuracao (*.ini *.cfg *.conf *.env *.toml)",
    "Codigo (*.py *.php *.js *.ts *.html *.css *.sql *.java *.c *.cpp *.cs)",
    "Scripts (*.bat *.cmd *.ps1 *.sh)",
    "Todos os arquivos (*)",
])


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = cfg
        self.tema = tema_mod.resolver(cfg.get("tema", "sistema"))

        self.setWindowTitle(APP)
        self.setAcceptDrops(True)          # requisito 19; tratado na etapa 4
        self._aplicar_icone()

        self.vinculos = Vinculos(self)
        self.barra = BarraDeStatus(self)
        self.setStatusBar(self.barra)
        # Vigia hibrido de alteracao externa (requisito 27). Criado antes do
        # centro porque `_adotar` ja' registra o documento nele.
        self.vigia = Vigia(self)
        self.vigia.mudou.connect(self._ao_mudar_no_disco)
        self.vigia.removido.connect(self._ao_remover_do_disco)
        # O centro vem ANTES de ligar os comandos: quase todo comando desta etapa
        # aponta para um metodo do editor, que precisa existir antes.
        self._montar_centro()
        self._ligar_editor()

        self._ligar_comandos()
        self.vinculos.construir_barra_de_menu(self.menuBar())
        self.ferramentas = QToolBar("Ferramentas", self)
        self.ferramentas.setObjectName("barraDeFerramentas")
        self.ferramentas.setMovable(False)
        self.addToolBar(self.ferramentas)
        self.vinculos.construir_barra_de_ferramentas(self.ferramentas)
        self.vinculos.registrar_atalhos_sem_menu()
        self.vinculos.sincronizar_alternaveis(cfg)

        self.aplicar_tema(self.tema)
        self.ferramentas.setVisible(
            bool(cfg.get("mostrar_barra_de_ferramentas", True)))
        self._restaurar_geometria()

    # -- construcao --------------------------------------------------------

    def _aplicar_icone(self) -> None:
        icone = recursos.raiz() / "icone.ico"
        if icone.is_file():
            self.setWindowIcon(QIcon(str(icone)))

    def _montar_centro(self) -> None:
        """Area central: um editor. A etapa 4 troca isto por abas."""
        self.documento = Documento.novo(self.cfg)
        self.editor = EditorDeTexto(self.cfg, self.tema, self)
        self.editor.setDocument(self.documento.qt)
        self.editor.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._menu_do_editor)
        self.setCentralWidget(self.editor)

    def _ligar_editor(self) -> None:
        """Conecta o editor a' barra de status."""
        self.editor.posicao_mudou.connect(self.barra.definir_posicao)
        self.editor.selecao_mudou.connect(self.barra.definir_selecao)
        self.editor.zoom_mudou.connect(
            lambda t: self.barra.showMessage(f"Fonte: {t} pt", 1500))
        self.barra.posicao_clicada.connect(self.ir_para_linha)
        self.barra.indentacao_clicada.connect(self.escolher_tabulacao)
        self.barra.codificacao_clicada.connect(self.escolher_codificacao)
        self.barra.fim_de_linha_clicado.connect(self._escolher_eol)
        self.barra.definir_posicao(0, 0)
        self._adotar(self.documento)

    def _escolher_eol(self) -> None:
        """Clique no campo de fim de linha da barra de status."""
        rotulos = ["Windows (CRLF)", "Unix (LF)", "Mac classico (CR)"]
        valores = [codificacao.CRLF, codificacao.LF, codificacao.CR]
        atual = valores.index(self.documento.fim_de_linha) \
            if self.documento.fim_de_linha in valores else 0
        escolha = dialogos.escolher(self, "Fim de linha", "Gravar usando:",
                                    rotulos, atual)
        if escolha is not None:
            self.definir_eol(valores[rotulos.index(escolha)])

    def _menu_do_editor(self, ponto) -> None:
        """Menu de contexto do editor (requisito 20), montado na hora.

        Montar a cada clique, em vez de uma vez, e' o que faz os itens
        refletirem o estado atual (ha' selecao? ha' o que desfazer?) sem
        precisar manter isso sincronizado.
        """
        menu = self.vinculos.menu_de_contexto(self.editor)
        menu.exec(self.editor.viewport().mapToGlobal(ponto))

    def _ligar_comandos(self) -> None:
        """Liga o que JA existe. O resto fica desabilitado no menu.

        E' de proposito que o menu mostre os comandos futuros desabilitados em
        vez de escondidos: o usuario ve o que o programa vai ter, e nenhum item
        clicavel finge funcionar.
        """
        e = self.editor
        ligacoes: dict[str, object] = {
            "arquivo.sair": self.close,
            "ajuda.sobre": self.mostrar_sobre,
            "ajuda.abrir_log": self.abrir_log,

            # -- arquivo -----------------------------------------------------
            "arquivo.novo": self.novo_documento,
            "arquivo.abrir": self.escolher_e_abrir,
            "arquivo.salvar": self.salvar,
            "arquivo.salvar_como": self.salvar_como,
            "arquivo.recarregar": self.recarregar,
            "arquivo.propriedades": self.mostrar_propriedades,
            "arquivo.abrir_local": self.abrir_local_do_arquivo,
            "arquivo.reabrir_como": self.reabrir_como,
            "codificacao.escolher": self.escolher_codificacao,
            "eol.crlf": lambda: self.definir_eol(codificacao.CRLF),
            "eol.lf": lambda: self.definir_eol(codificacao.LF),
            "eol.cr": lambda: self.definir_eol(codificacao.CR),

            # -- edicao basica (o Qt ja' faz; so' expomos nos menus) ---------
            "editar.desfazer": e.undo,
            "editar.refazer": e.redo,
            "editar.recortar": e.cut,
            "editar.copiar": e.copy,
            "editar.colar": e.paste,
            "editar.selecionar_tudo": e.selectAll,
            "editar.excluir": lambda: e.textCursor().removeSelectedText(),
            "editar.copiar_linha": self.copiar_linha,

            # -- linhas e indentacao ----------------------------------------
            "linha.duplicar": e.duplicar_linha,
            "linha.excluir": e.excluir_linha,
            "linha.mover_acima": lambda: e.mover_linha(para_baixo=False),
            "linha.mover_abaixo": lambda: e.mover_linha(para_baixo=True),
            "indentar.aumentar": e.indentar_selecao,
            "indentar.diminuir": e.desindentar_selecao,

            # -- navegacao e marcadores -------------------------------------
            "ir.linha": self.ir_para_linha,
            "marca.alternar": e.alternar_marcador,
            "marca.proximo": lambda: e.ir_para_marcador(adiante=True),
            "marca.anterior": lambda: e.ir_para_marcador(adiante=False),
            "marca.limpar": e.limpar_marcadores,

            # -- exibicao ----------------------------------------------------
            "exibir.tela_cheia": self.alternar_tela_cheia,
            "exibir.barra_de_ferramentas": self.alternar_barra_de_ferramentas,
            "exibir.aumentar_zoom": lambda: e.ajustar_zoom(+1),
            "exibir.diminuir_zoom": lambda: e.ajustar_zoom(-1),
            "exibir.zoom_normal": self.zoom_normal,
            "exibir.quebra_de_linha": lambda: self.alternar_opcao(
                "quebra_de_linha"),
            "exibir.espacos": lambda: self.alternar_opcao("mostrar_espacos"),
            "exibir.fim_de_linha": lambda: self.alternar_opcao(
                "mostrar_fim_de_linha"),
            "exibir.guias": lambda: self.alternar_opcao(
                "mostrar_guias_de_indentacao"),
            "exibir.linha_atual": lambda: self.alternar_opcao(
                "realcar_linha_atual"),

            # -- tabulacao ---------------------------------------------------
            "tab.2": lambda: self.definir_tabulacao(2),
            "tab.4": lambda: self.definir_tabulacao(4),
            "tab.8": lambda: self.definir_tabulacao(8),
            "tab.usar_tab": self.alternar_usar_tab,
            "indentar.tab_para_espacos": self.converter_tab_para_espacos,
            "indentar.espacos_para_tab": self.converter_espacos_para_tab,
        }

        # As operacoes de linha e as conversoes de caixa sao ligadas por tabela:
        # sao 19 comandos que so' diferem pela funcao pura que aplicam, e escrever
        # 19 lambdas na mao seria 19 oportunidades de trocar uma pela outra.
        from textforge.editor import caixa as cmod
        from textforge.editor import operacoes_linha as ops

        por_linhas = {
            "linha.ordenar": lambda l: ops.ordenar(l),
            "linha.ordenar_sem_caixa": lambda l: ops.ordenar(l, ignorar_caixa=True),
            "linha.inverter": ops.inverter,
            "linha.remover_duplicadas": lambda l: ops.remover_duplicadas(l),
            "linha.remover_vazias": lambda l: ops.remover_vazias(l),
            "linha.trim_inicio": ops.aparar_inicio,
            "linha.trim_fim": ops.aparar_fim,
        }
        for id_, funcao in por_linhas.items():
            ligacoes[id_] = (lambda f=funcao: self.editor.aplicar_em_linhas(f))

        for id_, funcao in cmod.POR_COMANDO.items():
            ligacoes[id_] = (lambda f=funcao: self.editor.converter_caixa(f))

        ligacoes["linha.prefixar"] = self.prefixar_linhas
        ligacoes["linha.sufixar"] = self.sufixar_linhas

        self.vinculos.ligar_muitos(ligacoes)

    # -- tema --------------------------------------------------------------

    def aplicar_tema(self, tema: tema_mod.Tema) -> None:
        """Troca o tema com a janela aberta.

        Funciona porque nenhum widget guarda cor literal: todos pedem por nome ao
        `Tema`. Ver o cabecalho de `tema.py`.
        """
        from PySide6.QtWidgets import QApplication

        self.tema = tema
        paleta = tema.qpalette()
        # A paleta vai na QApplication, e nao so' nesta janela: dialogos, menus
        # suspensos e caixas de mensagem sao janelas de nivel superior e nao
        # herdam a paleta do QMainWindow. Sem isto, o tema escuro deixaria o
        # editor escuro e todos os dialogos claros.
        instancia = QApplication.instance()
        if instancia is not None:
            instancia.setPalette(paleta)
        self.setPalette(paleta)

        # Trocar a paleta com a janela ja' montada nao repinta sozinho: os
        # widgets guardam as cores resolvidas na ultima "polidura" do estilo.
        # Sem este ciclo, ir do tema escuro para o claro deixava o texto da barra
        # de menu e da barra de status quase branco sobre fundo claro -- ilegivel.
        self._repolir(self)
        # A barra de status pinta os campos clicaveis por conta propria: um
        # QPushButton plano com folha de estilo nao reresolve `palette(...)`
        # numa troca de tema com a janela aberta.
        self.barra.aplicar_tema(tema)
        editor = getattr(self, "editor", None)
        if editor is not None:
            editor.aplicar_tema(tema)
        log.info("tema aplicado: %s (%s)", tema.nome, tema.tipo)

    def _repolir(self, widget: QWidget) -> None:
        estilo = widget.style()
        estilo.unpolish(widget)
        estilo.polish(widget)
        widget.update()
        for filho in widget.findChildren(QWidget):
            estilo.unpolish(filho)
            estilo.polish(filho)
            filho.update()

    # -- comandos ----------------------------------------------------------

    def alternar_tela_cheia(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def alternar_barra_de_ferramentas(self) -> None:
        visivel = not self.ferramentas.isVisible()
        self.ferramentas.setVisible(visivel)
        self.cfg["mostrar_barra_de_ferramentas"] = visivel

    def alternar_opcao(self, chave: str) -> None:
        """Inverte uma preferencia booleana e reaplica ao editor.

        Um metodo so' para as seis opcoes de exibicao, em vez de seis metodos
        quase iguais: a chave do config e' o unico dado que varia, e ela ja' vem
        declarada no proprio comando (`chave_de_config` em `acoes.py`).
        """
        self.cfg[chave] = not bool(self.cfg.get(chave, False))
        self.editor.aplicar_configuracao(self.cfg)
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def zoom_normal(self) -> None:
        self.cfg["fonte_tamanho"] = configuracao.padrao()["fonte_tamanho"]
        self.editor.aplicar_fonte()

    # -- tabulacao ---------------------------------------------------------

    def definir_tabulacao(self, largura: int) -> None:
        self.cfg["tabulacao"] = largura
        self.editor.definir_indentacao(
            Indentacao(usa_espacos=bool(self.cfg.get("usar_espacos", True)),
                       largura=largura))
        self._mostrar_indentacao()

    def alternar_usar_tab(self) -> None:
        self.cfg["usar_espacos"] = not bool(self.cfg.get("usar_espacos", True))
        self.definir_tabulacao(int(self.cfg.get("tabulacao", 4)))
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def escolher_tabulacao(self) -> None:
        """Chamado pelo clique no campo de indentacao da barra de status."""
        opcoes = ["Espacos: 2", "Espacos: 4", "Espacos: 8",
                  "TAB: 2", "TAB: 4", "TAB: 8"]
        atual = self.editor.indentacao
        rotulo = atual.rotulo()
        escolha = dialogos.escolher(
            self, "Indentacao", "Usar:", opcoes,
            opcoes.index(rotulo) if rotulo in opcoes else 1)
        if escolha is None:
            return
        tipo, _, largura = escolha.partition(": ")
        self.cfg["usar_espacos"] = tipo == "Espacos"
        self.definir_tabulacao(int(largura))
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def _mostrar_indentacao(self) -> None:
        self.barra.definir_indentacao(self.editor.indentacao.usa_espacos,
                                      self.editor.indentacao.largura)

    def converter_tab_para_espacos(self) -> None:
        from textforge.editor import indentacao as imod
        largura = self.editor.indentacao.largura
        self.editor.aplicar_em_linhas(
            lambda linhas: [imod.tab_para_espacos(l, largura) for l in linhas])

    def converter_espacos_para_tab(self) -> None:
        from textforge.editor import indentacao as imod
        largura = self.editor.indentacao.largura
        self.editor.aplicar_em_linhas(
            lambda linhas: [imod.espacos_para_tab(l, largura) for l in linhas])

    # -- linhas ------------------------------------------------------------

    def copiar_linha(self) -> None:
        """Copia a linha inteira sem precisar selecionar (requisito 40)."""
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.editor.copy()
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(cursor.block().text() + "\n")
        self.barra.showMessage("Linha copiada", 1500)

    def prefixar_linhas(self) -> None:
        from textforge.editor import operacoes_linha as ops
        texto = dialogos.pedir_texto(self, "Inserir no inicio das linhas",
                                     "Texto a inserir no inicio de cada linha:")
        if not texto:
            return
        self.editor.aplicar_em_linhas(lambda l: ops.prefixar(l, texto))

    def sufixar_linhas(self) -> None:
        from textforge.editor import operacoes_linha as ops
        texto = dialogos.pedir_texto(self, "Inserir no fim das linhas",
                                     "Texto a inserir no fim de cada linha:")
        if not texto:
            return
        self.editor.aplicar_em_linhas(lambda l: ops.sufixar(l, texto))

    # -- navegacao ---------------------------------------------------------

    def ir_para_linha(self) -> None:
        escolha = dialogos.pedir_linha(
            self, self.editor.document().blockCount(),
            self.editor.textCursor().blockNumber())
        if escolha is None:
            return
        self.editor.ir_para_linha(*escolha)
        self.editor.setFocus()

    def _atualizar_titulo(self) -> None:
        doc = self.documento
        marca = "*" if doc.modificado else ""
        local = f" - {doc.caminho.parent}" if doc.caminho else ""
        self.setWindowTitle(f"{marca}{doc.nome}{local} - {APP}")

    # ==================================================================
    # Arquivo (etapa 3)
    # ==================================================================

    def _adotar(self, doc: Documento) -> None:
        """Passa a editar `doc`: liga o QTextDocument ao editor e a barra."""
        anterior = getattr(self, "documento", None)
        if anterior is not None and anterior.caminho is not None:
            self.vigia.esquecer(anterior.caminho)

        self.documento = doc
        self.editor.setDocument(doc.qt)
        self.editor.setReadOnly(doc.somente_leitura)
        if self.cfg.get("detectar_indentacao", True):
            self.editor.definir_indentacao(doc.indentacao)
        doc.qt.modificationChanged.connect(self._atualizar_titulo)
        doc.metadados_mudaram.connect(self._mostrar_metadados)

        if doc.caminho is not None and doc.assinatura is not None:
            self.vigia.acompanhar(doc.caminho, doc.assinatura)
            configuracao.registrar_recente(self.cfg, doc.caminho)

        self._mostrar_metadados()
        self._atualizar_titulo()
        self.editor.setFocus()

    def _mostrar_metadados(self) -> None:
        doc = self.documento
        perfil = doc.perfil
        self.barra.definir_codificacao(
            perfil.rotulo if perfil else codificacao.ROTULOS.get(doc.codec,
                                                                 doc.codec),
            suspeita=bool(perfil and perfil.suspeito))
        self.barra.definir_fim_de_linha(
            codificacao.ROTULO_EOL.get(doc.fim_de_linha, "CRLF"),
            misto=doc.fins_de_linha_mistos)
        self.barra.definir_indentacao(doc.indentacao.usa_espacos,
                                      doc.indentacao.largura)
        self.barra.definir_linguagem("Texto")
        self.barra.definir_aviso(doc.aviso)
        self._atualizar_titulo()

    def _pode_descartar(self) -> bool:
        """Pergunta antes de perder alteracoes nao salvas."""
        if not self.documento.modificado:
            return True
        escolha = QMessageBox.question(
            self, APP,
            f"<b>{self.documento.nome}</b> tem alteracoes nao salvas.<br><br>"
            "Salvar antes de continuar?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if escolha == QMessageBox.StandardButton.Cancel:
            return False
        if escolha == QMessageBox.StandardButton.Save:
            return self.salvar()
        return True

    def novo_documento(self) -> None:
        if not self._pode_descartar():
            return
        self._adotar(Documento.novo(self.cfg))

    def escolher_e_abrir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        inicial = str(self.documento.caminho.parent) if self.documento.caminho \
            else ""
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir arquivo", inicial, FILTRO_DE_ARQUIVOS)
        if caminho:
            self.abrir_arquivo(caminho)

    def abrir_arquivo(self, caminho: str, linha: int = 0,
                      coluna: int = 0) -> bool:
        if not self._pode_descartar():
            return False
        try:
            doc = Documento.abrir(caminho, self.cfg)
        except OSError as exc:
            dialogos.avisar(self, f"Nao foi possivel abrir {caminho}.", str(exc))
            return False
        self._adotar(doc)
        if doc.binario:
            dialogos.avisar(
                self, f"{doc.nome}: {doc.aviso}",
                "O visualizador hexadecimal entra numa etapa seguinte. "
                "O conteudo NAO foi exibido como texto para nao mostrar "
                "caracteres corrompidos.")
        if linha:
            self.editor.ir_para_linha(linha, coluna)
        return True

    def salvar(self) -> bool:
        """Grava. Devolve False se o usuario cancelou ou algo impediu."""
        doc = self.documento
        if doc.caminho is None:
            return self.salvar_como()
        if doc.somente_leitura:
            dialogos.avisar(self, "Este documento esta' em somente leitura.",
                            doc.aviso)
            return False
        if self.cfg.get("aparar_espaco_final"):
            doc.aparar_espaco_final()
        if doc.fins_de_linha_mistos and not self._confirmar_eol_misto():
            return False
        try:
            doc.salvar()
        except arquivos.AlteradoNoDisco:
            return self._resolver_alteracao_externa(ao_salvar=True)
        except UnicodeEncodeError:
            return self._resolver_perda_ao_salvar()
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
            return False
        self.vigia.confirmar(doc.caminho, doc.assinatura)
        self.barra.showMessage(f"Salvo: {doc.nome}", 2000)
        self._mostrar_metadados()
        return True

    def _confirmar_eol_misto(self) -> bool:
        """Avisa se salvar vai normalizar os fins de linha de um arquivo misto.

        So' pergunta quando a normalizacao e' inevitavel (o numero de linhas
        mudou). Enquanto a correspondencia linha-a-linha existe, o documento
        preserva cada quebra e nao ha' nada a avisar.
        """
        self.documento.bytes_para_salvar(substituir=True)   # calcula a flag
        if not self.documento.eol_sera_normalizado:
            return True
        rotulo = codificacao.ROTULO_EOL.get(self.documento.fim_de_linha, "CRLF")
        return dialogos.confirmar(
            self, "Fins de linha misturados",
            f"Este arquivo tem fins de linha misturados, e as linhas inseridas "
            f"desfizeram a correspondencia com o original.<br><br>"
            f"Salvar agora vai converter TODAS as quebras para <b>{rotulo}</b>. "
            f"Continuar?", perigoso=True)

    def _resolver_perda_ao_salvar(self) -> bool:
        doc = self.documento
        perdas = codificacao.conferir_conversao(doc.texto(), doc.codec)
        escolha = dialogos.confirmar_perda_de_caracteres(self, doc.codec, perdas)
        if escolha == "cancelar":
            return False
        if escolha == "utf8":
            doc.codec, doc.bom = "utf-8", b""
            return self.salvar()
        try:
            doc.salvar(substituir_incompativeis=True)
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
            return False
        self.vigia.confirmar(doc.caminho, doc.assinatura)
        self._mostrar_metadados()
        return True

    def salvar_como(self) -> bool:
        from PySide6.QtWidgets import QFileDialog
        doc = self.documento
        sugestao = str(doc.caminho) if doc.caminho else doc.nome
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar como", sugestao, FILTRO_DE_ARQUIVOS)
        if not caminho:
            return False
        try:
            doc.salvar_como(caminho)
        except UnicodeEncodeError:
            return self._resolver_perda_ao_salvar()
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
            return False
        self.vigia.acompanhar(doc.caminho, doc.assinatura)
        configuracao.registrar_recente(self.cfg, doc.caminho)
        self.barra.showMessage(f"Salvo: {doc.nome}", 2000)
        self._mostrar_metadados()
        return True

    def recarregar(self) -> None:
        doc = self.documento
        if doc.caminho is None:
            return
        if doc.modificado and not dialogos.confirmar(
                self, "Recarregar",
                f"<b>{doc.nome}</b> tem alteracoes nao salvas.<br><br>"
                "Recarregar do disco vai descarta-las. Continuar?",
                perigoso=True):
            return
        try:
            doc.recarregar()
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel recarregar.", str(exc))
            return
        self.editor.setReadOnly(doc.somente_leitura)
        self.vigia.confirmar(doc.caminho, doc.assinatura)
        self._mostrar_metadados()
        self.barra.showMessage("Recarregado do disco", 2000)

    def reabrir_como(self) -> None:
        doc = self.documento
        if doc.caminho is None:
            dialogos.avisar(self, "Este documento ainda nao foi salvo.",
                            "Nao ha' arquivo no disco para reler.")
            return
        if doc.modificado and not dialogos.confirmar(
                self, "Reabrir com outra codificacao",
                "As alteracoes nao salvas serao descartadas. Continuar?",
                perigoso=True):
            return
        rotulos = [r for _, r in codificacao.OFERECIDAS]
        escolha = dialogos.escolher(self, "Reabrir como",
                                    "Ler o arquivo usando:", rotulos)
        if escolha is None:
            return
        codec = next(c for c, r in codificacao.OFERECIDAS if r == escolha)
        try:
            doc.reabrir_como(codec)
        except (OSError, LookupError) as exc:
            dialogos.avisar(self, "Nao foi possivel reabrir.", str(exc))
            return
        self.editor.setReadOnly(doc.somente_leitura)
        self._mostrar_metadados()

    def escolher_codificacao(self) -> None:
        """Converte a codificacao de GRAVACAO, avisando antes de perder algo."""
        doc = self.documento
        rotulos = [r for _, r in codificacao.OFERECIDAS]
        escolha = dialogos.escolher(self, "Converter codificacao",
                                    "Gravar este arquivo em:", rotulos)
        if escolha is None:
            return
        codec = next(c for c, r in codificacao.OFERECIDAS if r == escolha)
        com_bom = escolha.endswith("BOM")
        perdas = doc.definir_codificacao(
            "utf-8" if codec == "utf-8-sig" else codec, com_bom=com_bom)
        if perdas:
            resposta = dialogos.confirmar_perda_de_caracteres(self, codec, perdas)
            if resposta == "cancelar":
                return
            if resposta == "utf8":
                doc.definir_codificacao("utf-8", com_bom=False)
            else:
                doc.definir_codificacao(
                    "utf-8" if codec == "utf-8-sig" else codec,
                    com_bom=com_bom, substituir=True)
        self._mostrar_metadados()

    def definir_eol(self, fim_de_linha: str) -> None:
        self.documento.definir_fim_de_linha(fim_de_linha)
        self._mostrar_metadados()

    def mostrar_propriedades(self) -> None:
        dialogos.propriedades(self, self.documento.propriedades())

    def abrir_local_do_arquivo(self) -> None:
        doc = self.documento
        if doc.caminho is None:
            dialogos.avisar(self, "Este documento ainda nao foi salvo.")
            return
        if not arquivos.abrir_no_explorer(doc.caminho):
            dialogos.avisar(self, "Nao foi possivel abrir o Explorer.")

    # ==================================================================
    # Alteracao externa (requisito 27)
    # ==================================================================

    def _ao_mudar_no_disco(self, caminho: str, _assinatura) -> None:
        if (self.documento.caminho is None
                or str(self.documento.caminho) != caminho):
            return
        self._resolver_alteracao_externa()

    def _resolver_alteracao_externa(self, *, ao_salvar: bool = False) -> bool:
        doc = self.documento
        escolha = dialogos.alteracao_externa(
            self, doc.nome, doc.descrever_mudanca_externa(), doc.modificado)
        if escolha == "recarregar":
            try:
                doc.recarregar()
            except OSError as exc:
                dialogos.avisar(self, "Nao foi possivel recarregar.", str(exc))
                return False
            self.editor.setReadOnly(doc.somente_leitura)
            self.vigia.confirmar(doc.caminho, doc.assinatura)
            self._mostrar_metadados()
            return False
        if escolha == "comparar":
            dialogos.avisar(
                self, "Comparar arquivos entra numa etapa seguinte.",
                "Por enquanto, escolha Recarregar ou Manter a minha versao.")
            return False
        # "manter": pausa o aviso para este arquivo e, se veio de um salvamento,
        # grava por cima -- foi uma escolha explicita do usuario.
        self.vigia.pausar(doc.caminho) if doc.caminho else None
        if ao_salvar:
            try:
                doc.salvar(forcar=True)
            except OSError as exc:
                dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
                return False
            self.vigia.confirmar(doc.caminho, doc.assinatura)
            self.vigia.retomar(doc.caminho)
            self.barra.showMessage(f"Salvo: {doc.nome}", 2000)
            self._mostrar_metadados()
            return True
        return False

    def _ao_remover_do_disco(self, caminho: str) -> None:
        if (self.documento.caminho is None
                or str(self.documento.caminho) != caminho):
            return
        self.barra.definir_aviso("O arquivo foi apagado ou renomeado no disco")
        dialogos.avisar(
            self, f"{self.documento.nome} nao esta' mais no disco.",
            "O conteudo continua aberto aqui. Use Salvar para grava-lo de novo.")

    # ==================================================================
    # Arrastar e soltar (requisito 19)
    # ==================================================================

    def dragEnterEvent(self, evento) -> None:               # noqa: N802 - Qt
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento) -> None:                    # noqa: N802 - Qt
        locais = [u.toLocalFile() for u in evento.mimeData().urls()
                  if u.isLocalFile()]
        if not locais:
            return
        evento.acceptProposedAction()
        # Uma aba so' nesta etapa: abre o primeiro e avisa sobre o resto, em vez
        # de descartar em silencio os arquivos que o usuario arrastou.
        self.abrir_arquivo(locais[0])
        if len(locais) > 1:
            self.barra.showMessage(
                f"{len(locais) - 1} arquivo(s) ignorado(s): as abas entram na "
                f"etapa 4", 4000)

    def mostrar_sobre(self) -> None:
        QMessageBox.about(
            self, f"Sobre o {APP}",
            f"<h3>{APP} {VERSAO}</h3>"
            f"<p>Editor de arquivos tecnicos: texto, codigo-fonte, "
            f"configuracao e dados.</p>"
            f"<p>Nao executa o conteudo dos arquivos que abre.</p>"
            f"<p>{AUTOR} &middot; licenca MIT<br>"
            f"Interface em PySide6 (Qt for Python), LGPLv3.</p>")

    def abrir_log(self) -> None:
        caminho = configuracao.caminho_log()
        QMessageBox.information(
            self, "Log de diagnostico",
            f"O log fica em:<br><code>{caminho}</code><br><br>"
            "Ele registra caminhos, tamanhos e erros &mdash; nunca o conteudo "
            "dos seus arquivos.")

    # -- geometria ---------------------------------------------------------

    def _restaurar_geometria(self) -> None:
        bruto = self.cfg.get("geometria") or ""
        if bruto:
            try:
                if self.restoreGeometry(
                        QByteArray.fromBase64(bruto.encode("ascii"))):
                    self._restaurar_estado()
                    return
            except Exception:        # noqa: BLE001 - geometria invalida no config
                log.warning("geometria gravada ilegivel; usando o tamanho padrao")
        self.resize(1100, 720)

    def _restaurar_estado(self) -> None:
        bruto = self.cfg.get("estado_da_janela") or ""
        if not bruto:
            return
        try:
            self.restoreState(QByteArray.fromBase64(bruto.encode("ascii")))
        except Exception:            # noqa: BLE001
            log.warning("estado da janela ilegivel; ignorando")

    def closeEvent(self, event: QCloseEvent) -> None:       # noqa: N802 - Qt
        if not self._pode_descartar():
            event.ignore()
            return
        self.vigia.parar()
        self.cfg["geometria"] = bytes(
            self.saveGeometry().toBase64()).decode("ascii")
        self.cfg["estado_da_janela"] = bytes(
            self.saveState().toBase64()).decode("ascii")
        try:
            configuracao.salvar(self.cfg)
        except OSError as exc:
            # Nunca impedir o fechamento por causa das preferencias.
            log.warning("nao foi possivel salvar a configuracao: %s", exc)
        super().closeEvent(event)
