"""Janela principal: sobe, monta os menus, faz zoom e lembra a geometria.

    .venv\\Scripts\\python.exe tests\\teste_janela.py

Roda com QT_QPA_PLATFORM=offscreen, entao NAO prova que a aparencia esta' certa.
Prova o que da' para provar sem olhos: que a janela constroi sem excecao, que os
menus saem do registro, que os comandos ligados funcionam, e que fechar grava as
preferencias -- que e' onde um `closeEvent` quebrado passaria despercebido.
"""

from __future__ import annotations

import sys

from ajudantes import (appdata_temporario, checa, checa_igual, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import configuracao                            # noqa: E402
from textforge.interface import acoes                          # noqa: E402
from textforge.interface.janela import JanelaPrincipal         # noqa: E402

# ---------------------------------------------------------------------------
secao("1 - a janela constroi")

with appdata_temporario():
    cfg = configuracao.padrao()
    janela = JanelaPrincipal(cfg)

    # O titulo e' "<arquivo> - TextForge" (com "*" na frente se modificado), o
    # padrao de todo editor: o nome do arquivo primeiro, porque e' o que o usuario
    # procura na barra de tarefas com varias janelas abertas.
    checa("TextForge" in janela.windowTitle(),
          f"o titulo traz o nome do programa: {janela.windowTitle()!r}")
    checa(janela.windowTitle().startswith("Sem titulo"),
          "e comeca com o nome do documento")
    checa(janela.acceptDrops(),
          "a janela aceita arrastar e soltar (requisito 19)")
    checa(janela.centralWidget() is not None, "existe um widget central")
    checa(janela.statusBar() is not None, "existe barra de status")

    titulos = [a.text().replace("&", "") for a in janela.menuBar().actions()]
    checa_igual(titulos, list(acoes.ORDEM_DOS_MENUS),
                "os 8 menus do requisito 2, na ordem")

    checa(len(janela.ferramentas.actions()) > 0,
          "a barra de ferramentas foi preenchida")

    # ---------------------------------------------------------------------
    secao("2 - comandos ligados e desligados")

    checa(janela.vinculos.tem_tratador("arquivo.sair"),
          "'Sair' esta' ligado nesta etapa")
    checa(janela.vinculos.tem_tratador("exibir.aumentar_zoom"),
          "'Aumentar zoom' esta' ligado nesta etapa")
    checa(janela.vinculos.tem_tratador("arquivo.abrir"),
          "'Abrir' esta' ligado a partir da etapa 3")

    checa(janela.vinculos.tem_tratador("buscar.localizar"),
          "'Localizar' esta' ligado a partir da etapa 7")

    checa(janela.vinculos.tem_tratador("formatar.documento"),
          "'Formatar documento' esta' ligado a partir da etapa 8")

    checa(janela.vinculos.tem_tratador("ferramentas.tabela_csv"),
          "'Modo tabela (CSV)' esta' ligado a partir da etapa 9")

    checa(janela.vinculos.tem_tratador("ferramentas.acompanhar"),
          "'Acompanhar alteracoes (tail)' esta' ligado a partir da etapa 11")

    # Um comando ainda nao implementado tem de aparecer DESABILITADO, e nao
    # escondido: o usuario ve o que o programa vai ter, e nada clicavel finge
    # funcionar. `Comparar arquivos` esta' declarado como encaixe da v2.
    checa(not janela.vinculos.tem_tratador("ferramentas.comparar"),
          "'Comparar arquivos' ainda NAO esta' ligado (fica para a v2)")
    qa = janela.vinculos.qacao("ferramentas.comparar")
    checa(qa is not None and not qa.isEnabled(),
          "e por isso aparece desabilitado, em vez de fingir funcionar")

    # Todo comando com atalho tem QAction anexado a' janela; sem isso o atalho
    # simplesmente nao dispara, e a falha e' silenciosa.
    com_atalho = [c for c in acoes.REGISTRO.comandos if c.atalho]
    sem_qacao = [c.id for c in com_atalho if janela.vinculos.qacao(c.id) is None]
    checa_igual(sem_qacao, [], "todo comando com atalho virou QAction")

    # ---------------------------------------------------------------------
    secao("3 - editor no centro e comandos ligados a ele")

    from textforge.editor.widget import EditorDeTexto             # noqa: E402
    from textforge.interface.abas import GerenciadorAbas          # noqa: E402
    # O widget central e' um container com as abas MAIS a barra de busca
    # embutida. A barra fica ali, e nao numa doca, porque pertence ao documento
    # que esta' sendo editado -- uma doca poderia ser arrastada para longe dele.
    checa(janela.abas.parent() is not None
          and janela.centralWidget() is not None,
          "o widget central hospeda as abas e a barra de busca")
    checa(isinstance(janela.abas, GerenciadorAbas),
          "e janela.abas e' o gerenciador de abas")
    checa(janela.barra_de_busca.isHidden(),
          "a barra de busca comeca oculta (Ctrl+F a abre)")
    checa(isinstance(janela.editor, EditorDeTexto),
          "e janela.editor aponta para o editor da aba ativa")
    checa_igual(janela.abas.count(), 1,
                "sempre existe pelo menos UMA aba (a invariante da janela)")

    # A invariante existe para os ~50 comandos nao precisarem tratar "nenhum
    # documento aberto": fechar a ultima aba abre uma vazia no lugar.
    janela.fechar_aba_atual()
    checa_igual(janela.abas.count(), 1,
                "fechar a ultima aba cria uma vazia no lugar")

    # O zoom mora no EDITOR, nao na janela: e' o editor que tem a fonte e o
    # Ctrl+roda. A janela apenas encaminha o comando de menu.
    cfg["fonte_tamanho"] = 11
    janela.editor.aplicar_fonte()
    checa(janela.vinculos.acionar("exibir.aumentar_zoom"),
          "o comando de aumentar zoom esta' ligado")
    checa_igual(cfg["fonte_tamanho"], 12, "e aumentou o tamanho da fonte")
    janela.vinculos.acionar("exibir.zoom_normal")
    checa_igual(cfg["fonte_tamanho"], configuracao.padrao()["fonte_tamanho"],
                "zoom normal volta ao padrao")

    ESPERADOS_LIGADOS = [
        "editar.desfazer", "editar.refazer", "editar.copiar", "editar.colar",
        "editar.selecionar_tudo", "editar.copiar_linha",
        "linha.duplicar", "linha.excluir", "linha.mover_acima",
        "linha.ordenar", "linha.remover_duplicadas", "linha.remover_vazias",
        "linha.inverter", "linha.trim_inicio", "linha.trim_fim",
        "linha.prefixar", "linha.sufixar",
        "caixa.maiusculas", "caixa.snake", "caixa.camel",
        "indentar.aumentar", "indentar.diminuir",
        "indentar.tab_para_espacos", "indentar.espacos_para_tab",
        "ir.linha", "marca.alternar", "marca.proximo", "marca.limpar",
        "exibir.quebra_de_linha", "exibir.espacos", "exibir.fim_de_linha",
        "tab.2", "tab.4", "tab.8", "tab.usar_tab",
    ]
    faltando = [i for i in ESPERADOS_LIGADOS
                if not janela.vinculos.tem_tratador(i)]
    checa_igual(faltando, [],
                f"os {len(ESPERADOS_LIGADOS)} comandos da etapa 2 estao ligados")

    # ---------------------------------------------------------------------
    secao("4 - os comandos agem de verdade no editor")

    janela.editor.setPlainText("b\na\nb")
    janela.editor.selectAll()
    janela.vinculos.acionar("linha.ordenar")
    checa_igual(janela.editor.toPlainText(), "a\nb\nb",
                "'Ordenar linhas' pelo menu ordena o texto")

    janela.editor.selectAll()
    janela.vinculos.acionar("linha.remover_duplicadas")
    checa_igual(janela.editor.toPlainText(), "a\nb",
                "'Remover duplicadas' pelo menu funciona")

    janela.editor.undo()
    checa_igual(janela.editor.toPlainText(), "a\nb\nb",
                "e um unico undo desfaz a operacao do menu")

    janela.editor.setPlainText("numero_guia")
    janela.editor.selectAll()
    janela.vinculos.acionar("caixa.camel")
    checa_igual(janela.editor.toPlainText(), "numeroGuia",
                "'camelCase' pelo menu converte a selecao")

    # ---------------------------------------------------------------------
    secao("5 - opcoes de exibicao alternam e sao gravadas")

    antes = bool(cfg.get("quebra_de_linha"))
    janela.vinculos.acionar("exibir.quebra_de_linha")
    checa_igual(cfg["quebra_de_linha"], not antes,
                "alternar a quebra de linha grava a preferencia")
    qa = janela.vinculos.qacao("exibir.quebra_de_linha")
    checa_igual(qa.isChecked(), not antes,
                "e o item de menu passa a refletir o estado")

    janela.vinculos.acionar("tab.8")
    checa_igual(cfg["tabulacao"], 8, "'8 espacos' grava a tabulacao")
    checa_igual(janela.editor.indentacao.largura, 8,
                "e o editor passa a usar 8")

    # ---------------------------------------------------------------------
    secao("6 - barra de ferramentas e tema")

    visivel = janela.ferramentas.isVisible()
    janela.alternar_barra_de_ferramentas()
    checa_igual(cfg["mostrar_barra_de_ferramentas"], not visivel,
                "alternar a barra de ferramentas grava a preferencia")

    from textforge.interface import tema as tmod               # noqa: E402
    janela.aplicar_tema(tmod.embutido("escuro"))
    checa_igual(janela.tema.tipo, "escuro", "aplicar_tema troca o tema escuro")
    janela.aplicar_tema(tmod.embutido("claro"))
    checa_igual(janela.tema.tipo, "claro", "e troca de volta para o claro")

    from PySide6.QtWidgets import QApplication                 # noqa: E402
    paleta = QApplication.instance().palette()
    checa_igual(paleta.window().color().name(),
                janela.tema.cor("janela.fundo").name(),
                "a paleta vai para a QApplication (senao os dialogos nao seguem)")

    # ---------------------------------------------------------------------
    secao("6a - versao e autor no rodape")

    from textforge import APP, AUTOR, VERSAO                     # noqa: E402

    credito = janela.barra._credito
    checa(VERSAO in credito.text(), f"a versao aparece no rodape: {credito.text()!r}")
    checa(AUTOR in credito.text(), "e o autor tambem")
    checa(APP in credito.toolTip() and "desenvolvido por" in credito.toolTip(),
          "a dica traz o nome do programa e o 'desenvolvido por'")

    # PERMANENTE, e nao um `addWidget` comum: o Qt ESCONDE os widgets nao
    # permanentes a cada `showMessage()`, e um credito que pisca a cada
    # salvamento pareceria defeito.
    #
    # O que se verifica e' a POSICAO, e nao `isVisible()`: numa janela que nunca
    # foi exibida, `isVisible()` e' False para todo filho, e o teste passaria (ou
    # falharia) por um motivo que nao tem nada a ver com o que se quer provar.
    #
    # E nao se verifica `isHidden()` tampouco: MEDIDO nesta versao do Qt, o
    # `showMessage()` NAO esconde os widgets nao permanentes -- ele desenha a
    # mensagem sobre a area deles. A garantia real e' o credito estar na area
    # PERMANENTE, a' direita, longe de onde a mensagem e' desenhada.
    janela.show()
    from PySide6.QtWidgets import QApplication as _QApp            # noqa: E402
    _QApp.processEvents()
    x_da_mensagem = janela.barra._aviso.x()
    x_do_credito = credito.x()
    checa(x_do_credito > x_da_mensagem,
          f"o credito fica na area PERMANENTE, a' direita (x={x_do_credito}) e "
          f"nao onde a mensagem e' desenhada (x={x_da_mensagem})")

    janela.barra.showMessage("uma mensagem temporaria bem longa", 5000)
    _QApp.processEvents()
    checa(not credito.isHidden() and credito.x() == x_do_credito,
          "*** e uma mensagem temporaria nao o esconde nem o desloca ***")
    janela.barra.clearMessage()

    # E nao e' estado do documento: fechar a ultima aba nao pode apaga-lo.
    janela.barra.limpar()
    checa(VERSAO in credito.text(),
          "*** e sobrevive ao limpar() (nao e' estado do documento) ***")
    janela._mostrar_metadados()

    checa(janela.vinculos.tem_tratador("ajuda.sobre"),
          "clicar no credito leva ao dialogo Sobre, que ja' existia")

    # -- o link do autor no dialogo Sobre ---------------------------------
    # O dialogo e' modal; o teste substitui a caixa para capturar o texto sem
    # nunca exibi-la -- um modal em offscreen penduraria a suite para sempre.
    import re                                                    # noqa: E402
    import textforge                                             # noqa: E402
    from PySide6.QtCore import Qt as _Qt                         # noqa: E402
    from PySide6.QtWidgets import QMessageBox as _QMB            # noqa: E402
    from textforge.interface import janela as _jm                # noqa: E402

    capturado: dict = {}

    class _CaixaFalsa(_QMB):
        def exec(self):                                          # noqa: A003
            capturado["texto"] = self.text()
            capturado["flags"] = self.textInteractionFlags()
            return 0

    original_qmb, original_url = _jm.QMessageBox, _jm.LINKEDIN
    try:
        _jm.QMessageBox = _CaixaFalsa

        _jm.LINKEDIN = ""
        janela.mostrar_sobre()
        checa("<a href=" not in capturado["texto"],
              "*** sem LINKEDIN configurado, nenhum link e' inventado ***")
        checa(AUTOR in capturado["texto"], "e o autor aparece do mesmo jeito")

        _jm.LINKEDIN = "https://exemplo.invalido/perfil"
        janela.mostrar_sobre()
        achado = re.search(r"<a href='([^']+)'>([^<]+)</a>", capturado["texto"])
        checa(achado is not None, "com LINKEDIN configurado, o link aparece")
        if achado:
            checa_igual(achado.group(1), "https://exemplo.invalido/perfil",
                        "apontando para o endereco configurado")
            checa_igual(achado.group(2), "LinkedIn", "com o rotulo 'LinkedIn'")
        # Sem esta flag o `<a href>` fica azul e NAO abre ao ser clicado.
        checa(bool(capturado["flags"]
                   & _Qt.TextInteractionFlag.LinksAccessibleByMouse),
              "*** e e' CLICAVEL de verdade (LinksAccessibleByMouse) ***")
        checa(VERSAO in capturado["texto"],
              "o Sobre tambem traz a versao")

        # O Sobre e' onde alguem vai descobrir PARA QUE serve o programa, entao
        # a descricao e' conteudo, nao enfeite. Cada item citado aqui existe de
        # verdade -- se um recurso for removido, este teste cobra a atualizacao.
        _jm.LINKEDIN = ""
        janela.mostrar_sobre()
        texto = capturado["texto"]
        for termo in ("Codificacao", "Arquivos grandes", "Acompanhar log",
                      "Selecao em bloco", "Realce", "Formatar e validar",
                      "CSV em modo tabela", "Pesquisa"):
            checa(termo in texto, f"o Sobre diz o que faz: {termo}")
        checa("Nao executa o conteudo" in texto,
              "e mantem a promessa de nao executar o conteudo aberto")
        checa(texto.count("<li>") == texto.count("</li>"),
              "a lista do Sobre tem HTML balanceado")
    finally:
        _jm.QMessageBox, _jm.LINKEDIN = original_qmb, original_url

    # A URL configurada de verdade. `https://` NAO e' preciosismo: o texto vira
    # rich text com `<a href>` clicavel, e um esquema `file:` ou `javascript:` ali
    # seria um link que faz outra coisa ao ser clicado. O unico esquema aceito e' o
    # de uma pagina web.
    checa(not textforge.LINKEDIN or textforge.LINKEDIN.startswith("https://"),
          f"*** o LINKEDIN, quando configurado, e' https:// ***"
          f" ({textforge.LINKEDIN or 'vazio'})")
    checa(not textforge.LINKEDIN or "'" not in textforge.LINKEDIN,
          "e nao tem aspa simples, que quebraria o atributo href do HTML montado")
    if textforge.LINKEDIN:
        _jm.LINKEDIN = textforge.LINKEDIN
        try:
            _jm.QMessageBox = _CaixaFalsa
            janela.mostrar_sobre()
        finally:
            _jm.QMessageBox = original_qmb
        checa(textforge.LINKEDIN in capturado["texto"],
              "e a URL de verdade chega ao dialogo Sobre")

    # ---------------------------------------------------------------------
    secao("6b - os menus da barra continuam VIVOS (regressao)")

    # Esta secao guarda um defeito real, encontrado no .exe empacotado:
    # `QAction.menu()` devolve um QMenu cujo tempo de vida fica atrelado ao
    # wrapper Python do QAction. Assim que a funcao que iterou
    # `menuBar().actions()` retorna, o wrapper e' coletado e o shiboken DESTROI o
    # objeto C++ do menu -- a barra fica com um ponteiro pendurado, e abrir o menu
    # levanta "Internal C++ object (QMenu) already deleted".
    #
    # `gc.collect()` e' o que torna o teste deterministico: sem ele, o defeito so'
    # apareceria quando o coletor resolvesse rodar.
    #
    # E NOTE: a checagem abaixo NAO chama `acao.menu()`. Uma versao anterior deste
    # teste chamava, e com isso CAUSAVA o proprio defeito que pretendia detectar --
    # o menu morria na verificacao. `acao.menu()` e' veneno em qualquer contexto,
    # e a varredura estatica logo adiante e' o que impede alguem de reintroduzi-lo.
    import gc                                                    # noqa: E402
    from textforge.interface import acoes as amod                # noqa: E402
    gc.collect()

    mortos = []
    for grupo in amod.ORDEM_DOS_MENUS:
        alvo = janela.vinculos.menu(grupo)
        if alvo is None:
            continue
        try:
            len(alvo.actions())
        except RuntimeError:
            mortos.append(grupo)
    checa_igual(mortos, [],
                "nenhum menu da barra foi destruido apos a construcao")

    checa(janela.vinculos.menu("Linguagem") is not None,
          "vinculos.menu() acha o menu por grupo (sem passar por QAction.menu())")
    checa(janela.vinculos.menu("Inexistente") is None,
          "e devolve None para um grupo que nao existe")

    # Abrir o menu de Linguagem duas vezes: e' o caminho exato que estourava.
    janela._menu_linguagem.aboutToShow.emit()
    quantos = len(janela._menu_linguagem.actions())
    checa(quantos > 20,
          f"*** abrir o menu Linguagem preenche os provedores ({quantos} itens) ***")
    gc.collect()
    janela._menu_linguagem.aboutToShow.emit()
    checa_igual(len(janela._menu_linguagem.actions()), quantos,
                "e abrir de novo (apos um gc) da' o mesmo, sem estourar")

    janela._menu_recentes.aboutToShow.emit()
    checa(len(janela._menu_recentes.actions()) >= 1,
          "o menu de recentes tambem sobrevive e se preenche")

    # Varredura estatica: `QAction.menu()` nao pode voltar ao codigo. Ela olha a
    # ARVORE, e nao o texto, para os comentarios que CITAM o problema (inclusive
    # os deste arquivo) nao serem acusados como se fossem o problema.
    import ast                                                   # noqa: E402
    import pathlib                                               # noqa: E402
    from ajudantes import RAIZ                                   # noqa: E402

    culpados: list[str] = []
    for arquivo in list((RAIZ / "textforge").rglob("*.py")) + \
            list((RAIZ / "tests").glob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8", errors="replace")
        for no in ast.walk(ast.parse(fonte)):
            # `x.menu()` sem argumento. `self.vinculos.menu("Arquivo")` tem
            # argumento e e' justamente a forma CERTA, entao nao entra aqui.
            if (isinstance(no, ast.Call)
                    and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "menu"
                    and not no.args and not no.keywords):
                culpados.append(
                    f"{pathlib.Path(arquivo).name}:{no.lineno}")
    checa_igual(culpados, [],
                "*** ninguem chama `acao.menu()`: ele DESTROI o QMenu quando o "
                "wrapper do QAction e' coletado ***")

    # ---------------------------------------------------------------------
    secao("7 - fechar pergunta antes de perder alteracoes")

    # Fechar com alteracoes pendentes ABRE UM DIALOGO MODAL, e em modo offscreen
    # nao ha' ninguem para clicar nele -- a suite travaria para sempre. Testamos a
    # LIGACAO substituindo a pergunta, e nao o dialogo em si.
    janela.editor.textCursor().insertText("alteracao nao salva")
    checa(janela.documento.modificado, "o documento esta' modificado")

    perguntou = {"n": 0}
    real = janela.abas.pode_fechar

    def recusar(_aba) -> bool:
        perguntou["n"] += 1
        return False

    janela.abas.pode_fechar = recusar
    janela.close()
    checa(perguntou["n"] >= 1,
          "fechar a janela consulta pode_fechar de cada aba")
    checa_igual(janela.abas.count(), 1,
                "e a aba NAO e' fechada quando a resposta e' 'cancelar'")
    janela.abas.pode_fechar = real

    # ---------------------------------------------------------------------
    secao("7b - fechar grava as preferencias e a sessao")

    for aba in janela.abas.abas():
        aba.documento.qt.setModified(False)
    janela.resize(900, 600)
    janela.close()

    gravado = configuracao.carregar()
    checa(gravado.get("geometria"), "a geometria foi gravada ao fechar")
    checa_igual(gravado.get("fonte_tamanho"), cfg["fonte_tamanho"],
                "o tamanho da fonte foi gravado ao fechar")

    # ---------------------------------------------------------------------
    secao("8 - a geometria e' restaurada, e uma corrompida nao derruba")

    outra = JanelaPrincipal(configuracao.carregar())
    checa(outra.width() > 0 and outra.height() > 0,
          "a janela reabre com a geometria gravada")
    outra.documento.qt.setModified(False)
    outra.close()

    ruim = configuracao.padrao()
    ruim["geometria"] = "isso nao e base64 valido de QByteArray !!!"
    terceira = JanelaPrincipal(ruim)
    checa(terceira.width() > 0,
          "geometria corrompida no config cai no tamanho padrao, sem estourar")
    terceira.documento.qt.setModified(False)
    terceira.close()

    # ---------------------------------------------------------------------
    secao("9 - abrir e salvar arquivo de verdade (etapa 3)")

    from ajudantes import pasta_temporaria                        # noqa: E402
    with pasta_temporaria() as tmp:
        quarta = JanelaPrincipal(configuracao.padrao())

        for id_ in ("arquivo.novo", "arquivo.abrir", "arquivo.salvar",
                    "arquivo.salvar_como", "arquivo.recarregar",
                    "arquivo.propriedades", "arquivo.reabrir_como",
                    "codificacao.escolher", "eol.crlf", "eol.lf", "eol.cr"):
            checa(quarta.vinculos.tem_tratador(id_),
                  f"{id_} esta' ligado na etapa 3")

        alvo = tmp / "abrir.txt"
        alvo.write_bytes("coração\r\nsegunda linha\r\n".encode("cp1252"))
        checa(quarta.abrir_arquivo(str(alvo)), "abrir_arquivo devolve True")
        checa_igual(quarta.documento.nome, "abrir.txt",
                    "e o documento passa a ser o arquivo aberto")
        checa("coração" in quarta.editor.toPlainText(),
              "o conteudo cp1252 aparece no editor com os acentos certos")
        checa(quarta.windowTitle().startswith("abrir.txt"),
              f"o titulo da janela traz o nome: {quarta.windowTitle()!r}")

        # Salvar sem editar tem de devolver os MESMOS bytes.
        antes = alvo.read_bytes()
        checa(quarta.salvar(), "salvar devolve True")
        checa_igual(alvo.read_bytes(), antes,
                    "e o arquivo no disco fica byte a byte igual")

        # Editar, salvar, conferir que o cp1252 e o CRLF foram preservados.
        quarta.editor.setPlainText("ação\r\nnova linha")
        checa(quarta.salvar(), "salvar depois de editar devolve True")
        gravado = alvo.read_bytes()
        checa(b"\r\n" in gravado,
              "o CRLF original foi preservado na gravacao")
        checa("ação".encode("cp1252") in gravado,
              "e a codificacao cp1252 original tambem")
        checa(not quarta.documento.modificado,
              "depois de salvar, o documento nao esta' mais modificado")

        # Alteracao externa: salvar tem de ser recusado.
        alvo.write_bytes(b"mexido por outro programa\r\n")
        quarta.editor.setPlainText("minha versao")
        quarta.documento.qt.setModified(True)
        resolveu = {"n": 0}
        quarta._resolver_alteracao_externa = (
            lambda _doc, **_k: resolveu.update(n=resolveu["n"] + 1) or False)
        checa(not quarta.salvar(), "salvar e' recusado apos alteracao externa")
        checa_igual(resolveu["n"], 1,
                    "e o fluxo de alteracao externa (requisito 27) e' acionado")

        quarta.documento.qt.setModified(False)

        # -----------------------------------------------------------------
        secao("10 - varias abas e sessao (etapa 4)")

        outro = tmp / "segundo.py"
        outro.write_bytes(b"def f():\n  return 1\n")
        checa(quarta.abrir_arquivo(str(outro)), "abre um segundo arquivo")
        checa_igual(quarta.abas.count(), 2, "e agora sao duas abas")
        checa_igual(quarta.documento.nome, "segundo.py",
                    "a aba nova recebe o foco")
        checa_igual(quarta.documento.indentacao.largura, 2,
                    "e a indentacao detectada e' a DO ARQUIVO (2 espacos)")

        # Reabrir o mesmo arquivo foca a aba existente em vez de duplicar.
        checa(quarta.abrir_arquivo(str(alvo)), "reabrir o primeiro arquivo")
        checa_igual(quarta.abas.count(), 2, "NAO cria uma terceira aba")
        checa_igual(quarta.documento.nome, "abrir.txt",
                    "e foca a aba que ja' tinha o arquivo")

        # A barra de status acompanha a troca de aba.
        quarta.abas.setCurrentIndex(1)
        checa_igual(quarta.documento.nome, "segundo.py",
                    "trocar de aba troca o documento atual")

        instantaneo = quarta._capturar_sessao()
        checa_igual(len(instantaneo.abas), 2,
                    "a sessao captura as duas abas com arquivo")
        caminhos = {a.caminho for a in instantaneo.abas}
        checa(str(alvo) in caminhos and str(outro) in caminhos,
              "e os dois caminhos estao la'")

        # Uma aba SEM arquivo nao entra na sessao (ela vive na recuperacao).
        quarta.nova_aba()
        checa_igual(len(quarta._capturar_sessao().abas), 2,
                    "aba 'Sem titulo' NAO entra na sessao")

        # -----------------------------------------------------------------
        secao("11 - busca pela janela (etapa 7)")

        quarta.nova_aba()
        editor = quarta.abas.editor_atual()
        editor.setPlainText("alfa beta alfa gama alfa")

        quarta.abrir_busca()
        checa(not quarta.barra_de_busca.isHidden(),
              "Ctrl+F abre a barra de busca")

        quarta.barra_de_busca.campo.setText("alfa")
        from textforge.busca import Criterio                       # noqa: E402
        criterio = Criterio(texto="alfa")

        quarta._procurar_ao_digitar(criterio)
        # O cursor esta' na posicao 0, que E' o inicio da primeira ocorrencia --
        # entao o contador ja' sabe QUAL delas e' e mostra "1 de 3", que e' mais
        # informativo que o total solto.
        checa_igual(quarta.barra_de_busca.contador.text(), "1 de 3",
                    "o contador mostra 'N de total' quando o cursor esta' "
                    "sobre uma ocorrencia")
        checa_igual(editor.selecoes.quantas("ocorrencias"), 3,
                    "e as tres ocorrencias sao realcadas")

        # Com o cursor FORA de qualquer ocorrencia, mostra apenas o total.
        cursor_meio = editor.textCursor()
        cursor_meio.setPosition(6)          # dentro de "beta"
        editor.setTextCursor(cursor_meio)
        quarta._procurar_ao_digitar(criterio)
        checa_igual(quarta.barra_de_busca.contador.text(), "3 achado(s)",
                    "e mostra so' o total quando o cursor nao esta' em nenhuma")

        # Volta o cursor ao inicio para a sequencia de F3 comecar do primeiro.
        inicio = editor.textCursor()
        inicio.setPosition(0)
        editor.setTextCursor(inicio)

        quarta._procurar(criterio, False)
        checa_igual(editor.textCursor().selectedText(), "alfa",
                    "F3 seleciona a ocorrencia")
        checa_igual(quarta.barra_de_busca.contador.text(), "1 de 3",
                    "e o contador mostra '1 de 3'")
        quarta._procurar(criterio, False)
        checa_igual(quarta.barra_de_busca.contador.text(), "2 de 3",
                    "o F3 seguinte avanca para '2 de 3'")
        quarta._procurar(criterio, False)
        checa_igual(quarta.barra_de_busca.contador.text(), "3 de 3",
                    "e depois para '3 de 3'")
        quarta._procurar(criterio, False)
        checa_igual(quarta.barra_de_busca.contador.text(), "1 de 3",
                    "passando da ultima, circula para a primeira (como todo F3)")
        quarta._procurar(criterio, True)
        checa_igual(quarta.barra_de_busca.contador.text(), "3 de 3",
                    "e Shift+F3 do inicio circula para a ultima")

        # Regex invalida NAO abre dialogo: e' o estado normal enquanto se digita.
        ruim = Criterio(texto="(\\d+", expressao_regular=True)
        quarta._procurar_ao_digitar(ruim)
        checa_igual(quarta.barra_de_busca.contador.text(), "regex invalida",
                    "regex incompleta avisa na barra, sem dialogo modal")
        checa(quarta.barra_de_busca.campo.toolTip(),
              "e a mensagem do erro fica na dica do campo")

        # Substituir todos pela janela.
        quarta._substituir_tudo(criterio, "OMEGA", False)
        checa_igual(editor.toPlainText(), "OMEGA beta OMEGA gama OMEGA",
                    "'Substituir todos' pela janela troca as tres")
        editor.undo()
        checa_igual(editor.toPlainText(), "alfa beta alfa gama alfa",
                    "e UM Ctrl+Z desfaz tudo")

        quarta.barra_de_busca.esconder()
        checa_igual(editor.selecoes.quantas("ocorrencias"), 0,
                    "fechar a barra limpa o realce das ocorrencias")

        # -----------------------------------------------------------------
        secao("12 - formatar pela janela (etapa 8)")

        # O exemplo LITERAL do requisito 39: abrir o XML compactado e formatar.
        xml = tmp / "config.xml"
        xml.write_bytes(
            b"<config><servidor><ip>192.168.0.10</ip></servidor></config>\r\n")
        checa(quarta.abrir_arquivo(str(xml)), "abre o XML")
        checa_igual(quarta.documento.nome_da_linguagem, "XML",
                    "e a linguagem e' detectada como XML")

        quarta.vinculos.acionar("formatar.documento")
        texto = quarta.abas.editor_atual().toPlainText()
        checa("\n    <servidor>" in texto,
              "'Formatar documento' produz a hierarquia indentada do requisito 39")
        checa("192.168.0.10" in texto, "e o conteudo sobrevive")

        # UM undo desfaz a formatacao inteira.
        quarta.abas.editor_atual().undo()
        checa("\n    <servidor>" not in quarta.abas.editor_atual().toPlainText(),
              "e UM Ctrl+Z desfaz a formatacao toda")
        quarta.abas.editor_atual().redo()

        # Validar um XML quebrado abre o painel Problemas e navega ate' o erro.
        ruim = tmp / "quebrado.xml"
        ruim.write_bytes(b"<a>\n  <b>\n</a>\n")
        quarta.abrir_arquivo(str(ruim))
        quarta.vinculos.acionar("formatar.validar")
        checa(not quarta.doca_problemas.isHidden(),
              "validar um XML quebrado abre o painel Problemas")
        checa(quarta.painel_problemas.arvore.topLevelItemCount() >= 1,
              "com o problema listado")
        destino = quarta.painel_problemas.primeiro_erro()
        checa(destino is not None, "e o problema e' navegavel")
        checa_igual(quarta.abas.editor_atual().textCursor().blockNumber(), 2,
                    "o cursor foi para a linha do erro (linha 3, base zero 2)")

        # Validar um XML bom limpa o painel.
        quarta.abrir_arquivo(str(xml))
        quarta.vinculos.acionar("formatar.validar")
        checa("valido" in quarta.painel_problemas.cabecalho.text().lower()
              or "Nenhum" in quarta.painel_problemas.cabecalho.text(),
              f"XML valido limpa o painel: "
              f"{quarta.painel_problemas.cabecalho.text()!r}")

        # JSON com chave duplicada: RECUSA, e o documento NAO e' alterado.
        jsonf = tmp / "dup.json"
        jsonf.write_bytes(b'{"a": 1, "a": 2}')
        quarta.abrir_arquivo(str(jsonf))
        antes_json = quarta.abas.editor_atual().toPlainText()
        quarta.vinculos.acionar("formatar.documento")
        checa_igual(quarta.abas.editor_atual().toPlainText(), antes_json,
                    "chave duplicada: o documento NAO e' alterado")
        checa(not quarta.doca_problemas.isHidden(),
              "e o painel Problemas explica por que")

        for aba in quarta.abas.abas():
            aba.documento.qt.setModified(False)
        quarta.close()

sys.exit(resumir())
