"""Indentacao: deteccao por arquivo, largura visual e conversoes.

    .venv\\Scripts\\python.exe tests\\teste_indentacao.py

Nao precisa de Qt: `indentacao.py` e' logica pura, de proposito.

O que este arquivo protege: a regra de que a indentacao DO ARQUIVO vence a
preferencia global. Abrir um .py alheio indentado com 2 espacos e digitar com 4
suja o diff com alteracoes que ninguem pediu -- exatamente o que o requisito 38
proibe.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, resumir, secao

from textforge.editor import indentacao as ind
from textforge.editor.indentacao import Indentacao

# ---------------------------------------------------------------------------
secao("1 - a unidade e o rotulo")

checa_igual(Indentacao(True, 4).unidade(), "    ", "4 espacos: a unidade sao 4 espacos")
checa_igual(Indentacao(True, 2).unidade(), "  ", "2 espacos: a unidade sao 2 espacos")
checa_igual(Indentacao(False, 4).unidade(), "\t", "TAB: a unidade e' um TAB")
checa_igual(Indentacao(True, 4).rotulo(), "Espacos: 4", "rotulo com espacos")
checa_igual(Indentacao(False, 8).rotulo(), "TAB: 8", "rotulo com TAB")

# ---------------------------------------------------------------------------
secao("2 - largura visual: um TAB nao vale uma coluna")

i4 = Indentacao(True, 4)
checa_igual(i4.largura_visual(""), 0, "prefixo vazio: coluna 0")
checa_igual(i4.largura_visual("    "), 4, "4 espacos: coluna 4")
checa_igual(i4.largura_visual("\t"), 4, "um TAB com largura 4: coluna 4")
checa_igual(i4.largura_visual("\t\t"), 8, "dois TAB: coluna 8")
# O caso que um `len()` erraria: TAB depois de espacos vai ate' a PROXIMA parada
# de tabulacao, nao soma 4.
checa_igual(i4.largura_visual("  \t"), 4,
            "2 espacos + TAB: o TAB completa ate' a coluna 4, nao 6")
checa_igual(i4.largura_visual("   \t"), 4, "3 espacos + TAB: tambem coluna 4")
checa_igual(i4.largura_visual("    \t"), 8,
            "4 espacos + TAB: o TAB vai para a coluna 8")
checa_igual(Indentacao(True, 8).largura_visual("\t"), 8,
            "com largura 8, um TAB vale 8 colunas")

# ---------------------------------------------------------------------------
secao("3 - deteccao de indentacao em codigo real")

PY_2 = """def f():
  if x:
    return 1
  return 0

class C:
  def g(self):
    pass
"""
checa_igual(ind.detectar(PY_2), Indentacao(True, 2),
            "Python indentado com 2 espacos e' detectado como 2")

PY_4 = """def f():
    if x:
        return 1
    return 0
"""
checa_igual(ind.detectar(PY_4), Indentacao(True, 4),
            "Python indentado com 4 espacos e' detectado como 4")

COM_TAB = "def f():\n\tif x:\n\t\treturn 1\n\treturn 0\n"
detectado = ind.detectar(COM_TAB)
checa(not detectado.usa_espacos, "arquivo com TAB e' detectado como TAB")

MISTO_MAIS_TAB = "\ta\n\tb\n\tc\n\td\n  e\n"
checa(not ind.detectar(MISTO_MAIS_TAB).usa_espacos,
      "arquivo misto com maioria TAB e' detectado como TAB")

# O caso que uma contagem de valores ABSOLUTOS erraria: num arquivo indentado com
# 2, ha' muitas linhas com 4 espacos (nivel 2) e o valor mais comum poderia ser 4.
NIVEIS_PROFUNDOS = """a
  b
    c
      d
    e
  f
g
  h
    i
