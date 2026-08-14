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

from textforge import (APP, AUTOR, VERSAO, arquivos, busca, codificacao,
                       configuracao, log_interno, recursos,
                       sessao as sessao_mod)
from textforge import busca_em_arquivos as bfa
from textforge.documento import Documento
from textforge.editor.indentacao import Indentacao
from textforge.interface import acoes, dialogos
from textforge.interface import tema as tema_mod
from textforge.interface.abas import Aba, GerenciadorAbas
from textforge.interface.barra_de_busca import BarraDeBusca
from textforge.interface.barra_de_status import BarraDeStatus
from textforge.interface.menus import Vinculos
from textforge.interface.painel_estrutura import PainelEstrutura
from textforge.interface.painel_problemas import PainelProblemas, Problema
from textforge.interface.painel_resultados import PainelResultados
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
        # A janela GARANTE a propria dependencia, em vez de confiar que quem a
        # construiu registrou as linguagens. A chamada e' idempotente.
        from textforge import linguagens
        linguagens.carregar_embutidos()

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
        self.abas.indexacao_andou.connect(self._ao_indexar_arquivo_grande)
        self.abas.indexacao_terminou.connect(self._ao_terminar_indexacao)
        # `_montar_busca` troca o widget central por um container com as abas e a
        # barra de busca embutida, entao vem ANTES do painel Estrutura.
        self._montar_busca()
        self._montar_painel_estrutura()
        self._montar_painel_problemas()
        self._faixas_da_busca: list[busca.Faixa] = []

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
        self.barra.visualizador_clicado.connect(self.alternar_modo_tabela)

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
        # Em `recursos/`, e nao na raiz do projeto: aquela pasta inteira ja' vai
        # para dentro do .exe pelo `datas` do .spec, entao o icone funciona no
        # fonte e no empacotado sem nenhuma regra a mais.
        icone = recursos.caminho("icone.ico")
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

            # -- formatadores (requisito 6) -----------------------------------
            "formatar.documento": self.formatar_documento,
            "formatar.selecao": self.formatar_selecao,
            "formatar.compactar": self.compactar_documento,
            "formatar.validar": self.validar_documento,
            "formatar.ir_para_erro": self.ir_para_erro,
            "formatar.ordenar_chaves": self.formatar_ordenando,
            "exibir.painel_problemas": self.alternar_painel_problemas,

            # -- visualizadores (requisito 6, item CSV) -----------------------
            "ferramentas.tabela_csv": self.alternar_modo_tabela,
            # -- acompanhar log (requisito 26) --------------------------------
            "ferramentas.acompanhar": self.alternar_acompanhamento,

            # -- extras (requisitos 24 e 25) ----------------------------------
            "editar.comentar": self.alternar_comentario,
            "ferramentas.paleta": self.abrir_paleta,
            "ferramentas.abertura_rapida": self.abertura_rapida,
            "ferramentas.configuracoes": self.abrir_configuracoes,
            "ajuda.atalhos": self.mostrar_atalhos,

            # -- busca (requisito 8) -----------------------------------------
            "buscar.localizar": lambda: self.abrir_busca(),
            "buscar.substituir": lambda: self.abrir_busca(com_substituicao=True),
            "buscar.proximo": lambda: self._repetir_busca(False),
            "buscar.anterior": lambda: self._repetir_busca(True),
            "buscar.em_arquivos": self.pesquisar_em_arquivos,
            "buscar.contar": self.contar_ocorrencias,
            "buscar.selecionar_ocorrencias": self.selecionar_ocorrencias,

            # -- navegacao ---------------------------------------------------
            "ir.linha": self.ir_para_linha,
            "ir.par": self.ir_para_par,
            "exibir.painel_estrutura": self.alternar_painel_estrutura,
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

        from textforge.servicos import conversoes, hashes
        for id_, funcao in conversoes.POR_COMANDO.items():
            ligacoes[id_] = (lambda f=funcao, i=id_: self._converter(f, i))
        for id_, nome in hashes.POR_COMANDO.items():
            ligacoes[id_] = (lambda a=nome: self.calcular_hash(a))

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
        for atributo in ("painel_estrutura", "barra_de_busca",
                         "painel_resultados", "painel_problemas"):
            widget = getattr(self, atributo, None)
            if widget is not None:
                widget.aplicar_tema(tema)
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
        # A marca de "Acompanhar" e' POR ABA, e nao uma preferencia global: com
        # duas abas abertas, uma acompanhando e outra nao, o menu tem de refletir a
        # que esta' na frente.
        self._marcar_acompanhamento(aba.tem_view("tail"))
        if aba.view_atual() == "tail":
            self._mostrar_metadados()
            aba.view("tail").setFocus()
            return
        if aba.view_atual() == "grande":
            visor = aba.visor_grande.visor
            self.barra.definir_posicao(visor.linha_atual, 0)
            self._mostrar_metadados()
            visor.setFocus()
            return
        editor = aba.editor
        # Nada de conectar/desconectar aqui: o gerenciador de abas ja' repassa os
        # sinais SO' da aba ativa (ver `_repassar` em abas.py). Trocar as conexoes
        # a cada aba gerava RuntimeWarning do PySide na primeira troca.
        cursor = editor.textCursor()
        self.barra.definir_posicao(cursor.blockNumber(),
                                   cursor.positionInBlock())
        self._mostrar_metadados()
        if self.doca_estrutura.isVisible():
            self.painel_estrutura.acompanhar(aba.documento)
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
        # Celulas editadas na grade e nunca aplicadas ao texto: sem isto, a aba
        # fecharia sem sequer PERGUNTAR, porque o documento nao esta' modificado.
        self._sincronizar_visualizador(aba)
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
        # O mmap do modo de arquivo grande NAO e' liberado aqui: quem faz isso e'
        # `Aba.encerrar()`, que roda depois e sabe cancelar a thread de indexacao
        # antes de fechar o mapeamento. Fechar o mmap com o worker lendo dele
        # produziria um ValueError na thread de disco.

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
                self._ir_para_linha_na_aba(linha, coluna)
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
            self._ir_para_linha_na_aba(linha, coluna)
        self._mostrar_metadados()
        return True

    def _ir_para_linha_na_aba(self, linha: int, coluna: int = 0) -> None:
        """Leva o cursor a uma linha, seja qual for a view da aba.

        Usado pelo `--line` da linha de comando, pelo painel Resultados e pelo
        painel Problemas. `linha` chega em BASE ZERO, como no resto do nucleo.
        """
        visor = self.visor_grande()
        if visor is not None:
            visor.ir_para_linha(linha)
            visor.setFocus()
            return
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.ir_para_linha(linha, coluna)

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
        # Salvar com a grade aberta grava o que esta' na GRADE. Sem isto, editar
        # celulas e apertar Ctrl+S gravaria o texto de antes das edicoes.
        self._sincronizar_visualizador()
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
        aba = self.abas.aba_atual()
        self.barra.definir_visualizador(
            aba.view_atual() if aba else "texto",
            disponivel=self._oferece_tabela(aba))
        self._atualizar_titulo()

    # ==================================================================
    # Modo de arquivo grande (requisito 15)
    # ==================================================================

    def visor_grande(self):
        """O `VisorDeArquivoGrande` da aba ativa, ou None.

        Os comandos que existem nos dois mundos (ir para linha, pesquisar,
        copiar) consultam isto ANTES de pegar o editor. E' um `if` por comando, e
        e' o preco de o modo de arquivo grande nao ter um QTextDocument -- muito
        menor que o de manter duas janelas diferentes.
        """
        aba = self.abas.aba_atual()
        if aba is None or aba.visor_grande is None:
            return None
        return aba.visor_grande.visor if aba.view_atual() == "grande" else None

    def _ao_indexar_arquivo_grande(self, varrido: int, total: int) -> None:
        self.barra.mostrar_progresso(varrido, total)
        self.barra.definir_aviso(
            f"Indexando... {varrido * 100 // max(1, total)}% "
            f"({self.documento.total_de_linhas():,} linhas ate' agora)"
            .replace(",", "."))

    def _ao_terminar_indexacao(self, linhas: int) -> None:
        self.barra.esconder_progresso()
        self.barra.definir_aviso("")
        self.barra.showMessage(f"Indice completo: {linhas:,} linhas"
                               .replace(",", "."), 4000)
        self._mostrar_metadados()

    def _buscar_no_arquivo_grande(self, criterio: busca.Criterio) -> None:
        """Pesquisa num arquivo grande: em thread, com resultados em streaming.

        A barra de busca embutida nao serve aqui -- ela trabalha com `QTextCursor`
        sobre um QTextDocument que, neste modo, esta' vazio de proposito. Os
        achados vao para o painel Resultados, que ja' e' clicavel, cancelavel e
        preparado para receber em lotes.
        """
        from textforge import tarefas
        from textforge.busca_em_arquivos import Resultado, Resumo

        visor = self.visor_grande()
        if visor is None or self._criterio_valido(criterio) is None:
            return
        padrao = criterio.compilar()
        fonte = visor.fonte
        caminho = str(fonte.caminho)
        # Realce imediato nas linhas JA visiveis: o resultado completo pode levar
        # segundos num arquivo de 1 GB, e ver o termo aceso na tela na hora e' o
        # que diz ao usuario que a busca entendeu o que ele pediu.
        visor.definir_realce(padrao)

        def trabalho(tarefa: tarefas.Tarefa) -> tuple[list, Resumo]:
            achados: list[Resultado] = []
            cortado = False
            for achado in fonte.buscar(padrao, 0, cancelar=tarefa.cancelada):
                tarefa.checar_cancelamento()
                achados.append(Resultado(caminho=fonte.caminho,
                                         linha=achado.linha,
                                         coluna=achado.inicio,
                                         tamanho=achado.fim - achado.inicio,
                                         trecho=achado.texto[:400]))
                if len(achados) >= bfa.LIMITE_DE_RESULTADOS:
                    # Teto declarado, e nao truncamento silencioso: um termo comum
                    # num log de 1 GB tem milhoes de ocorrencias, e enche-las numa
                    # arvore da interface derrubaria o programa. O `cortado` faz o
                    # painel dizer que parou.
                    cortado = True
                    break
                tarefa.progresso(len(achados), -1)
            return achados, Resumo(arquivos_lidos=1, arquivos_com_ocorrencia=1,
                                   ocorrencias=len(achados), cortado=cortado)

        self._cancelar_busca()
        self.doca_resultados.show()
        self.painel_resultados.comecar(criterio.descricao(), caminho)
        tarefa = tarefas.Tarefa(f"buscar em {fonte.caminho.name}", trabalho)
        tarefa.sinais.concluido.connect(self._busca_concluida)
        tarefa.sinais.cancelado.connect(self.painel_resultados.cancelado)
        tarefa.sinais.erro.connect(self.painel_resultados.falhou)
        tarefa.sinais.progresso.connect(
            lambda feito, _t: self.barra.mostrar_progresso(feito, -1))
        tarefa.sinais.terminou.connect(self.barra.esconder_progresso)
        self._tarefa_de_busca = tarefa
        tarefas.rodar(tarefa, disco=True)

    # ==================================================================
    # Acompanhar log ao vivo (requisito 26)
    # ==================================================================

    def alternar_acompanhamento(self) -> None:
        aba = self.abas.aba_atual()
        if aba is None:
            return
        if aba.tem_view("tail"):
            self.parar_acompanhamento()
        else:
            self.iniciar_acompanhamento()

    def iniciar_acompanhamento(self) -> bool:
        from textforge.visualizadores.registro_ao_vivo import VisualizadorAoVivo

        aba = self.abas.aba_atual()
        if aba is None:
            return False
        doc = aba.documento
        if doc.caminho is None:
            dialogos.avisar(
                self, "Este documento ainda nao foi salvo.",
                "Acompanhar alteracoes precisa de um arquivo no disco. Salve o "
                "arquivo primeiro, ou abra o .log que voce quer acompanhar.")
            self._marcar_acompanhamento(False)
            return False
        if doc.modificado:
            # Acompanhar um arquivo com edicoes pendentes e' pedir para perde-las:
            # a view ao vivo mostra o DISCO, e o que esta' na memoria nao esta' la'.
            if not dialogos.confirmar(
                    self, "Acompanhar alteracoes",
                    f"<b>{doc.nome}</b> tem alteracoes nao salvas.<br><br>"
                    "O acompanhamento mostra o que esta' no DISCO, e nao o que "
                    "voce editou. Suas alteracoes continuam na aba de texto. "
                    "Continuar?"):
                self._marcar_acompanhamento(False)
                return False

        vista = VisualizadorAoVivo(doc.caminho, doc.codec, self.cfg, self.tema, aba)
        aba.registrar_view("tail", vista)
        aba.trocar_para("tail")
        vista.iniciar()
        # Enquanto o tail roda, o vigia de alteracao externa fica CALADO para este
        # arquivo: um log ativo muda a cada segundo, e o dialogo "alterado no
        # disco" apareceria sem parar sobre a view que existe justamente para
        # mostrar essa mudanca.
        self.vigia.pausar(doc.caminho)
        self._marcar_acompanhamento(True)
        self.barra.showMessage(f"Acompanhando {doc.nome}", 4000)
        self._mostrar_metadados()
        return True

    def parar_acompanhamento(self) -> None:
        aba = self.abas.aba_atual()
        if aba is None or not aba.tem_view("tail"):
            return
        doc = aba.documento
        # De volta a' view de origem: um arquivo grande volta para o visor, um
        # arquivo normal volta para o editor.
        aba.trocar_para("grande" if aba.tem_view("grande") else "texto")
        aba.remover_view("tail")
        if doc.caminho is not None:
            # O vigia volta a avisar -- mas com a assinatura ATUAL, senao o
            # primeiro aviso seria sobre as linhas que o proprio tail ja' mostrou.
            self.vigia.confirmar(doc.caminho,
                                 arquivos.Assinatura.de_caminho(doc.caminho))
            self.vigia.retomar(doc.caminho)
        self._marcar_acompanhamento(False)
        self.barra.showMessage("Acompanhamento encerrado", 3000)
        self._mostrar_metadados()

    def _marcar_acompanhamento(self, ligado: bool) -> None:
        """Mantem a marca do item de menu em sincronia com o estado real.

        O item e' `alternavel` sem chave de configuracao: o estado NAO e' uma
        preferencia salva, e' o que esta' acontecendo nesta aba. Sem isto, cancelar
        o dialogo de confirmacao deixaria o menu marcado para um acompanhamento que
        nunca comecou.
        """
        qacao = self.vinculos.qacao("ferramentas.acompanhar")
        if qacao is not None:
            qacao.setChecked(ligado)

    # ==================================================================
    # Modo tabela do CSV (requisito 6, item CSV)
    # ==================================================================

    def _oferece_tabela(self, aba: Aba | None) -> bool:
        """Mostrar a alternancia Texto <-> Tabela na barra de status?

        A resposta vem do PROVEDOR (`visualizador_preferido()`), e nao de uma
        analise do conteudo. `_mostrar_metadados` roda em toda troca de aba, todo
        salvamento e toda mudanca de codificacao; farejar o texto ali custaria uma
        varredura do documento inteiro a cada uma dessas vezes, para responder algo
        que a extensao ja' responde.

        O `.dat` tabular, que nao tem provedor de CSV, continua atendido: o item
        "Modo tabela (CSV)" do menu Ferramentas esta' sempre ativo e faz a deteccao
        na hora -- pagando o custo uma vez, quando o usuario pediu.
        """
        if aba is None or aba.view_atual() == "grande":
            # Um CSV de 1 GB nao vira grade: montar a tabela exige o texto inteiro
            # em memoria, que e' exatamente o que o modo de arquivo grande evita.
            return False
        if aba.view_atual() == "tabela":
            return True
        provedor = aba.documento.provedor
        return (provedor is not None
                and provedor.visualizador_preferido() == "tabela")

    def alternar_modo_tabela(self) -> None:
        aba = self.abas.aba_atual()
        if aba is None:
            return
        if aba.view_atual() == "tabela":
            self.voltar_ao_modo_texto()
        else:
            self.abrir_modo_tabela()

    def abrir_modo_tabela(self) -> bool:
        from textforge.analisadores import de_csv
        from textforge.visualizadores.tabela_csv import VisualizadorCsv

        aba = self.abas.aba_atual()
        if aba is None:
            return False
        texto = aba.documento.texto()
        dialeto = de_csv.detectar(texto)
        if dialeto.colunas < 2:
            dialogos.avisar(
                self, "Este arquivo nao parece uma tabela.",
                "O TextForge nao encontrou um delimitador consistente "
                f"({dialeto.como_decidiu}). O modo tabela precisa de pelo menos "
                "duas colunas separadas por ; , TAB | ou dois-pontos.")
            return False

        # A tabela e' construida do texto ATUAL e descartada ao voltar. Guardar a
        # tabela entre trocas de modo faria a proxima abertura mostrar o conteudo
        # de antes das edicoes feitas em modo texto.
        vista = VisualizadorCsv(texto, dialeto, aba)
        vista.voltar_para_texto.connect(self.voltar_ao_modo_texto)
        if aba.documento.somente_leitura:
            from PySide6.QtWidgets import QAbstractItemView
            vista.tabela.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
        vista.aplicar_tema(self.tema)
        aba.registrar_view("tabela", vista)
        aba.trocar_para("tabela")
        self.barra.showMessage(f"Modo tabela — {dialeto.descrever()}", 5000)
        self._mostrar_metadados()
        return True

    def voltar_ao_modo_texto(self) -> bool:
        """Aplica o que foi editado na grade e volta ao editor.

        A escrita de volta e' UM `QTextCursor` com `beginEditBlock`: desfazer uma
        sessao inteira de edicao na tabela e' um Ctrl+Z so'. E se nada foi
        editado, NADA e' escrito -- o documento nao fica marcado como modificado
        por ter sido apenas OLHADO em outra forma.
        """
        from PySide6.QtGui import QTextCursor

        aba = self.abas.aba_atual()
        if aba is None or aba.view_atual() != "tabela":
            return False
        vista = aba.view("tabela")
        editor = aba.editor

        if vista is not None and vista.alterado:
            if aba.documento.somente_leitura:
                dialogos.avisar(self, "Este documento esta' em somente leitura.",
                                aba.documento.aviso)
            else:
                cursor = QTextCursor(editor.document())
                cursor.select(QTextCursor.SelectionType.Document)
                cursor.beginEditBlock()
                try:
                    cursor.insertText(vista.para_texto())
                finally:
                    cursor.endEditBlock()
                self.barra.showMessage("Alteracoes da tabela aplicadas", 3000)

        aba.trocar_para("texto")
        aba.remover_view("tabela")
        self._mostrar_metadados()
        return True

    def _sincronizar_visualizador(self, aba: Aba | None = None) -> None:
        """Traz para o documento o que estiver pendente numa view alternativa.

        Chamado antes de salvar e antes de fechar: o requisito e' que a
        sincronizacao aconteca em ATO DO USUARIO (troca de modo, salvar, fechar) e
        nao a cada tecla digitada na grade -- reconstruir um CSV de 200 mil
        registros por tecla e' inviavel.
        """
        aba = aba if aba is not None else self.abas.aba_atual()
        if aba is None or aba.view_atual() != "tabela":
            return
        vista = aba.view("tabela")
        if vista is None or not vista.alterado:
            return
        from PySide6.QtGui import QTextCursor
        cursor = QTextCursor(aba.editor.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.beginEditBlock()
        try:
            cursor.insertText(vista.para_texto())
        finally:
            cursor.endEditBlock()
        vista.modelo.confirmar_gravacao()

    # ==================================================================
    # Formatadores (requisito 6)
    # ==================================================================

    def _montar_painel_problemas(self) -> None:
        from PySide6.QtWidgets import QDockWidget

        self.painel_problemas = PainelProblemas(self)
        self.painel_problemas.problema_escolhido.connect(self._ir_para_problema)

        self.doca_problemas = QDockWidget("Problemas", self)
        self.doca_problemas.setObjectName("docaProblemas")
        self.doca_problemas.setWidget(self.painel_problemas)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.doca_problemas)
        self.doca_problemas.hide()

    def alternar_painel_problemas(self) -> None:
        self.doca_problemas.setVisible(not self.doca_problemas.isVisible())

    def _ir_para_problema(self, linha: int, coluna: int, posicao) -> None:
        editor = self.abas.editor_atual()
        if editor is None:
            return
        if posicao is not None:
            # A posicao ABSOLUTA e' preferida quando existe: leva o cursor ao
            # caractere exato sem recalcular linha e coluna.
            from PySide6.QtGui import QTextCursor
            cursor = editor.textCursor()
            cursor.setPosition(min(int(posicao),
                                   editor.document().characterCount() - 1))
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
        else:
            # O painel guarda em base 1 (como o usuario ve); o editor conta de zero.
            editor.ir_para_linha(max(0, linha - 1), max(0, coluna - 1))
        editor.setFocus()

    def _formatador_atual(self):
        doc = self.abas.documento_atual()
        if doc is None or doc.provedor is None:
            return None, None
        return doc.provedor.formatador(), doc

    def _opcoes_de_formatacao(self, doc) -> dict:
        """As opcoes vem da indentacao DO ARQUIVO, nao da preferencia global.

        Formatar com 4 espacos um arquivo indentado com 2 mudaria toda linha dele --
        um diff inteiro por causa de uma preferencia.
        """
        return {"usa_espacos": doc.indentacao.usa_espacos,
                "largura": doc.indentacao.largura,
                "comprimento_de_linha": self.cfg.get("comprimento_de_linha")}

    def _aplicar_saida(self, doc, saida, origem: str, *,
                       so_selecao: bool = False) -> bool:
        """Trata os tres desfechos possiveis de um formatador."""
        from textforge.formatadores.base import ErroDeSintaxe, Recusa, Resultado

        editor = self.abas.editor_atual()
        if editor is None:
            return False

        if isinstance(saida, ErroDeSintaxe):
            problema = Problema.de_erro(saida, origem)
            self.painel_problemas.mostrar([problema], origem)
            self.doca_problemas.show()
            self._ir_para_problema(saida.linha, saida.coluna, saida.posicao)
            self.barra.showMessage(saida.descrever(), 8000)
            return False

        if isinstance(saida, Recusa):
            self.painel_problemas.mostrar([Problema.de_recusa(saida, origem)],
                                          origem)
            self.doca_problemas.show()
            self.barra.showMessage("Formatacao recusada — veja o painel Problemas",
                                   6000)
            return False

        if not isinstance(saida, Resultado):
            return False

        if so_selecao:
            cursor = editor.textCursor()
            cursor.beginEditBlock()
            try:
                cursor.insertText(saida.texto.rstrip("\n"))
            finally:
                cursor.endEditBlock()
        else:
            # UM passo de desfazer para o documento inteiro: sem isso, desfazer uma
            # formatacao exigiria um Ctrl+Z por linha alterada.
            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.beginEditBlock()
            try:
                cursor.insertText(saida.texto)
            finally:
                cursor.endEditBlock()

        problemas = [Problema.de_aviso(a, origem) for a in saida.avisos]
        self.painel_problemas.mostrar(problemas, origem)
        if problemas:
            self.doca_problemas.show()
            self.barra.showMessage(
                f"Formatado com {len(problemas)} aviso(s) — veja o painel "
                f"Problemas", 6000)
        else:
            self.barra.showMessage(f"Formatado ({origem})", 3000)
        return True

    def formatar_documento(self) -> None:
        formatador, doc = self._formatador_atual()
        if formatador is None:
            self._sem_formatador(doc)
            return
        saida = formatador.formatar(doc.texto(), self._opcoes_de_formatacao(doc))
        self._aplicar_saida(doc, saida, formatador.nome)

    def formatar_selecao(self) -> None:
        formatador, doc = self._formatador_atual()
        if formatador is None:
            self._sem_formatador(doc)
            return
        editor = self.abas.editor_atual()
        cursor = editor.textCursor() if editor else None
        if cursor is None or not cursor.hasSelection():
            dialogos.avisar(self, "Nenhum texto selecionado.",
                            "Selecione o trecho a formatar, ou use "
                            "'Formatar documento'.")
            return
        trecho = cursor.selectedText().replace(
            codificacao.SEPARADOR_DE_PARAGRAFO, "\n")
        saida = formatador.formatar(trecho, self._opcoes_de_formatacao(doc))
        self._aplicar_saida(doc, saida, formatador.nome, so_selecao=True)

    def compactar_documento(self) -> None:
        formatador, doc = self._formatador_atual()
        if formatador is None:
            self._sem_formatador(doc)
            return
        saida = formatador.compactar(doc.texto(), self._opcoes_de_formatacao(doc))
        self._aplicar_saida(doc, saida, formatador.nome)

    def formatar_ordenando(self) -> None:
        """Formatar JSON ordenando as propriedades (requisito 6-JSON)."""
        formatador, doc = self._formatador_atual()
        if formatador is None or not hasattr(formatador, "formatar_ordenando"):
            dialogos.avisar(
                self, "Ordenar propriedades so' vale para JSON.",
                f"A linguagem atual e' {doc.nome_da_linguagem if doc else '?'}.")
            return
        saida = formatador.formatar_ordenando(doc.texto(),
                                              self._opcoes_de_formatacao(doc))
        self._aplicar_saida(doc, saida, formatador.nome)

    def validar_documento(self) -> None:
        """Validar e' comando SEPARADO de formatar.

        Num arquivo grande e invalido o usuario quer o ERRO, e nao esperar uma
        formatacao que vai falhar de qualquer forma.
        """
        formatador, doc = self._formatador_atual()
        if formatador is None:
            self._sem_formatador(doc)
            return
        erro = formatador.validar(doc.texto())
        if erro is None:
            self.painel_problemas.mostrar([], formatador.nome)
            self.barra.showMessage(f"{formatador.nome} valido", 4000)
            return
        self.painel_problemas.mostrar([Problema.de_erro(erro, formatador.nome)],
                                      formatador.nome)
        self.doca_problemas.show()
        self._ir_para_problema(erro.linha, erro.coluna, erro.posicao)
        self.barra.showMessage(erro.descrever(), 8000)

    def ir_para_erro(self) -> None:
        destino = self.painel_problemas.primeiro_erro()
        if destino is None:
            self.validar_documento()
            return
        self._ir_para_problema(*destino)

    def _sem_formatador(self, doc) -> None:
        nome = doc.nome_da_linguagem if doc is not None else "?"
        dialogos.avisar(
            self, f"Nao ha' formatador para {nome}.",
            "Formatadores disponiveis: XML, JSON, SQL, CSS, HTML e Python. "
            "Voce pode trocar a linguagem no menu Linguagem.")

    # ==================================================================
    # Busca (requisito 8)
    # ==================================================================

    def _montar_busca(self) -> None:
        from PySide6.QtWidgets import QDockWidget, QVBoxLayout, QWidget

        self.barra_de_busca = BarraDeBusca(self)
        self.barra_de_busca.procurar.connect(self._procurar)
        self.barra_de_busca.procurar_incremental.connect(self._procurar_ao_digitar)
        self.barra_de_busca.substituir_atual.connect(self._substituir_atual)
        self.barra_de_busca.substituir_tudo.connect(self._substituir_tudo)
        self.barra_de_busca.fechada.connect(self._limpar_realce_de_busca)

        # A barra fica ENTRE o editor e a barra de status, e nao numa doca: ela
        # pertence ao documento que esta' sendo editado, e uma doca poderia ser
        # arrastada para longe dele.
        centro = QWidget(self)
        layout = QVBoxLayout(centro)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.abas, 1)
        layout.addWidget(self.barra_de_busca)
        self.setCentralWidget(centro)

        self.painel_resultados = PainelResultados(self)
        self.painel_resultados.resultado_escolhido.connect(
            self._abrir_resultado)
        self.painel_resultados.cancelar_pedido.connect(self._cancelar_busca)

        self.doca_resultados = QDockWidget("Resultados da pesquisa", self)
        self.doca_resultados.setObjectName("docaResultados")
        self.doca_resultados.setWidget(self.painel_resultados)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.doca_resultados)
        self.doca_resultados.hide()
        self._tarefa_de_busca = None

    def abrir_busca(self, *, com_substituicao: bool = False) -> None:
        editor = self.abas.editor_atual()
        inicial = ""
        if editor is not None:
            cursor = editor.textCursor()
            if cursor.hasSelection():
                selecionado = cursor.selectedText()
                # Selecao de varias linhas nao serve como termo de busca: o U+2029
                # do Qt nunca casaria com nada digitavel.
                if codificacao.SEPARADOR_DE_PARAGRAFO not in selecionado:
                    inicial = selecionado
        self.barra_de_busca.mostrar(com_substituicao=com_substituicao,
                                    texto_inicial=inicial)

    def _repetir_busca(self, para_tras: bool) -> None:
        """F3 / Shift+F3. Abre a barra se ela estiver fechada.

        Repetir a busca sem ter buscado antes NAO deve ser um erro: o gesto natural
        e' selecionar uma palavra e apertar F3.
        """
        criterio = self.barra_de_busca.criterio()
        if criterio.vazio:
            self.abrir_busca()
            return
        self._procurar(criterio, para_tras)

    def _criterio_valido(self, criterio: busca.Criterio):
        """Compila o criterio, mostrando o erro na propria barra."""
        if criterio.vazio:
            self.barra_de_busca.definir_contador(0, 0)
            return None
        try:
            criterio.compilar()
        except busca.CriterioInvalido as exc:
            # Regex invalida e' o estado NORMAL enquanto o usuario digita "(\d+".
            # O aviso vai para a barra, e nunca para um dialogo.
            self.barra_de_busca.definir_contador(0, 0, erro=str(exc))
            self._limpar_realce_de_busca()
            return None
        return criterio

    def _procurar_ao_digitar(self, criterio: busca.Criterio) -> None:
        """Atualiza contador e realce de todas as ocorrencias, sem mover o cursor."""
        visor = self.visor_grande()
        if visor is not None:
            # Num arquivo grande NAO ha' busca incremental a cada tecla: varrer 1
            # GB por caractere digitado deixaria a digitacao impossivel. So' o
            # realce das linhas visiveis acompanha; o Enter dispara a varredura.
            criterio = self._criterio_valido(criterio)
            visor.definir_realce(criterio.compilar() if criterio else None)
            return
        editor = self.abas.editor_atual()
        if editor is None or self._criterio_valido(criterio) is None:
            return
        faixas, cortado = busca.todas_no_documento(editor.document(), criterio)
        self._faixas_da_busca = faixas
        self._realcar_ocorrencias(editor, faixas)
        atual = busca.ordinal(faixas, editor.textCursor().selectionStart())
        self.barra_de_busca.definir_contador(atual, len(faixas))
        if cortado:
            self.barra.showMessage(
                f"Mais de {len(faixas)} ocorrencias: o realce foi limitado", 4000)

    def _procurar(self, criterio: busca.Criterio, para_tras: bool) -> None:
        if self.visor_grande() is not None:
            self._buscar_no_arquivo_grande(criterio)
            return
        editor = self.abas.editor_atual()
        if editor is None or self._criterio_valido(criterio) is None:
            return
        cursor = editor.textCursor()
        # Partir do FIM da selecao ao avancar e do INICIO ao voltar: senao o F3
        # acharia de novo a ocorrencia que ja' esta' selecionada.
        origem = cursor.selectionStart() if para_tras else cursor.selectionEnd()
        faixa = busca.achar(editor.document(), criterio, origem,
                            para_tras=para_tras)
        if faixa is None:
            self.barra.showMessage(
                f"Nao encontrado: {criterio.descricao()}", 3000)
            self.barra_de_busca.definir_contador(0, 0)
            return
        self._selecionar_faixa(editor, faixa)
        faixas, _ = busca.todas_no_documento(editor.document(), criterio)
        self._faixas_da_busca = faixas
        self._realcar_ocorrencias(editor, faixas, atual=faixa)
        self.barra_de_busca.definir_contador(
            busca.ordinal(faixas, faixa.inicio), len(faixas))

    def _selecionar_faixa(self, editor, faixa: busca.Faixa) -> None:
        from PySide6.QtGui import QTextCursor

        cursor = editor.textCursor()
        cursor.setPosition(faixa.inicio)
        cursor.setPosition(faixa.fim, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

    def _realcar_ocorrencias(self, editor, faixas: list[busca.Faixa],
                             atual: busca.Faixa | None = None) -> None:
        """Pinta todas as ocorrencias, e a atual numa cor propria.

        Sao DUAS camadas de selecao (ver `selecoes.py`): a ordem de pintura
        declarada la' garante que a atual apareca sobre as demais.
        """
        from PySide6.QtGui import QTextCursor
        from PySide6.QtWidgets import QTextEdit

        def marcar(faixa: busca.Faixa, cor: str) -> QTextEdit.ExtraSelection:
            selecao = QTextEdit.ExtraSelection()
            selecao.format.setBackground(editor.tema.cor(cor))
            cursor = QTextCursor(editor.document())
            cursor.setPosition(faixa.inicio)
            cursor.setPosition(faixa.fim, QTextCursor.MoveMode.KeepAnchor)
            selecao.cursor = cursor
            return selecao

        editor.selecoes.definir(
            "ocorrencias", [marcar(f, "editor.ocorrencia") for f in faixas])
        editor.selecoes.definir(
            "ocorrencia_atual",
            [marcar(atual, "editor.ocorrencia_atual")] if atual else [])

    def _limpar_realce_de_busca(self) -> None:
        self._faixas_da_busca = []
        for aba in self.abas.abas():
            aba.editor.selecoes.limpar("ocorrencias")
            aba.editor.selecoes.limpar("ocorrencia_atual")
            # O visor de arquivo grande nao usa `ExtraSelection` -- ele guarda o
            # proprio padrao e o aplica nas linhas visiveis a cada pintura.
            if aba.visor_grande is not None:
                aba.visor_grande.visor.definir_realce(None)

    def _substituir_atual(self, criterio: busca.Criterio,
                          substituicao: str) -> None:
        editor = self.abas.editor_atual()
        if editor is None or self._criterio_valido(criterio) is None:
            return
        cursor = editor.textCursor()
        faixa = busca.achar(editor.document(), criterio, cursor.selectionStart())
        if faixa is None:
            self.barra.showMessage("Nao encontrado", 2000)
            return
        # Se a selecao atual NAO e' o casamento, apenas vai para ele: substituir
        # algo que o usuario nao esta' vendo e' o caminho mais curto para uma
        # alteracao que ele nao pediu.
        if (cursor.selectionStart(), cursor.selectionEnd()) != (faixa.inicio,
                                                               faixa.fim):
            self._selecionar_faixa(editor, faixa)
            return
        try:
            busca.substituir_uma(editor.document(), faixa, substituicao, criterio)
        except busca.CriterioInvalido as exc:
            dialogos.avisar(self, "Substituicao invalida.", str(exc))
            return
        self._procurar(criterio, False)

    def _substituir_tudo(self, criterio: busca.Criterio, substituicao: str,
                         so_na_selecao: bool) -> None:
        editor = self.abas.editor_atual()
        if editor is None or self._criterio_valido(criterio) is None:
            return
        limite = None
        if so_na_selecao:
            cursor = editor.textCursor()
            if not cursor.hasSelection():
                dialogos.avisar(self, "Nenhum texto selecionado.",
                                "Marque 'Na selecao' apenas com texto selecionado.")
                return
            limite = (cursor.selectionStart(), cursor.selectionEnd())
        try:
            quantas = busca.substituir_todos(editor.document(), criterio,
                                             substituicao,
                                             limite_da_selecao=limite)
        except busca.CriterioInvalido as exc:
            dialogos.avisar(self, "Substituicao invalida.", str(exc))
            return
        self.barra.showMessage(
            f"{quantas} ocorrencia(s) substituida(s) — um Ctrl+Z desfaz tudo",
            5000)
        self._procurar_ao_digitar(criterio)

    def contar_ocorrencias(self) -> None:
        """Conta as ocorrencias da selecao (requisito 40)."""
        editor = self.abas.editor_atual()
        if editor is None:
            return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            dialogos.avisar(self, "Selecione o texto a contar.")
            return
        criterio = busca.Criterio(texto=cursor.selectedText())
        faixas, cortado = busca.todas_no_documento(editor.document(), criterio)
        sufixo = " (lista cortada)" if cortado else ""
        self.barra.showMessage(
            f'"{criterio.texto[:40]}": {len(faixas)} ocorrencia(s){sufixo}', 6000)
        self._realcar_ocorrencias(editor, faixas)

    def selecionar_ocorrencias(self) -> None:
        """Seleciona todas as ocorrencias da selecao (requisito 40).

        Sem multi-cursor ainda, o que se pode fazer de util e' REALCAR todas e levar
        o cursor a' primeira -- e dizer quantas. Prometer "selecionar" e mover
        apenas o cursor seria pior que ser explicito.
        """
        self.contar_ocorrencias()

    # ==================================================================
    # Pesquisar em arquivos (requisito 8)
    # ==================================================================

    def pesquisar_em_arquivos(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        editor = self.abas.editor_atual()
        termo = ""
        if editor is not None and editor.textCursor().hasSelection():
            termo = editor.textCursor().selectedText()
        termo = dialogos.pedir_texto(self, "Pesquisar em arquivos",
                                     "Texto a procurar:", termo)
        if not termo:
            return

        doc = self.abas.documento_atual()
        sugestao = str(doc.caminho.parent) if (doc and doc.caminho) else ""
        pasta = QFileDialog.getExistingDirectory(
            self, "Pesquisar em qual pasta?", sugestao)
        if not pasta:
            return

        filtros = dialogos.pedir_texto(
            self, "Filtros", "Extensoes (ex.: *.php *.py *.xml):", "*")
        if filtros is None:
            return

        criterio = busca.Criterio(texto=termo)
        self._iniciar_busca_em_arquivos(pasta, criterio,
                                       bfa.filtros_de(filtros))

    def _iniciar_busca_em_arquivos(self, pasta: str, criterio: busca.Criterio,
                                   filtros: list[str]) -> None:
        from textforge import tarefas

        self._cancelar_busca()
        self.doca_resultados.show()
        self.painel_resultados.comecar(criterio.descricao(), pasta)

        tarefa = bfa.montar_tarefa(pasta, criterio, filtros)
        tarefa.sinais.concluido.connect(self._busca_concluida)
        tarefa.sinais.cancelado.connect(self.painel_resultados.cancelado)
        tarefa.sinais.erro.connect(self.painel_resultados.falhou)
        tarefa.sinais.mensagem.connect(
            lambda p: self.painel_resultados.progresso(0, p))
        tarefa.sinais.progresso.connect(
            lambda feito, _t: self.barra.mostrar_progresso(feito, -1))
        tarefa.sinais.terminou.connect(self.barra.esconder_progresso)
        self._tarefa_de_busca = tarefa
        # `disco=True`: e' I/O de arquivo, e nao deve competir com a CPU do realce.
        tarefas.rodar(tarefa, disco=True)

    def _busca_concluida(self, resultado) -> None:
        if not resultado:
            return
        achados, resumo = resultado
        self.painel_resultados.acrescentar(achados)
        self.painel_resultados.terminar(resumo)
        self._tarefa_de_busca = None

    def _cancelar_busca(self) -> None:
        if self._tarefa_de_busca is not None:
            self._tarefa_de_busca.cancelar()
            self._tarefa_de_busca = None

    def _abrir_resultado(self, caminho: str, linha: int, coluna: int) -> None:
        self.abrir_arquivo(caminho, linha, coluna)

    # ==================================================================
    # Painel Estrutura (requisito 11)
    # ==================================================================

    def _montar_painel_estrutura(self) -> None:
        from PySide6.QtWidgets import QDockWidget

        self.painel_estrutura = PainelEstrutura(self)
        self.painel_estrutura.linha_escolhida.connect(self._ir_para_da_estrutura)

        self.doca_estrutura = QDockWidget("Estrutura", self)
        self.doca_estrutura.setObjectName("docaEstrutura")
        self.doca_estrutura.setWidget(self.painel_estrutura)
        self.doca_estrutura.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.doca_estrutura)
        # Comeca OCULTO: o painel custa uma analise do documento, e quem nao o usa
        # nao deve pagar por ele. `restoreState` reabre se o usuario o deixou aberto.
        self.doca_estrutura.hide()

    def alternar_painel_estrutura(self) -> None:
        visivel = not self.doca_estrutura.isVisible()
        self.doca_estrutura.setVisible(visivel)
        if visivel:
            self.painel_estrutura.acompanhar(self.abas.documento_atual())

    def _ir_para_da_estrutura(self, linha: int, coluna: int) -> None:
        editor = self.abas.editor_atual()
        if editor is not None:
            editor.ir_para_linha(linha, coluna)
            editor.setFocus()

    def ir_para_par(self) -> None:
        editor = self.abas.editor_atual()
        if editor is not None and not editor.ir_para_par():
            self.barra.showMessage("Nenhum par correspondente aqui", 2000)

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

    # ==================================================================
    # Conversoes e hashes (requisitos 24 e 25)
    # ==================================================================

    def _converter(self, funcao, id_do_comando: str) -> None:
        """Converte a SELECAO. Sem selecao, o documento inteiro.

        A codificacao passada e' a DO DOCUMENTO, e nao UTF-8 fixo: Base64 e URL
        trabalham sobre bytes, e `"acao"` em cp1252 produz um Base64 diferente do
        de UTF-8. Usar o codec do arquivo faz o resultado casar com o resto do que
        o usuario esta' editando.
        """
        from textforge.servicos.conversoes import ConversaoInvalida

        editor = self.abas.editor_atual()
        doc = self.abas.documento_atual()
        if editor is None or doc is None:
            return
        cursor = editor.textCursor()
        tinha_selecao = cursor.hasSelection()
        if tinha_selecao:
            entrada = cursor.selectedText().replace(
                codificacao.SEPARADOR_DE_PARAGRAFO, "\n")
        else:
            entrada = doc.texto()
        if not entrada:
            self.barra.showMessage("Nada para converter", 3000)
            return

        try:
            saida = funcao(entrada, doc.codec)
        except ConversaoInvalida as exc:
            dialogos.avisar(self, "Nao foi possivel converter.", str(exc))
            return

        if saida == entrada:
            self.barra.showMessage("A conversao nao mudou nada", 3000)
            return

        if tinha_selecao:
            cursor.beginEditBlock()
            try:
                cursor.insertText(saida)
            finally:
                cursor.endEditBlock()
        else:
            from PySide6.QtGui import QTextCursor
            inteiro = QTextCursor(editor.document())
            inteiro.select(QTextCursor.SelectionType.Document)
            inteiro.beginEditBlock()
            try:
                inteiro.insertText(saida)
            finally:
                inteiro.endEditBlock()
        rotulo = acoes.REGISTRO.por_id(id_do_comando)
        self.barra.showMessage(
            f"{rotulo.rotulo_limpo if rotulo else 'Convertido'}"
            f"{' (selecao)' if tinha_selecao else ' (documento inteiro)'}", 4000)

    def calcular_hash(self, algoritmo: str) -> None:
        """Hash da SELECAO, ou do ARQUIVO NO DISCO quando nao ha' selecao.

        A distincao e' declarada na caixa de resultado, e nao e' detalhe: o hash do
        arquivo tem BOM e CRLF; o do texto em memoria nao. Quem compara com um
        `.sha256` publicado ou com o `certutil` quer o do ARQUIVO -- e nao ter isso
        escrito na tela faria o usuario achar que uma das ferramentas esta' errada.
        """
        from textforge.servicos import hashes

        editor = self.abas.editor_atual()
        doc = self.abas.documento_atual()
        if doc is None:
            return
        cursor = editor.textCursor() if editor is not None else None

        if cursor is not None and cursor.hasSelection():
            texto = cursor.selectedText().replace(
                codificacao.SEPARADOR_DE_PARAGRAFO, "\n")
            try:
                valor = hashes.de_texto(texto, algoritmo, doc.codec)
            except UnicodeEncodeError:
                dialogos.avisar(
                    self, f"Nao foi possivel calcular o {algoritmo}.",
                    f"A selecao tem caracteres que nao existem em {doc.codec}. "
                    f"Converta o arquivo para UTF-8 antes.")
                return
            self._mostrar_hash(algoritmo, valor,
                               f"selecao ({len(texto)} caracteres, {doc.codec})")
            return

        if doc.caminho is None:
            texto = doc.texto()
            valor = hashes.de_texto(texto, algoritmo, doc.codec)
            self._mostrar_hash(algoritmo, valor,
                               f"texto em memoria ({doc.codec}, sem BOM, LF)")
            return

        self._hash_de_arquivo(doc.caminho, algoritmo)

    def _hash_de_arquivo(self, caminho, algoritmo: str) -> None:
        """Em thread: um SHA-512 de 1 GB leva segundos."""
        from textforge import tarefas
        from textforge.servicos import hashes

        alvo = pathlib.Path(caminho)

        def trabalho(tarefa: tarefas.Tarefa) -> str:
            return hashes.de_arquivo(
                alvo, algoritmo,
                progresso=lambda lidos, total: tarefa.progresso(lidos, total),
                cancelar=tarefa.cancelada)

        tarefa = tarefas.Tarefa(f"{algoritmo} de {alvo.name}", trabalho)
        tamanho = arquivos.tamanho_de(alvo)
        tarefa.sinais.concluido.connect(
            lambda valor: self._mostrar_hash(
                algoritmo, str(valor),
                f"arquivo no disco ({tamanho:,} bytes)".replace(",", "."))
            if valor else None)
        tarefa.sinais.progresso.connect(self.barra.mostrar_progresso)
        tarefa.sinais.terminou.connect(self.barra.esconder_progresso)
        tarefa.sinais.erro.connect(
            lambda t: dialogos.avisar(self, f"Nao foi possivel calcular o "
                                            f"{algoritmo}.", str(t)))
        self.barra.showMessage(f"Calculando {algoritmo} de {alvo.name}...", 2000)
        tarefas.rodar(tarefa, disco=True)

    def _mostrar_hash(self, algoritmo: str, valor: str, origem: str) -> None:
        from textforge.servicos import hashes

        if not valor:
            return
        QApplication.clipboard().setText(valor)
        dialogos.avisar(
            self, f"{algoritmo}  —  {origem}",
            f"{hashes.formatar(valor, agrupado=True)}\n\n"
            f"(ja' copiado para a area de transferencia)")

    # ==================================================================
    # Comentar / descomentar (requisito 22)
    # ==================================================================

    def alternar_comentario(self) -> None:
        """Ctrl+/ nas linhas selecionadas, usando o comentario DA LINGUAGEM.

        Se qualquer linha nao estiver comentada, COMENTA todas; so' descomenta
        quando todas ja' estao. E' o comportamento de todo editor, e evita o
        vaivem confuso de alternar linha a linha.

        O prefixo entra na MENOR indentacao do bloco, e nao na coluna zero: um
        bloco de Python indentado receberia `# ` grudado na margem e a leitura do
        codigo pioraria a cada comentario.
        """
        from PySide6.QtGui import QTextCursor

        editor = self.abas.editor_atual()
        doc = self.abas.documento_atual()
        if editor is None or doc is None:
            return
        marca = getattr(doc.provedor, "comentario_de_linha", None)
        if not marca:
            dialogos.avisar(
                self, f"{doc.nome_da_linguagem} nao tem comentario de linha.",
                "Escolha outra linguagem no menu Linguagem, ou use o comentario "
                "de bloco da propria sintaxe.")
            return

        cursor = editor.textCursor()
        tinha_selecao = cursor.hasSelection()
        primeira = doc.qt.findBlock(cursor.selectionStart()).blockNumber() \
            if tinha_selecao else cursor.blockNumber()
        ultima = doc.qt.findBlock(cursor.selectionEnd()).blockNumber() \
            if tinha_selecao else primeira
        coluna_original = cursor.positionInBlock()

        linhas = [doc.qt.findBlockByNumber(n).text()
                  for n in range(primeira, ultima + 1)]
        uteis = [l for l in linhas if l.strip()]
        if not uteis:
            return
        comentadas = all(l.lstrip().startswith(marca) for l in uteis)
        recuo = min(len(l) - len(l.lstrip()) for l in uteis)

        novas = []
        for linha in linhas:
            if not linha.strip():
                novas.append(linha)
            elif comentadas:
                sem = linha.lstrip()
                depois = sem[len(marca):]
                # Tira o espaco que NOS colocamos, e nao um do usuario: so' quando
                # ele e' o primeiro caractere depois da marca.
                novas.append(linha[:len(linha) - len(sem)]
                             + (depois[1:] if depois.startswith(" ") else depois))
            else:
                novas.append(linha[:recuo] + f"{marca} " + linha[recuo:])

        alvo = QTextCursor(doc.qt)
        alvo.setPosition(doc.qt.findBlockByNumber(primeira).position())
        fim = doc.qt.findBlockByNumber(ultima)
        alvo.setPosition(fim.position() + fim.length() - 1,
                         QTextCursor.MoveMode.KeepAnchor)
        alvo.beginEditBlock()
        try:
            alvo.insertText("\n".join(novas))
        finally:
            alvo.endEditBlock()

        # A SELECAO E' RESTAURADA sobre as mesmas linhas. `insertText` colapsa o
        # cursor no fim do texto inserido, e sem restaurar, um segundo Ctrl+/
        # atuaria so' na ULTIMA linha -- ou seja, comentar e descomentar deixaria
        # o bloco pela metade. E' tambem o que o usuario espera: a selecao
        # sobrevive ao comando, para ele poder repetir.
        novo = QTextCursor(doc.qt)
        bloco_final = doc.qt.findBlockByNumber(ultima)
        if tinha_selecao:
            novo.setPosition(doc.qt.findBlockByNumber(primeira).position())
            novo.setPosition(bloco_final.position() + bloco_final.length() - 1,
                             QTextCursor.MoveMode.KeepAnchor)
        else:
            # Sem selecao, o cursor volta para a mesma linha, com a coluna
            # deslocada pelo prefixo que entrou (ou saiu).
            deslocamento = len(novas[0]) - len(linhas[0])
            novo.setPosition(min(bloco_final.position()
                                 + max(0, coluna_original + deslocamento),
                                 bloco_final.position()
                                 + bloco_final.length() - 1))
        editor.setTextCursor(novo)

    # ==================================================================
    # Paleta de comandos e abertura rapida (requisito 23)
    # ==================================================================

    def abrir_paleta(self) -> None:
        from textforge.interface import paleta_de_comandos as pal

        paleta = pal.PaletaDeComandos(self)
        paleta.definir_itens(
            pal.itens_de_comandos(self.vinculos),
            dica="Digite as iniciais — \"fdoc\" acha \"Formatar documento\". "
                 "Enter executa, Esc fecha.")
        paleta.escolhido.connect(self.vinculos.acionar)
        self._estilizar_paleta(paleta)
        paleta.mostrar()

    def abertura_rapida(self) -> None:
        from textforge.interface import paleta_de_comandos as pal

        doc = self.abas.documento_atual()
        pasta = doc.caminho.parent if (doc and doc.caminho) else None
        abertos = [str(a.documento.caminho) for a in self.abas.abas()
                   if a.documento.caminho is not None]
        paleta = pal.PaletaDeComandos(self)
        paleta.definir_itens(
            pal.itens_de_arquivos(list(self.cfg.get("recentes", [])),
                                  abertos, pasta),
            dica=f"Abertos, recentes e a pasta {pasta or '(nenhuma)'}. "
                 "A varredura da pasta tem teto — não é um indexador.")
        paleta.escolhido.connect(self.abrir_arquivo)
        self._estilizar_paleta(paleta)
        paleta.mostrar()

    def _estilizar_paleta(self, paleta) -> None:
        tema = self.tema
        paleta.setStyleSheet(f"""
            QDialog {{ background: {tema.cor('janela.fundo').name()};
                       border: 1px solid {tema.cor('janela.borda').name()}; }}
            QLineEdit {{ background: {tema.cor('janela.campo_fundo').name()};
                         color: {tema.cor('janela.texto').name()};
                         border: 1px solid {tema.cor('janela.borda').name()};
                         padding: 6px; font-size: 13px; }}
            QListWidget {{ background: {tema.cor('janela.fundo').name()};
                           color: {tema.cor('janela.texto').name()};
                           border: none; }}
            QListWidget::item {{ padding: 3px 4px; }}
            QListWidget::item:selected {{
                background: {tema.cor('janela.destaque').name()};
                color: {tema.cor('janela.texto_do_destaque').name()}; }}
            QLabel#rodapeDaPaleta {{
                color: {tema.cor('janela.texto_apagado').name()};
                font-size: 11px; }}
        """)

    # ==================================================================
    # Configuracoes e ajuda
    # ==================================================================

    def abrir_configuracoes(self) -> None:
        """Abre o `config.json` COMO ARQUIVO, numa aba do proprio editor.

        Nao ha' dialogo de preferencias, e a escolha e' consciente: as ~40 chaves
        de configuracao ja' estao documentadas por comentario no `configuracao.py`,
        o publico deste programa edita JSON o dia inteiro, e um dialogo seria mais
        codigo de interface para manter em sincronia com o arquivo. O arquivo E' a
        interface -- e ele e' recarregado ao salvar.
        """
        caminho = configuracao.caminho_config()
        try:
            if not caminho.exists():
                configuracao.salvar(self.cfg)
        except OSError as exc:
            dialogos.avisar(self, "Nao foi possivel criar o config.json.",
                            str(exc))
            return
        if self.abrir_arquivo(str(caminho)):
            self.barra.showMessage(
                "Edite e salve: as preferencias sao reaplicadas ao salvar.", 8000)

    def mostrar_atalhos(self) -> None:
        """Lista os atalhos GERADOS do registro, e nao uma lista escrita a mao.

        Uma lista escrita a mao desatualiza no primeiro atalho que mudar, e o
        usuario passa a nao confiar em nenhuma linha dela.
        """
        from textforge.interface import paleta_de_comandos as pal

        itens = []
        for comando in acoes.REGISTRO.comandos:
            if not comando.atalho or not self.vinculos.tem_tratador(comando.id):
                continue
            itens.append((comando.id, f"{comando.atalho}    "
                                      f"{comando.rotulo_limpo}",
                          comando.caminho_na_palette))
        paleta = pal.PaletaDeComandos(self)
        paleta.definir_itens(
            sorted(itens, key=lambda i: i[2]),
            dica=f"{len(itens)} atalhos ativos. Enter executa o comando.")
        paleta.escolhido.connect(self.vinculos.acionar)
        self._estilizar_paleta(paleta)
        paleta.setWindowTitle("Atalhos")
        paleta.mostrar()

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
        visor = self.visor_grande()
        if visor is not None:
            escolha = dialogos.pedir_linha(self, visor.fonte.total_de_linhas(),
                                           visor.linha_atual)
            if escolha is not None:
                visor.ir_para_linha(escolha[0])
                visor.setFocus()
            return
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
        # As tarefas ja' foram canceladas pelo `encerrar()` de cada aba; esta
        # espera curta so' garante que uma thread de indexacao nao continue lendo
        # de um mmap enquanto o processo desmonta. Um teto de 2 s, e nao os 30 s
        # padrao: fechar o editor nunca pode parecer travado.
        from textforge import tarefas as _tarefas
        _tarefas.esperar_tudo(2000)
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
