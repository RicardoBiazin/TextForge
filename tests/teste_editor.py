"""EditorDeTexto: margem, linha atual, Tab em bloco, undo, marcadores, zoom.

    .venv\\Scripts\\python.exe tests\\teste_editor.py

Roda em modo offscreen, entao NAO prova aparencia. Prova o que da' para provar
sem olhos, e o que mais quebra em silencio:

  * a margem cresce quando o arquivo passa de 99 para 100 linhas -- senao o
    numero da linha aparece cortado;
  * uma operacao sobre 500 linhas e' UM passo de desfazer -- senao "remover
    duplicadas" exigiria 500 Ctrl+Z, o que e' o mesmo que nao poder desfazer;
  * a coluna na barra de status conta colunas VISUAIS, nao caracteres -- num
    arquivo indentado com TAB, contar caracteres faz a barra mentir;
  * mudar o espacamento de linha nao marca o documento como modificado -- senao
    abrir um arquivo ja' o mostraria com asterisco de "nao salvo", e o usuario
    acabaria salvando uma alteracao que nunca fez.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, preparar_qt, pular, resumir, secao

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtCore import QEvent, QPoint, Qt                 # noqa: E402
from PySide6.QtGui import QKeyEvent, QTextCursor              # noqa: E402

from textforge import configuracao                             # noqa: E402
from textforge.editor import caixa                             # noqa: E402
from textforge.editor import operacoes_linha as ops            # noqa: E402
from textforge.editor.indentacao import Indentacao             # noqa: E402
from textforge.editor.widget import EditorDeTexto              # noqa: E402
from textforge.interface import tema as tmod                   # noqa: E402

TEMA = tmod.embutido("escuro")


def novo_editor(texto: str = "", **opcoes) -> EditorDeTexto:
    cfg = configuracao.padrao()
    cfg.update(opcoes)
    editor = EditorDeTexto(cfg, TEMA)
    editor.resize(800, 400)
    if texto:
        editor.setPlainText(texto)
        editor.document().setModified(False)
        editor.document().clearUndoRedoStacks()
    return editor


def teclar(editor: EditorDeTexto, tecla, modificadores=Qt.KeyboardModifier.NoModifier,
           texto: str = "") -> None:
    evento = QKeyEvent(QEvent.Type.KeyPress, tecla, modificadores, texto)
    editor.keyPressEvent(evento)


# ---------------------------------------------------------------------------
secao("1 - a margem acompanha o numero de digitos")

editor = novo_editor("\n".join(f"linha {i}" for i in range(99)))
largura_99 = editor.margem.largura_dos_numeros()
editor.setPlainText("\n".join(f"linha {i}" for i in range(100)))
largura_100 = editor.margem.largura_dos_numeros()
checa(largura_100 > largura_99,
      f"a margem cresce de 99 para 100 linhas ({largura_99} -> {largura_100})")

editor.setPlainText("\n".join(f"l{i}" for i in range(1000)))
checa(editor.margem.largura_dos_numeros() > largura_100,
      "e cresce de novo em 1000 linhas")

vazio = novo_editor()
checa(vazio.margem.largura_total() > 0,
      "documento vazio tem margem com largura positiva")
# Pintar um documento vazio e' o caminho mais curto para um IndexError no
# paintEvent; se isto estourar, o editor nem abre.
vazio.margem.render(vazio.margem.grab())
checa(True, "pintar a margem de um documento vazio nao estoura")

editor.margem.render(editor.margem.grab())
checa(True, "pintar a margem de um documento com 1000 linhas nao estoura")

# ---------------------------------------------------------------------------
secao("2 - realce da linha atual e camadas de selecao")

editor = novo_editor("a\nb\nc")
checa(editor.selecoes.tem("linha_atual"),
      "a linha atual e' realcada por padrao")

# Camadas independentes: quem mexe numa nao pode apagar a outra. Sem isto, o
# realce da busca apagaria o da linha atual e vice-versa.
from PySide6.QtWidgets import QTextEdit                        # noqa: E402

sel = QTextEdit.ExtraSelection()
sel.cursor = editor.textCursor()
sel.format.setBackground(TEMA.cor("editor.ocorrencia"))
editor.selecoes.definir("ocorrencias", [sel, sel, sel])
checa(editor.selecoes.tem("linha_atual") and editor.selecoes.tem("ocorrencias"),
      "duas camadas coexistem")
checa_igual(editor.selecoes.quantas("ocorrencias"), 3,
            "a camada guarda as 3 selecoes")
editor.selecoes.limpar("ocorrencias")
checa(editor.selecoes.tem("linha_atual"),
      "limpar uma camada NAO apaga as outras")

# A ordem de pintura e' deliberada: a ocorrencia atual tem de aparecer sobre o
# realce das demais.
editor.selecoes.definir("ocorrencias", [sel])
editor.selecoes.definir("ocorrencia_atual", [sel])
camadas = editor.selecoes.camadas()
checa(camadas.index("linha_atual") < camadas.index("ocorrencias")
      < camadas.index("ocorrencia_atual"),
      "a ordem de pintura e' linha_atual < ocorrencias < ocorrencia_atual")

desligado = novo_editor("a", realcar_linha_atual=False)
checa(not desligado.selecoes.tem("linha_atual"),
      "com a preferencia desligada, nao ha' realce de linha atual")

# ---------------------------------------------------------------------------
secao("3 - posicao do cursor em colunas VISUAIS")

editor = novo_editor("\tcodigo\n    outro", tabulacao=4)
recebido: list[tuple[int, int]] = []
editor.posicao_mudou.connect(lambda l, c: recebido.append((l, c)))

cursor = editor.textCursor()
cursor.setPosition(1)               # logo depois do TAB, na linha 0
editor.setTextCursor(cursor)
checa_igual(recebido[-1], (0, 4),
            "depois de um TAB, a coluna e' 4 (visual), nao 1 (caracteres)")

cursor.setPosition(editor.document().findBlockByNumber(1).position() + 4)
editor.setTextCursor(cursor)
checa_igual(recebido[-1], (1, 4), "linha 1, depois de 4 espacos: coluna 4")
checa_igual(recebido[-1][0], 1,
            "a linha e' reportada em BASE ZERO (a barra de status soma 1)")

# ---------------------------------------------------------------------------
secao("4 - contagem da selecao usa U+2029, nao \\n")

editor = novo_editor("um\ndois\ntres")
contagem: list[tuple[int, int]] = []
editor.selecao_mudou.connect(lambda c, l: contagem.append((c, l)))
cursor = editor.textCursor()
cursor.setPosition(0)
cursor.setPosition(len("um\ndois"), QTextCursor.MoveMode.KeepAnchor)
editor.setTextCursor(cursor)
checa_igual(contagem[-1][1], 2,
            "selecao de 2 linhas reporta 2 linhas (contar '\\n' daria sempre 1)")
checa_igual(contagem[-1][0], 7, "e reporta 7 caracteres")

cursor.clearSelection()
editor.setTextCursor(cursor)
checa_igual(contagem[-1], (0, 0), "sem selecao, reporta zero")

# ---------------------------------------------------------------------------
secao("5 - faixa de linhas selecionadas")

editor = novo_editor("a\nb\nc\nd")
checa_igual(editor.faixa_de_linhas_selecionadas(), (0, 1),
            "sem selecao, e' a linha do cursor")

cursor = editor.textCursor()
cursor.setPosition(0)
cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)   # "a\nb"
editor.setTextCursor(cursor)
checa_igual(editor.faixa_de_linhas_selecionadas(), (0, 2),
            "selecao tocando 2 linhas devolve 2 linhas")

# O caso que engana: selecao que termina EXATAMENTE no inicio da linha seguinte.
cursor.setPosition(0)
cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)   # "a\n"
editor.setTextCursor(cursor)
checa_igual(editor.faixa_de_linhas_selecionadas(), (0, 1),
            "selecao terminando no inicio da linha 1 NAO inclui a linha 1")

# ---------------------------------------------------------------------------
secao("6 - uma operacao em massa e' UM passo de desfazer")

muitas = "\n".join(["repetida"] * 250 + ["unica"] + ["repetida"] * 250)
editor = novo_editor(muitas)
editor.selectAll()
antes = editor.toPlainText()
editor.aplicar_em_linhas(ops.remover_duplicadas)
depois = editor.toPlainText()
checa(len(depois.split("\n")) == 2,
      f"remover duplicadas de 501 linhas deixou {len(depois.split(chr(10)))}")
editor.undo()
checa_igual(editor.toPlainText(), antes,
            "UM undo desfaz a operacao inteira (nao 500 undos)")
editor.redo()
checa_igual(editor.toPlainText(), depois, "e um redo refaz")

# ---------------------------------------------------------------------------
secao("7 - Tab e Shift+Tab")

editor = novo_editor("a\nb\nc", tabulacao=4, usar_espacos=True)
cursor = editor.textCursor()
cursor.setPosition(0)
cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Tab)
checa_igual(editor.toPlainText(), "    a\n    b\nc",
            "Tab com 2 linhas selecionadas indenta o BLOCO")
teclar(editor, Qt.Key.Key_Backtab)
checa_igual(editor.toPlainText(), "a\nb\nc", "Shift+Tab desindenta o bloco")

editor.undo()
checa_igual(editor.toPlainText(), "    a\n    b\nc",
            "indentar bloco e desindentar sao passos de undo separados")

# Sem selecao, Tab insere a UNIDADE de indentacao, nao um TAB literal.
editor = novo_editor("", tabulacao=4, usar_espacos=True)
teclar(editor, Qt.Key.Key_Tab)
checa_igual(editor.toPlainText(), "    ",
            "com 'usar_espacos', Tab insere 4 espacos e nao um TAB")

editor = novo_editor("", tabulacao=4, usar_espacos=False)
teclar(editor, Qt.Key.Key_Tab)
checa_igual(editor.toPlainText(), "\t",
            "com 'usar_espacos' desligado, Tab insere um TAB de verdade")

# Tab no meio de uma coluna vai ate' a PROXIMA parada de tabulacao.
editor = novo_editor("ab", tabulacao=4, usar_espacos=True)
cursor = editor.textCursor()
cursor.setPosition(2)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Tab)
checa_igual(editor.toPlainText(), "ab  ",
            "Tab na coluna 2 insere 2 espacos (ate' a coluna 4), nao 4")

# ---------------------------------------------------------------------------
secao("8 - auto-indent no Enter")

editor = novo_editor("    codigo", tabulacao=4, usar_espacos=True)
cursor = editor.textCursor()
cursor.movePosition(QTextCursor.MoveOperation.End)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Return)
checa_igual(editor.toPlainText(), "    codigo\n    ",
            "Enter repete a indentacao da linha anterior")

editor = novo_editor("\t\tcodigo", usar_espacos=False)
cursor = editor.textCursor()
cursor.movePosition(QTextCursor.MoveOperation.End)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Return)
checa_igual(editor.toPlainText(), "\t\tcodigo\n\t\t",
            "Enter repete os TAB da linha anterior")

# Com um provedor que declara 'aumenta_indentacao' (etapa 5), soma um nivel.
import re                                                      # noqa: E402


class ProvedorFalso:
    aumenta_indentacao = re.compile(r":\s*$")


editor = novo_editor("if x:", tabulacao=4, usar_espacos=True)
editor.provedor = ProvedorFalso()
cursor = editor.textCursor()
cursor.movePosition(QTextCursor.MoveOperation.End)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Return)
checa_igual(editor.toPlainText(), "if x:\n    ",
            "com a regra do provedor, ':' no fim soma um nivel")

# ---------------------------------------------------------------------------
secao("9 - Backspace apaga um nivel de indentacao")

editor = novo_editor("        x", tabulacao=4, usar_espacos=True)
cursor = editor.textCursor()
cursor.setPosition(8)               # depois dos 8 espacos, antes do 'x'
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Backspace)
checa_igual(editor.toPlainText(), "    x",
            "Backspace na indentacao apaga um NIVEL inteiro (4 espacos)")

# No meio do texto, Backspace apaga um caractere so'.
editor = novo_editor("abc", usar_espacos=True)
cursor = editor.textCursor()
cursor.setPosition(3)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Backspace)
checa_igual(editor.toPlainText(), "ab",
            "no meio do texto, Backspace apaga UM caractere")

editor = novo_editor("      x", tabulacao=4, usar_espacos=True)
cursor = editor.textCursor()
cursor.setPosition(6)
editor.setTextCursor(cursor)
teclar(editor, Qt.Key.Key_Backspace)
checa_igual(editor.toPlainText(), "    x",
            "de 6 espacos, Backspace volta para a parada em 4")

# ---------------------------------------------------------------------------
secao("10 - operacoes de linha aplicadas ao editor")

editor = novo_editor("b\na\nb")
editor.selectAll()
editor.aplicar_em_linhas(lambda l: ops.ordenar(l))
checa_igual(editor.toPlainText(), "a\nb\nb", "ordenar pelo editor")

editor = novo_editor("linha")
editor.duplicar_linha()
checa_igual(editor.toPlainText(), "linha\nlinha", "duplicar a linha do cursor")

editor = novo_editor("a\nb\nc")
cursor = editor.textCursor()
cursor.setPosition(editor.document().findBlockByNumber(1).position())
editor.setTextCursor(cursor)
editor.excluir_linha()
checa_igual(editor.toPlainText(), "a\nc",
            "excluir linha remove a linha, nao deixa uma vazia")

editor = novo_editor("a\nb\nc")
cursor = editor.textCursor()
cursor.setPosition(editor.document().findBlockByNumber(2).position())
editor.setTextCursor(cursor)
editor.mover_linha(para_baixo=False)
checa_igual(editor.toPlainText(), "a\nc\nb", "mover linha para cima")
checa_igual(editor.textCursor().blockNumber(), 1,
            "e o cursor acompanha a linha movida")
editor.mover_linha(para_baixo=True)
checa_igual(editor.toPlainText(), "a\nb\nc", "mover de volta para baixo")

editor = novo_editor("a\nb")
cursor = editor.textCursor()
cursor.setPosition(0)
editor.setTextCursor(cursor)
antes = editor.toPlainText()
editor.mover_linha(para_baixo=False)
checa_igual(editor.toPlainText(), antes,
            "mover a primeira linha para cima nao faz nada")

# ---------------------------------------------------------------------------
secao("11 - conversao de caixa no editor")

editor = novo_editor("numero_guia = 1")
cursor = editor.textCursor()
cursor.setPosition(0)
cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
editor.setTextCursor(cursor)
editor.converter_caixa(caixa.camel)
checa_igual(editor.toPlainText(), "numeroGuia = 1",
            "converter a selecao para camelCase")

# Sem selecao, age na palavra sob o cursor -- e' o que faz o comando ser usavel.
editor = novo_editor("numero_guia")
cursor = editor.textCursor()
cursor.setPosition(4)
editor.setTextCursor(cursor)
editor.converter_caixa(caixa.maiusculas)
checa("NUMERO_GUIA" in editor.toPlainText(),
      "sem selecao, converte a palavra sob o cursor")

# ---------------------------------------------------------------------------
secao("12 - marcadores")

editor = novo_editor("\n".join(f"l{i}" for i in range(10)))
checa_igual(editor.marcadores(), [], "comeca sem marcadores")

mudancas = {"n": 0}
editor.marcadores_mudaram.connect(lambda: mudancas.update(n=mudancas["n"] + 1))

editor.ir_para_linha(3)
editor.alternar_marcador()
checa_igual(editor.marcadores(), [3], "alternar marca a linha do cursor")
editor.alternar_marcador()
checa_igual(editor.marcadores(), [], "alternar de novo desmarca")
checa_igual(mudancas["n"], 2, "cada alternancia emite o sinal")

for linha in (1, 5, 8):
    editor.alternar_marcador(linha)
checa_igual(editor.marcadores(), [1, 5, 8], "marcadores vem ordenados")

editor.ir_para_linha(0)
checa(editor.ir_para_marcador(adiante=True), "ir_para_marcador acha o proximo")
checa_igual(editor.textCursor().blockNumber(), 1, "foi para a linha 1")
editor.ir_para_marcador(adiante=True)
checa_igual(editor.textCursor().blockNumber(), 5, "e depois para a linha 5")
editor.ir_para_linha(9)
editor.ir_para_marcador(adiante=True)
checa_igual(editor.textCursor().blockNumber(), 1,
            "depois do ultimo marcador, circula para o primeiro")
editor.ir_para_marcador(adiante=False)
checa_igual(editor.textCursor().blockNumber(), 8,
            "para tras, circula para o ultimo")

editor.limpar_marcadores()
checa_igual(editor.marcadores(), [], "limpar remove todos")
checa(not editor.ir_para_marcador(),
      "sem marcadores, ir_para_marcador devolve False em vez de estourar")

# ---------------------------------------------------------------------------
secao("13 - ir para linha")

editor = novo_editor("\n".join(f"l{i}" for i in range(100)))
editor.ir_para_linha(49)
checa_igual(editor.textCursor().blockNumber(), 49, "ir para a linha 49 (base 0)")
editor.ir_para_linha(0, 0)
checa_igual(editor.textCursor().blockNumber(), 0, "ir para a primeira linha")

# Fora da faixa nao pode estourar: o usuario digita 99999 no Ctrl+G.
editor.ir_para_linha(99999)
checa_igual(editor.textCursor().blockNumber(), 99,
            "linha adiante do fim para na ultima")
editor.ir_para_linha(-5)
checa_igual(editor.textCursor().blockNumber(), 0,
            "linha negativa para na primeira")

editor = novo_editor("abcdefgh")
editor.ir_para_linha(0, 4)
checa_igual(editor.textCursor().positionInBlock(), 4, "ir para a coluna 4")
editor.ir_para_linha(0, 9999)
checa_igual(editor.textCursor().positionInBlock(), 8,
            "coluna adiante do fim da linha para no fim")

# ---------------------------------------------------------------------------
secao("14 - zoom")

editor = novo_editor("x", fonte_tamanho=11)
tamanhos: list[int] = []
editor.zoom_mudou.connect(tamanhos.append)
editor.ajustar_zoom(+3)
checa_igual(editor.cfg["fonte_tamanho"], 14, "zoom soma ao tamanho")
checa_igual(tamanhos[-1], 14, "e emite o sinal com o valor novo")
checa_igual(editor.font().pointSize(), 14, "a fonte do widget acompanha")

for _ in range(50):
    editor.ajustar_zoom(-1)
checa(editor.cfg["fonte_tamanho"] >= 6, "o zoom tem piso")
antes = len(tamanhos)
editor.ajustar_zoom(-1)
checa_igual(len(tamanhos), antes,
            "no piso, nao emite sinal repetido (nada mudou)")

for _ in range(200):
    editor.ajustar_zoom(+1)
checa(editor.cfg["fonte_tamanho"] <= 48, "o zoom tem teto")

# ---------------------------------------------------------------------------
secao("15 - espacamento de linha nao marca o documento como modificado")

# Se marcasse, abrir um arquivo ja' o mostraria com o asterisco de "nao salvo", e
# o usuario acabaria salvando uma alteracao que ele nunca fez.
editor = novo_editor("a\nb\nc", fonte_espacamento=1.5)
checa(not editor.document().isModified(),
      "com espacamento 1.5, o documento recem-aberto NAO esta' modificado")

editor = novo_editor("a\nb\nc", fonte_espacamento=1.0)
editor.cfg["fonte_espacamento"] = 1.8
editor.aplicar_espacamento()
checa(not editor.document().isModified(),
      "mudar o espacamento com o arquivo aberto tambem nao o marca")

# ---------------------------------------------------------------------------
secao("16 - invisiveis, quebra de linha e tabulacao")

from PySide6.QtGui import QTextOption                          # noqa: E402
from PySide6.QtWidgets import QPlainTextEdit                   # noqa: E402

editor = novo_editor("a\tb", mostrar_espacos=True)
marcas = editor.document().defaultTextOption().flags()
checa(bool(marcas & QTextOption.Flag.ShowTabsAndSpaces),
      "com 'mostrar_espacos', a marca do Qt esta' ligada")
editor.cfg["mostrar_espacos"] = False
editor.aplicar_invisiveis()
marcas = editor.document().defaultTextOption().flags()
checa(not (marcas & QTextOption.Flag.ShowTabsAndSpaces),
      "desligando a preferencia, a marca sai")

editor = novo_editor("x", quebra_de_linha=True)
checa_igual(editor.lineWrapMode(), QPlainTextEdit.LineWrapMode.WidgetWidth,
            "com quebra de linha, o modo e' WidgetWidth")
editor.definir_quebra_de_linha(False)
checa_igual(editor.lineWrapMode(), QPlainTextEdit.LineWrapMode.NoWrap,
            "sem quebra de linha, o modo e' NoWrap")

# O TAB em PIXELS tem de acompanhar a largura configurada.
e4 = novo_editor("x", tabulacao=4)
e8 = novo_editor("x", tabulacao=8)
checa(e8.tabStopDistance() > e4.tabStopDistance(),
      "tabulacao 8 gera uma parada de TAB mais larga que 4")
e4.definir_indentacao(Indentacao(True, 8))
checa(abs(e4.tabStopDistance() - e8.tabStopDistance()) < 0.01,
      "trocar a indentacao recalcula a parada de TAB")

# ---------------------------------------------------------------------------
secao("17 - desenhar o texto nao estoura em nenhuma combinacao")

# O paintEvent e' onde um erro derruba o programa inteiro, e onde offscreen ainda
# consegue provar algo util: que o desenho roda de ponta a ponta.
for opcoes in ({}, {"mostrar_espacos": True}, {"mostrar_fim_de_linha": True},
               {"mostrar_guias_de_indentacao": True}, {"coluna_limite": 80},
               {"quebra_de_linha": True},
               {"mostrar_espacos": True, "mostrar_fim_de_linha": True,
                "mostrar_guias_de_indentacao": True, "coluna_limite": 80}):
    e = novo_editor("def f():\n\tif x:\n        return 1\n\nfim   ", **opcoes)
    e.grab()
    checa(True, f"desenhar com {opcoes or 'as opcoes padrao'} nao estoura")

vazio = novo_editor("", mostrar_fim_de_linha=True,
                    mostrar_guias_de_indentacao=True, coluna_limite=80)
vazio.grab()
checa(True, "desenhar um documento VAZIO com tudo ligado nao estoura")

# ---------------------------------------------------------------------------
secao("18 - selecao em BLOCO (Alt+arrastar)")

LARGURA_FIXA = ("codigo  001  ativo\n"
                "codigo  002  ativo\n"
                "codigo  003  ativo\n")

e = novo_editor(LARGURA_FIXA)
e.bloco.definir(0, 8, 2, 11)
checa(e.bloco.ativa, "definir() liga a selecao em bloco")
checa_igual(e.bloco.retangulo.linhas, 3, "tres linhas")
checa_igual(e.bloco.retangulo.largura, 3, "e tres colunas de largura")
checa_igual(e.bloco.texto(), "001\n002\n003",
            "*** o texto do bloco e' so' a coluna, e nao as linhas inteiras ***")
checa_igual(e.selecoes.quantas("bloco"), 3,
            "o retangulo e' pintado com uma ExtraSelection por linha")

secao("18b - digitar altera todas as linhas de uma vez")

e.bloco.substituir("XXX")
checa_igual(e.toPlainText(),
            "codigo  XXX  ativo\ncodigo  XXX  ativo\ncodigo  XXX  ativo\n",
            "digitar sobre o bloco troca a coluna nas TRES linhas")
e.undo()
checa_igual(e.toPlainText(), LARGURA_FIXA,
            "*** e UM Ctrl+Z desfaz as tres (nao uma por linha) ***")

e2 = novo_editor(LARGURA_FIXA)
e2.bloco.definir(0, 8, 2, 8)          # largura ZERO: um cursor por linha
checa(e2.bloco.retangulo.vazio, "largura zero e' um cursor por linha")
e2.bloco.substituir("# ")
checa_igual(e2.toPlainText(),
            "codigo  # 001  ativo\ncodigo  # 002  ativo\ncodigo  # 003  ativo\n",
            "com largura zero, o texto e' INSERIDO nas tres linhas")

secao("18c - apagar")

e3 = novo_editor(LARGURA_FIXA)
e3.bloco.definir(0, 8, 2, 11)
e3.bloco.apagar()
checa_igual(e3.toPlainText(),
            "codigo    ativo\ncodigo    ativo\ncodigo    ativo\n",
            "apagar tira a coluna das tres linhas")

secao("18d - linha mais curta que o retangulo")

DESIGUAL = "linha bem longa aqui\ncurta\noutra linha longa ok\n"
e4 = novo_editor(DESIGUAL)
e4.bloco.definir(0, 10, 2, 15)
checa_igual(e4.bloco.texto(), "longa\n\na lon",
            "*** a linha curta contribui com VAZIO, e nao e' pulada "
            "(a contagem de linhas se mantem) ***")
e4.bloco.substituir("#")
linhas = e4.toPlainText().split("\n")
checa_igual(linhas[1], "curta     #",
            "*** e ao escrever, a linha curta e' completada com espacos ate' a "
            "coluna (senao o texto sairia fora de coluna) ***")

secao("18e - colunas VISUAIS: um TAB nao vale uma coluna")

COM_TAB = "\tum\n    dois\n"
e5 = novo_editor(COM_TAB, usar_espacos=True, tabulacao=4)
checa_igual(e5.bloco.coluna_visual("\tum", 1), 4,
            "depois de um TAB de largura 4, a coluna visual e' 4")
checa_igual(e5.bloco.coluna_visual("    dois", 4), 4,
            "e quatro espacos dao a mesma coluna 4")
checa_igual(e5.bloco.posicao_da_coluna("\tum", 4), 1,
            "a coluna 4 da linha com TAB cai no caractere 1")
checa_igual(e5.bloco.posicao_da_coluna("\tum", 2), 1,
            "coluna DENTRO do TAB pula o TAB inteiro: ele comeca ANTES dela, "
            "entao pertence ao lado esquerdo")
checa_igual(e5.bloco.posicao_da_coluna("\tum", 0), 0,
            "e a coluna 0 pega o TAB, porque ele comeca la'")
e5.bloco.definir(0, 4, 1, 6)
checa_igual(e5.bloco.texto(), "um\ndo",
            "*** o retangulo sai alinhado nas duas linhas, apesar do TAB ***")
checa_igual(e5.bloco.posicao_da_coluna("ab", 99), 2,
            "coluna alem do fim devolve o comprimento da linha")

secao("18f - copiar, recortar e colar o bloco (regressao)")

# ESTE E' O TESTE DO DEFEITO RELATADO: apertar Ctrl para depois apertar C gera um
# KeyPress do PROPRIO Ctrl antes do C. Numa versao anterior ele caia na regra de
# "tecla sem semantica de bloco sai do modo", e a selecao sumia no caminho entre o
# Ctrl e o C -- o Ctrl+C nunca chegava a ter bloco para copiar.
from PySide6.QtWidgets import QApplication                      # noqa: E402

e8 = novo_editor(LARGURA_FIXA)
e8.bloco.definir(0, 8, 2, 11)
for modificador in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt):
    teclar(e8, modificador)
    checa(e8.bloco.ativa,
          f"*** apertar {modificador.name} sozinho NAO desfaz a selecao ***")

QApplication.clipboard().setText("<nada>")
e8.copy()
checa_igual(QApplication.clipboard().text(), "001\n002\n003",
            "copy() copia o BLOCO, e nao a selecao normal (vazia)")
checa(e8.bloco.ativa, "e copiar nao desfaz a selecao")

# Copiar tem de funcionar tambem pelo caminho do QAction: o atalho do menu e'
# resolvido pelo QShortcutMap ANTES de o evento chegar ao widget, entao tratar
# so' no keyPressEvent deixaria o menu copiando a selecao vazia.
QApplication.clipboard().setText("<nada>")
teclar(e8, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
checa_igual(QApplication.clipboard().text(), "001\n002\n003",
            "e Ctrl+C pelo teclado da' o mesmo resultado")

e9 = novo_editor(LARGURA_FIXA)
e9.bloco.definir(0, 8, 2, 11)
e9.cut()
checa_igual(QApplication.clipboard().text(), "001\n002\n003",
            "cut() copia o bloco")
checa_igual(e9.toPlainText(),
            "codigo    ativo\ncodigo    ativo\ncodigo    ativo\n",
            "e apaga a coluna nas tres linhas")

secao("18g - colar sobre um bloco: as tres regras")

e10 = novo_editor(LARGURA_FIXA)
e10.bloco.definir(0, 8, 2, 11)
QApplication.clipboard().setText("ZZZ")
e10.paste()
checa_igual(e10.toPlainText(),
            "codigo  ZZZ  ativo\ncodigo  ZZZ  ativo\ncodigo  ZZZ  ativo\n",
            "1 linha na area de transferencia vai para TODAS as linhas do bloco")

e11 = novo_editor(LARGURA_FIXA)
e11.bloco.definir(0, 8, 2, 11)
QApplication.clipboard().setText("AA\nBB\nCC")
e11.paste()
checa_igual(e11.toPlainText(),
            "codigo  AA  ativo\ncodigo  BB  ativo\ncodigo  CC  ativo\n",
            "*** 3 linhas num bloco de 3 linhas: uma para cada ***")
e11.undo()
checa_igual(e11.toPlainText(), LARGURA_FIXA,
            "e UM Ctrl+Z desfaz o colar em coluna inteiro")

e12 = novo_editor(LARGURA_FIXA)
e12.bloco.definir(0, 8, 2, 11)
QApplication.clipboard().setText("AA\nBB")          # 2 linhas num bloco de 3
e12.paste()
checa(not e12.bloco.ativa,
      "contagem que nao bate sai do modo bloco e cola normal "
      "(inventar uma regra daria resultado imprevisivel)")

secao("18h - o bloco some quando deve")

e6 = novo_editor(LARGURA_FIXA)
e6.bloco.definir(0, 0, 2, 3)
teclar(e6, Qt.Key.Key_Escape)
checa(not e6.bloco.ativa, "Esc limpa a selecao em bloco")
checa_igual(e6.selecoes.quantas("bloco"), 0, "e a camada de desenho tambem")

e6.bloco.definir(0, 0, 2, 3)
teclar(e6, Qt.Key.Key_Down)
checa(not e6.bloco.ativa,
      "uma seta sozinha sai do modo bloco (em vez de inventar semantica)")

e7 = novo_editor(LARGURA_FIXA)
e7.bloco.definir(0, 8, 2, 11)
e7.grab()
checa(True, "desenhar com selecao em bloco ativa nao estoura")

sys.exit(resumir())
