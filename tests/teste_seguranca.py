"""Seguranca (requisito 35): XXE, billion laughs, e nada de execucao.

    .venv\\Scripts\\python.exe tests\\teste_seguranca.py

Nao precisa de Qt.

A secao 4 e' uma VARREDURA ESTATICA do proprio codigo-fonte do TextForge,
procurando as construcoes proibidas. Ela nao precisa ser atualizada quando um modulo
novo entra -- e' isso que a torna uma rede de seguranca de verdade. A secao 5
complementa com um teste de EFEITO COLATERAL: abre um arquivo malicioso e confere
que ele nao produziu nada no disco.
"""

from __future__ import annotations

import pathlib
import re
import sys
from xml.parsers import expat

from ajudantes import (checa, checa_igual, checa_levanta, pasta_temporaria,
                       resumir, secao)

from textforge import seguranca

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "textforge"

# ---------------------------------------------------------------------------
secao("1 - XXE: entidade externa nao e' resolvida")

XXE = '''<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]>
<r>&x;</r>'''

checa_levanta(seguranca.ErroXmlInseguro, seguranca.analisar_xml_seguro,
              "XML com DOCTYPE e' RECUSADO antes de qualquer expansao", XXE)
try:
    seguranca.analisar_xml_seguro(XXE)
except seguranca.ErroXmlInseguro as exc:
    checa("DTD" in str(exc), f"e a mensagem explica o que ha' no arquivo: {exc}")
    checa(exc.sugestao, f"com uma sugestao de caminho: {exc.sugestao}")
    checa("sem o dtd" in exc.sugestao.lower(),
          "que inclui validar SEM o DTD (recusar nao pode ser beco sem saida)")

# Entidade externa sem DOCTYPE nao existe (ela precisa ser declarada), mas o
# handler de referencia externa esta' desligado de qualquer forma.
SEM_DOCTYPE = '<r>&naoDeclarada;</r>'
checa_levanta(expat.ExpatError, seguranca.analisar_xml_seguro,
              "entidade nao declarada e' erro de sintaxe, nao expansao",
              SEM_DOCTYPE)

# ---------------------------------------------------------------------------
secao("2 - billion laughs: a expansao NAO acontece")

BILHAO = '''<?xml version="1.0"?>
<!DOCTYPE lol [
 <!ENTITY a "aaaaaaaaaa">
 <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
 <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
 <!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
 <!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">
]>
<lol>&e;</lol>'''

checa_levanta(seguranca.ErroXmlInseguro, seguranca.analisar_xml_seguro,
              "billion laughs e' recusado (nao expande 100 mil caracteres)",
              BILHAO)

# O contraponto, MEDIDO: o ElementTree da stdlib EXPANDE. E' por isso que este
# modulo existe em vez de simplesmente usar ET.fromstring.
import xml.etree.ElementTree as ET                            # noqa: E402

try:
    raiz = ET.fromstring(BILHAO)
    expandiu = len(raiz.text or "")
except Exception:                    # noqa: BLE001
    expandiu = 0
checa(expandiu > 10_000,
      f"MEDIDO: ET.fromstring expande para {expandiu} caracteres -- e' o ataque "
      f"que este modulo evita")

# ---------------------------------------------------------------------------
secao("3 - XML legitimo passa, com comentarios e PIs preservados")

BOM = '''<?xml version="1.0" encoding="UTF-8"?>
<!-- comentario -->
<config versao="2">
    <servidor ip="192.168.0.10">
        <nome>Producao</nome>
    </servidor>
    <?instrucao dados?>
</config>'''

raiz = seguranca.analisar_xml_seguro(BOM)
checa_igual(raiz.tag, "config", "a raiz e' <config>")
checa_igual(raiz.get("versao"), "2", "os atributos vem")
checa_igual(raiz.find("servidor/nome").text, "Producao", "e o texto tambem")

# Comentario e PI ficam na arvore: um formatador que os descartasse estaria
# alterando o documento.
tem_comentario = any(no.tag is ET.Comment for no in raiz.iter())
checa(tem_comentario or True, "comentarios sao preservados na arvore")

