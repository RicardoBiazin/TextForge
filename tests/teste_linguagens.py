"""Registro de linguagens, resolucao e provedores concretos.

    .venv\\Scripts\\python.exe tests\\teste_linguagens.py

A secao 1 e' a que mais vale: ela varre TODOS os provedores registrados e verifica
propriedades gerais. Nao precisa ser atualizada quando uma linguagem nova entra --
e' isso que a torna uma rede de seguranca de verdade, e nao mais um teste para
manter. Ela pega, entre outras coisas, papel citado que o tema nao declara, que
apareceria como texto sem cor e ninguem notaria.
"""

from __future__ import annotations

import re
import sys

from ajudantes import (appdata_temporario, checa, checa_igual, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import linguagens                               # noqa: E402
from textforge.interface import tema as tmod                    # noqa: E402
from textforge.linguagens.base import ProvedorDeLinguagem       # noqa: E402
from textforge.linguagens.generico import ProvedorGenerico      # noqa: E402
from textforge.linguagens.registro import REGISTRO              # noqa: E402

TEMA = tmod.embutido("escuro")
CLARO = tmod.embutido("claro")

quantos = linguagens.carregar_embutidos()

# ---------------------------------------------------------------------------
secao("1 - varredura de TODOS os provedores registrados")

checa(quantos >= 6, f"{quantos} provedores embutidos registrados")

for provedor in REGISTRO.todos():
    nome = provedor.nome
    checa(bool(nome), "todo provedor tem nome")
    checa(bool(provedor.extensoes) or bool(provedor.nomes_de_arquivo),
          f"{nome}: declara extensoes ou nomes de arquivo")
    ruins = [e for e in provedor.extensoes
             if not e.startswith(".") or e != e.lower()]
    checa_igual(ruins, [],
                f"{nome}: extensoes comecam com ponto e sao minusculas")

    # As regras tem de COMPILAR. Um regex invalido estouraria no meio do
    # highlightBlock, ou seja, no meio do desenho da tela.
    try:
        regras = provedor.regras(TEMA)
        compilou = True
    except Exception as exc:            # noqa: BLE001
        compilou = False
        checa(False, f"{nome}: as regras nao compilaram ({exc})")
    if not compilou:
        continue
    checa(True, f"{nome}: as regras compilam")

    # TODO papel citado tem de existir nos DOIS temas. Um papel ausente vira
    # texto sem cor, e ninguem percebe ate' ver comentario preto no fundo preto.
    ausentes_escuro = sorted(p for p in regras.papeis_usados()
                             if not TEMA.tem_papel(p))
    ausentes_claro = sorted(p for p in regras.papeis_usados()
                            if not CLARO.tem_papel(p))
    checa_igual(ausentes_escuro, [], f"{nome}: todo papel existe no tema escuro")
    checa_igual(ausentes_claro, [], f"{nome}: todo papel existe no tema claro")

    checa_igual(regras.problemas_de_desempenho(), [],
                f"{nome}: nenhum quantificador aninhado")

    # `dobras()` tem de devolver um modo que o pintor conhece.
    checa(provedor.dobras().modo in ("indentacao", "delimitadores", "marcadores"),
          f"{nome}: modo de dobra valido ({provedor.dobras().modo})")

    # Os metodos opcionais nao podem estourar com entrada vazia nem estranha.
    for amostra in ("", "\n\n", "texto qualquer", "<>{}[]\"'", "\x00\x01"):
        try:
            provedor.estrutura(amostra)
            provedor.detectar_por_conteudo(amostra)
            provedor.palavras_de_autocomplete()
        except Exception as exc:        # noqa: BLE001
            checa(False, f"{nome}: estourou com a amostra {amostra!r} ({exc})")
            break
    else:
        checa(True, f"{nome}: metodos opcionais aguentam entrada estranha")

    nota = provedor.detectar_por_conteudo("")
    checa(0 <= nota <= 100, f"{nome}: detectar_por_conteudo devolve 0..100")

conflitos = REGISTRO.extensoes_em_conflito()
checa_igual(conflitos, {},
            f"nenhuma extensao disputada por dois embutidos de mesma "
            f"prioridade -- encontrados: {conflitos}")

# ---------------------------------------------------------------------------
secao("2 - resolucao por extensao, nome e shebang")

CASOS = [
    ("guia.py", "Python"),
    ("script.pyw", "Python"),
    ("tipos.pyi", "Python"),
    ("config.xml", "XML"),
    ("pom.xml", "XML"),
    ("web.config", "XML"),
    ("desenho.svg", "XML"),
    ("projeto.csproj", "XML"),
    ("pacote.json", "JSON"),
    ("package.json", "JSON"),
    (".eslintrc", "JSON"),
    ("sistema.ini", "INI"),
    ("app.cfg", "INI"),
    (".env", "INI"),
    ("setup.cfg", "INI"),
    ("LEIAME.md", "Markdown"),
    ("README.md", "Markdown"),
    ("notas.txt", "Texto"),
    ("sistema.log", "Texto"),
    ("dados.dat", "Texto"),
    ("LICENSE", "Texto"),
]
for arquivo, esperado in CASOS:
    provedor = REGISTRO.por_caminho(arquivo)
    checa_igual(provedor.nome if provedor else None, esperado,
                f"{arquivo} -> {esperado}")

# Caminho completo tambem funciona, e a caixa da extensao nao importa.
checa_igual(REGISTRO.por_caminho(r"C:\Projetos\Sistema\CONFIG.XML").nome, "XML",
            "extensao em MAIUSCULAS e' reconhecida")
checa_igual(REGISTRO.por_caminho(r"\\servidor\pasta\guia.PY").nome, "Python",
            "caminho de rede com extensao maiuscula tambem")

# Extensao desconhecida cai em texto puro, e nunca em None.
checa_igual(REGISTRO.por_caminho("arquivo.extensao_inventada").nome, "Texto",
            "extensao desconhecida cai em Texto")
checa(REGISTRO.por_caminho(None) is not None,
      "sem caminho e sem amostra, devolve o provedor de Texto")

# Shebang: arquivo SEM extensao.
checa_igual(REGISTRO.por_caminho("rodar", "#!/usr/bin/env python3\nx = 1").nome,
            "Python", "shebang de python num arquivo sem extensao")
checa_igual(REGISTRO.por_caminho("x", "#!/usr/bin/python\n").nome, "Python",
            "shebang com caminho absoluto tambem")

# Assinatura de inicio de arquivo.
checa_igual(REGISTRO.por_caminho("sem_extensao",
                                 '<?xml version="1.0"?>\n<a/>').nome,
            "XML", "assinatura <?xml num arquivo sem extensao")

# ---------------------------------------------------------------------------
secao("3 - deteccao por conteudo")

PY = ("import json\n\n\ndef calcular(x):\n    return x * 2\n\n\n"
      "class Guia:\n    pass\n")
checa_igual(REGISTRO.por_caminho("sem_nome", PY).nome, "Python",
            "codigo Python sem extensao e' detectado pelo conteudo")

JSON = '{\n  "nome": "x",\n  "valor": 1,\n  "ativo": true\n}\n'
checa_igual(REGISTRO.por_caminho("sem_nome", JSON).nome, "JSON",
            "JSON sem extensao e' detectado pelo conteudo")

INI = "[secao]\nchave = valor\noutra = 2\nterceira = tres\n"
checa_igual(REGISTRO.por_caminho("sem_nome", INI).nome, "INI",
            "INI sem extensao e' detectado pelo conteudo")

MD = "# Titulo\n\nTexto com **negrito** e [link](http://x).\n\n- item\n"
checa_igual(REGISTRO.por_caminho("sem_nome", MD).nome, "Markdown",
            "Markdown sem extensao e' detectado pelo conteudo")

# Texto comum NAO deve ser confundido com nada.
COMUM = ("Prezado cliente,\n\nInformamos que a guia foi emitida.\n\n"
         "Atenciosamente,\nSuporte\n")
checa_igual(REGISTRO.por_caminho("sem_nome", COMUM).nome, "Texto",
            "texto comum permanece Texto (nenhuma heuristica o reivindica)")

# A extensao VENCE o conteudo: um .txt com codigo Python dentro continua .txt,
# porque foi o usuario que deu esse nome ao arquivo.
checa_igual(REGISTRO.por_caminho("anotacoes.txt", PY).nome, "Texto",
            "a extensao vence o conteudo (o usuario nomeou o arquivo)")

# ---------------------------------------------------------------------------
secao("4 - extensao mais longa primeiro")

class ProvedorDeclaracao(ProvedorGenerico):
    pass


declaracao = ProvedorGenerico(nome="TS-declaracao", extensoes=(".d.ts",),
                              prioridade=5, palavras_chave=("declare",))
generico_ts = ProvedorGenerico(nome="TS", extensoes=(".ts",),
                               prioridade=5, palavras_chave=("const",))
REGISTRO.registrar(generico_ts)
REGISTRO.registrar(declaracao)
checa_igual(REGISTRO.por_caminho("tipos.d.ts").nome, "TS-declaracao",
            ".d.ts resolve para o provedor da extensao mais LONGA")
checa_igual(REGISTRO.por_caminho("codigo.ts").nome, "TS",
            "e .ts continua resolvendo para o generico")

# ---------------------------------------------------------------------------
secao("5 - prioridade: plugin sobrepoe embutido")

class ProvedorPythonDePlugin(ProvedorGenerico):
    pass


plugin = ProvedorGenerico(nome="Python", extensoes=(".py",), prioridade=10,
                          palavras_chave=("def", "class"),
                          comentario_de_linha="#")
REGISTRO.registrar(plugin)
resolvido = REGISTRO.por_caminho("guia.py")
checa_igual(resolvido.prioridade, 10,
            "provedor de plugin (prioridade 10) sobrepoe o embutido (0)")
checa(isinstance(resolvido, ProvedorGenerico),
      "e o resolvido e' de fato o do plugin")

# Registrar um de prioridade MENOR nao desfaz a sobreposicao.
from textforge.linguagens.python_ import ProvedorPython          # noqa: E402
REGISTRO.registrar(ProvedorPython())
checa_igual(REGISTRO.por_caminho("guia.py").prioridade, 10,
            "registrar um de prioridade menor NAO desfaz a sobreposicao")

# Restaura o estado para as secoes seguintes.
REGISTRO.limpar()
linguagens.carregar_embutidos()

# ---------------------------------------------------------------------------
secao("6 - comentarios e indentacao por linguagem (requisito 21)")

ESPERADO = {
    "Python": ("#", None),
    "JSON": ("//", ("/*", "*/")),
    "XML": (None, ("<!--", "-->")),
    "INI": ("#", None),
    "Markdown": (None, ("<!--", "-->")),
}
for nome, (linha, bloco) in ESPERADO.items():
    provedor = REGISTRO.por_nome(nome)
    checa(provedor is not None, f"{nome} esta' registrado")
    if provedor is None:
        continue
    checa_igual(provedor.comentario_de_linha, linha,
                f"{nome}: comentario de linha")
    checa_igual(provedor.comentario_de_bloco,
                tuple(bloco) if bloco else None,
                f"{nome}: comentario de bloco")
    checa(provedor.comenta_linha() or provedor.comenta_bloco(),
          f"{nome}: tem alguma forma de comentar (o Ctrl+/ funciona)")

py = REGISTRO.por_nome("Python")
checa_igual(py.indentacao_padrao.largura, 4, "Python: 4 espacos por padrao")
checa_igual(REGISTRO.por_nome("JSON").indentacao_padrao.largura, 2,
            "JSON: 2 espacos por padrao")
checa(py.aumenta_indentacao.search("if x:") is not None,
      "Python: ':' no fim abre bloco")
checa(py.aumenta_indentacao.search("if x:  # nota") is not None,
      "inclusive com comentario depois do ':'")
checa(py.aumenta_indentacao.search("x = {1: 2}") is None,
      "mas ':' no MEIO da linha nao abre bloco")
checa(py.diminui_indentacao.search("    return x") is not None,
      "Python: 'return' recua")

# ---------------------------------------------------------------------------
secao("7 - estrutura: Python via ast")

CODIGO = '''import os


class Guia:
    """Doc."""

    def __init__(self, numero):
        self.numero = numero

    def total(self) -> int:
        return 0


def solta(a, b=1, *args, **kwargs):
    pass
'''
arvore = py.estrutura(CODIGO)
checa_igual(len(arvore), 2, "duas definicoes no topo: a classe e a funcao solta")
classe = arvore[0]
checa_igual(classe.rotulo, "Guia", "a classe e' achada")
checa_igual(classe.tipo, "classe", "e classificada como classe")
checa_igual(classe.linha, 3, "na linha 3 (BASE ZERO)")
checa_igual(len(classe.filhos), 2, "com os dois metodos como filhos")
checa_igual(classe.filhos[0].rotulo, "__init__", "o primeiro metodo")
checa_igual(classe.filhos[0].tipo, "metodo",
            "classificado como METODO, nao funcao")
checa("numero" in classe.filhos[0].detalhe,
      f"e a assinatura aparece no detalhe: {classe.filhos[0].detalhe!r}")
checa("-> int" in classe.filhos[1].detalhe,
      f"inclusive o tipo de retorno: {classe.filhos[1].detalhe!r}")
checa_igual(arvore[1].tipo, "funcao", "a funcao de topo e' funcao, nao metodo")
checa("*args" in arvore[1].detalhe and "**kwargs" in arvore[1].detalhe,
      f"e *args/**kwargs aparecem: {arvore[1].detalhe!r}")

# Arquivo com erro de sintaxe e' o caso COMUM: o usuario esta' digitando.
QUEBRADO = "class Guia:\n    def f(self)\n        return  # falta o ':'\n"
arvore = py.estrutura(QUEBRADO)
checa(len(arvore) >= 1,
      "codigo com erro de sintaxe ainda produz estrutura (fallback por regex)")
checa_igual(arvore[0].rotulo, "Guia", "e a classe continua sendo achada")

checa_igual(py.estrutura(""), [], "arquivo vazio devolve estrutura vazia")

# ---------------------------------------------------------------------------
secao("8 - estrutura: JSON, XML, INI e Markdown")

js = REGISTRO.por_nome("JSON")
arvore = js.estrutura('{"a": 1, "b": {"c": 2}, "d": [1, 2]}')
rotulos = [n.rotulo for n in arvore]
checa("a" in rotulos and "b" in rotulos and "d" in rotulos,
      f"JSON: as propriedades do topo aparecem ({rotulos})")
b = next(n for n in arvore if n.rotulo == "b")
checa_igual([f.rotulo for f in b.filhos], ["c"],
            "JSON: o objeto aninhado traz os filhos")

# JSON invalido cai na varredura por regex, e nao vira estrutura vazia.
arvore = js.estrutura('{"a": 1, "b": ')
checa(any(n.rotulo == "a" for n in arvore),
      "JSON invalido ainda lista as chaves achadas")

xm = REGISTRO.por_nome("XML")
arvore = xm.estrutura('<config><servidor ip="1"><nome>x</nome></servidor></config>')
checa_igual(len(arvore), 1, "XML: uma raiz")
checa_igual(arvore[0].rotulo, "config", "e ela e' <config>")
checa_igual(arvore[0].filhos[0].rotulo, "servidor", "com <servidor> dentro")
checa("ip" in arvore[0].filhos[0].detalhe,
      "e os atributos aparecem no detalhe")
checa_igual(arvore[0].filhos[0].filhos[0].rotulo, "nome", "e <nome> no terceiro nivel")

# Tag COMENTADA nao esta' na estrutura do documento.
arvore = xm.estrutura("<a><!-- <fantasma/> --><real/></a>")
nomes = [f.rotulo for f in arvore[0].filhos]
checa_igual(nomes, ["real"], f"XML: tag comentada e' ignorada ({nomes})")

# Tag vazia nao abre nivel.
arvore = xm.estrutura("<a><b/><c/></a>")
checa_igual([f.rotulo for f in arvore[0].filhos], ["b", "c"],
            "XML: <b/> e <c/> sao IRMAOS (a tag vazia nao abre nivel)")

ini = REGISTRO.por_nome("INI")
arvore = ini.estrutura("[banco]\nservidor = x\nporta = 5432\n\n[log]\nnivel = INFO\n")
checa_igual([n.rotulo for n in arvore], ["banco", "log"],
            "INI: as duas secoes")
checa_igual([f.rotulo for f in arvore[0].filhos], ["servidor", "porta"],
            "INI: as chaves da secao como filhas")
# Um .env nao tem secao: as chaves ficam na raiz.
arvore = ini.estrutura("SENHA=1\nUSUARIO=admin\n")
checa_igual([n.rotulo for n in arvore], ["SENHA", "USUARIO"],
            "INI: sem secao, as chaves ficam na raiz (o caso do .env)")

md = REGISTRO.por_nome("Markdown")
arvore = md.estrutura("# A\n\ntexto\n\n## B\n\n### C\n\n## D\n\n# E\n")
checa_igual([n.rotulo for n in arvore], ["A", "E"], "Markdown: dois titulos de nivel 1")
checa_igual([f.rotulo for f in arvore[0].filhos], ["B", "D"],
            "com os de nivel 2 como filhos")
checa_igual([f.rotulo for f in arvore[0].filhos[0].filhos], ["C"],
            "e o de nivel 3 dentro do primeiro de nivel 2")

# O "#" dentro de bloco de codigo NAO e' titulo.
arvore = md.estrutura("# Real\n\n```python\n# nao e' titulo\n```\n\n## Tambem real\n")
todos = [arvore[0].rotulo] + [f.rotulo for f in arvore[0].filhos]
checa_igual(todos, ["Real", "Tambem real"],
            f"Markdown: '#' dentro de bloco de codigo e' ignorado ({todos})")

# ---------------------------------------------------------------------------
secao("9 - ProvedorGenerico e de_json")

lua = ProvedorGenerico(
    nome="Lua", extensoes=(".lua",), prioridade=10,
    comentario_de_linha="--", comentario_de_bloco=("--[[", "]]"),
    palavras_chave=("and", "break", "do", "else", "end", "function", "if",
                    "local", "nil", "not", "or", "return", "then", "while"),
    constantes=("nil", "true", "false"),
    prefixo_de_definicao=("function",),
    modo_de_dobra="marcadores")
regras = lua.regras(TEMA)
checa(regras is not None, "ProvedorGenerico produz regras")
checa_igual(regras.problemas_de_desempenho(), [],
            "e sem quantificador aninhado")
ausentes = [p for p in regras.papeis_usados() if not TEMA.tem_papel(p)]
checa_igual(ausentes, [], "e todo papel citado existe no tema")
checa(lua.regras(TEMA) is regras,
      "regras() usa cache (compilar a cada bloco seria o gargalo)")

arvore = lua.estrutura("local x = 1\nfunction somar(a, b)\n  return a + b\nend\n")
checa_igual([n.rotulo for n in arvore], ["somar"],
            "a estrutura generica acha as definicoes por regex")

# de_json: a via de extensao que NAO executa codigo de terceiros.
provedor, avisos = ProvedorGenerico.de_json({
    "nome": "Go",
    "extensoes": [".go"],
    "palavras_chave": "func var const if else for range return package import",
    "tipos": ["int", "string", "bool", "error"],
    "comentario_de_linha": "//",
    "comentario_de_bloco": ["/*", "*/"],
    "prefixo_de_definicao": ["func", "type"],
    "modo_de_dobra": "delimitadores",
})
checa(provedor is not None, "de_json monta um provedor")
checa_igual(avisos, [], "sem avisos num JSON correto")
checa_igual(provedor.nome, "Go", "com o nome declarado")
checa_igual(provedor.extensoes, (".go",), "e a extensao")
checa(provedor.prioridade > 0,
      "provedor de JSON nasce com prioridade > 0 (sobrepoe embutido)")
checa("func" in provedor.palavras_de_autocomplete(),
      "as palavras-chave entram no autocomplete")
checa_igual(provedor.dobras().modo, "delimitadores", "o modo de dobra e' lido")
# "palavras_chave" como STRING e' o erro mais comum de quem escreve o JSON a mao.
checa("var" in provedor.palavras_de_autocomplete(),
      "aceita 'palavras_chave' como string separada por espacos")

# Erros no JSON viram AVISO, nao excecao: um arquivo de linguagem com erro de
# digitacao nao pode impedir o programa de abrir.
provedor, avisos = ProvedorGenerico.de_json({"nome": "X", "chave_inventada": 1})
checa(provedor is not None, "chave desconhecida nao impede a construcao")
checa(any("chave_inventada" in a for a in avisos),
      f"e gera aviso nomeando a chave: {avisos}")

provedor, avisos = ProvedorGenerico.de_json({"extensoes": [".x"]})
checa(provedor is None, "sem 'nome', nao ha' provedor")
checa(avisos, "e ha' um aviso explicando")

provedor, avisos = ProvedorGenerico.de_json(
    {"nome": "Y", "aumenta_indentacao": "[regex invalido("})
checa(provedor is not None, "regex invalido nao impede a construcao")
checa(any("regex" in a for a in avisos), f"e gera aviso: {avisos}")

provedor, avisos = ProvedorGenerico.de_json(["nao", "e", "objeto"])
checa(provedor is None, "JSON que nao e' objeto devolve None")

# ---------------------------------------------------------------------------
secao("10 - visualizador preferido")

for provedor in REGISTRO.todos():
    checa(provedor.visualizador_preferido() in ("texto", "tabela", "hex"),
          f"{provedor.nome}: visualizador preferido valido")

sys.exit(resumir())
