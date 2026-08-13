"""Motor de realce: regras combinadas, pilha internada, contextos multi-linha.

    .venv\\Scripts\\python.exe tests\\teste_realce.py

As verificacoes que carregam o peso:

  * uma string tripla aberta na linha 1 e fechada na linha 5 pinta as CINCO linhas,
    e um "#" dentro dela nao vira comentario. E' o teste do contexto multi-linha.
  * editar a linha 3 NAO muda o estado da linha 10. E' o que prova que o
    internamento da pilha faz o QSyntaxHighlighter parar de propagar -- com um
    contador incremental, o realce reprocessaria o documento inteiro a cada tecla.
  * uma regra que casa VAZIO nao trava o laco. `x*` casa string vazia em qualquer
    posicao, e sem a guarda o programa congela.
  * nenhum padrao tem quantificador aninhado. `(a+)+` sobre 5 MB numa linha nao
    termina, e o realce roda na thread da interface.
"""

from __future__ import annotations

import re
import sys

from ajudantes import checa, checa_igual, preparar_qt, pular, resumir, secao

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QTextCursor, QTextDocument         # noqa: E402

from textforge import configuracao                            # noqa: E402
from textforge.interface import tema as tmod                   # noqa: E402
from textforge.realce.dados_do_bloco import DadosDoBloco       # noqa: E402
from textforge.realce.pilha import Internador                  # noqa: E402
from textforge.realce.pintor import Pintor                     # noqa: E402
from textforge.realce.regras import (Contexto, Regra, RegrasDeRealce,
                                     alternativa_de_palavras,
                                     texto_com_escape)         # noqa: E402

TEMA = tmod.embutido("escuro")
CFG = configuracao.padrao()

# ---------------------------------------------------------------------------
secao("1 - Contexto combina as regras num regex so'")

regras = tuple(
    Regra(re.compile(rf"\bp{i}\b"), f"papel{i}") for i in range(12)
)
ctx = Contexto("raiz", regras)
checa(ctx.combinado is not None, "12 regras viram UM regex combinado")

for i in range(12):
    casamento = ctx.combinado.search(f"antes p{i} depois")
    checa(casamento is not None, f"o regex combinado acha p{i}")
    regra = ctx.regra_de(casamento)
    checa(regra is not None and regra.papel == f"papel{i}",
          f"e regra_de() identifica a regra certa para p{i}")

vazio = Contexto("vazio", ())
checa(vazio.combinado is None, "contexto sem regras nao compila regex")

# Grupos internos continuam funcionando -- e' como "def nome" pinta o nome.
com_grupo = Contexto("g", (
    Regra(re.compile(r"\bdef\s+(?P<nome>\w+)"), "palavra_chave",
          papeis_por_grupo={"nome": "definicao"}),
    Regra(re.compile(r"\bclass\s+(?P<klass>\w+)"), "palavra_chave",
          papeis_por_grupo={"klass": "definicao"}),
))
casamento = com_grupo.combinado.search("def calcular(x):")
checa(casamento is not None and casamento.group("nome") == "calcular",
      "grupo nomeado interno sobrevive a' combinacao")

# Dois grupos com o MESMO nome no mesmo contexto: erro claro na construcao, e nao
# comportamento errado em tempo de execucao.
try:
    Contexto("ruim", (
        Regra(re.compile(r"a(?P<x>\w)"), "papel1"),
        Regra(re.compile(r"b(?P<x>\w)"), "papel2"),
    ))
    checa(False, "grupo nomeado repetido deveria levantar ValueError")
except ValueError as exc:
    checa("unico no contexto" in str(exc),
          "grupo nomeado repetido levanta erro explicando o que corrigir")

# Bandeiras diferentes no mesmo contexto: as regras entram no MESMO regex, e um
# regex tem um conjunto de bandeiras so'.
try:
    Contexto("bandeiras", (
        Regra(re.compile(r"abc"), "p1"),
        Regra(re.compile(r"def", re.IGNORECASE), "p2"),
    ))
    checa(False, "bandeiras diferentes deveriam levantar ValueError")
except ValueError as exc:
    checa("(?i:" in str(exc),
          "e o erro sugere a flag com ESCOPO como solucao")

# ---------------------------------------------------------------------------
secao("2 - validacao de RegrasDeRealce")

try:
    RegrasDeRealce(inicial="nao_existe", contextos={"raiz": Contexto("raiz", ())})
    checa(False, "contexto inicial inexistente deveria levantar")
except ValueError:
    checa(True, "contexto inicial inexistente levanta ValueError")

try:
    RegrasDeRealce(inicial="raiz", contextos={"raiz": Contexto("raiz", (
        Regra(re.compile("a"), "p", entrar_em="fantasma"),))})
    checa(False, "entrar_em para contexto inexistente deveria levantar")
except ValueError as exc:
    checa("fantasma" in str(exc),
          "entrar_em invalido levanta ValueError nomeando o contexto")

try:
    Regra(re.compile("a"), "p", entrar_em="x", sair=True)
    checa(False, "entrar e sair juntos deveriam levantar")
