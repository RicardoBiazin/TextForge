"""Janela principal.

Etapa 0: janela vazia com titulo, icone e geometria lembrada -- o suficiente
para o app ser executavel e para o restante das etapas terem onde encostar.
As etapas seguintes acrescentam menus (a partir de `acoes.py`), abas, barra de
status e paineis.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QLabel, QMainWindow

from textforge import APP, VERSAO, configuracao, log_interno, recursos

log = log_interno.obter(__name__)


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(APP)
        self._aplicar_icone()
        self._restaurar_geometria()

        aviso = QLabel(
            f"{APP} {VERSAO}\n\n"
            "Fundacao pronta. Abrir arquivos entra na etapa 3.",
            alignment=Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(aviso)

    # -- aparencia ---------------------------------------------------------

    def _aplicar_icone(self) -> None:
        icone = recursos.raiz() / "icone.ico"
        if icone.is_file():
            self.setWindowIcon(QIcon(str(icone)))

    def _restaurar_geometria(self) -> None:
        """Devolve a janela ao tamanho e posicao da ultima sessao.

        Geometria gravada e' `QByteArray` em base64 no JSON. Se a tela onde a
        janela estava nao existir mais (notebook que saiu do dock), o Qt ja'
        cuida de trazer a janela para uma tela visivel.
        """
        bruto = self.cfg.get("geometria") or ""
        if bruto:
            try:
                self.restoreGeometry(QByteArray.fromBase64(bruto.encode("ascii")))
                return
            except Exception:        # noqa: BLE001 - geometria invalida no config
                log.warning("geometria gravada ilegivel; usando o tamanho padrao")
        self.resize(1100, 720)

    def closeEvent(self, event: QCloseEvent) -> None:       # noqa: N802 - Qt
        self.cfg["geometria"] = bytes(
            self.saveGeometry().toBase64()).decode("ascii")
        try:
            configuracao.salvar(self.cfg)
        except OSError as exc:
            # Nao impedir o fechamento por causa das preferencias.
            log.warning("nao foi possivel salvar a configuracao: %s", exc)
        super().closeEvent(event)
