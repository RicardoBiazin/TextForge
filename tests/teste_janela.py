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