except ValueError:
    checa(True, "uma regra nao pode entrar e sair ao mesmo tempo")

try:
    Regra(re.compile("a"), "")
    checa(False, "regra sem papel deveria levantar")
except ValueError:
    checa(True, "regra sem papel levanta ValueError")

# ---------------------------------------------------------------------------
secao("3 - Internador de pilha")

i = Internador()
checa_igual(i.pilha_de(0), (), "o id 0 e' a pilha vazia")
checa_igual(i.pilha_de(-1), (),
            "id -1 (o que o Qt passa no bloco 0) devolve pilha vazia")
checa_igual(i.pilha_de(9999), (), "id desconhecido devolve pilha vazia")

a = i.id_de(("raiz",))
b = i.id_de(("raiz", "texto"))
checa(a != b, "pilhas diferentes recebem ids diferentes")
checa_igual(i.pilha_de(a), ("raiz",), "e a ida e volta preserva a pilha")
checa_igual(i.pilha_de(b), ("raiz", "texto"), "inclusive a de dois niveis")

# O ponto central: MESMA pilha, MESMO id. E' isso que faz o QSyntaxHighlighter
# parar de propagar o reprocessamento.
checa_igual(i.id_de(("raiz",)), a, "a MESMA pilha recebe o MESMO id")
checa_igual(i.id_de(("raiz", "texto")), b, "confirmado para a de dois niveis")

profunda = ("html", "script", "template", "expressao")
ident = i.id_de(profunda)
checa_igual(i.pilha_de(ident), profunda,
            "pilha de 4 niveis (HTML > script > template > ${}) cabe")

# ---------------------------------------------------------------------------
secao("4 - contexto multi-linha: string tripla do Python")

from textforge.linguagens.python_ import ProvedorPython        # noqa: E402

PY = '''"""Docstring
com # nao-comentario
e "aspas" dentro
de varias linhas
"""
codigo = 1
# comentario de verdade
'''

doc = QTextDocument()
doc.setPlainText(PY)
pintor = Pintor(doc, ProvedorPython(), TEMA, CFG)


def papeis_de(documento: QTextDocument, numero: int) -> set[str]:
    """Papeis pintados numa linha, lidos do DadosDoBloco."""
    bloco = documento.findBlockByNumber(numero)
    dados = bloco.userData()
    if not isinstance(dados, DadosDoBloco):
        return set()
    return {t.papel for t in dados.tokens}


def papeis_da_linha(numero: int) -> set[str]:
    return papeis_de(doc, numero)


for linha in range(5):
    papeis = papeis_da_linha(linha)
    checa("texto_literal" in papeis,
          f"linha {linha} da docstring esta' pintada como texto literal")

checa("comentario" not in papeis_da_linha(1),
      "o '#' DENTRO da docstring NAO e' comentario")
checa("comentario" in papeis_da_linha(6),
      "mas o '#' fora dela e' comentario de verdade")
checa("palavra_chave" not in papeis_da_linha(1),
      "e nenhuma palavra dentro da docstring e' palavra-chave")

# A pilha volta ao normal depois do fechamento.
dados5 = doc.findBlockByNumber(5).userData()
checa_igual(dados5.pilha_ao_terminar, ("raiz",),
            "depois de fechar a docstring, a pilha volta a ('raiz',)")
dados2 = doc.findBlockByNumber(2).userData()
checa_igual(dados2.pilha_ao_terminar, ("raiz", "tres_aspas"),
            "e dentro dela a pilha tem dois niveis")

# ---------------------------------------------------------------------------
secao("5 - editar uma linha NAO muda o estado das linhas distantes")

MUITAS = "\n".join([f"x = {i}" for i in range(30)])
doc2 = QTextDocument()
doc2.setPlainText(MUITAS)
pintor2 = Pintor(doc2, ProvedorPython(), TEMA, CFG)

antes = [doc2.findBlockByNumber(n).userState() for n in range(30)]
cursor = QTextCursor(doc2.findBlockByNumber(3))
cursor.insertText("# ")
depois = [doc2.findBlockByNumber(n).userState() for n in range(30)]
checa_igual(antes[10:], depois[10:],
            "editar a linha 3 nao alterou o estado das linhas 10 a 29")
checa(len(pintor2.internador) <= 3,
      f"e o internador tem poucos ids ({len(pintor2.internador)}), "
      f"nao um por bloco")

# ---------------------------------------------------------------------------
secao("6 - regra que casa VAZIO nao trava")

# `x*` casa string vazia em qualquer posicao. Sem a guarda de avanco minimo, o
# laco do pintor nunca terminaria -- e o programa congelaria, nao daria erro.
perigosa = RegrasDeRealce(inicial="raiz", contextos={
    "raiz": Contexto("raiz", (Regra(re.compile(r"x*"), "numero"),))})


class ProvedorPerigoso(ProvedorPython):
    nome = "Perigoso"

    def regras(self, tema):
        return perigosa


doc3 = QTextDocument()
doc3.setPlainText("abc def ghi\nsegunda linha")
Pintor(doc3, ProvedorPerigoso(), TEMA, CFG)
checa(True, "regra que casa vazio termina (nao trava o pintor)")

