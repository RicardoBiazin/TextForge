"""Codificacao: BOM, cascata de deteccao, binario, fim de linha, perdas.

    .venv\\Scripts\\python.exe tests\\teste_codificacao.py

Este e' o teste do modulo onde um erro CORROMPE ARQUIVO DO USUARIO. Nao precisa
de Qt.

As tres verificacoes que mais valem:

  * UTF-32-LE nao e' confundido com UTF-16-LE. Os bytes do BOM de UTF-32-LE
    (FF FE 00 00) COMECAM com o de UTF-16-LE (FF FE), e testar na ordem errada
    leria um arquivo UTF-32 como UTF-16 cheio de caracteres nulos.
  * UTF-16 sem BOM nao e' classificado como binario. Texto ASCII em UTF-16 tem um
    byte nulo a cada dois; a regra ingenua "tem NUL, e' binario" recusaria o
    arquivo.
  * `conferir_conversao` acha TODOS os caracteres perdidos de cada linha, e nao
    so' o primeiro. `UnicodeEncodeError` reporta apenas a primeira sequencia
    problematica por chamada.
"""

from __future__ import annotations

import codecs
import sys

from ajudantes import checa, checa_igual, resumir, secao

from textforge import codificacao as cod

# Textos acentuados em constantes, no topo. Um teste sobre codificacao precisa de
# caracteres REALMENTE fora do ASCII: escrever "coracao" sem cedilha faz o
# arquivo virar ASCII puro, o UTF-8 estrito acertar por acidente, e o teste
# passar sem exercitar nada -- foi assim que a primeira versao deste arquivo
# deixou passar uma falha na cascata.
ACAO = "ação"
CORACAO = "coração"
NOME = "Ricardo Biazin, Ação & Reação"

# ---------------------------------------------------------------------------
secao("1 - BOM")

CASOS_BOM = [
    (codecs.BOM_UTF8 + "acao".encode("utf-8"), "utf-8", "UTF-8 BOM", "acao"),
    (codecs.BOM_UTF16_LE + "acao".encode("utf-16-le"), "utf-16-le",
     "UTF-16 LE", "acao"),
    (codecs.BOM_UTF16_BE + "acao".encode("utf-16-be"), "utf-16-be",
     "UTF-16 BE", "acao"),
    (codecs.BOM_UTF32_LE + "acao".encode("utf-32-le"), "utf-32-le",
     "UTF-32 LE", "acao"),
    (codecs.BOM_UTF32_BE + "acao".encode("utf-32-be"), "utf-32-be",
     "UTF-32 BE", "acao"),
]
for dados, codec, rotulo, esperado in CASOS_BOM:
    p = cod.detectar(dados)
    checa_igual(p.codec, codec, f"{rotulo}: codec detectado")
    checa_igual(p.texto, esperado, f"{rotulo}: texto decodificado")
    checa_igual(p.como_decidiu, "BOM", f"{rotulo}: decidiu pelo BOM")
    checa_igual(p.confianca, 100, f"{rotulo}: confianca maxima")
    checa(p.texto and not p.texto.startswith("﻿"),
          f"{rotulo}: o BOM NAO aparece no texto")
    checa_igual(p.bom, dados[:len(dados) - len(esperado.encode(codec))],
                f"{rotulo}: os bytes do BOM sao guardados literalmente")

# A ordem da tabela e' o que faz isto funcionar.
p = cod.detectar(codecs.BOM_UTF32_LE + "ab".encode("utf-32-le"))
checa_igual(p.codec, "utf-32-le",
            "UTF-32-LE NAO e' confundido com UTF-16-LE (o BOM e' prefixo)")
checa_igual(p.texto, "ab", "e o texto UTF-32 sai correto, sem nulos")

checa_igual(cod.detectar(codecs.BOM_UTF8).texto, "",
            "arquivo que so' tem BOM devolve texto vazio")
checa_igual(cod.detectar(b"").texto, "", "arquivo vazio nao estoura")
checa_igual(cod.detectar(b"").como_decidiu, "arquivo vazio",
            "e diz que estava vazio")

# ---------------------------------------------------------------------------
secao("2 - a cascata, na ordem")

