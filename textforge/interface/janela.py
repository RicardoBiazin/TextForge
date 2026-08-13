"""Janela principal.

Hospeda o gerenciador de abas, a barra de menu gerada do registro de comandos, a
barra de ferramentas, a barra de status e o vigia de alteracao externa.

O que esta janela NAO faz, de proposito: regra de negocio. Abrir arquivo, detectar
codificacao, formatar e buscar sao dos modulos do nucleo; aqui so' se liga o
comando a' funcao e se mostra o resultado. E' o que permite testar encoding, busca
e formatadores sem subir uma QApplication.

Invariante que simplifica tudo: SEMPRE existe pelo menos uma aba. Ao fechar a
ultima, uma aba vazia toma o lugar. Sem isso, cada um dos ~50 comandos precisaria
tratar o caso "nenhum documento aberto".
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QMessageBox, QToolBar, QWidget)

from textforge import (APP, AUTOR, VERSAO, arquivos, codificacao, configuracao,
                       log_interno, recursos, sessao as sessao_mod)
from textforge.documento import Documento
from textforge.editor.indentacao import Indentacao
from textforge.interface import dialogos
from textforge.interface import tema as tema_mod
from textforge.interface.abas import Aba, GerenciadorAbas
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

# Comandos que sao apenas um metodo do editor. Ligar por tabela evita ~15 lambdas
# quase iguais, onde e' facil trocar uma pela outra sem ninguem notar.
DIRETO_NO_EDITOR: dict[str, str] = {
    "editar.desfazer": "undo",
    "editar.refazer": "redo",
    "editar.recortar": "cut",
    "editar.copiar": "copy",
    "editar.colar": "paste",
    "editar.selecionar_tudo": "selectAll",
    "linha.duplicar": "duplicar_linha",
    "linha.excluir": "excluir_linha",
    "indentar.aumentar": "indentar_selecao",
    "indentar.diminuir": "desindentar_selecao",
    "marca.alternar": "alternar_marcador",
    "marca.limpar": "limpar_marcadores",
}


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict, *, restaurar_sessao: bool = False) -> None:
        super().__init__()
        self.cfg = cfg
        self.tema = tema_mod.resolver(cfg.get("tema", "sistema"))

        self.setWindowTitle(APP)
        self.setAcceptDrops(True)          # requisito 19
        self._aplicar_icone()

        self.vinculos = Vinculos(self)
        self.barra = BarraDeStatus(self)
        self.setStatusBar(self.barra)

        self.vigia = Vigia(self)
        self.vigia.mudou.connect(self._ao_mudar_no_disco)
        self.vigia.removido.connect(self._ao_remover_do_disco)

        self.abas = GerenciadorAbas(cfg, self.tema, self)
        self.abas.pode_fechar = self._pode_fechar_aba
        self.abas.montar_menu_do_editor = self.vinculos.menu_de_contexto
        self.abas.documento_trocado.connect(self._ao_trocar_de_aba)
        self.abas.titulo_mudou.connect(self._atualizar_titulo)
        self.abas.posicao_mudou.connect(self.barra.definir_posicao)
        self.abas.selecao_mudou.connect(self.barra.definir_selecao)
        self.setCentralWidget(self.abas)

        self.barra.posicao_clicada.connect(self.ir_para_linha)
        self.barra.indentacao_clicada.connect(self.escolher_tabulacao)
        self.barra.codificacao_clicada.connect(self.escolher_codificacao)
        self.barra.fim_de_linha_clicado.connect(self._escolher_eol)

        self._ligar_comandos()
        self.vinculos.construir_barra_de_menu(self.menuBar())
        self.ferramentas = QToolBar("Ferramentas", self)
        self.ferramentas.setObjectName("barraDeFerramentas")
        self.ferramentas.setMovable(False)
        self.addToolBar(self.ferramentas)
        self.vinculos.construir_barra_de_ferramentas(self.ferramentas)
        self.vinculos.registrar_atalhos_sem_menu()
        self.vinculos.sincronizar_alternaveis(cfg)
        self._montar_menu_de_recentes()
        self._montar_menu_de_linguagens()
        self.barra.linguagem_clicada.connect(self.escolher_linguagem)

        self.aplicar_tema(self.tema)
        self.ferramentas.setVisible(
            bool(cfg.get("mostrar_barra_de_ferramentas", True)))
        self._restaurar_geometria()

        # Trava de sessao e copia de recuperacao (requisitos 16 e 17).
        self.trava = sessao_mod.Trava()
        self._temporizador_de_recuperacao = QTimer(self)
        self._temporizador_de_recuperacao.timeout.connect(self._gravar_recuperacao)

        if restaurar_sessao:
            self._iniciar_sessao()
        if self.abas.count() == 0:
            self.nova_aba()

    # ==================================================================
    # Acesso ao documento e ao editor da aba ativa
    # ==================================================================

    @property
    def documento(self) -> Documento:
        doc = self.abas.documento_atual()
        if doc is None:                     # invariante: sempre ha' uma aba
            aba = self.nova_aba()
            return aba.documento
        return doc

    @property
    def editor(self):
        aba = self.abas.aba_atual()
        if aba is None:
            return self.nova_aba().editor
        return aba.editor

    def _no_editor(self, nome_do_metodo: str) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            getattr(editor, nome_do_metodo)()

    # ==================================================================
    # Construcao
    # ==================================================================

    def _aplicar_icone(self) -> None:
        icone = recursos.raiz() / "icone.ico"
        if icone.is_file():
            self.setWindowIcon(QIcon(str(icone)))

    def _ligar_comandos(self) -> None:
        """Liga o que JA existe. O resto fica desabilitado no menu.

        E' de proposito que o menu mostre os comandos futuros desabilitados em vez
        de escondidos: o usuario ve o que o programa vai ter, e nenhum item
        clicavel finge funcionar.
        """
        from textforge.editor import caixa as cmod
        from textforge.editor import operacoes_linha as ops

        ligacoes: dict[str, object] = {
            "arquivo.sair": self.close,
            "ajuda.sobre": self.mostrar_sobre,
            "ajuda.abrir_log": self.abrir_log,

            # -- arquivo -----------------------------------------------------
            "arquivo.novo": self.nova_aba,
            "arquivo.abrir": self.escolher_e_abrir,
            "arquivo.salvar": self.salvar,
            "arquivo.salvar_como": self.salvar_como,
            "arquivo.salvar_todos": self.salvar_todos,
            "arquivo.recarregar": self.recarregar,
            "arquivo.fechar": self.fechar_aba_atual,
            "arquivo.fechar_todas": self.fechar_todas_as_abas,
            "arquivo.propriedades": self.mostrar_propriedades,
            "arquivo.abrir_local": self.abrir_local_do_arquivo,
            "arquivo.reabrir_como": self.reabrir_como,
            "codificacao.escolher": self.escolher_codificacao,
            "eol.crlf": lambda: self.definir_eol(codificacao.CRLF),
            "eol.lf": lambda: self.definir_eol(codificacao.LF),
            "eol.cr": lambda: self.definir_eol(codificacao.CR),

            # -- edicao ------------------------------------------------------
            "editar.excluir": self.excluir_selecao,
            "editar.copiar_linha": self.copiar_linha,
            "linha.mover_acima": lambda: self.mover_linha(False),
            "linha.mover_abaixo": lambda: self.mover_linha(True),
            "linha.prefixar": self.prefixar_linhas,
            "linha.sufixar": self.sufixar_linhas,

            # -- linguagem ---------------------------------------------------
            "linguagem.detectar": self.redetectar_linguagem,
            "linguagem.texto": self.usar_texto_puro,

            # -- navegacao ---------------------------------------------------
            "ir.linha": self.ir_para_linha,
            "marca.proximo": lambda: self._marcador(True),
            "marca.anterior": lambda: self._marcador(False),

            # -- exibicao ----------------------------------------------------
            "exibir.tela_cheia": self.alternar_tela_cheia,
            "exibir.barra_de_ferramentas": self.alternar_barra_de_ferramentas,
            "exibir.aumentar_zoom": lambda: self.zoom(+1),
            "exibir.diminuir_zoom": lambda: self.zoom(-1),
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

        for id_, metodo in DIRETO_NO_EDITOR.items():
            ligacoes[id_] = (lambda m=metodo: self._no_editor(m))

        por_linhas = {
            "linha.ordenar": lambda l: ops.ordenar(l),
            "linha.ordenar_sem_caixa": lambda l: ops.ordenar(l,
                                                             ignorar_caixa=True),
            "linha.inverter": ops.inverter,
            "linha.remover_duplicadas": lambda l: ops.remover_duplicadas(l),
            "linha.remover_vazias": lambda l: ops.remover_vazias(l),
            "linha.trim_inicio": ops.aparar_inicio,
            "linha.trim_fim": ops.aparar_fim,
        }
        for id_, funcao in por_linhas.items():
            ligacoes[id_] = (lambda f=funcao: self._aplicar_em_linhas(f))
        for id_, funcao in cmod.POR_COMANDO.items():
            ligacoes[id_] = (lambda f=funcao: self._converter_caixa(f))

        self.vinculos.ligar_muitos(ligacoes)

    def _montar_menu_de_linguagens(self) -> None:
        """Preenche o menu Linguagem com os provedores registrados.

        Reconstruido a cada abertura do menu, para refletir o provedor da aba
        atual com a marca de selecao -- e para um plugin que registre uma
        linguagem em tempo de execucao aparecer sem reiniciar o programa.
        """
        menu = self._menu_da_barra("Linguagem")
        if menu is None:
            return
        self._menu_linguagem = menu
        menu.aboutToShow.connect(self._preencher_linguagens)

    def _menu_da_barra(self, titulo: str):
        for acao in self.menuBar().actions():
            if acao.text().replace("&", "") == titulo:
                return acao.menu()
        return None

    def _preencher_linguagens(self) -> None:
        from textforge.linguagens import REGISTRO

        menu = self._menu_linguagem
        menu.clear()
        doc = self.abas.documento_atual()
        atual = doc.nome_da_linguagem if doc else ""

        acao = menu.addAction("Detectar automaticamente")
        acao.triggered.connect(self.redetectar_linguagem)
        acao.setEnabled(bool(doc) and doc.linguagem_manual)
        menu.addSeparator()

        for provedor in sorted(REGISTRO.todos(), key=lambda p: p.nome.lower()):
            item = menu.addAction(provedor.nome)
            item.setCheckable(True)
            item.setChecked(provedor.nome == atual)
            extensoes = " ".join(provedor.extensoes[:6])
            if extensoes:
                item.setToolTip(extensoes)
            item.triggered.connect(
                lambda _c=False, p=provedor: self.definir_linguagem(p))

    def definir_linguagem(self, provedor) -> None:
        aba = self.abas.aba_atual()
        if aba is None:
            return
        aba.documento.definir_linguagem(provedor)
        aba.definir_provedor(provedor)
        self._mostrar_metadados()
        self.barra.showMessage(f"Linguagem: {provedor.nome}", 2000)

    def redetectar_linguagem(self) -> None:
        aba = self.abas.aba_atual()
        if aba is None:
            return
        aba.documento.detectar_linguagem()
        aba.definir_provedor(aba.documento.provedor)
        self._mostrar_metadados()
        self.barra.showMessage(
            f"Linguagem detectada: {aba.documento.nome_da_linguagem}", 2000)

    def usar_texto_puro(self) -> None:
        from textforge.linguagens import REGISTRO

        provedor = REGISTRO.de_texto()
        if provedor is not None:
            self.definir_linguagem(provedor)

    def escolher_linguagem(self) -> None:
        """Clique no campo de linguagem da barra de status."""
        from textforge.linguagens import REGISTRO

        nomes = sorted(p.nome for p in REGISTRO.todos())
        if not nomes:
            return
        doc = self.abas.documento_atual()
        atual = doc.nome_da_linguagem if doc else ""
        escolha = dialogos.escolher(
            self, "Linguagem", "Realce de sintaxe:", nomes,
            nomes.index(atual) if atual in nomes else 0)
        if escolha is None:
            return
        provedor = REGISTRO.por_nome(escolha)
        if provedor is not None:
            self.definir_linguagem(provedor)

    def _montar_menu_de_recentes(self) -> None:
        """Submenu "Arquivos recentes", reconstruido a cada abertura.

        Reconstruir na hora, em vez de manter sincronizado, e' o que garante que a
        lista nunca fique desatualizada em relacao ao config.
        """
        menu_arquivo = None
        for acao in self.menuBar().actions():
            if acao.text().replace("&", "") == "Arquivo":
                menu_arquivo = acao.menu()
                break
        if menu_arquivo is None:
            return
        self._menu_recentes = menu_arquivo.addMenu("Arquivos &recentes")
        self._menu_recentes.aboutToShow.connect(self._preencher_recentes)

    def _preencher_recentes(self) -> None:
        menu = self._menu_recentes
        menu.clear()
        recentes = [r for r in self.cfg.get("recentes", [])
                    if pathlib.Path(r).is_file()]
        if not recentes:
            menu.addAction("(nenhum)").setEnabled(False)
            return
        for i, caminho in enumerate(recentes, start=1):
            nome = pathlib.Path(caminho).name
            acao = menu.addAction(f"&{i}  {nome}")
            acao.setToolTip(caminho)
            acao.triggered.connect(
                lambda _c=False, alvo=caminho: self.abrir_arquivo(alvo))
        menu.addSeparator()
        menu.addAction("Limpar a lista", self._limpar_recentes)

    def _limpar_recentes(self) -> None:
        self.cfg["recentes"] = []
        configuracao.salvar(self.cfg)

    # ==================================================================
    # Tema e configuracao
    # ==================================================================

    def aplicar_tema(self, tema: tema_mod.Tema) -> None:
        """Troca o tema com a janela aberta.

        Funciona porque nenhum widget guarda cor literal: todos pedem por nome ao
        `Tema`. Ver o cabecalho de `tema.py`.
        """
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
        # Trocar a paleta com a janela montada nao repinta sozinho: os widgets
        # guardam as cores resolvidas na ultima polidura do estilo. Sem este
        # ciclo, ir do escuro para o claro deixava o texto dos menus e da barra
        # de status quase branco sobre fundo claro -- ilegivel.
        self._repolir(self)
        self.barra.aplicar_tema(tema)
        self.abas.aplicar_tema(tema)
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

    def alternar_opcao(self, chave: str) -> None:
        """Inverte uma preferencia booleana e reaplica a TODAS as abas."""
        self.cfg[chave] = not bool(self.cfg.get(chave, False))
        self.abas.aplicar_configuracao(self.cfg)
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def alternar_tela_cheia(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def alternar_barra_de_ferramentas(self) -> None:
        visivel = not self.ferramentas.isVisible()
        self.ferramentas.setVisible(visivel)
        self.cfg["mostrar_barra_de_ferramentas"] = visivel

    def zoom(self, passos: int) -> None:
        editor = self.abas.editor_atual()
        if editor is None:
            return
        editor.ajustar_zoom(passos)
        # O zoom e' uma preferencia, nao um estado de aba: as outras abas seguem.
        self.abas.aplicar_configuracao(self.cfg)

    def zoom_normal(self) -> None:
        self.cfg["fonte_tamanho"] = configuracao.padrao()["fonte_tamanho"]
        self.abas.aplicar_configuracao(self.cfg)

    # ==================================================================
    # Abas
    # ==================================================================

    def nova_aba(self) -> Aba:
        return self.abas.adicionar(Documento.novo(self.cfg))

    def _ao_trocar_de_aba(self, aba: Aba | None) -> None:
        if aba is None:
            return
        editor = aba.editor
        # Nada de conectar/desconectar aqui: o gerenciador de abas ja' repassa os
        # sinais SO' da aba ativa (ver `_repassar` em abas.py). Trocar as conexoes
        # a cada aba gerava RuntimeWarning do PySide na primeira troca.
        cursor = editor.textCursor()
        self.barra.definir_posicao(cursor.blockNumber(),
                                   cursor.positionInBlock())
        self._mostrar_metadados()
        editor.setFocus()

    def fechar_aba_atual(self) -> None:
        indice = self.abas.currentIndex()
        if indice >= 0 and self.abas.fechar(indice) and self.abas.count() == 0:
            self.nova_aba()

    def fechar_todas_as_abas(self) -> None:
        if self.abas.fechar_todas():
            self.nova_aba()

    def _pode_fechar_aba(self, aba: Aba) -> bool:
        """Pergunta antes de perder alteracoes de UMA aba."""
        doc = aba.documento
        if not doc.modificado:
            self._desmontar(doc)
            return True
        self.abas.setCurrentWidget(aba)
        escolha = QMessageBox.question(
            self, APP,
            f"<b>{doc.nome}</b> tem alteracoes nao salvas.<br><br>"
            "Salvar antes de fechar?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if escolha == QMessageBox.StandardButton.Cancel:
            return False
        if escolha == QMessageBox.StandardButton.Save and not self.salvar():
            return False
        self._desmontar(doc)
        return True

    def _desmontar(self, doc: Documento) -> None:
        if doc.caminho is not None:
            self.vigia.esquecer(doc.caminho)
        sessao_mod.esquecer_copia(doc)

    # ==================================================================
    # Arquivo
    # ==================================================================

    def escolher_e_abrir(self) -> None:
        atual = self.abas.documento_atual()
        inicial = str(atual.caminho.parent) if (atual and atual.caminho) else ""
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Abrir arquivo(s)", inicial, FILTRO_DE_ARQUIVOS)
        for caminho in caminhos:
            self.abrir_arquivo(caminho)

    def abrir_arquivo(self, caminho: str, linha: int = 0,
                      coluna: int = 0) -> bool:
        """Abre numa aba nova, ou foca a aba que ja' tem este arquivo."""
        try:
            alvo = pathlib.Path(caminho)
            chave = str(alvo.resolve()).lower()
        except OSError:
            chave = str(caminho).lower()
        existente = self.abas.indice_por_chave(chave)
        if existente >= 0:
            self.abas.setCurrentIndex(existente)
            if linha:
                self.abas.editor_atual().ir_para_linha(linha, coluna)
            return True

        try:
            doc = Documento.abrir(caminho, self.cfg)
        except OSError as exc:
            dialogos.avisar(self, f"Nao foi possivel abrir {caminho}.", str(exc))
            return False

        # Uma aba vazia e intocada e' descartada ao abrir um arquivo: senao o
        # usuario acumula "Sem titulo 1" a cada arquivo que abre.
        vazia = self._aba_vazia_descartavel()
        aba = self.abas.adicionar(doc)
        if vazia is not None and vazia is not aba:
            self.abas.removeTab(self.abas.indexOf(vazia))
            vazia.deleteLater()

        if doc.caminho is not None and doc.assinatura is not None:
            self.vigia.acompanhar(doc.caminho, doc.assinatura)
            configuracao.registrar_recente(self.cfg, doc.caminho)
        if doc.binario:
            dialogos.avisar(
                self, f"{doc.nome}: {doc.aviso}",
                "O visualizador hexadecimal entra numa etapa seguinte. O "
                "conteudo NAO foi exibido como texto para nao mostrar "
                "caracteres corrompidos.")
        if linha:
            aba.editor.ir_para_linha(linha, coluna)
        self._mostrar_metadados()
        return True

    def _aba_vazia_descartavel(self) -> Aba | None:
        aba = self.abas.aba_atual()
        if (aba is not None and aba.documento.caminho is None
                and not aba.documento.modificado
                and not aba.documento.texto().strip()):
            return aba
        return None

    def salvar(self) -> bool:
        doc = self.abas.documento_atual()
        if doc is None:
            return False
        if doc.caminho is None:
            return self.salvar_como()
        if doc.somente_leitura:
            dialogos.avisar(self, "Este documento esta' em somente leitura.",
                            doc.aviso)
            return False
        if self.cfg.get("aparar_espaco_final"):
            doc.aparar_espaco_final()
        if doc.fins_de_linha_mistos and not self._confirmar_eol_misto(doc):
            return False
        try:
            doc.salvar()
        except arquivos.AlteradoNoDisco:
            return self._resolver_alteracao_externa(doc, ao_salvar=True)
        except UnicodeEncodeError:
            return self._resolver_perda_ao_salvar(doc)
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
            return False
        self.vigia.confirmar(doc.caminho, doc.assinatura)
        sessao_mod.esquecer_copia(doc)
        self.barra.showMessage(f"Salvo: {doc.nome}", 2000)
        self._mostrar_metadados()
        return True

    def salvar_todos(self) -> bool:
        """Grava todas as abas modificadas. Para na primeira que falhar."""
        atual = self.abas.currentIndex()
        gravadas = 0
        for aba in self.abas.com_pendencias():
            self.abas.setCurrentWidget(aba)
            if not self.salvar():
                self.abas.setCurrentIndex(atual)
                return False
            gravadas += 1
        self.abas.setCurrentIndex(atual)
        self.barra.showMessage(f"{gravadas} arquivo(s) salvo(s)", 2000)
        return True

    def _confirmar_eol_misto(self, doc: Documento) -> bool:
        """Avisa se salvar vai normalizar os fins de linha de um arquivo misto.

        So' pergunta quando a normalizacao e' inevitavel (o numero de linhas
        mudou). Enquanto a correspondencia linha-a-linha existe, o documento
        preserva cada quebra e nao ha' nada a avisar.
        """
        doc.bytes_para_salvar(substituir=True)      # calcula a flag
        if not doc.eol_sera_normalizado:
            return True
        rotulo = codificacao.ROTULO_EOL.get(doc.fim_de_linha, "CRLF")
        return dialogos.confirmar(
            self, "Fins de linha misturados",
            f"Este arquivo tem fins de linha misturados, e as linhas inseridas "
            f"desfizeram a correspondencia com o original.<br><br>"
            f"Salvar agora vai converter TODAS as quebras para <b>{rotulo}</b>. "
            f"Continuar?", perigoso=True)

    def _resolver_perda_ao_salvar(self, doc: Documento) -> bool:
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
        doc = self.abas.documento_atual()
        if doc is None:
            return False
        sugestao = str(doc.caminho) if doc.caminho else doc.nome
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar como", sugestao, FILTRO_DE_ARQUIVOS)
        if not caminho:
            return False
        try:
            doc.salvar_como(caminho)
        except UnicodeEncodeError:
            return self._resolver_perda_ao_salvar(doc)
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel salvar.", str(exc))
            return False
        self.vigia.acompanhar(doc.caminho, doc.assinatura)
        configuracao.registrar_recente(self.cfg, doc.caminho)
        self.abas.atualizar_todos_os_titulos()
        self.barra.showMessage(f"Salvo: {doc.nome}", 2000)
        self._mostrar_metadados()
        return True

    def recarregar(self) -> None:
        doc = self.abas.documento_atual()
        if doc is None or doc.caminho is None:
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
        doc = self.abas.documento_atual()
        if doc is None:
            return
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
            doc.reabrir_como("utf-8-sig" if escolha.endswith("BOM") else codec)
        except (OSError, LookupError) as exc:
            dialogos.avisar(self, "Nao foi possivel reabrir.", str(exc))
            return
        self.editor.setReadOnly(doc.somente_leitura)
        self._mostrar_metadados()

    def escolher_codificacao(self) -> None:
        """Converte a codificacao de GRAVACAO, avisando antes de perder algo."""
        doc = self.abas.documento_atual()
        if doc is None:
            return
        rotulos = [r for _, r in codificacao.OFERECIDAS]
        escolha = dialogos.escolher(self, "Converter codificacao",
                                    "Gravar este arquivo em:", rotulos)
        if escolha is None:
            return
        codec = next(c for c, r in codificacao.OFERECIDAS if r == escolha)
        com_bom = escolha.endswith("BOM")
        alvo = "utf-8" if codec == "utf-8-sig" else codec
        perdas = doc.definir_codificacao(alvo, com_bom=com_bom)
        if perdas:
            resposta = dialogos.confirmar_perda_de_caracteres(self, codec, perdas)
            if resposta == "cancelar":
                return
            if resposta == "utf8":
                doc.definir_codificacao("utf-8", com_bom=False)
            else:
                doc.definir_codificacao(alvo, com_bom=com_bom, substituir=True)
        self._mostrar_metadados()

    def definir_eol(self, fim_de_linha: str) -> None:
        doc = self.abas.documento_atual()
        if doc is not None:
            doc.definir_fim_de_linha(fim_de_linha)
            self._mostrar_metadados()

    def mostrar_propriedades(self) -> None:
        doc = self.abas.documento_atual()
        if doc is not None:
            dialogos.propriedades(self, doc.propriedades())

    def abrir_local_do_arquivo(self) -> None:
        doc = self.abas.documento_atual()
        if doc is None or doc.caminho is None:
            dialogos.avisar(self, "Este documento ainda nao foi salvo.")
            return
        if not arquivos.abrir_no_explorer(doc.caminho):
            dialogos.avisar(self, "Nao foi possivel abrir o Explorer.")

    # ==================================================================
    # Barra de status
    # ==================================================================

    def _mostrar_metadados(self) -> None:
        doc = self.abas.documento_atual()
        if doc is None:
            self.barra.limpar()
            return
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
        self.barra.definir_linguagem(doc.nome_da_linguagem)
        self.barra.definir_aviso(doc.aviso)
        self._atualizar_titulo()

    def _atualizar_titulo(self) -> None:
        doc = self.abas.documento_atual()
        if doc is None:
            self.setWindowTitle(APP)
            return
        marca = "*" if doc.modificado else ""
        local = f" - {doc.caminho.parent}" if doc.caminho else ""
        pendentes = len(self.abas.com_pendencias())
        extra = f"  [{pendentes} nao salvos]" if pendentes > 1 else ""
        self.setWindowTitle(f"{marca}{doc.nome}{local} - {APP}{extra}")

    def _escolher_eol(self) -> None:
        rotulos = ["Windows (CRLF)", "Unix (LF)", "Mac classico (CR)"]
        valores = [codificacao.CRLF, codificacao.LF, codificacao.CR]
        doc = self.abas.documento_atual()
        atual = valores.index(doc.fim_de_linha) if (
            doc and doc.fim_de_linha in valores) else 0
        escolha = dialogos.escolher(self, "Fim de linha", "Gravar usando:",
                                    rotulos, atual)
        if escolha is not None:
            self.definir_eol(valores[rotulos.index(escolha)])

    # ==================================================================
    # Comandos que agem no editor da aba ativa
    # ==================================================================

    def _aplicar_em_linhas(self, funcao) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.aplicar_em_linhas(funcao)

    def _converter_caixa(self, funcao) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.converter_caixa(funcao)

    def _marcador(self, adiante: bool) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.ir_para_marcador(adiante=adiante)

    def mover_linha(self, para_baixo: bool) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.mover_linha(para_baixo=para_baixo)

    def excluir_selecao(self) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.textCursor().removeSelectedText()

    def copiar_linha(self) -> None:
        """Copia a linha inteira sem precisar selecionar (requisito 40)."""
        editor = self.abas.editor_atual()
        if editor is None:
            return
        cursor = editor.textCursor()
        if cursor.hasSelection():
            editor.copy()
            return
        QApplication.clipboard().setText(cursor.block().text() + "\n")
        self.barra.showMessage("Linha copiada", 1500)

    def prefixar_linhas(self) -> None:
        from textforge.editor import operacoes_linha as ops
        texto = dialogos.pedir_texto(self, "Inserir no inicio das linhas",
                                     "Texto a inserir no inicio de cada linha:")
        if texto:
            self._aplicar_em_linhas(lambda l: ops.prefixar(l, texto))

    def sufixar_linhas(self) -> None:
        from textforge.editor import operacoes_linha as ops
        texto = dialogos.pedir_texto(self, "Inserir no fim das linhas",
                                     "Texto a inserir no fim de cada linha:")
        if texto:
            self._aplicar_em_linhas(lambda l: ops.sufixar(l, texto))

    def ir_para_linha(self) -> None:
        editor = self.abas.editor_atual()
        if editor is None:
            return
        escolha = dialogos.pedir_linha(self, editor.document().blockCount(),
                                       editor.textCursor().blockNumber())
        if escolha is None:
            return
        editor.ir_para_linha(*escolha)
        editor.setFocus()

    # -- tabulacao ---------------------------------------------------------

    def definir_tabulacao(self, largura: int) -> None:
        self.cfg["tabulacao"] = largura
        nova = Indentacao(usa_espacos=bool(self.cfg.get("usar_espacos", True)),
                          largura=largura)
        for aba in self.abas.abas():
            aba.editor.definir_indentacao(nova)
            aba.documento.definir_indentacao(nova)
        self._mostrar_metadados()

    def alternar_usar_tab(self) -> None:
        self.cfg["usar_espacos"] = not bool(self.cfg.get("usar_espacos", True))
        self.definir_tabulacao(int(self.cfg.get("tabulacao", 4)))
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def escolher_tabulacao(self) -> None:
        opcoes = ["Espacos: 2", "Espacos: 4", "Espacos: 8",
                  "TAB: 2", "TAB: 4", "TAB: 8"]
        doc = self.abas.documento_atual()
        rotulo = doc.indentacao.rotulo() if doc else "Espacos: 4"
        escolha = dialogos.escolher(
            self, "Indentacao", "Usar:", opcoes,
            opcoes.index(rotulo) if rotulo in opcoes else 1)
        if escolha is None:
            return
        tipo, _, largura = escolha.partition(": ")
        self.cfg["usar_espacos"] = tipo == "Espacos"
        self.definir_tabulacao(int(largura))
        self.vinculos.sincronizar_alternaveis(self.cfg)

    def converter_tab_para_espacos(self) -> None:
        from textforge.editor import indentacao as imod
        editor = self.abas.editor_atual()
        if editor is None:
            return
        largura = editor.indentacao.largura
        editor.aplicar_em_linhas(
            lambda linhas: [imod.tab_para_espacos(l, largura) for l in linhas])

    def converter_espacos_para_tab(self) -> None:
        from textforge.editor import indentacao as imod
        editor = self.abas.editor_atual()
        if editor is None:
            return
        largura = editor.indentacao.largura
        editor.aplicar_em_linhas(
            lambda linhas: [imod.espacos_para_tab(l, largura) for l in linhas])

    # ==================================================================
    # Alteracao externa (requisito 27)
    # ==================================================================

    def _aba_do_caminho(self, caminho: str) -> Aba | None:
        for aba in self.abas.abas():
            if (aba.documento.caminho is not None
                    and str(aba.documento.caminho) == caminho):
                return aba
        return None

    def _ao_mudar_no_disco(self, caminho: str, _assinatura) -> None:
        aba = self._aba_do_caminho(caminho)
        if aba is None:
            return
        self.abas.setCurrentWidget(aba)
        self._resolver_alteracao_externa(aba.documento)

    def _resolver_alteracao_externa(self, doc: Documento, *,
                                    ao_salvar: bool = False) -> bool:
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
        if doc.caminho is not None:
            self.vigia.pausar(doc.caminho)
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
        aba = self._aba_do_caminho(caminho)
        if aba is None:
            return
        self.barra.definir_aviso("O arquivo foi apagado ou renomeado no disco")
        dialogos.avisar(
            self, f"{aba.documento.nome} nao esta' mais no disco.",
            "O conteudo continua aberto aqui. Use Salvar para grava-lo de novo.")

    # ==================================================================
    # Sessao e recuperacao (requisitos 16 e 17)
    # ==================================================================

    def _iniciar_sessao(self) -> None:
        """Oferece a recuperacao e restaura a sessao anterior, nessa ordem.

        A recuperacao vem PRIMEIRO: ela representa trabalho que o usuario pode
        perder, e a sessao e' apenas comodidade.
        """
        if self.trava.sessao_anterior_morreu():
            self._oferecer_recuperacao()
        self.trava.adquirir()
        self._restaurar_sessao()
        intervalo = int(self.cfg.get("recuperacao_intervalo_s", 30))
        if intervalo > 0:
            self._temporizador_de_recuperacao.start(intervalo * 1000)

    def _oferecer_recuperacao(self) -> None:
        recuperaveis = sessao_mod.listar_recuperaveis()
        if not recuperaveis:
            return
        nomes = "<br>".join(
            f"&bull; {r.nome} <span style='color:gray'>({r.quando_texto})"
            f"</span>" for r in recuperaveis[:12])
        if len(recuperaveis) > 12:
            nomes += f"<br>&bull; e mais {len(recuperaveis) - 12}"
        if not dialogos.confirmar(
                self, "Recuperar arquivos",
                f"Existem <b>{len(recuperaveis)}</b> arquivo(s) nao salvo(s) da "
                f"ultima sessao:<br><br>{nomes}<br><br>Deseja recupera-los?"):
            sessao_mod.limpar_recuperacao()
            return
        for r in recuperaveis:
            doc = Documento.novo(self.cfg)
            # A copia guarda BYTES ja' codificados, entao a recuperacao passa pela
            # mesma decodificacao de sempre: um arquivo cp1252 volta cp1252.
            perfil = codificacao.detectar(
                r.bytes_do_conteudo,
                self.cfg.get("codificacao_preferida_legado", "cp1252"))
            doc.definir_texto(perfil.texto, marcar_modificado=True)
            doc.codec = r.codec or perfil.codec
            doc.bom = r.bom
            doc.fim_de_linha = r.fim_de_linha or codificacao.CRLF
            doc.perfil = perfil
            if r.caminho_original:
                doc.caminho = pathlib.Path(r.caminho_original)
                # NAO carrega a assinatura do disco: o arquivo de la' e' a versao
                # ANTIGA, e o conteudo recuperado e' mais novo. Deixar a
                # assinatura vazia faz o primeiro salvamento avisar sobre a
                # diferenca, que e' o comportamento correto.
            else:
                doc.rotulo_sem_titulo = r.nome
            self.abas.adicionar(doc)
        sessao_mod.limpar_recuperacao()
        self.barra.showMessage(
            f"{len(recuperaveis)} arquivo(s) recuperado(s). Confira antes de "
            f"salvar.", 8000)

    def _restaurar_sessao(self) -> None:
        if not self.cfg.get("restaurar_sessao", True):
            return
        sessao = sessao_mod.carregar_sessao()
        vivas = sessao_mod.abas_existentes(sessao)
        if not vivas:
            return
        for estado in vivas:
            if not self.abrir_arquivo(estado.caminho):
                continue
            editor = self.abas.editor_atual()
            if editor is None:
                continue
            cursor = editor.textCursor()
            cursor.setPosition(min(estado.cursor,
                                   editor.document().characterCount() - 1))
            editor.setTextCursor(cursor)
            editor.verticalScrollBar().setValue(estado.rolagem)
        if 0 <= sessao.ativa < self.abas.count():
            self.abas.setCurrentIndex(sessao.ativa)
        log.info("sessao restaurada: %d aba(s)", len(vivas))

    def _capturar_sessao(self) -> sessao_mod.Sessao:
        estados: list[sessao_mod.EstadoDeAba] = []
        for aba in self.abas.abas():
            doc = aba.documento
            if doc.caminho is None:
                continue          # documento sem arquivo vive na recuperacao
            estados.append(sessao_mod.EstadoDeAba(
                caminho=str(doc.caminho),
                cursor=aba.editor.textCursor().position(),
                rolagem=aba.editor.verticalScrollBar().value(),
                codec=doc.codec,
                fim_de_linha=doc.fim_de_linha,
                view=aba.view_atual()))
        return sessao_mod.Sessao(abas=estados,
                                 ativa=max(0, self.abas.currentIndex()))

    def _gravar_recuperacao(self) -> None:
        """Copia de seguranca periodica dos documentos MODIFICADOS."""
        gravados = 0
        for aba in self.abas.com_pendencias():
            doc = aba.documento
            if not sessao_mod.pasta_permitida(doc.caminho, self.cfg):
                continue
            if sessao_mod.gravar_copia(doc) is not None:
                gravados += 1
        if gravados:
            log.debug("copia de recuperacao gravada para %d documento(s)",
                      gravados)

    # ==================================================================
    # Arrastar e soltar (requisito 19)
    # ==================================================================

    def dragEnterEvent(self, evento) -> None:               # noqa: N802 - Qt
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dragMoveEvent(self, evento) -> None:                # noqa: N802 - Qt
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento) -> None:                    # noqa: N802 - Qt
        locais = [u.toLocalFile() for u in evento.mimeData().urls()
                  if u.isLocalFile()]
        if not locais:
            return
        evento.acceptProposedAction()
        pastas = [c for c in locais if pathlib.Path(c).is_dir()]
        arquivos_ = [c for c in locais if not pathlib.Path(c).is_dir()]
        for caminho in arquivos_:
            self.abrir_arquivo(caminho)
        if pastas:
            self.barra.showMessage(
                f"{len(pastas)} pasta(s) ignorada(s): o painel Arquivos entra "
                f"numa etapa seguinte", 4000)

    # ==================================================================
    # Ajuda
    # ==================================================================

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
        if caminho.is_file():
            self.abrir_arquivo(str(caminho))
            return
        dialogos.avisar(self, "O log ainda nao foi criado.",
                        f"Ele sera' gravado em {caminho}")

    # ==================================================================
    # Geometria e fechamento
    # ==================================================================

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
        # A sessao e' capturada ANTES de fechar as abas: depois, nao ha' mais o
        # que gravar.
        instantaneo = self._capturar_sessao()
        if not self.abas.fechar_todas():
            event.ignore()
            return

        self._temporizador_de_recuperacao.stop()
        self.vigia.parar()
        try:
            sessao_mod.salvar_sessao(instantaneo)
        except OSError as exc:
            log.warning("nao foi possivel salvar a sessao: %s", exc)
        self.trava.liberar()

        self.cfg["geometria"] = bytes(
            self.saveGeometry().toBase64()).decode("ascii")
        self.cfg["estado_da_janela"] = bytes(
            self.saveState().toBase64()).decode("ascii")
        try:
            configuracao.salvar(self.cfg)
        except OSError as exc:
            log.warning("nao foi possivel salvar a configuracao: %s", exc)
        super().closeEvent(event)