# ---------------------------------------------------------------------------
secao("7 - limites de disponibilidade")

longa = "x" * 50_000
doc4 = QTextDocument()
doc4.setPlainText(longa)
cfg_curto = dict(CFG, limite_realce_por_linha=1000)
p4 = Pintor(doc4, ProvedorPython(), TEMA, cfg_curto)
dados = doc4.findBlockByNumber(0).userData()
checa(isinstance(dados, DadosDoBloco) and not dados.tokens,
      "linha acima do limite fica SEM realce (mas o resto do arquivo funciona)")

cfg_min = dict(CFG, limite_realce_mb=0)
doc5 = QTextDocument()
doc5.setPlainText("def f(): pass")
p5 = Pintor(doc5, ProvedorPython(), TEMA, cfg_min)
checa(p5.realce_desligado_por_tamanho(),
      "arquivo acima do limite desliga o realce inteiro")
checa(not papeis_de(doc5, 0), "e nenhum token e' gravado")

# ---------------------------------------------------------------------------
secao("8 - DadosDoBloco alimenta dobra, pares e autocomplete")

CODIGO = "def f(x):\n    if (x):\n        return [1, 2]\n"
doc6 = QTextDocument()
doc6.setPlainText(CODIGO)
p6 = Pintor(doc6, ProvedorPython(), TEMA, CFG)

d0 = doc6.findBlockByNumber(0).userData()
d1 = doc6.findBlockByNumber(1).userData()
d2 = doc6.findBlockByNumber(2).userData()

checa_igual(d0.nivel_de_dobra, 0, "linha 0 tem nivel de dobra 0")
checa_igual(d1.nivel_de_dobra, 1, "linha 1 (4 espacos) tem nivel 1")
checa_igual(d2.nivel_de_dobra, 2, "linha 2 (8 espacos) tem nivel 2")
checa(d0.abre_dobra, "'def f(x):' ABRE uma regiao dobravel")
checa(d1.abre_dobra, "'if (x):' tambem abre")
checa(not d2.abre_dobra, "'return [1, 2]' nao abre")

parenteses = [p.caractere for p in d0.pares]
checa("(" in parenteses and ")" in parenteses,
      "os parenteses de 'def f(x)' estao registrados para o pareamento")
checa(any(p.abre for p in d0.pares) and any(not p.abre for p in d0.pares),
      "e a abertura e o fechamento sao distinguidos")

# Delimitador DENTRO de string nao conta como par: casar um "(" de texto com um
# ")" de codigo seria pior que nao casar.
doc7 = QTextDocument()
doc7.setPlainText('x = "aqui ( dentro"')
p7 = Pintor(doc7, ProvedorPython(), TEMA, CFG)
d7 = doc7.findBlockByNumber(0).userData()
checa(not any(p.caractere == "(" for p in d7.pares),
      "parentese DENTRO de string nao entra no pareamento")

checa(p7.dentro_de_texto_ou_comentario(0, 10),
      "dentro_de_texto_ou_comentario acerta dentro da string")
checa(not p7.dentro_de_texto_ou_comentario(0, 0),
      "e acerta fora dela (o autocomplete usa isso)")
checa_igual(p7.papel_em(0, 10), "texto_literal",
            "papel_em devolve 'texto_literal' dentro da string")
checa_igual(p7.papel_em(0, 500), "",
            "e string vazia para coluna fora da linha, sem estourar")

vazia = QTextDocument()
vazia.setPlainText("")
Pintor(vazia, ProvedorPython(), TEMA, CFG)
checa(True, "pintar um documento VAZIO nao estoura")

# ---------------------------------------------------------------------------
secao("9 - ajudantes de declaracao")

fonte = alternativa_de_palavras(["in", "int", "if"])
padrao = re.compile(fonte)
checa(padrao.fullmatch("int") is not None,
      "alternativa_de_palavras casa 'int' inteiro "
      "(a mais longa vem primeiro, senao 'in' venceria)")
checa(padrao.fullmatch("in") is not None, "e casa 'in' tambem")
checa(padrao.search("integral") is None,
      "mas nao casa dentro de outra palavra (limite \\b)")

t = re.compile(texto_com_escape('"'))
checa(t.fullmatch('"simples"') is not None, "string simples casa")
checa(t.fullmatch('"com \\" escapada"') is not None,
      "aspas escapadas NAO fecham a string")
checa(t.match('"nao fechada') is None, "string sem fechamento nao casa")

# ---------------------------------------------------------------------------
secao("10 - nenhum provedor tem quantificador aninhado")

from textforge import linguagens                               # noqa: E402

linguagens.carregar_embutidos()
problemas: list[str] = []
for provedor in linguagens.REGISTRO.todos():
    achados = provedor.regras(TEMA).problemas_de_desempenho()
    problemas.extend(f"{provedor.nome}: {a}" for a in achados)
checa_igual(problemas, [],
            "nenhum padrao de nenhum provedor tem quantificador aninhado "
            "(seria backtracking catastrofico na thread da interface)")

sys.exit(resumir())