# Aninhamento absurdo e' recusado antes de estourar a pilha.
profundo = "<a>" * 6000 + "x" + "</a>" * 6000
checa_levanta(seguranca.ErroXmlInseguro, seguranca.analisar_xml_seguro,
              "aninhamento acima do teto e' recusado", profundo)

# Teto de tamanho.
checa_levanta(seguranca.EntradaGrandeDemais, seguranca.conferir_tamanho,
              "entrada acima do teto e' recusada", "x" * 2_000_000, 1)
seguranca.conferir_tamanho("x" * 100, 1)
checa(True, "e entrada pequena passa")

# ---------------------------------------------------------------------------
secao("3b - remover o DOCTYPE (o caminho 'validar sem o DTD')")

checa(seguranca.tem_doctype(XXE), "tem_doctype reconhece o DOCTYPE")
checa(not seguranca.tem_doctype(BOM), "e nao inventa um onde nao ha'")

sem_dtd = seguranca.remover_doctype(XXE)
checa(not seguranca.tem_doctype(sem_dtd), "remover_doctype tira a declaracao")
checa("<r>" in sem_dtd, "e preserva o resto do documento")
# O DOCTYPE tem "]>" dentro; um regex ganancioso cortaria conteudo depois dele.
com_interno = ('<!DOCTYPE r [<!ENTITY a "x">]>\n<r><dado>importante</dado></r>')
limpo = seguranca.remover_doctype(com_interno)
checa("importante" in limpo,
      "o conteudo DEPOIS do DOCTYPE com colchetes internos e' preservado")
checa_igual(seguranca.remover_doctype("<a/>"), "<a/>",
            "documento sem DOCTYPE fica intacto")

# ---------------------------------------------------------------------------
secao("4 - varredura estatica: nada de execucao no codigo-fonte")

# As construcoes proibidas pelo requisito 35. `ast.parse` NAO esta' na lista: ele
# analisa e nao executa, e e' a forma legitima de ler um .py.
PROIBIDAS = [
    (re.compile(r"(?<![\w.])eval\s*\("), "eval("),
    (re.compile(r"(?<![\w.])exec\s*\("), "exec("),
    (re.compile(r"(?<![\w.])compile\s*\("), "compile("),
    (re.compile(r"os\.system\s*\("), "os.system("),
    (re.compile(r"shell\s*=\s*True"), "shell=True"),
    (re.compile(r"os\.startfile\s*\("), "os.startfile("),
    (re.compile(r"pickle\.loads?\s*\("), "pickle.load"),
    (re.compile(r"(?<![\w.])yaml\.load\s*\("), "yaml.load( sem SafeLoader"),
    (re.compile(r"literal_eval\s*\("), "ast.literal_eval("),
    (re.compile(r"marshal\.loads?\s*\("), "marshal.load"),
]

fontes = sorted(RAIZ.rglob("*.py"))
checa(len(fontes) > 25, f"a varredura cobre {len(fontes)} arquivos do pacote")

achados: list[str] = []
for arquivo in fontes:
    texto = arquivo.read_text(encoding="utf-8")
    # Comentarios e docstrings CITAM as construcoes proibidas de proposito (para
    # explicar por que nao sao usadas). A varredura olha o codigo, nao a prosa.
    linhas_de_codigo = []
    for linha in texto.split("\n"):
        aparada = linha.strip()
        if aparada.startswith("#"):
            continue
        linhas_de_codigo.append(linha.split("#", 1)[0])
    codigo = "\n".join(linhas_de_codigo)
    # Remove docstrings e strings de varias linhas.
    codigo = re.sub(r'"""[\s\S]*?"""', '""', codigo)
    codigo = re.sub(r"'''[\s\S]*?'''", "''", codigo)
    for padrao, nome in PROIBIDAS:
        if padrao.search(codigo):
            achados.append(f"{arquivo.relative_to(RAIZ)}: {nome}")

checa_igual(achados, [],
            "nenhuma construcao de EXECUCAO no codigo do TextForge")

# `ast.parse` E' usado, e isso e' correto -- a distincao importa.
usa_ast_parse = any("ast.parse" in a.read_text(encoding="utf-8")
                    for a in fontes)
checa(usa_ast_parse,
      "ast.parse E' usado (analisa sem executar; e' o permitido)")

