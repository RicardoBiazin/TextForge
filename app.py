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
    import time
    # Marcado o mais cedo possivel. NAO mede a descompactacao do modo um-arquivo
    # nem a varredura do antivirus, que acontecem ANTES de o Python existir --
    # justamente por isso a diferenca entre este numero e o cronometro de quem
    # esta' olhando a tela e' informativa: ela E' o custo do empacotamento.
    _t0 = time.perf_counter()

    from textforge import cli

    args = cli.analisar(argv)

    from textforge import log_interno, relatorio_de_erro
    log = log_interno.preparar()
    relatorio_de_erro.instalar()

    def _marca(etapa: str) -> None:
        """Registra quanto se passou desde o inicio do `main`.

        Existe porque "esta' demorando para abrir" nao se resolve por palpite: com
        estas marcas no log da' para ver se o tempo esta' no Qt, na sessao
        restaurada, ou fora do Python (empacotamento e antivirus).
        """
        log.info("partida: %-22s %6.2f s", etapa, time.perf_counter() - _t0)

    _marca("log pronto")

    for bruto, motivo in args.recusados:
        log.warning("caminho recusado (%s): %s", motivo, bruto)

    from textforge import configuracao, instancia_unica
    cfg = configuracao.carregar()
    _marca("configuracao")

    # Os provedores de linguagem sao registrados ANTES da janela: o primeiro
    # documento aberto ja' precisa deles para detectar a linguagem.
    from textforge import linguagens
    log.info("linguagens registradas: %d", linguagens.carregar_embutidos())
    _marca("linguagens")

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
    _marca("QApplication")

    # Fusion, e nao o estilo nativo do Windows. O estilo nativo desenha barra de
    # menu, barra de status e abas com as cores do SISTEMA e ignora boa parte da
    # QPalette -- no tema claro o texto do menu saia quase branco sobre fundo
    # claro, ilegivel. O Fusion honra a paleta inteira, que e' o que torna o
    # tema customizavel do requisito 28 possivel.
    app.setStyle("Fusion")

    from textforge.interface.janela import JanelaPrincipal
    # A sessao so' e' restaurada quando o TextForge e' aberto SEM arquivos: quem
    # deu duplo-clique num arquivo quer aquele arquivo, e nao as 12 abas da vez
    # anterior. E na autoverificacao do build, nunca.
    janela = JanelaPrincipal(
        cfg, restaurar_sessao=not args.alvos and not args.autoverificacao)
    _marca("janela montada")

    servidor = None
    if not args.nova_janela and not args.autoverificacao:
        servidor = instancia_unica.preparar(
            lambda pedido: _atender(janela, pedido, log), janela)
        if servidor is not None:
            app.aboutToQuit.connect(servidor.parar)
    _marca("instancia unica")

    if args.autoverificacao:
        return _autoverificar(janela, log)

    janela.show()
    _marca("JANELA NA TELA")
    # Os arquivos da linha de comando sao abertos DEPOIS do show(): assim a
    # janela aparece imediatamente e um arquivo grande nao atrasa a partida.
    for alvo in args.alvos:
        janela.abrir_arquivo(str(alvo.caminho), alvo.linha, alvo.coluna)
    if args.alvos:
        _marca("arquivos abertos")
    return app.exec()


def _atender(janela, pedido: dict, log) -> None:
    """Abre os arquivos que outra instancia mandou (o "Abrir com" do Windows)."""
    log.info("pedido recebido de outra instancia: %d arquivo(s)",
             len(pedido.get("arquivos", [])))
    janela.setWindowState(
        janela.windowState() & ~janela.windowState().__class__.WindowMinimized)
    janela.raise_()
    janela.activateWindow()
    for item in pedido.get("arquivos", []):
        caminho = item.get("caminho")
        if caminho:
            janela.abrir_arquivo(caminho, int(item.get("linha") or 0),
                                 int(item.get("coluna") or 0))


def _autoverificar(janela, log) -> int:
    """Confere que o executavel empacotado realmente funciona.

    Existe porque `excludes` agressivos no .spec quebram o app SO' em tempo de
    execucao. Sem esta checagem, "os excludes quebraram o app" chegaria como
    relatorio de bug do usuario em vez de falha de build.
    """
    import importlib.util

    # A lista e' o que o programa REALMENTE importa hoje. `difflib` estava aqui e
    # foi tirado: o diff e' encaixe da v2, ninguem o importa, e exigi-lo fazia a
    # autoverificacao reprovar um build correto. Uma checagem que reprova sem
    # defeito e' pior que nenhuma -- ensina a ignorar o resultado.
    faltando = [nome for nome in (
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork",       # QLocalServer: instancia unica e "Abrir com"
        "charset_normalizer",      # deteccao de encoding
        "json", "csv", "mmap", "codecs", "unicodedata", "hashlib", "base64",
        "urllib.parse", "html", "sqlparse",
        "xml.parsers.expat", "xml.etree.ElementTree",
    ) if importlib.util.find_spec(nome) is None]

    if faltando:
        log.error("autoverificacao FALHOU, modulos ausentes: %s",
                  ", ".join(faltando))
        print("FALHA: modulos ausentes no pacote: " + ", ".join(faltando))
        return 1

    # As OPCIONAIS nao reprovam o build -- o programa funciona sem elas --, mas
    # SAO relatadas. Elas entram no pacote se estiverem no venv na hora do build,
    # e sem este relatorio isso acontece por acidente: quem empacota numa maquina
    # sem black distribui um TextForge que nunca formata Python, e so' descobre
    # pelo usuario reclamando.
    for nome, recurso in (("black", "formatar Python"),
                          ("lxml", "XML com CDATA e DOCTYPE")):
        presente = importlib.util.find_spec(nome) is not None
        estado = "incluida" if presente else "AUSENTE"
        log.info("opcional %-6s %-9s (%s)", nome, estado, recurso)
        print(f"  opcional {nome:<6} {estado:<9} ({recurso})")

    janela.show()
    janela.close()
    log.info("autoverificacao OK")
    print("autoverificacao OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
