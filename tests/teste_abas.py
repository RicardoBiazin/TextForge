"""Abas: identidade por arquivo, asterisco, menu de contexto, fechamento.

    .venv\\Scripts\\python.exe tests\\teste_abas.py

A verificacao mais importante e' a de IDENTIDADE: abrir o mesmo arquivo duas vezes
tem de FOCAR a aba existente, comparando por caminho resolvido e ignorando a caixa.
No Windows o mesmo arquivo chega com caixa diferente do Explorer, pela forma curta
8.3, ou por caminho relativo -- e duas abas do mesmo arquivo divergem, com uma das
versoes se perdendo no primeiro salvamento.

A segunda e' o vazamento: fechar uma aba tem de liberar o QTextDocument. Vinte
arquivos de 10 MB abertos e fechados ao longo do dia seriam 200 MB retidos.
"""

from __future__ import annotations

import gc
import sys
import weakref

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import configuracao                             # noqa: E402
from textforge.documento import Documento                       # noqa: E402
from textforge.interface import tema as tmod                    # noqa: E402
from textforge.interface.abas import GerenciadorAbas            # noqa: E402

CFG = configuracao.padrao()
TEMA = tmod.embutido("escuro")


def novo_gerenciador() -> GerenciadorAbas:
    g = GerenciadorAbas(CFG, TEMA)
    g.resize(800, 400)
    return g


# ---------------------------------------------------------------------------
secao("1 - adicionar e navegar")

g = novo_gerenciador()
checa_igual(g.count(), 0, "comeca sem abas")
checa(g.aba_atual() is None, "e sem aba atual")
checa(g.documento_atual() is None, "e sem documento atual")

a1 = g.adicionar(Documento.novo(CFG))
checa_igual(g.count(), 1, "adicionar cria a aba")
checa(g.aba_atual() is a1, "e a foca")
checa(g.documento_atual() is a1.documento, "documento_atual aponta para ela")
checa(g.editor_atual() is a1.editor, "editor_atual tambem")
checa(g.tabText(0).startswith("Sem titulo"),
      f"o titulo vem do documento: {g.tabText(0)!r}")

a2 = g.adicionar(Documento.novo(CFG))
checa_igual(g.count(), 2, "segunda aba")
checa(g.aba_atual() is a2, "a nova aba recebe o foco")
checa_igual(len(g.abas()), 2, "abas() lista as duas")

# ---------------------------------------------------------------------------
secao("2 - identidade: uma aba por ARQUIVO")

with pasta_temporaria() as pasta:
    alvo = pasta / "Config.XML"
    alvo.write_bytes(b"<a/>")

    g = novo_gerenciador()
    primeira = g.adicionar(Documento.abrir(alvo, CFG))
    checa_igual(g.count(), 1, "abre o arquivo numa aba")

    # Mesmo arquivo, caixa diferente: e' como o Explorer entrega.
    segunda = g.adicionar(Documento.abrir(pasta / "config.xml", CFG))
    checa_igual(g.count(), 1,
                "abrir o MESMO arquivo com outra caixa NAO cria segunda aba")
    checa(segunda is primeira, "e devolve a aba existente")

    # Caminho com ".." resolvendo para o mesmo arquivo.
    terceira = g.adicionar(
        Documento.abrir(pasta / ".." / pasta.name / "Config.XML", CFG))
    checa_igual(g.count(), 1, "caminho com '..' tambem reusa a aba")
    checa(terceira is primeira, "e devolve a mesma")

    # Arquivo diferente: aba nova.
    outro = pasta / "outro.xml"
    outro.write_bytes(b"<b/>")
    g.adicionar(Documento.abrir(outro, CFG))
    checa_igual(g.count(), 2, "arquivo diferente abre aba nova")

    checa(g.indice_por_chave(Documento.abrir(alvo, CFG).chave()) == 0,
          "indice_por_chave acha a aba certa")
    checa_igual(g.indice_por_chave("nao/existe"), -1,
                "e devolve -1 para chave desconhecida")

# Dois documentos SEM arquivo nunca colidem entre si.
g = novo_gerenciador()
g.adicionar(Documento.novo(CFG))
g.adicionar(Documento.novo(CFG))
checa_igual(g.count(), 2, "duas abas 'Sem titulo' coexistem")

# ---------------------------------------------------------------------------
secao("3 - asterisco de modificado (requisito 2)")

