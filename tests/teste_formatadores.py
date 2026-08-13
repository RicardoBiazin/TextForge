"""Formatadores (requisito 6): XML, JSON, SQL, CSS, HTML e Python.

    .venv\\Scripts\\python.exe tests\\teste_formatadores.py

Nao precisa de Qt.

As verificacoes de FIDELIDADE sao as que importam mais, porque um formatador que
"funciona" mas altera o conteudo entrega um arquivo diferente do que o usuario abriu,
e ele so' descobre quando o sistema que consome o arquivo quebra:

  * JSON: 1.10 nao vira 1.1, e um id de 20 digitos nao perde digitos;
  * JSON: chave duplicada e' RECUSA, porque formatar apagaria dados;
  * XML: CDATA e' RECUSA no caminho da stdlib, e a declaracao <?xml?> e' preservada;
  * XML: conteudo misto NAO recebe indentacao;
  * HTML: linha com texto e tag inline juntos nao e' reindentada (mudaria a pagina);
  * todos: formatar duas vezes da' o mesmo resultado (idempotencia).
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, resumir, secao

from textforge.formatadores import de_css, de_html, de_json, de_python, de_sql
from textforge.formatadores import de_xml
from textforge.formatadores.base import ErroDeSintaxe, Recusa, Resultado

OPCOES = {"usa_espacos": True, "largura": 2}
OPCOES4 = {"usa_espacos": True, "largura": 4}

# ---------------------------------------------------------------------------
secao("1 - JSON: formatar, compactar, validar")

f = de_json.FORMATADOR
checa(f.validar('{"a": 1}') is None, "JSON valido nao tem erro")
checa(f.validar("") is not None, "documento vazio e' erro")

saida = f.formatar('{"b":1,"a":[1,2],"c":{"d":true}}', OPCOES)
checa(isinstance(saida, Resultado), "formatar devolve Resultado")
checa("\n" in saida.texto, "e o resultado tem quebras de linha")
checa('"b": 1' in saida.texto, "com espaco depois dos dois-pontos")

# Idempotencia: formatar duas vezes da' o mesmo.
uma = f.formatar('{"b":1,"a":2}', OPCOES).texto
duas = f.formatar(uma, OPCOES).texto
checa_igual(duas, uma, "formatar e' idempotente")

# A ORDEM original das chaves e' preservada por padrao.
checa(saida.texto.index('"b"') < saida.texto.index('"a"'),
      "a ordem original das propriedades e' preservada")

ordenada = f.formatar_ordenando('{"b":1,"a":2}', OPCOES)
checa(ordenada.texto.index('"a"') < ordenada.texto.index('"b"'),
      "e 'Ordenar propriedades' ordena de verdade")
checa(ordenada.avisos, "avisando que a ordem foi alterada")

compacta = f.compactar('{\n  "a": 1,\n  "b": [1, 2]\n}', OPCOES)
checa("\n" not in compacta.texto.strip(), "compactar produz uma linha so'")
checa_igual(compacta.texto.strip(), '{"a":1,"b":[1,2]}',
            "sem espacos desnecessarios")

# Compactar e formatar volta ao mesmo.
original = f.formatar('{"a":1,"b":[1,2]}', OPCOES).texto
volta = f.formatar(f.compactar(original, OPCOES).texto, OPCOES).texto
checa_igual(volta, original, "compactar + formatar volta ao mesmo resultado")

# ---------------------------------------------------------------------------
secao("2 - JSON: erro com linha, coluna e POSICAO navegavel")

erro = f.validar('{"a": 1,\n "b" 2}')
checa(isinstance(erro, ErroDeSintaxe), "JSON invalido devolve ErroDeSintaxe")
checa_igual(erro.linha, 2, "com a linha certa")
checa(erro.coluna > 1, f"e a coluna ({erro.coluna})")
checa(erro.posicao is not None,
      "e a POSICAO absoluta, que leva o cursor direto ao caractere")
checa("dois-pontos" in erro.motivo,
      f"com o motivo traduzido: {erro.motivo}")
checa(erro.contexto.strip().startswith('"b"'),
      f"e o trecho da linha: {erro.contexto!r}")

# A posicao aponta MESMO para o lugar do erro.
texto = '{"a": 1,\n "b" 2}'
checa(texto[erro.posicao:erro.posicao + 1] in ("2", " "),
      f"a posicao {erro.posicao} aponta para o problema: "
      f"{texto[erro.posicao:erro.posicao + 3]!r}")

erro = f.validar("{a: 1}")
checa("aspas DUPLAS" in erro.motivo,
      f"nome de propriedade sem aspas: {erro.motivo}")
erro = f.validar('{"a": 1} lixo')
checa("depois do fim" in erro.motivo, f"conteudo extra: {erro.motivo}")

# Aninhamento profundo vira mensagem, nao traceback.
profundo = "[" * 100_000 + "]" * 100_000
erro = f.validar(profundo)
checa(erro is not None, "aninhamento de 100 mil niveis devolve erro")
checa("profundo" in erro.motivo or "analisar" in erro.motivo,
      f"com mensagem legivel: {erro.motivo}")

# NaN e Infinity nao sao JSON valido.
checa(f.validar('{"a": NaN}') is not None,
      "NaN e' recusado (nao e' JSON valido)")
checa(f.validar('{"a": Infinity}') is not None, "Infinity tambem")

# ---------------------------------------------------------------------------
secao("3 - JSON: FIDELIDADE numerica")

# json.loads devolveria float e perderia estes tres.
CASOS = [
    ('{"a": 1.10}', "1.10", "1.10 nao vira 1.1"),
    ('{"a": 12345678901234567890}', "12345678901234567890",
     "id de 20 digitos nao perde digitos"),
    ('{"a": 1e400}', "1e400", "1e400 nao vira Infinity"),
    ('{"a": 0.1000000000000000055511151231257827}',
     "0.1000000000000000055511151231257827",
     "numero de precisao alta sobrevive"),
    ('{"a": -0.0}', "-0.0", "o zero negativo sobrevive"),
    ('{"a": 1E+2}', "1E+2", "a notacao exponencial e' preservada como escrita"),
]
for entrada, esperado, descricao in CASOS:
    saida = f.formatar(entrada, OPCOES)
    checa(isinstance(saida, Resultado) and esperado in saida.texto,
          f"{descricao} (saida: {getattr(saida, 'texto', saida)!r})")

# ---------------------------------------------------------------------------
secao("4 - JSON: chave duplicada e' RECUSA, nao perda silenciosa")

saida = f.formatar('{"a": 1, "a": 2}', OPCOES)
checa(isinstance(saida, Recusa),
      "chave duplicada devolve Recusa (formatar APAGARIA a primeira)")
checa("duplicada" in saida.motivo, f"dizendo o problema: {saida.motivo}")
checa("'a'" in saida.motivo, "e nomeando a chave")
checa(saida.sugestao, f"com uma sugestao: {saida.sugestao}")

# Chave repetida em NIVEIS diferentes nao e' duplicata.
saida = f.formatar('{"a": 1, "b": {"a": 2}}', OPCOES)
checa(isinstance(saida, Resultado),
      "a mesma chave em niveis diferentes NAO e' duplicata")

# ---------------------------------------------------------------------------
secao("5 - XML: formatar, compactar, validar")

x = de_xml.FORMATADOR
checa(de_xml.motor() in ("stdlib", "lxml"),
      f"o motor de XML e' '{de_xml.motor()}'")

# O exemplo LITERAL do requisito 39.
COMPACTO = "<config><servidor><ip>192.168.0.10</ip></servidor></config>"
saida = x.formatar(COMPACTO, OPCOES4)
checa(isinstance(saida, Resultado), "formatar XML devolve Resultado")
esperado = ("<config>\n"
            "    <servidor>\n"
            "        <ip>192.168.0.10</ip>\n"
            "    </servidor>\n"
            "</config>\n")
checa_igual(saida.texto, esperado,
            "e produz EXATAMENTE a hierarquia do exemplo do requisito 39")

uma = x.formatar(COMPACTO, OPCOES4).texto
duas = x.formatar(uma, OPCOES4).texto
checa_igual(duas, uma, "formatar XML e' idempotente")

compacta = x.compactar(esperado, OPCOES4)
checa("\n" not in compacta.texto.strip(), "compactar XML da' uma linha")
checa("192.168.0.10" in compacta.texto,
      "e o TEXTO dos elementos e' preservado (nao e' indentacao)")

checa(x.validar(COMPACTO) is None, "XML bem-formado nao tem erro")

# ---------------------------------------------------------------------------
secao("6 - XML: erro com linha e coluna certas")

erro = x.validar("<a>\n  <b>\n</a>")
checa(isinstance(erro, ErroDeSintaxe), "tag desencontrada e' erro")
checa_igual(erro.linha, 3, "na linha 3")
checa("fechamento" in erro.motivo or "mismatch" in erro.motivo.lower(),
      f"com motivo legivel: {erro.motivo}")

# A COLUNA em caracteres, num XML acentuado. E' o teste da medicao feita em
# seguranca.py: converter byte->caractere deslocaria a coluna para tras.
COM_ACENTO = "<a>çãçãçã</a><b>"
erro = x.validar(COM_ACENTO)
checa(erro is not None, "XML com conteudo extra e' invalido")
checa_igual(erro.coluna, COM_ACENTO.index("<b>") + 1,
            f"e a coluna e' a de CARACTERES ({COM_ACENTO.index('<b>') + 1}), "
            f"nao a de bytes "
            f"({len(COM_ACENTO[:COM_ACENTO.index('<b>')].encode('utf-8')) + 1})")

checa(x.validar("") is not None, "XML vazio e' erro")
checa(x.validar("<a>") is not None, "tag nao fechada e' erro")

# ---------------------------------------------------------------------------
secao("7 - XML: fidelidade")

# A declaracao <?xml?> e' preservada LITERALMENTE.
COM_DECL = ('<?xml version="1.0" encoding="ISO-8859-1"?>'
            "<a><b>x</b></a>")
saida = x.formatar(COM_DECL, OPCOES4)
checa(saida.texto.startswith('<?xml version="1.0" encoding="ISO-8859-1"?>'),
      "a declaracao <?xml?> e' preservada exatamente como estava")

# Comentario sobrevive.
saida = x.formatar("<a><!-- nota --><b>x</b></a>", OPCOES4)
checa("<!-- nota -->" in saida.texto, "o comentario e' preservado")

# Instrucao de processamento sobrevive.
saida = x.formatar("<a><?php echo 1; ?><b>x</b></a>", OPCOES4)
checa("<?php" in saida.texto, "a instrucao de processamento e' preservada")

# Prefixo de namespace NAO vira ns0.
COM_NS = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
          "<soap:Body><x>1</x></soap:Body></soap:Envelope>")
saida = x.formatar(COM_NS, OPCOES4)
checa("soap:" in saida.texto,
      "o prefixo de namespace e' preservado (nao vira ns0:)")
checa("ns0:" not in saida.texto, "e nenhum ns0 aparece")

# CONTEUDO MISTO nao recebe indentacao: indenta-lo mudaria o texto exibido.
MISTO = "<p>antes <b>forte</b> depois</p>"
saida = x.formatar(MISTO, OPCOES4)
checa("antes <b>forte</b> depois" in saida.texto.replace("\n", "").replace(
      "    ", ""),
      "conteudo misto nao e' quebrado")
checa("antes" in saida.texto and "depois" in saida.texto,
      "e o texto em volta da tag inline sobrevive")

# CDATA: RECUSA no caminho da stdlib.
COM_CDATA = "<a><![CDATA[texto com <tags> dentro]]></a>"
saida = x.formatar(COM_CDATA, OPCOES4)
if de_xml.motor() == "stdlib":
    checa(isinstance(saida, Recusa),
          "com a stdlib, CDATA e' RECUSADO (seria convertido em texto escapado)")
    checa("CDATA" in saida.motivo, "dizendo o motivo")
    checa("lxml" in saida.sugestao, "e sugerindo instalar o lxml")
else:
    checa(isinstance(saida, Resultado),
          "com lxml, o CDATA e' preservado e a formatacao acontece")

# DOCTYPE: RECUSA.
saida = x.formatar('<!DOCTYPE a><a><b>x</b></a>', OPCOES4)
checa(isinstance(saida, Recusa), "XML com DOCTYPE e' recusado")
checa("DTD" in saida.motivo, "explicando que o DTD nao e' expandido")

# XXE e billion laughs: recusados pelo formatador tambem.
XXE = ('<!DOCTYPE r [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]>'
       "<r>&x;</r>")
checa(isinstance(x.formatar(XXE, OPCOES4), Recusa),
      "XXE e' recusado pelo formatador")

# ---------------------------------------------------------------------------
secao("8 - SQL")

s = de_sql.FORMATADOR
saida = s.formatar("select a,b from t where x=1", OPCOES4)
if isinstance(saida, Recusa):
    checa("sqlparse" in saida.motivo,
          "sem o sqlparse, a recusa diz como instalar")
else:
    checa("SELECT" in saida.texto,
          "as palavras reservadas vao para MAIUSCULAS")
    checa("FROM" in saida.texto and "WHERE" in saida.texto,
          "e as clausulas tambem")
    checa("\n" in saida.texto, "o SQL e' quebrado em linhas")
    uma = s.formatar("select a from t", OPCOES4).texto
    duas = s.formatar(uma, OPCOES4).texto
    checa_igual(duas, uma, "formatar SQL e' idempotente")

# A validacao ESTRUTURAL.
checa(s.validar("SELECT * FROM t") is None, "SQL simples nao tem erro estrutural")
erro = s.validar("SELECT * FROM (SELECT a FROM b")
checa(erro is not None, "parentese sem fechamento e' detectado")
checa("fechamento" in erro.motivo, f"com motivo claro: {erro.motivo}")
erro = s.validar("SELECT * FROM t)")
checa(erro is not None and "abertura" in erro.motivo,
      "parentese sobrando tambem")
erro = s.validar("SELECT 'nao fechada FROM t")
checa(erro is not None and "apostrofo" in erro.motivo,
      f"apostrofo nao fechado: {erro.motivo}")

# A aspa DOBRADA e' o escape do SQL: nao pode ser tomada por string nao fechada.
checa(s.validar("SELECT 'ABC''123' FROM t") is None,
      "a aspa dobrada ('') e' o escape do SQL, e nao abre string nova")
# Parentese dentro de string ou de comentario nao conta.
checa(s.validar("SELECT '(' FROM t") is None,
      "parentese dentro de string nao conta no balanceamento")
checa(s.validar("-- ( comentario\nSELECT 1") is None,
      "parentese em comentario de linha tambem nao")
checa(s.validar("/* ( */ SELECT 1") is None,
      "nem em comentario de bloco")
erro = s.validar("/* nao fechado\nSELECT 1")
checa(erro is not None, "comentario de bloco nao fechado e' erro")

# ---------------------------------------------------------------------------
secao("9 - CSS")

c = de_css.FORMATADOR
saida = c.formatar(".a{color:red;background:blue}", OPCOES)
checa(isinstance(saida, Resultado), "formatar CSS devolve Resultado")
checa("color: red;" in saida.texto, "espaco depois dos dois-pontos, e ';' no fim")
checa(".a {" in saida.texto, "e espaco antes da chave")

uma = c.formatar(".a{color:red}", OPCOES).texto
duas = c.formatar(uma, OPCOES).texto
checa_igual(duas, uma, "formatar CSS e' idempotente")

# Um valor com dois-pontos dentro (url) nao pode ser quebrado no primeiro ":".
saida = c.formatar('.a{background:url(http://x/y.png)}', OPCOES)
checa("url(http://x/y.png)" in saida.texto,
      "o ':' dentro de uma url nao quebra a declaracao")

# String com ';' dentro e' conteudo, e nao separador.
saida = c.formatar('.a{content:"a;b";color:red}', OPCOES)
checa('"a;b"' in saida.texto,
      "o ';' DENTRO de uma string nao e' tratado como separador")

# Seletor com virgula vira uma linha por seletor.
saida = c.formatar("h1,h2,h3{margin:0}", OPCOES)
checa(saida.texto.count("\n") >= 3,
      "seletor com virgula produz uma linha por seletor")

compacta = c.compactar(".a {\n  color: red;\n}\n", OPCOES)
checa("\n" not in compacta.texto.strip(), "compactar CSS da' uma linha")
checa(compacta.avisos, "avisando que os comentarios foram removidos")

# Validacao estrutural.
checa(c.validar(".a{color:red}") is None, "CSS balanceado nao tem erro")
erro = c.validar(".a{color:red")
checa(erro is not None and "fechamento" in erro.motivo,
      "chave sem fechamento e' detectada")
erro = c.validar(".a{}}")
checa(erro is not None and "abertura" in erro.motivo, "chave sobrando tambem")
erro = c.validar("/* nao fechado\n.a{}")
checa(erro is not None, "comentario nao fechado e' erro")
checa(c.validar('.a{content:"{"}') is None,
      "chave dentro de string nao conta no balanceamento")

# ---------------------------------------------------------------------------
secao("10 - HTML: conservador de proposito")

h = de_html.FORMATADOR
saida = h.formatar("<div>\n<p>a</p>\n</div>", OPCOES)
checa(isinstance(saida, Resultado), "formatar HTML devolve Resultado")
checa("  <p>a</p>" in saida.texto, "as tags estruturais sao indentadas")

uma = h.formatar("<div>\n<span>a</span>\n</div>", OPCOES).texto
duas = h.formatar(uma, OPCOES).texto
checa_igual(duas, uma, "formatar HTML e' idempotente")

# Linha com texto e tag INLINE junto nao e' reindentada: mudaria a pagina.
MISTO_HTML = "<div>\ntexto <b>forte</b> mais texto\n</div>"
saida = h.formatar(MISTO_HTML, OPCOES)
checa("texto <b>forte</b> mais texto" in saida.texto,
      "linha de conteudo misto NAO e' quebrada")
checa(saida.avisos, f"e ha' aviso explicando: {saida.avisos}")
checa("inline" in " ".join(saida.avisos),
      "o aviso menciona o espaco em volta do elemento inline")

# <pre> e <script> ficam intocados: o espaco dentro deles e' conteudo.
COM_PRE = "<div>\n<pre>\n   espaco   preservado\n</pre>\n</div>"
saida = h.formatar(COM_PRE, OPCOES)
checa("   espaco   preservado" in saida.texto,
      "o interior de <pre> fica INTACTO (o espaco la' e' exibido na pagina)")

COM_SCRIPT = "<div>\n<script>\n    var x = 1;\n</script>\n</div>"
saida = h.formatar(COM_SCRIPT, OPCOES)
checa("    var x = 1;" in saida.texto,
      "o interior de <script> nao e' reindentado")

# Tag vazia nao abre nivel.
saida = h.formatar("<div>\n<br>\n<p>a</p>\n</div>", OPCOES)
linhas = saida.texto.split("\n")
recuo_br = len(linhas[1]) - len(linhas[1].lstrip())
recuo_p = next(len(l) - len(l.lstrip()) for l in linhas if "<p>" in l)
checa_igual(recuo_br, recuo_p, "<br> nao abre nivel de indentacao")

# Validacao: fechamento sem abertura.
checa(h.validar("<div><p>a</p></div>") is None, "HTML equilibrado nao tem erro")
erro = h.validar("<div>a</span></div>")
checa(erro is not None and "nao foi aberto" in erro.motivo,
      f"</span> sem abertura e' detectado: {erro.motivo if erro else ''}")
# Tag nao fechada NAO e' erro: o padrao HTML permite, e o navegador fecha.
checa(h.validar("<ul><li>a<li>b</ul>") is None,
      "<li> sem fechamento NAO e' erro (o padrao HTML permite)")

# ---------------------------------------------------------------------------
secao("11 - Python")

p = de_python.FORMATADOR
checa(p.validar("def f():\n    return 1\n") is None,
      "Python valido nao tem erro")
erro = p.validar("def f(:\n    pass\n")
checa(isinstance(erro, ErroDeSintaxe), "erro de sintaxe e' detectado")
checa_igual(erro.linha, 1, "com a linha")
checa(erro.motivo, f"e o motivo: {erro.motivo}")
checa(erro.contexto, "e o trecho da linha")

saida = p.formatar("x = { 'a':1 }", OPCOES4)
if isinstance(saida, Recusa):
    checa("black" in saida.motivo, "sem o black, a recusa diz como instalar")
    checa("pip install black" in saida.sugestao,
          "com o comando exato de instalacao")
else:
    checa(isinstance(saida, Resultado), "com o black instalado, formata")
    uma = saida.texto
    duas = p.formatar(uma, OPCOES4).texto
    checa_igual(duas, uma, "formatar Python e' idempotente")

# Formatar codigo INVALIDO devolve o erro, e nao tenta formatar.
saida = p.formatar("def f(:\n    pass\n", OPCOES4)
checa(isinstance(saida, ErroDeSintaxe),
      "formatar codigo com erro de sintaxe devolve o ERRO")

# Python nao tem forma compactada, e recusar e' a resposta honesta.
saida = p.compactar("x = 1\ny = 2\n", OPCOES4)
checa(isinstance(saida, Recusa), "compactar Python e' RECUSADO")
checa("indentacao" in saida.motivo,
      f"porque a indentacao E' a sintaxe: {saida.motivo}")

# ---------------------------------------------------------------------------
secao("12 - a indentacao vem do ARQUIVO, nao da preferencia")

# Formatar com 4 espacos um arquivo indentado com 2 mudaria toda linha dele.
com2 = de_json.FORMATADOR.formatar('{"a":{"b":1}}',
                                   {"usa_espacos": True, "largura": 2}).texto
com4 = de_json.FORMATADOR.formatar('{"a":{"b":1}}',
                                   {"usa_espacos": True, "largura": 4}).texto
checa('\n  "a"' in com2, "com largura 2, o recuo e' de 2 espacos")
checa('\n    "a"' in com4, "com largura 4, e' de 4")

com_tab = de_json.FORMATADOR.formatar('{"a":{"b":1}}',
                                      {"usa_espacos": False,
                                       "largura": 4}).texto
checa("\n\t" in com_tab, "e com TAB, o recuo e' um TAB de verdade")

xml2 = de_xml.FORMATADOR.formatar("<a><b>x</b></a>",
                                  {"usa_espacos": True, "largura": 2}).texto
checa("\n  <b>" in xml2, "o XML tambem respeita a largura pedida")

# ---------------------------------------------------------------------------
secao("13 - entrada vazia e entrada absurda nao estouram")

for formatador in (de_json.FORMATADOR, de_xml.FORMATADOR, de_sql.FORMATADOR,
                   de_css.FORMATADOR, de_html.FORMATADOR,
                   de_python.FORMATADOR):
    nome = formatador.nome
    for entrada in ("", "   ", "\n\n\n"):
        try:
            formatador.formatar(entrada, OPCOES)
            formatador.compactar(entrada, OPCOES)
            formatador.validar(entrada)
            ok = True
        except Exception as exc:        # noqa: BLE001
            ok = False
            checa(False, f"{nome} estourou com entrada vazia: {exc}")
        if not ok:
            break
    else:
        checa(True, f"{nome}: entrada vazia nao estoura")

    # Entrada que nao e' da linguagem: tem de devolver erro ou recusa, nunca
    # estourar nem produzir lixo.
    try:
        formatador.formatar("\x00\x01 lixo binario <<>>", OPCOES)
        formatador.validar("\x00\x01 lixo binario <<>>")
        checa(True, f"{nome}: entrada absurda nao estoura")
    except Exception as exc:            # noqa: BLE001
        checa(False, f"{nome} estourou com entrada absurda: {exc}")

sys.exit(resumir())