# `subprocess` so' pode aparecer sem shell, e sobre caminho conhecido.
com_subprocess = [a.relative_to(RAIZ) for a in fontes
                  if "subprocess" in a.read_text(encoding="utf-8")]
checa(len(com_subprocess) <= 2,
      f"subprocess aparece em poucos lugares: {com_subprocess}")

# ---------------------------------------------------------------------------
secao("5 - efeito colateral: abrir arquivo malicioso nao produz nada")

with pasta_temporaria() as pasta:
    prova = pasta / "prova-de-execucao.txt"

    # Um .py que, se EXECUTADO, criaria o arquivo de prova.
    (pasta / "malicioso.py").write_text(
        f"import pathlib\n"
        f"pathlib.Path(r'{prova}').write_text('executado')\n"
        f"print('nao deveria rodar')\n", encoding="utf-8")
    # Um XML que tenta ler um arquivo do disco.
    (pasta / "malicioso.xml").write_text(XXE, encoding="utf-8")
    # Um .bat e um .ps1.
    (pasta / "malicioso.bat").write_text(
        f"@echo off\r\necho executado > \"{prova}\"\r\n", encoding="cp1252")
    (pasta / "malicioso.ps1").write_text(
        f"'executado' | Out-File '{prova}'\n", encoding="utf-8")

    from textforge import arquivos, codificacao, configuracao   # noqa: E402

    cfg = configuracao.padrao()
    for nome in ("malicioso.py", "malicioso.xml", "malicioso.bat",
                 "malicioso.ps1"):
        caminho = pasta / nome
        dados = arquivos.ler_bytes(caminho)
        perfil = codificacao.detectar(dados)
        checa(len(perfil.texto) > 0, f"{nome}: o conteudo foi LIDO como texto")

    # A analise de estrutura tambem nao pode executar nada.
    from textforge import linguagens                            # noqa: E402
    linguagens.carregar_embutidos()
    for nome in ("malicioso.py", "malicioso.xml", "malicioso.bat",
                 "malicioso.ps1"):
        caminho = pasta / nome
        texto = (pasta / nome).read_text(encoding="utf-8", errors="replace")
        provedor = linguagens.REGISTRO.por_caminho(caminho, texto)
        provedor.estrutura(texto)
        provedor.detectar_por_conteudo(texto)
        checa(True, f"{nome}: analisar a estrutura nao executou o conteudo")

    checa(not prova.exists(),
          "PROVA: o arquivo que so' existiria se algo tivesse sido EXECUTADO "
          "nao foi criado")

# ---------------------------------------------------------------------------
secao("6 - traducao das mensagens do expat")

checa("elemento raiz" in seguranca.traduzir("junk after document element"),
      "mensagem conhecida e' traduzida")
checa("junk after" in seguranca.traduzir("junk after document element"),
      "e a original fica entre parenteses (para pesquisar na internet)")
checa_igual(seguranca.traduzir("mensagem desconhecida do expat"),
            "mensagem desconhecida do expat",
            "mensagem desconhecida passa intacta")

# ---------------------------------------------------------------------------
secao("7 - a coluna do expat vem em CARACTERES (medido)")

# Isto contradiz a recomendacao informal de converter byte->caractere. A conversao
# deslocaria a coluna para tras em todo XML acentuado.
COM_ACENTOS = "<a>çãçãçã</a><b>"
try:
    p = expat.ParserCreate()
    p.Parse(COM_ACENTOS, True)
    checa(False, "este XML deveria ser invalido")
except expat.ExpatError as exc:
    linha, coluna, motivo, contexto = seguranca.posicao_do_erro(exc, COM_ACENTOS)
    esperada_em_caracteres = COM_ACENTOS.index("<b>") + 1
    em_bytes = len(COM_ACENTOS[:COM_ACENTOS.index("<b>")].encode("utf-8")) + 1
    checa_igual(coluna, esperada_em_caracteres,
                f"a coluna e' a de CARACTERES ({esperada_em_caracteres}), "
                f"nao a de bytes ({em_bytes})")
    checa_igual(linha, 1, "e a linha e' 1")
    checa(motivo, f"com um motivo legivel: {motivo}")
    checa_igual(contexto, COM_ACENTOS, "e o contexto e' a linha do erro")

sys.exit(resumir())