"""
checa_igual(ind.detectar(NIVEIS_PROFUNDOS).largura, 2,
            "niveis profundos com passo 2 nao sao confundidos com 4")

OITO = "a\n        b\n                c\n        d\n"
checa_igual(ind.detectar(OITO).largura, 8, "passo de 8 espacos e' detectado")

# Sem sinal nenhum: fica o padrao do usuario, nao um palpite.
padrao = Indentacao(True, 3)
checa_igual(ind.detectar("uma linha so", padrao), padrao,
            "arquivo sem indentacao mantem a preferencia do usuario")
checa_igual(ind.detectar("", padrao), padrao, "arquivo vazio mantem o padrao")
checa_igual(ind.detectar("a\nb\nc\n", padrao), padrao,
            "arquivo sem nenhuma linha indentada mantem o padrao")

# Linha em branco com espacos nao pode contar como indentacao.
checa_igual(ind.detectar("a\n   \nb\n", padrao), padrao,
            "linha em branco com espacos nao e' tomada por indentacao")

# ---------------------------------------------------------------------------
secao("4 - prefixo de indentacao")

checa_igual(ind.prefixo_de_indentacao("    codigo"), "    ",
            "extrai os espacos do inicio")
checa_igual(ind.prefixo_de_indentacao("\t\tcodigo"), "\t\t",
            "extrai os TAB do inicio")
checa_igual(ind.prefixo_de_indentacao("  \t codigo"), "  \t ",
            "extrai a mistura literalmente")
checa_igual(ind.prefixo_de_indentacao("codigo"), "", "sem indentacao: vazio")
checa_igual(ind.prefixo_de_indentacao("   "), "   ",
            "linha so' com espacos: o prefixo e' a linha inteira")

# ---------------------------------------------------------------------------
secao("5 - TAB para espacos e volta")

# O caso que um replace ingenuo erraria: TAB no MEIO da linha.
checa_igual(ind.tab_para_espacos("a\tb", 4), "a   b",
            "TAB no meio expande ate' a parada de tabulacao (3 espacos), "
            "nao 4")
checa_igual(ind.tab_para_espacos("\tx", 4), "    x",
            "TAB no inicio expande para 4")
checa_igual(ind.tab_para_espacos("ab\tc", 4), "ab  c",
            "depois de 2 caracteres, o TAB vale 2 espacos")
checa_igual(ind.tab_para_espacos("linha1\n\tlinha2", 4), "linha1\n    linha2",
            "cada linha e' expandida em separado")

checa_igual(ind.espacos_para_tab("    codigo", 4), "\tcodigo",
            "4 espacos de indentacao viram um TAB")
checa_igual(ind.espacos_para_tab("        codigo", 4), "\t\tcodigo",
            "8 espacos viram dois TAB")
checa_igual(ind.espacos_para_tab("      codigo", 4), "\t  codigo",
            "6 espacos viram um TAB e 2 espacos")
# O cuidado central: espaco DENTRO do texto e' conteudo, nao indentacao.
checa_igual(ind.espacos_para_tab("a    b", 4), "a    b",
            "espaco no MEIO da linha NAO e' convertido (seria alterar dados)")
checa_igual(ind.espacos_para_tab("codigo", 4), "codigo",
            "linha sem indentacao fica intacta")

ida = ind.espacos_para_tab(ind.tab_para_espacos("\t\tx", 4), 4)
checa_igual(ida, "\t\tx", "ida e volta preserva a indentacao original")

# ---------------------------------------------------------------------------
secao("6 - indentar e desindentar blocos")

linhas = ["a", "  b", "c"]
checa_igual(ind.indentar(linhas, Indentacao(True, 4)),
            ["    a", "      b", "    c"], "indentar soma um nivel a cada linha")
checa_igual(ind.indentar(linhas, Indentacao(False, 4)),
            ["\ta", "\t  b", "\tc"], "com TAB, indentar insere TAB")

# Indentar linha em branco criaria espaco no fim da linha: ruido no diff.
checa_igual(ind.indentar(["a", "", "b"], Indentacao(True, 2)),
            ["  a", "", "  b"], "linha em branco NAO e' indentada")
checa_igual(ind.indentar(["a", "   ", "b"], Indentacao(True, 2)),
            ["  a", "   ", "  b"], "linha so' com espacos tambem nao e'")

checa_igual(ind.desindentar(["    a", "        b"], Indentacao(True, 4)),
            ["a", "    b"], "desindentar remove um nivel")
checa_igual(ind.desindentar(["\ta", "\t\tb"], Indentacao(True, 4)),
            ["a", "\tb"], "desindentar remove um TAB inteiro")
checa_igual(ind.desindentar(["  a"], Indentacao(True, 4)), ["a"],
            "com menos espacos que a largura, remove o que existe")
checa_igual(ind.desindentar(["a"], Indentacao(True, 4)), ["a"],
            "linha sem indentacao nao muda e nao estoura")
checa_igual(ind.desindentar([""], Indentacao(True, 4)), [""],
            "linha vazia nao estoura")

# ---------------------------------------------------------------------------
secao("7 - auto-indent")

import re                                                    # noqa: E402

i = Indentacao(True, 4)
checa_igual(ind.proxima_indentacao("    codigo", i), "    ",
            "sem regra, repete a indentacao da linha anterior")
checa_igual(ind.proxima_indentacao("codigo", i), "",
            "linha sem indentacao: a proxima tambem sem")
checa_igual(ind.proxima_indentacao("\t\tcodigo", i), "\t\t",
            "repete os TAB da linha anterior")

aumenta = re.compile(r":\s*$")
checa_igual(ind.proxima_indentacao("    if x:", i, aumenta), "        ",
            "com a regra do Python, ':' no fim soma um nivel")
checa_igual(ind.proxima_indentacao("    codigo", i, aumenta), "    ",
            "sem ':' no fim, nao soma nivel")

chaves = re.compile(r"\{\s*$")
checa_igual(ind.proxima_indentacao("  if (x) {", i, chaves), "      ",
            "com a regra de chaves, '{' no fim soma um nivel")

sys.exit(resumir())