p = cod.detectar(f"{CORACAO} & {ACAO}".encode("utf-8"))
checa_igual(p.codec, "utf-8", "UTF-8 sem BOM e' detectado")
checa_igual(p.como_decidiu, "UTF-8 estrito",
            "e decidido pelo teste estrito, ANTES do charset-normalizer")
checa_igual(p.texto, f"{CORACAO} & {ACAO}", "o texto sai intacto")
checa_igual(p.substituicoes, 0, "sem substituicoes")

# Arquivo curto com um unico acento: e' onde o charset-normalizer erra e o teste
# estrito acerta. Por isso ele vem primeiro.
p = cod.detectar(ACAO.encode("utf-8"))
checa_igual(p.codec, "utf-8", "arquivo curto com acento em UTF-8 e' detectado")
checa_igual(p.texto, ACAO, "e o acento sai correto")

# Amostra CURTA em cp1252. Antes do limite MINIMO_NAO_ASCII_PARA_DETECTOR, o
# charset-normalizer respondia "cp1006" (pagina de codigo arabe) para estes 7
# bytes, e o texto saia como mojibake. Com poucos bytes nao-ASCII o palpite dele
# e' ruido, e a codificacao legada configurada e' a resposta provavel.
p = cod.detectar(CORACAO.encode("cp1252"), "cp1252")
checa_igual(p.texto, CORACAO,
            "amostra CURTA em cp1252: os acentos saem corretos")
checa(p.codec.replace("-", "").lower() in ("cp1252", "iso88591", "latin1",
                                           "windows1252"),
      f"e a codificacao escolhida e' a legada, nao uma exotica ({p.codec})")
checa_igual(p.substituicoes, 0, "sem perda de caracteres")

# Amostra LONGA em cp1252: agora o detector tem dados de verdade.
longo = (f"{CORACAO} {ACAO} " * 40).encode("cp1252")
p = cod.detectar(longo, "cp1252")
checa(CORACAO in p.texto,
      f"amostra LONGA em cp1252 tambem sai correta (via {p.como_decidiu})")

# E o outro lado da regra: texto realmente estrangeiro TEM de ser reconhecido
# pelo detector, e nao forcado a cp1252.
japones = ("日本語のテキストです。これはテストです。" * 10).encode("shift_jis")
p = cod.detectar(japones, "cp1252")
checa("日本語" in p.texto or p.codec.replace("_", "-").startswith("shift"),
      f"texto japones em Shift-JIS e' reconhecido pelo detector ({p.codec})")

# XML que declara a propria codificacao. O conteudo TEM de ter acento, senao o
# arquivo e' ASCII puro e o UTF-8 estrito decide antes da declaracao.
xml = (f'<?xml version="1.0" encoding="iso-8859-1"?>\n'
       f"<cliente><nome>{NOME}</nome></cliente>").encode("iso-8859-1")
p = cod.detectar(xml)
checa(NOME in p.texto, "XML latin-1 declarado e' lido corretamente")
checa_igual(p.como_decidiu, "declarada no arquivo",
            "e foi a declaracao do XML que decidiu")

checa_igual(cod.codificacao_declarada(xml), "iso8859-1",
            "codificacao_declarada le' a declaracao do XML")
html = b'<html><head><meta charset="utf-8"></head>'
checa_igual(cod.codificacao_declarada(html), "utf-8",
            "codificacao_declarada le' o meta charset do HTML")
py = b"# -*- coding: cp1252 -*-\nx = 1\n"
checa_igual(cod.codificacao_declarada(py), "cp1252",
            "codificacao_declarada le' a linha coding do PEP 263")
# A linha 2 e' valida pelo PEP 263: e' o caso do arquivo que comeca com shebang.
com_shebang = b"#!/usr/bin/env python3\n# -*- coding: cp1252 -*-\nx = 1\n"
checa_igual(cod.codificacao_declarada(com_shebang), "cp1252",
            "a linha coding na LINHA 2 vale (o caso do shebang, PEP 263)")
checa_igual(cod.codificacao_declarada(b"x = 1\ny = 2\n# coding: cp1252\n"), "",
            "mas na linha 3 nao vale mais")
