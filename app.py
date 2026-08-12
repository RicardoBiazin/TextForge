"""Ponto de entrada do TextForge.

    python app.py
    python app.py config.xml
    python app.py arquivo.txt --line 850

Este arquivo e' de proposito minusculo: e' o alvo do PyInstaller e o unico lugar
onde a ordem de inicializacao esta' escrita. Toda logica vive no pacote
`textforge`.

Ordem, e o motivo de cada passo vir onde vem:

  1. CLI            -- se o usuario pediu --versao, nem vale subir o Qt.
  2. log e excepthook -- ligados ANTES de qualquer outra coisa poder falhar.
  3. instancia unica -- antes de criar a janela: se ja' existe uma instancia,
                        este processo entrega os arquivos e morre sem custo.
  4. QApplication e janela.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from textforge import cli

    args = cli.analisar(argv)

    from textforge import log_interno, relatorio_de_erro
    log = log_interno.preparar()
    relatorio_de_erro.instalar()

    for bruto, motivo in args.recusados:
        log.warning("caminho recusado (%s): %s", motivo, bruto)

    from textforge import configuracao, instancia_unica
    cfg = configuracao.carregar()

    if not args.nova_janela and not args.autoverificacao and args.alvos:
        if instancia_unica.enviar_para_instancia_existente(args.como_pedido()):
            return 0

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    if args.autoverificacao:
        # Modo de verificacao do build: sem janela de verdade. Ver cli.py.
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("TextForge")
    app.setApplicationVersion(__import__("textforge").VERSAO)

    from textforge.interface.janela import JanelaPrincipal
    janela = JanelaPrincipal(cfg)

    servidor = None
    if not args.nova_janela and not args.autoverificacao:
        servidor = instancia_unica.preparar(
            lambda pedido: log.info("pedido recebido: %r", pedido), janela)
        if servidor is not None:
            app.aboutToQuit.connect(servidor.parar)

    if args.autoverificacao:
        return _autoverificar(janela, log)

    janela.show()
    return app.exec()


def _autoverificar(janela, log) -> int:
    """Confere que o executavel empacotado realmente funciona.

    Existe porque `excludes` agressivos no .spec quebram o app SO' em tempo de
    execucao. Sem esta checagem, "os excludes quebraram o app" chegaria como
    relatorio de bug do usuario em vez de falha de build.
    """
    import importlib.util

    faltando = [nome for nome in (
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork",       # QLocalServer: instancia unica e "Abrir com"
        "charset_normalizer",      # deteccao de encoding
        "json", "csv", "difflib", "mmap", "codecs", "unicodedata",
        "xml.parsers.expat", "xml.etree.ElementTree",
    ) if importlib.util.find_spec(nome) is None]

    if faltando:
        log.error("autoverificacao FALHOU, modulos ausentes: %s",
                  ", ".join(faltando))
        print("FALHA: modulos ausentes no pacote: " + ", ".join(faltando))
        return 1

    janela.show()
    janela.close()
    log.info("autoverificacao OK")
    print("autoverificacao OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
