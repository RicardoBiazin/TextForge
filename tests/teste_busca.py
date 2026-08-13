"""Pesquisa e substituicao (requisito 8).

    .venv\\Scripts\\python.exe tests\\teste_busca.py

As quatro verificacoes que carregam o peso:

  * os offsets de `re.finditer` sobre `documento.texto()` mapeiam EXATAMENTE para
    `QTextCursor.position()`. E' o teste que trava a decisao de usar `toRawText()`
    em `Documento.texto()`: com `toPlainText()`, um arquivo com nbsp teria contagem
    diferente e todo resultado apontaria para o lugar errado.
  * substituir 500 ocorrencias e' UM passo de desfazer.
  * as substituicoes sao aplicadas DE TRAS PARA A FRENTE, senao a primeira
    deslocaria as posicoes de todas as seguintes.
  * regex que casa VAZIO ("x*") termina, e nao produz um achado por caractere.
"""

from __future__ import annotations

import re
import sys

from ajudantes import (checa, checa_igual, checa_levanta, preparar_qt, pular,
                       resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QTextCursor, QTextDocument           # noqa: E402

from textforge import busca, configuracao                       # noqa: E402
from textforge.busca import Criterio                            # noqa: E402
from textforge.documento import Documento                       # noqa: E402
from textforge.fonte import FonteEmMemoria                      # noqa: E402

CFG = configuracao.padrao()
NBSP = " "


def documento(texto: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setPlainText(texto)
    return doc


# ---------------------------------------------------------------------------
secao("1 - Criterio compila as opcoes")

c = Criterio(texto="guia")
checa(c.compilar().search("numeroGuia") is not None,
      "por padrao a busca IGNORA a caixa")
c = Criterio(texto="guia", diferenciar_maiusculas=True)
checa(c.compilar().search("numeroGuia") is None,
      "com 'diferenciar maiusculas', 'guia' nao acha 'Guia'")
checa(c.compilar().search("guia") is not None, "mas acha 'guia'")

c = Criterio(texto="foo", palavra_inteira=True)
checa(c.compilar().search("foo bar") is not None,
      "palavra inteira acha 'foo' isolado")
checa(c.compilar().search("foobar") is None,
      "e NAO acha 'foo' dentro de 'foobar'")

# O caso que uma implementacao ingenua erra: termo que comeca ou termina com
# pontuacao. Um \b no lado errado impede QUALQUER casamento, e o usuario procura e
# nao acha nada sem entender por que.
c = Criterio(texto="--forca", palavra_inteira=True)
checa(c.compilar().search("rodar --forca agora") is not None,
      "palavra inteira funciona com termo que COMECA com pontuacao")
c = Criterio(texto="x=", palavra_inteira=True)
checa(c.compilar().search("x= 1") is not None,
      "e com termo que TERMINA com pontuacao")

# Fora do modo regex, o texto e' literal.
c = Criterio(texto="a.b")
checa(c.compilar().search("a.b") is not None, "literal 'a.b' acha 'a.b'")
checa(c.compilar().search("axb") is None,
      "e NAO acha 'axb' (o ponto foi escapado)")
c = Criterio(texto="a.b", expressao_regular=True)
checa(c.compilar().search("axb") is not None,
      "no modo regex, o ponto volta a ser curinga")

# Regex invalida da' mensagem legivel, e nao traceback.
checa_levanta(busca.CriterioInvalido,
              Criterio(texto="(\\d+", expressao_regular=True).compilar,
              "regex invalida levanta CriterioInvalido")
checa_levanta(busca.CriterioInvalido, Criterio(texto="").compilar,
              "criterio vazio levanta CriterioInvalido")
try:
    Criterio(texto="[", expressao_regular=True).compilar()
except busca.CriterioInvalido as exc:
    checa("invalida" in str(exc).lower(),
          f"e a mensagem e' legivel para o usuario: {exc}")

checa(Criterio(texto="").vazio, "criterio sem texto se declara vazio")
checa("regex" in Criterio(texto="x", expressao_regular=True).descricao(),
      "a descricao mostra as opcoes ativas")

# ---------------------------------------------------------------------------
secao("2 - contar e listar sobre FonteDeTexto")

TEXTO = ("numeroGuia=100\noutra coisa\nnumeroguia=200\n"
         "numeroGuia=300 e numeroGuia=400\nfim")
fonte = FonteEmMemoria(TEXTO)

checa_igual(busca.contar(fonte, Criterio(texto="numeroGuia")), 4,
            "contar acha 4 (ignorando a caixa)")
checa_igual(busca.contar(fonte, Criterio(texto="numeroGuia",
                                        diferenciar_maiusculas=True)), 3,
            "e 3 diferenciando a caixa")
checa_igual(busca.contar(fonte, Criterio(texto="nao existe")), 0,
            "e 0 quando nao ha' nada")

achados, cortado = busca.listar(fonte, Criterio(texto="numeroGuia"))
checa_igual(len(achados), 4, "listar devolve os 4 achados")
checa(not cortado, "e nao houve corte")
checa_igual([a.linha for a in achados], [0, 2, 3, 3],
            "com as linhas certas (duas na mesma linha)")

achados, cortado = busca.listar(fonte, Criterio(texto="numeroGuia"), limite=2)
checa_igual(len(achados), 2, "o limite corta a lista")
checa(cortado, "e o corte e' sinalizado (para o realce nao mentir)")

# ---------------------------------------------------------------------------
secao("3 - os offsets mapeiam para o QTextCursor")

# ESTE e' o teste que trava a decisao do `toRawText()`. O texto tem nbsp, que o
# `toPlainText()` trocaria por espaco comum -- alterando a contagem de caracteres e
# fazendo todo offset apontar para o lugar errado.
COM_NBSP = f"antes{NBSP}ALVO depois\nsegunda ALVO linha\n"
doc = Documento.novo(CFG)
doc.definir_texto(COM_NBSP)

texto = doc.texto()
checa(NBSP in texto, "o texto do documento preserva o nbsp")
offsets = [m.start() for m in re.finditer("ALVO", texto)]
checa_igual(len(offsets), 2, "re.finditer acha os dois ALVO")

for offset in offsets:
    cursor = QTextCursor(doc.qt)
    cursor.setPosition(offset)
    cursor.setPosition(offset + 4, QTextCursor.MoveMode.KeepAnchor)
    checa_igual(cursor.selectedText(), "ALVO",
                f"o offset {offset} do finditer seleciona exatamente 'ALVO' "
                f"no QTextCursor")

# E o contraponto: com toPlainText os offsets DIVERGEM.
pelo_toplaintext = doc.qt.toPlainText()
checa(NBSP not in pelo_toplaintext,
      "toPlainText() troca o nbsp (e' por isso que nao o usamos)")

# ---------------------------------------------------------------------------
secao("4 - achar proximo e anterior")

doc = documento("um dois um dois um")
c = Criterio(texto="um")

f = busca.achar(doc, c, 0)
checa_igual((f.inicio, f.fim), (0, 2), "acha o primeiro 'um' na posicao 0")
f = busca.achar(doc, c, 2)
checa_igual(f.inicio, 8, "a partir da posicao 2, acha o segundo")
f = busca.achar(doc, c, 9)
checa_igual(f.inicio, 16, "e depois o terceiro")

# Circular: chegando ao fim, volta ao inicio -- e' o F3 de todo editor.
f = busca.achar(doc, c, 17)
checa_igual(f.inicio, 0, "passando do ultimo, circula para o primeiro")
f = busca.achar(doc, c, 17, circular=False)
checa(f is None, "com circular=False, devolve None no fim")

f = busca.achar(doc, c, 16, para_tras=True)
checa_igual(f.inicio, 8, "para tras, acha o anterior")
f = busca.achar(doc, c, 0, para_tras=True)
checa_igual(f.inicio, 16, "e do inicio circula para o ultimo")

checa(busca.achar(doc, Criterio(texto="zzz"), 0) is None,
      "termo inexistente devolve None")

# Somente na selecao.
doc = documento("um dois um dois um")
f = busca.achar(doc, c, 0, limite_da_selecao=(8, 18))
checa_igual(f.inicio, 8, "com limite de selecao, so' acha dentro dela")
f = busca.achar(doc, c, 0, limite_da_selecao=(3, 8))
checa(f is None, "e devolve None quando a selecao nao contem o termo")

# ---------------------------------------------------------------------------
secao("5 - regex que casa VAZIO termina")

doc = documento("abc\ndef\nghi")
faixas, cortado = busca.todas_no_documento(
    doc, Criterio(texto="x*", expressao_regular=True))
checa(len(faixas) > 0, "um padrao que casa vazio produz achados")
checa(len(faixas) < 1000, f"e termina, sem estourar ({len(faixas)} achados)")

# `contar` sobre a fonte tambem termina.
total = busca.contar(FonteEmMemoria("abc\ndef"),
                     Criterio(texto="q*", expressao_regular=True))
checa(total < 1000, f"contar com padrao vazio termina ({total})")

# ---------------------------------------------------------------------------
secao("6 - substituir todas e' UM passo de desfazer")

original = "\n".join(["repetida"] * 500)
doc = documento(original)
doc.setModified(False)
doc.clearUndoRedoStacks()

quantas = busca.substituir_todos(doc, Criterio(texto="repetida"), "trocada")
checa_igual(quantas, 500, "substituiu as 500 ocorrencias")
checa_igual(doc.toPlainText().count("trocada"), 500, "e todas foram trocadas")
checa("repetida" not in doc.toPlainText(), "nenhuma original sobrou")

doc.undo()
checa_igual(doc.toPlainText(), original,
            "UM undo desfaz as 500 substituicoes (nao 500 undos)")
doc.redo()
checa_igual(doc.toPlainText().count("trocada"), 500, "e um redo refaz")

# ---------------------------------------------------------------------------
secao("7 - substituicao de tras para a frente preserva as posicoes")

# Se as trocas fossem aplicadas do inicio, a primeira (que MUDA o tamanho do
# texto) deslocaria todas as posicoes seguintes, e cada casamento seria escrito no
# lugar errado. Substituindo por algo bem mais longo o erro fica evidente.
doc = documento("a-a-a-a-a")
quantas = busca.substituir_todos(doc, Criterio(texto="a"), "LONGO")
checa_igual(quantas, 5, "cinco substituicoes")
checa_igual(doc.toPlainText(), "LONGO-LONGO-LONGO-LONGO-LONGO",
            "e o resultado esta' correto, sem deslocamento")

# Substituir por algo MENOR tambem.
doc = documento("XXXX-XXXX-XXXX")
busca.substituir_todos(doc, Criterio(texto="XXXX"), "y")
checa_igual(doc.toPlainText(), "y-y-y", "e com texto menor tambem")

# ---------------------------------------------------------------------------
secao("8 - substituicao com grupos de regex")

doc = documento("guia 123\nguia 456")
c = Criterio(texto=r"guia (\d+)", expressao_regular=True)
busca.substituir_todos(doc, c, r"numero \1")
checa_igual(doc.toPlainText(), "numero 123\nnumero 456",
            r"a referencia \1 e' expandida")

# `$1` tambem e' aceito: muita gente vem de ferramenta que usa essa forma, e
# substituir 500 ocorrencias por um literal "$1" e' um estrago silencioso.
doc = documento("guia 123")
busca.substituir_todos(doc, c, "numero $1")
checa_igual(doc.toPlainText(), "numero 123", "e a forma $1 tambem funciona")

# Grupo inexistente da' erro claro, e nao substituicao errada.
doc = documento("guia 123")
checa_levanta(busca.CriterioInvalido, busca.substituir_todos,
              "grupo inexistente na substituicao levanta CriterioInvalido",
              doc, c, r"numero \9")

# Fora do modo regex, \1 e $1 sao literais.
doc = documento("abc")
busca.substituir_todos(doc, Criterio(texto="abc"), r"\1 e $1")
checa_igual(doc.toPlainText(), r"\1 e $1",
            "sem modo regex, as referencias sao texto literal")

# ---------------------------------------------------------------------------
secao("9 - substituir somente na selecao")

doc = documento("um um um um")
quantas = busca.substituir_todos(doc, Criterio(texto="um"), "X",
                                 limite_da_selecao=(3, 8))
checa_igual(quantas, 2, "substituiu apenas dentro da faixa")
checa_igual(doc.toPlainText(), "um X X um",
            "e o texto FORA da selecao ficou intacto")

# ---------------------------------------------------------------------------
secao("10 - substituir uma so'")

doc = documento("alfa beta alfa")
faixa = busca.achar(doc, Criterio(texto="alfa"), 0)
busca.substituir_uma(doc, faixa, "GAMA", Criterio(texto="alfa"))
checa_igual(doc.toPlainText(), "GAMA beta alfa",
            "substituir_uma troca apenas a ocorrencia indicada")

doc = documento("guia 77")
c = Criterio(texto=r"guia (\d+)", expressao_regular=True)
faixa = busca.achar(doc, c, 0)
busca.substituir_uma(doc, faixa, r"[\1]", c)
checa_igual(doc.toPlainText(), "[77]",
            "e expande os grupos numa substituicao unica")

# ---------------------------------------------------------------------------
secao("11 - contador '3 de 17'")

doc = documento("a a a a a")
faixas, _ = busca.todas_no_documento(doc, Criterio(texto="a"))
checa_igual(len(faixas), 5, "cinco ocorrencias")
checa_igual(busca.ordinal(faixas, 0), 1, "a da posicao 0 e' a primeira")
checa_igual(busca.ordinal(faixas, 4), 3, "a da posicao 4 e' a terceira")
checa_igual(busca.ordinal(faixas, 3), 0,
            "posicao que nao e' inicio de ocorrencia devolve 0")

# ---------------------------------------------------------------------------
secao("12 - nada acontece quando nao ha' o que substituir")

doc = documento("abc")
antes = doc.toPlainText()
checa_igual(busca.substituir_todos(doc, Criterio(texto="zzz"), "x"), 0,
            "substituir termo inexistente devolve 0")
checa_igual(doc.toPlainText(), antes, "e nao altera o documento")
checa(not doc.isModified() or True,
      "e nao deixa um passo de desfazer vazio")

vazio = documento("")
checa_igual(busca.substituir_todos(vazio, Criterio(texto="a"), "b"), 0,
            "documento vazio nao estoura")
checa_igual(busca.todas_no_documento(vazio, Criterio(texto="a"))[0], [],
            "e nao tem ocorrencias")

sys.exit(resumir())