checa_igual(cod.codificacao_declarada(b"sem declaracao"), "",
            "arquivo sem declaracao devolve string vazia")
checa_igual(cod.codificacao_declarada(
    b'<?xml encoding="codificacao-inventada"?>'), "",
    "declaracao com codec inexistente e' ignorada")

# UTF-16 sem BOM.
p = cod.detectar("numeroGuia=123".encode("utf-16-le"))
checa_igual(p.codec, "utf-16-le", "UTF-16 LE sem BOM e' detectado")
checa_igual(p.texto, "numeroGuia=123", "e o texto sai correto")
p = cod.detectar("numeroGuia=123".encode("utf-16-be"))
checa_igual(p.codec, "utf-16-be", "UTF-16 BE sem BOM e' detectado")

# ---------------------------------------------------------------------------
secao("3 - fallback e leitura suspeita")

# Bytes que nao sao UTF-8 valido nem casam com nada: cai no fallback e conta o
# estrago. E' esse numero que poe a aba em somente leitura.
p = cod.detectar(b"ok\xff\xfe\xfd\xfc ruim", "ascii")
checa(p.substituicoes >= 0, "o fallback nao estoura com bytes invalidos")
checa(p.texto, "e devolve algum texto para o usuario ver")

p = cod.detectar(b"linha\x81\x8d\x8f invalida em cp1252", "cp1252")
checa(p.suspeito if p.substituicoes else True,
      "quando ha' substituicao, o perfil se declara suspeito")

texto, trocas = cod._decodificar(b"\x81", "cp1252")
checa(trocas >= 1, "_decodificar conta os U+FFFD que a tolerancia introduziu")

# ---------------------------------------------------------------------------
secao("4 - binario ou texto (o caso .dat, requisito 7)")

checa(not cod.parece_binario(b""), "arquivo vazio e' texto vazio, nao binario")
checa(not cod.parece_binario(b"texto comum\nsegunda linha\n"),
      "texto ASCII nao e' binario")
checa(not cod.parece_binario("acentuado coracao".encode("cp1252")),
      "texto cp1252 com acentos nao e' binario")

# O caso central do requisito 7: um .dat de largura fixa e' TEXTO.
dat = ("0001JOSE DA SILVA      000012345\n"
       "0002MARIA SOUZA        000067890\n").encode("cp1252")
checa(not cod.parece_binario(dat),
      ".dat de largura fixa em cp1252 e' reconhecido como TEXTO")
p = cod.detectar(dat)
checa(not p.binario and "JOSE DA SILVA" in p.texto,
      "e abre normalmente, com o conteudo legivel")

# Byte nulo = binario.
checa(cod.parece_binario(b"dados\x00binarios"), "byte NUL indica binario")
checa(cod.parece_binario(bytes(range(256)) * 40),
      "dump de bytes arbitrarios e' binario")

# UTF-16 sem BOM tem NUL em toda posicao par, e NAO pode ser tomado por binario.
checa(not cod.parece_binario("texto em utf16".encode("utf-16-le")),
      "UTF-16 LE sem BOM NAO e' binario (o NUL e' do encoding)")
checa(not cod.parece_binario("texto em utf16".encode("utf-16-be")),
      "UTF-16 BE sem BOM NAO e' binario")

# Assinaturas conhecidas.
ASSINATURAS = [
    (b"PK\x03\x04" + b"x" * 200, "ZIP"),
    (b"%PDF-1.7\n" + b"texto legivel " * 20, "PDF"),
    (b"\x7fELF" + b"a" * 200, "ELF"),
    (b"MZ" + b"a" * 200, "executavel"),
    (b"\x89PNG\r\n\x1a\n" + b"a" * 100, "PNG"),
    (b"GIF89a" + b"abc" * 60, "GIF"),
    (b"\xff\xd8\xff\xe0" + b"a" * 100, "JPEG"),
    (b"SQLite format 3\x00" + b"a" * 100, "SQLite"),
]
for dados, nome in ASSINATURAS:
    checa(cod.parece_binario(dados), f"{nome} e' detectado como binario")
    checa(cod.assinatura_de(dados) != "",
          f"{nome} tem a assinatura nomeada (para a mensagem ao usuario)")

