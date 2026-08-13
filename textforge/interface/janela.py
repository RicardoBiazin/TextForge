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
from PySide6.QtWidgets import (QLabel, QMainWindow, QMessageBox, QToolBar,
                               QVBoxLayout, QWidget)

from textforge import APP, AUTOR, VERSAO, configuracao, log_interno, recursos
from textforge.interface import tema as tema_mod
from textforge.interface.barra_de_status import BarraDeStatus
from textforge.interface.menus import Vinculos

log = log_interno.obter(__name__)

ZOOM_MINIMO = 6
ZOOM_MAXIMO = 48


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = cfg
        self.tema = tema_mod.resolver(cfg.get("tema", "sistema"))

        self.setWindowTitle(APP)
        self.setAcceptDrops(True)          # requisito 19; tratado na etapa 4
        self._aplicar_icone()

        self.vinculos = Vinculos(self)
        self._montar_centro()
        self.barra = BarraDeStatus(self)
        self.setStatusBar(self.barra)

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
        """Area central. A etapa 4 troca isto pelo gerenciador de abas."""
        centro = QWidget(self)
        layout = QVBoxLayout(centro)
        layout.setContentsMargins(0, 0, 0, 0)
        self._boas_vindas = QLabel(
            f"<h2>{APP} {VERSAO}</h2>"
            "<p>Arraste arquivos para esta janela, ou use "
            "<b>Arquivo &gt; Abrir</b>.</p>"
            "<p style='color:gray'>Abrir arquivos entra na etapa 3.</p>",
            alignment=Qt.AlignmentFlag.AlignCenter)
        self._boas_vindas.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._boas_vindas)
        self.setCentralWidget(centro)

    def _ligar_comandos(self) -> None:
        """Liga o que JA existe. O resto fica desabilitado no menu.

        E' de proposito que o menu mostre os comandos futuros desabilitados em
        vez de escondidos: o usuario ve o que o programa vai ter, e nenhum item
        clicavel finge funcionar.
        """
        self.vinculos.ligar_muitos({
            "arquivo.sair": self.close,
            "exibir.tela_cheia": self.alternar_tela_cheia,
            "exibir.barra_de_ferramentas": self.alternar_barra_de_ferramentas,
            "exibir.aumentar_zoom": lambda: self.ajustar_zoom(+1),
            "exibir.diminuir_zoom": lambda: self.ajustar_zoom(-1),
            "exibir.zoom_normal": self.zoom_normal,
            "ajuda.sobre": self.mostrar_sobre,
            "ajuda.abrir_log": self.abrir_log,
        })

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

    def ajustar_zoom(self, passos: int) -> None:
        tamanho = int(self.cfg.get("fonte_tamanho", 11)) + passos
        self.cfg["fonte_tamanho"] = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, tamanho))
        self.aplicar_fonte()

    def zoom_normal(self) -> None:
        self.cfg["fonte_tamanho"] = configuracao.padrao()["fonte_tamanho"]
        self.aplicar_fonte()

    def aplicar_fonte(self) -> None:
        """Repassa fonte e tamanho aos editores. Sem editores ainda, so' loga."""
        log.info("fonte: %s %dpt", self.cfg.get("fonte"),
                 self.cfg.get("fonte_tamanho"))

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