with pasta_temporaria() as pasta:
    alvo = pasta / "mod.txt"
    alvo.write_bytes(b"original\r\n")
    g = novo_gerenciador()
    aba = g.adicionar(Documento.abrir(alvo, CFG))
    checa_igual(g.tabText(0), "mod.txt", "sem asterisco quando salvo")

    # ATENCAO: `setPlainText()` ZERA a flag de modificado do QTextDocument, entao
    # nao serve para simular uma edicao do usuario. Um `insertText` num cursor e'
    # o que reproduz a digitacao -- inclusive marcar o documento como modificado.
    aba.editor.textCursor().insertText("mexido ")
    checa_igual(g.tabText(0), "*mod.txt",
                "o asterisco aparece ao modificar (sem precisar de codigo extra)")

    aba.documento.qt.setModified(False)
    checa_igual(g.tabText(0), "mod.txt", "e sai quando o documento e' salvo")

    checa_igual(g.tabToolTip(0), str(alvo),
                "a dica da aba mostra o caminho completo")

    checa_igual(len(g.com_pendencias()), 0, "sem pendencias")
    aba.editor.textCursor().insertText("de novo ")
    checa_igual(len(g.com_pendencias()), 1, "com_pendencias acha a aba alterada")

    # A armadilha, escrita como teste para ninguem cair nela de novo.
    aba.documento.qt.setModified(False)
    aba.editor.setPlainText("trocado por setPlainText")
    checa(not aba.documento.modificado,
          "setPlainText() ZERA a flag de modificado (nao e' uma edicao do usuario)")
    aba.documento.definir_texto("agora com marcar_modificado", marcar_modificado=True)
    checa(aba.documento.modificado,
          "definir_texto(marcar_modificado=True) marca de verdade "
          "-- e' o que faz o conteudo recuperado nao se perder")

# ---------------------------------------------------------------------------
secao("4 - fechar")

g = novo_gerenciador()
for _ in range(4):
    g.adicionar(Documento.novo(CFG))
checa_igual(g.count(), 4, "quatro abas")

checa(g.fechar(1), "fechar devolve True")
checa_igual(g.count(), 3, "e remove a aba")
checa(not g.fechar(99), "fechar indice invalido devolve False, sem estourar")

g.setCurrentIndex(1)
checa(g.fechar_a_direita(1), "fechar_a_direita")
checa_igual(g.count(), 2, "sobram as abas ate' o indice")

g = novo_gerenciador()
for _ in range(4):
    g.adicionar(Documento.novo(CFG))
alvo = g.widget(2)
checa(g.fechar_outras(2), "fechar_outras")
checa_igual(g.count(), 1, "sobra uma aba")
checa(g.widget(0) is alvo, "e e' a que foi escolhida")

checa(g.fechar_todas(), "fechar_todas")
checa_igual(g.count(), 0, "nao sobra nenhuma")

# `pode_fechar` e' o gancho da janela para perguntar sobre pendencias.
g = novo_gerenciador()
g.adicionar(Documento.novo(CFG))
g.pode_fechar = lambda aba: False
checa(not g.fechar(0), "pode_fechar=False impede o fechamento")
checa_igual(g.count(), 1, "e a aba continua aberta")
g.pode_fechar = lambda aba: True
checa(g.fechar(0), "e com True fecha")

# ---------------------------------------------------------------------------
secao("5 - fechar libera o QTextDocument (nao vaza)")

# ESTE TESTE JA' NASCEU FRACO E MASCAROU UM VAZAMENTO DE VERDADE. A condicao era
# `referencia() is None or True` -- ou seja, sempre verdadeira. Enquanto isso, o
# QTextDocument NUNCA era liberado: as lambdas de `GerenciadorAbas.adicionar`
# capturam a aba no `__defaults__`, e a conexao vive num objeto que a propria aba
# possui, formando um ciclo que atravessa o C++ e que o coletor do Python nao
# enxerga. MEDIDO: 20 abas de um arquivo de 1,1 MB faziam a memoria privada subir
# 523 MB; com as conexoes desfeitas em `Aba.encerrar()`, 41 MB.
from PySide6.QtCore import QCoreApplication, QEvent              # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402


def drenar_eventos() -> None:
    """`processEvents()` NAO entrega DeferredDelete.

    E' o detalhe que faz a diferenca entre "o objeto vazou" e "a destruicao ainda
    nao foi processada" -- sem `sendPostedEvents(DeferredDelete)` o teste acusaria
    vazamento em codigo correto.
    """
    for _ in range(4):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()


g = novo_gerenciador()
doc = Documento.novo(CFG)
doc.definir_texto("x" * 100_000)
g.adicionar(doc)
referencia = weakref.ref(doc.qt)
del doc
g.fechar(0)
drenar_eventos()
checa(referencia() is None,
      "*** o QTextDocument da aba fechada e' LIBERADO (sem esta desconexao, um "
      "arquivo de 10 MB ficava na memoria para sempre) ***")
checa_igual(g.count(), 0, "e a aba saiu de fato")

# O documento inteiro tambem, e nao so' o QTextDocument.
g2 = novo_gerenciador()
d2 = Documento.novo(CFG)
d2.definir_texto("y" * 50_000)
aba2 = g2.adicionar(d2)
refs = (weakref.ref(d2), weakref.ref(aba2))
del d2, aba2
g2.fechar(0)
drenar_eventos()
checa_igual([r() is None for r in refs], [True, True],
            "o Documento e a Aba tambem sao liberados")