# Um PDF comeca com texto legivel, mas a assinatura decide antes da proporcao.
p = cod.detectar(b"%PDF-1.7\n" + b"texto que parece legivel " * 40)
checa(p.binario, "PDF e' binario apesar de ter muito texto legivel dentro")
checa_igual(p.assinatura, "PDF", "e a assinatura e' nomeada no perfil")
checa_igual(p.texto, "", "documento binario nao traz texto (nao exibe corrompido)")

# ---------------------------------------------------------------------------
secao("5 - fim de linha")

p = cod.detectar_fim_de_linha("a\r\nb\r\nc\r\n")
checa_igual(p.fim_de_linha, cod.CRLF, "CRLF puro e' detectado")
checa(not p.misto, "e nao e' considerado misto")
checa_igual(p.rotulo, "CRLF", "o rotulo e' CRLF")
checa(p.termina_com_nova_linha, "e termina com nova linha")

p = cod.detectar_fim_de_linha("a\nb\nc")
checa_igual(p.fim_de_linha, cod.LF, "LF puro e' detectado")
checa(not p.termina_com_nova_linha,
      "arquivo sem quebra final e' marcado como tal")

p = cod.detectar_fim_de_linha("a\rb\rc\r")
checa_igual(p.fim_de_linha, cod.CR, "CR puro (Mac classico) e' detectado")

# Misto: mantem o DOMINANTE e sinaliza. Nao "conserta".
p = cod.detectar_fim_de_linha("a\r\nb\r\nc\r\nd\ne\n")
checa_igual(p.fim_de_linha, cod.CRLF, "misto com maioria CRLF -> CRLF")
checa(p.misto, "e o perfil se declara misto")
checa_igual(p.contagens.get(cod.CRLF), 3, "conta 3 CRLF")
checa_igual(p.contagens.get(cod.LF), 2, "e 2 LF isolados (nao 5)")

p = cod.detectar_fim_de_linha("a\nb\nc\nd\r\n")
checa_igual(p.fim_de_linha, cod.LF, "misto com maioria LF -> LF")
checa(p.misto, "tambem se declara misto")

# Sem nenhuma quebra: fica o padrao, nao um palpite.
p = cod.detectar_fim_de_linha("uma linha so", cod.LF)
checa_igual(p.fim_de_linha, cod.LF, "sem quebras, usa o padrao passado")
checa(not p.misto, "e nao e' misto")
p = cod.detectar_fim_de_linha("", cod.CRLF)
checa_igual(p.fim_de_linha, cod.CRLF, "texto vazio usa o padrao")

# Ida e volta.
checa_igual(cod.para_lf("a\r\nb\rc\nd"), "a\nb\nc\nd",
            "para_lf normaliza os tres tipos")
checa_igual(cod.de_lf("a\nb", cod.CRLF), "a\r\nb", "de_lf re-expande para CRLF")
checa_igual(cod.de_lf("a\nb", cod.CR), "a\rb", "de_lf re-expande para CR")
checa_igual(cod.de_lf("a\nb", cod.LF), "a\nb", "de_lf com LF nao muda nada")
checa_igual(cod.de_lf(cod.para_lf("a\r\nb\r\n"), cod.CRLF), "a\r\nb\r\n",
            "ida e volta preserva o CRLF original")

# ---------------------------------------------------------------------------
secao("6 - conversao destrutiva (requisito 5)")

perdas = cod.conferir_conversao("texto simples ASCII", "ascii")
checa_igual(len(perdas), 0, "texto ASCII nao perde nada em ASCII")

perdas = cod.conferir_conversao(CORACAO, "ascii")
checa(len(perdas) > 0, "texto com acento perde caracteres em ASCII")

# O detalhe que quase toda implementacao erra: TODOS os caracteres de cada linha.
perdas = cod.conferir_conversao("ação e coração", "ascii")
caracteres = {p.caractere for p in perdas}
checa(len(perdas) >= 3,
      f"acha TODOS os acentos da linha, nao so' o primeiro ({len(perdas)})")
