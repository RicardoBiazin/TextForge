"""Captura de excecoes nao tratadas.

Sem isto o TextForge empacotado seria mudo: com `console=False` no PyInstaller
nao existe stderr para onde o traceback iria, e um erro nao tratado simplesmente
fecharia a janela sem nenhuma pista. Este modulo instala um `sys.excepthook`
global que grava %APPDATA%\\TextForge\\erro.log e, se houver interface no ar,
mostra um dialogo com o caminho do arquivo.

Vale a mesma regra de privacidade do `log_interno`: caminho, tamanho e tipo,
nunca bytes do documento.
"""

from __future__ import annotations

import sys
import traceback
import types
from typing import Any

from textforge import APP, VERSAO
from textforge import configuracao, log_interno

log = log_interno.obter(__name__)

_anterior: Any = None
_instalado = False


def _gravar(texto: str) -> str | None:
    try:
        alvo = configuracao.caminho_erro()
        with open(alvo, "a", encoding="utf-8") as f:
            f.write(texto)
        return str(alvo)
    except OSError:
        return None


def _mostrar_dialogo(resumo: str, arquivo: str | None) -> None:
    """Avisa o usuario, se e somente se ja' existe uma QApplication.

    Criar uma QApplication aqui seria pior: se a falha aconteceu ANTES da
    interface subir, abrir uma janela nova pode falhar tambem e mascarar o erro
    original.
    """
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return
    if QApplication.instance() is None:
        return
    try:
        caixa = QMessageBox()
        caixa.setIcon(QMessageBox.Icon.Critical)
        caixa.setWindowTitle(f"{APP} - erro inesperado")
        caixa.setText("Ocorreu um erro inesperado.\n\n"
                      "Seus arquivos abertos nao foram alterados.")
        detalhe = resumo
        if arquivo:
            caixa.setInformativeText(f"Os detalhes tecnicos foram gravados em:\n{arquivo}")
        caixa.setDetailedText(detalhe)
        caixa.exec()
    except Exception:            # noqa: BLE001 - o relator nunca pode estourar
        pass


def tratar(tipo: type[BaseException], valor: BaseException,
           rastro: types.TracebackType | None) -> None:
    """O excepthook. Publico para o teste poder chamar direto."""
    if issubclass(tipo, KeyboardInterrupt):
        if _anterior is not None:
            _anterior(tipo, valor, rastro)
        return

    linhas = traceback.format_exception(tipo, valor, rastro)
    resumo = "".join(linhas)
    cabecalho = f"\n{'=' * 70}\n{APP} {VERSAO} - excecao nao tratada\n"
    arquivo = _gravar(cabecalho + resumo)

    log.error("excecao nao tratada: %s: %s", tipo.__name__, valor)
    for linha in resumo.rstrip().splitlines():
        log.error("  %s", linha)

    _mostrar_dialogo(resumo, arquivo)


def instalar() -> None:
    """Instala o hook global. Idempotente."""
    global _anterior, _instalado
    if _instalado:
        return
    _anterior = sys.excepthook
    sys.excepthook = tratar
    _instalado = True