# E as conexoes ficaram registradas para poderem ser desfeitas -- se alguem
# acrescentar um `connect` novo em `adicionar` sem por na lista, o vazamento volta.
g3 = novo_gerenciador()
d3 = Documento.novo(CFG)
aba3 = g3.adicionar(d3)
checa(len(aba3.conexoes) >= 7,
      f"as conexoes do gerenciador ficam guardadas na aba "
      f"({len(aba3.conexoes)}), para serem desfeitas ao fechar")
g3.fechar(0)
checa_igual(aba3.conexoes, [], "e a lista e' esvaziada ao encerrar")

# ---------------------------------------------------------------------------
secao("6 - duplicar aba")

g = novo_gerenciador()
original = g.adicionar(Documento.novo(CFG))
original.documento.definir_texto("linha 1\nlinha 2\nlinha 3")
original.documento.codec = "cp1252"
original.documento.fim_de_linha = "\n"

copia = g.duplicar(0)
checa(copia is not None, "duplicar devolve a aba nova")
checa_igual(g.count(), 2, "e cria uma segunda aba")
checa_igual(copia.documento.texto(), original.documento.texto(),
            "o conteudo e' o mesmo")
checa_igual(copia.documento.codec, "cp1252", "a codificacao e' herdada")
checa_igual(copia.documento.fim_de_linha, "\n", "o fim de linha e' herdado")
checa("copia" in g.tabText(1), f"o titulo indica a copia: {g.tabText(1)!r}")

# Documentos INDEPENDENTES: duplicar serve para experimentar sem perder o
# original. Compartilhar o QTextDocument seria o Split View, outro recurso.
checa(copia.documento.qt is not original.documento.qt,
      "os QTextDocument sao independentes")
copia.editor.setPlainText("mexido so' na copia")
checa("linha 1" in original.documento.texto(),
      "editar a copia NAO altera o original")

checa(g.duplicar(99) is None, "duplicar indice invalido devolve None")

# ---------------------------------------------------------------------------
secao("7 - menu de contexto da aba (requisito 2)")

from PySide6.QtCore import QPoint                              # noqa: E402

with pasta_temporaria() as pasta:
    alvo = pasta / "ctx.txt"
    alvo.write_bytes(b"x")
    g = novo_gerenciador()
    g.adicionar(Documento.abrir(alvo, CFG))
    g.adicionar(Documento.novo(CFG))
    # `construir_menu_da_aba` monta SEM exibir. Chamar o `_menu_da_aba` completo
    # abriria um QMenu modal, que em modo offscreen fica aberto para sempre --
    # foi exatamente o que travou a primeira versao desta suite.
    menu = g.construir_menu_da_aba(0)
    checa(menu is not None, "construir_menu_da_aba devolve um menu")
    rotulos = [a.text() for a in menu.actions() if a.text()]
    for esperado in ("Fechar", "Fechar outras", "Duplicar aba",
                     "Abrir local do arquivo", "Copiar caminho completo",
                     "Copiar nome do arquivo"):
        checa(any(esperado in r for r in rotulos),
              f"o menu tem '{esperado}' (requisito 2)")

    por_rotulo = {a.text(): a for a in menu.actions()}
    adireita = next((a for r, a in por_rotulo.items() if "direita" in r), None)
    checa(adireita is not None and adireita.isEnabled(),
          "'Fechar abas a' direita' habilitado quando ha' abas a' direita")

    # Numa aba SEM arquivo, os itens que dependem do caminho ficam desabilitados.
    menu = g.construir_menu_da_aba(1)
    por_rotulo = {a.text(): a for a in menu.actions()}
    copiar = next((a for r, a in por_rotulo.items()
                   if "Copiar caminho" in r), None)
    checa(copiar is not None and not copiar.isEnabled(),
          "'Copiar caminho' fica desabilitado em aba sem arquivo")
    adireita = next((a for r, a in por_rotulo.items() if "direita" in r), None)
    checa(adireita is not None and not adireita.isEnabled(),
          "e 'Fechar a' direita' desabilitado na ultima aba")

    checa(g.construir_menu_da_aba(99) is None,
          "indice invalido devolve None em vez de estourar")
    checa(g.construir_menu_da_aba(-1) is None, "indice negativo tambem")

# ---------------------------------------------------------------------------
secao("8 - a pilha de views existe desde ja'")

g = novo_gerenciador()
aba = g.adicionar(Documento.novo(CFG))
checa_igual(aba.view_atual(), "texto", "a view inicial e' o editor de texto")
checa(not aba.trocar_para("tabela"),
      "trocar para uma view nao registrada devolve False, sem estourar")

from PySide6.QtWidgets import QLabel                            # noqa: E402

falsa = QLabel("tabela de mentira")
aba.registrar_view("tabela", falsa)
checa(aba.trocar_para("tabela"), "depois de registrar, a troca funciona")
checa_igual(aba.view_atual(), "tabela", "e view_atual reflete a troca")
checa(aba.trocar_para("texto"), "e volta para o texto")
checa_igual(aba.view_atual(), "texto", "confirmado")

sys.exit(resumir())
