"""Painel Estrutura (requisito 11): arvore, filtro, navegacao, desempenho.

    .venv\\Scripts\\python.exe tests\\teste_painel_estrutura.py

Duas verificacoes de DESEMPENHO carregam peso aqui, porque sem elas o painel
tornaria a digitacao lenta em arquivo grande:

  * o painel OCULTO nao recalcula nada -- quem nunca abre o painel nao paga por ele;
  * a reconstrucao e' com ATRASO, e nao a cada caractere. `ast.parse` num arquivo de
    5 mil linhas leva dezenas de milissegundos, e fazer isso por tecla travaria a
    digitacao.

E uma de robustez: o filtro tem de MANTER os pais dos itens que casam. Sem isso,
filtrar num XML esconderia a tag procurada junto com a arvore inteira.
"""

from __future__ import annotations

import sys

from ajudantes import (checa, checa_igual, preparar_qt, pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtCore import Qt                                  # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

from textforge import configuracao, linguagens                  # noqa: E402
from textforge.documento import Documento                       # noqa: E402
from textforge.interface import tema as tmod                     # noqa: E402
from textforge.interface.painel_estrutura import PainelEstrutura  # noqa: E402

linguagens.carregar_embutidos()
CFG = configuracao.padrao()
TEMA = tmod.embutido("escuro")
REG = linguagens.REGISTRO

CODIGO = '''class Guia:
    def um(self):
        pass

    def dois(self):
        pass


class Outra:
    def tres(self):
        pass


def solta():
    pass
'''


def documento(texto: str, linguagem: str) -> Documento:
    doc = Documento.novo(CFG)
    doc.definir_texto(texto)
    doc.provedor = REG.por_nome(linguagem)
    return doc


def rotulos(painel: PainelEstrutura) -> list[str]:
    """Rotulos de topo, sem a marca de tipo."""
    raiz = painel.arvore.invisibleRootItem()
    return [raiz.child(i).text(0).split("  ", 1)[-1]
            for i in range(raiz.childCount())]


def visiveis(painel: PainelEstrutura) -> list[str]:
    """Rotulos de topo que NAO estao ocultos pelo filtro."""
    raiz = painel.arvore.invisibleRootItem()
    return [raiz.child(i).text(0).split("  ", 1)[-1]
            for i in range(raiz.childCount()) if not raiz.child(i).isHidden()]


# ---------------------------------------------------------------------------
secao("1 - a arvore reflete a estrutura")

painel = PainelEstrutura()
painel.resize(300, 500)
painel.show()                     # visivel: reconstroi de verdade
doc = documento(CODIGO, "Python")
painel.acompanhar(doc)

checa_igual(rotulos(painel), ["Guia", "Outra", "solta"],
            "as tres definicoes de topo aparecem")
raiz = painel.arvore.invisibleRootItem()
guia = raiz.child(0)
checa_igual(guia.childCount(), 2, "a classe Guia tem dois metodos como filhos")
checa_igual(guia.child(0).text(0).split("  ", 1)[-1], "um",
            "e o primeiro e' 'um'")
checa("C" in guia.text(0), f"a classe leva a marca de tipo: {guia.text(0)!r}")
checa("m" in guia.child(0).text(0),
      f"e o metodo leva a dele: {guia.child(0).text(0)!r}")

# A linha e a coluna viajam no item: e' o que o clique usa para navegar.
# A coluna e' a do NO (o `class`), nao a do nome: e' o que o `ast` reporta em
# `col_offset`, e navegar para o inicio da declaracao e' o comportamento util.
dados = guia.data(0, Qt.ItemDataRole.UserRole)
checa_igual(dados, (0, 0),
            "o item guarda (linha, coluna) da definicao, em BASE ZERO")

# ---------------------------------------------------------------------------
secao("2 - navegacao ao clicar")

destinos: list[tuple[int, int]] = []
painel.linha_escolhida.connect(lambda l, c: destinos.append((l, c)))
painel._ao_escolher(raiz.child(2))          # "solta"
checa_igual(len(destinos), 1, "clicar num item emite o sinal")
# `def solta():` e' a 14a linha do CODIGO, ou seja indice 13 em base zero.
checa_igual(destinos[0][0], 13, "e a linha e' a da definicao de 'solta'")
checa_igual(CODIGO.split("\n")[13].strip(), "def solta():",
            "conferindo a contagem de linhas do proprio teste")

# Um item de MENSAGEM (sem dados) nao pode emitir nada.
vazio = PainelEstrutura()
vazio.show()
vazio.acompanhar(documento("", "Python"))
emitidos: list[tuple[int, int]] = []
vazio.linha_escolhida.connect(lambda l, c: emitidos.append((l, c)))
raiz_vazia = vazio.arvore.invisibleRootItem()
if raiz_vazia.childCount():
    vazio._ao_escolher(raiz_vazia.child(0))
checa_igual(emitidos, [],
            "clicar na mensagem 'sem estrutura' nao navega para lugar nenhum")

# ---------------------------------------------------------------------------
secao("3 - filtro preserva os pais")

painel.filtro.setText("dois")
QApplication.processEvents()
# "Guia" nao casa com "dois", mas o filho dela casa -- entao ela CONTINUA visivel.
checa("Guia" in visiveis(painel),
      "o PAI de um item que casa continua visivel (senao o filtro seria inutil)")
checa("solta" not in visiveis(painel),
      "e um item que nao casa nem tem filho que casa e' escondido")
checa(raiz.child(0).isExpanded(),
      "o pai e' expandido automaticamente, para o achado aparecer")

painel.filtro.setText("")
QApplication.processEvents()
checa_igual(sorted(visiveis(painel)), ["Guia", "Outra", "solta"],
            "limpar o filtro devolve todos os itens")

painel.filtro.setText("NAO EXISTE NADA ASSIM")
QApplication.processEvents()
checa_igual(visiveis(painel), [],
            "filtro sem nenhum resultado esconde tudo, sem estourar")
painel.filtro.setText("")
QApplication.processEvents()

# ---------------------------------------------------------------------------
secao("4 - desempenho: oculto nao recalcula, e a reconstrucao tem atraso")

oculto = PainelEstrutura()
oculto.hide()
contagem = {"n": 0}


class ProvedorContado:
    """Provedor que conta quantas vezes a estrutura e' pedida."""

    nome = "Contado"

    def regras(self, tema):
        return REG.por_nome("Texto").regras(tema)

    def dobras(self):
        return REG.por_nome("Texto").dobras()

    def estrutura(self, texto):
        contagem["n"] += 1
        return []


doc2 = documento("a\nb\nc\n", "Texto")
doc2.provedor = ProvedorContado()
oculto.acompanhar(doc2)
chamadas_iniciais = contagem["n"]

# Digitar com o painel OCULTO nao pode disparar analise.
from PySide6.QtGui import QTextCursor                          # noqa: E402

for _ in range(20):
    QTextCursor(doc2.qt).insertText("x")
QApplication.processEvents()
checa_igual(contagem["n"], chamadas_iniciais,
            "com o painel OCULTO, digitar NAO recalcula a estrutura")

# Visivel: digitar agenda UMA reconstrucao, nao uma por tecla.
oculto.show()
QApplication.processEvents()
antes = contagem["n"]
for _ in range(20):
    QTextCursor(doc2.qt).insertText("y")
QApplication.processEvents()
checa(contagem["n"] - antes <= 1,
      f"20 teclas agendam no maximo UMA reconstrucao "
      f"(foram {contagem['n'] - antes})")
checa(oculto._temporizador.isActive() or contagem["n"] > antes,
      "e a reconstrucao fica agendada no temporizador")

# ---------------------------------------------------------------------------
secao("5 - robustez")

# Provedor com defeito nao pode derrubar a janela.
class ProvedorQuebrado(ProvedorContado):
    nome = "Quebrado"

    def estrutura(self, texto):
        raise RuntimeError("falha proposital")


ruim = PainelEstrutura()
ruim.show()
doc3 = documento("x", "Texto")
doc3.provedor = ProvedorQuebrado()
ruim.acompanhar(doc3)
checa(True, "provedor que estoura na estrutura nao derruba o painel")
checa(ruim.arvore.topLevelItemCount() >= 1,
      "e o painel mostra uma mensagem em vez de ficar vazio sem explicacao")

# Documento sem provedor.
sem = PainelEstrutura()
sem.show()
doc4 = Documento.novo(CFG)
doc4.provedor = None
sem.acompanhar(doc4)
checa(sem.arvore.topLevelItemCount() >= 1,
      "documento sem linguagem mostra mensagem, nao arvore vazia")

# acompanhar(None) nao pode estourar.
sem.acompanhar(None)
checa(True, "acompanhar(None) nao estoura")

# Trocar de documento desliga o anterior: sem isso, os dois emitiriam e o painel
# reconstruiria duas vezes por tecla.
trocador = PainelEstrutura()
trocador.show()
a = documento(CODIGO, "Python")
b = documento("def outro():\n    pass\n", "Python")
trocador.acompanhar(a)
trocador.acompanhar(b)
checa_igual(rotulos(trocador), ["outro"],
            "depois de trocar, o painel mostra a estrutura do documento NOVO")

# ---------------------------------------------------------------------------
secao("6 - arvore profunda nao e' toda expandida")

XML = "<a>" + "".join(f"<n{i}>" for i in range(6)) + "x" \
      + "".join(f"</n{i}>" for i in reversed(range(6))) + "</a>"
profundo = PainelEstrutura()
profundo.show()
profundo.acompanhar(documento(XML, "XML"))
raiz_p = profundo.arvore.invisibleRootItem()
checa_igual(raiz_p.childCount(), 1, "XML profundo tem uma raiz")
topo = raiz_p.child(0)
checa(topo.isExpanded(), "o topo e' expandido")
if topo.childCount():
    nivel2 = topo.child(0)
    checa(nivel2.isExpanded(), "o segundo nivel tambem")
    if nivel2.childCount():
        checa(not nivel2.child(0).isExpanded(),
              "mas o terceiro NAO (num XML de 500 tags, expandir tudo produz "
              "uma lista inutilizavel)")

# ---------------------------------------------------------------------------
secao("7 - tema")

profundo.aplicar_tema(tmod.embutido("claro"))
checa("background" in profundo.arvore.styleSheet(),
      "aplicar_tema pinta a arvore com as cores do tema")
profundo.aplicar_tema(TEMA)
checa(True, "e trocar de volta funciona")

sys.exit(resumir())
