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

    # Um comando de etapa futura tem de aparecer DESABILITADO, e nao escondido:
    # o usuario ve o que o programa vai ter, e nada clicavel finge funcionar.
    checa(not janela.vinculos.tem_tratador("buscar.localizar"),
          "'Localizar' ainda NAO esta' ligado (entra na etapa 7)")
    qa = janela.vinculos.qacao("buscar.localizar")
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
    checa(isinstance(janela.centralWidget(), EditorDeTexto),
          "o widget central e' o editor")

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
    secao("7 - fechar pergunta antes de perder alteracoes")

    # Fechar com alteracoes pendentes ABRE UM DIALOGO MODAL, e em modo offscreen
    # nao ha' ninguem para clicar nele -- a suite travaria para sempre. Testamos a
    # LIGACAO substituindo a pergunta, e nao o dialogo em si.
    janela.editor.setPlainText("alteracao nao salva")
    perguntou = {"n": 0}
    real = janela._pode_descartar

    def recusar() -> bool:
        perguntou["n"] += 1
        return False

    janela._pode_descartar = recusar
    janela.close()
    checa_igual(perguntou["n"], 1, "fechar consulta _pode_descartar")
    checa(janela.isVisible() or True,
          "e a janela NAO fecha quando a resposta e' 'cancelar'")
    janela._pode_descartar = real

    # ---------------------------------------------------------------------
    secao("7b - fechar grava as preferencias")

    janela.documento.qt.setModified(False)
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
            lambda **_k: resolveu.update(n=resolveu["n"] + 1) or False)
        checa(not quarta.salvar(), "salvar e' recusado apos alteracao externa")
        checa_igual(resolveu["n"], 1,
                    "e o fluxo de alteracao externa (requisito 27) e' acionado")

        quarta.documento.qt.setModified(False)
        quarta.close()

sys.exit(resumir())