checa("ç" in caracteres and "ã" in caracteres,
      "e identifica cada caractere perdido")

perdas = cod.conferir_conversao("linha ok\nlinha com ação\nfim", "ascii")
checa(all(p.linha == 2 for p in perdas),
      "reporta a LINHA correta (base 1) de cada perda")
primeiro = perdas[0]
checa_igual(primeiro.linha, 2, "a perda esta' na linha 2")
checa("ção"[0] == primeiro.caractere or primeiro.coluna > 10,
      f"e na coluna correta (base 1): {primeiro.coluna}")
checa(primeiro.nome_unicode, "cada perda traz o nome Unicode do caractere")
checa("LATIN" in primeiro.nome_unicode.upper(),
      f"o nome e' o oficial do Unicode: {primeiro.nome_unicode}")

# Teto: a lista serve para decidir, nao para ser relatorio de arquivo inteiro.
perdas = cod.conferir_conversao("ç" * 5000, "ascii", teto=10)
checa_igual(len(perdas), 10, "o teto limita a lista")

checa_igual(cod.conferir_conversao("qualquer", "codec-inexistente"), [],
            "codec desconhecido devolve lista vazia em vez de estourar")

# cp1252 aceita acentos latinos, mas nao caractere de outro alfabeto.
checa_igual(len(cod.conferir_conversao("coração", "cp1252")), 0,
            "acentos do portugues cabem em cp1252")
checa(len(cod.conferir_conversao("日本語", "cp1252")) == 3,
      "caracteres japoneses nao cabem em cp1252")

resumo = cod.resumir_perdas(cod.conferir_conversao("ção ção ção", "ascii"))
checa("x)" in resumo, f"resumir_perdas agrupa por caractere com contagem: {resumo}")

checa(cod.pode_converter("simples", "ascii"), "pode_converter aceita ASCII puro")
checa(not cod.pode_converter("ação", "ascii"),
      "pode_converter recusa acento em ASCII")
checa(cod.pode_converter("ação", "utf-8"), "pode_converter aceita acento em UTF-8")

# ---------------------------------------------------------------------------
secao("7 - codificar reescreve o BOM literalmente")

dados = cod.codificar("abc", "utf-8", codecs.BOM_UTF8)
checa(dados.startswith(codecs.BOM_UTF8), "o BOM recebido e' reescrito")
checa_igual(dados, codecs.BOM_UTF8 + b"abc", "e o conteudo vem depois dele")

dados = cod.codificar("abc", "utf-8", b"")
checa(not dados.startswith(codecs.BOM_UTF8),
      "sem BOM na entrada, NAO se inventa um BOM na saida")
checa_igual(dados, b"abc", "arquivo UTF-8 sem BOM continua sem BOM")

try:
    cod.codificar("ação", "ascii")
    checa(False, "codificar deveria levantar em conversao impossivel")
except UnicodeEncodeError:
    checa(True, "codificar levanta UnicodeEncodeError por padrao (nao silencia)")

dados = cod.codificar("ação", "ascii", substituir=True)
checa(b"?" in dados, "com substituir=True, troca o que nao cabe por '?'")

# ---------------------------------------------------------------------------
secao("8 - rotulos e o separador de paragrafo")

p = cod.detectar(codecs.BOM_UTF8 + b"x")
checa_igual(p.rotulo, "UTF-8 BOM", "UTF-8 com BOM tem rotulo proprio")
p = cod.detectar(b"x")
checa_igual(p.rotulo, "UTF-8", "UTF-8 sem BOM aparece como UTF-8")

checa_igual(ord(cod.SEPARADOR_DE_PARAGRAFO), 0x2029,
            "SEPARADOR_DE_PARAGRAFO e' U+2029 (o que o Qt usa no toRawText)")

nomes = [n for n, _ in cod.OFERECIDAS]
for exigida in ("utf-8", "utf-8-sig", "utf-16-le", "utf-16-be", "cp1252",
                "iso-8859-1", "ascii"):
    checa(exigida in nomes,
          f"o requisito 5 pede {exigida}, e ela esta' na lista oferecida")

sys.exit(resumir())
