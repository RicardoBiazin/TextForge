"""TextForge -- editor de arquivos tecnicos para Windows.

Editor de texto, codigo-fonte, configuracao e dados: txt, csv, log, ini, json,
xml, yaml, py, php, js, ts, html, css, sql, md, bat, ps1, sh, java, c, cpp, go,
rs, dat. NAO e' editor de documentos ricos -- doc/docx estao fora de escopo.

Fonte unica da versao: a janela, o log, o `versao.txt` do executavel e o
`teste_empacotamento.py` leem daqui.
"""

from __future__ import annotations

# Nome de EXIBICAO: titulo da janela, dialogos, README.
APP = "TextForge"
# Nome usado em ARQUIVO e PASTA. Sem espacos de proposito: espaco em nome de
# executavel obriga aspas em todo caminho que o referencia, e e' onde o registro
# de "Abrir com" quebra em silencio.
APP_ARQUIVO = "TextForge"

VERSAO = "0.1.1"
AUTOR = "Ricardo Biazin"

# Perfil do autor, mostrado como link no dialogo Sobre. VAZIO nao quebra nada: o
# link simplesmente nao aparece. E' de proposito que o valor esteja aqui e nao
# escrito no meio do dialogo -- e' o mesmo principio da VERSAO, um lugar so'.
#
# So' entra aqui endereco CONFERIDO pelo dono do perfil: um link de rede social
# aponta para uma pessoa real, e um slug adivinhado levaria o usuario para o perfil
# de outra pessoa.
LINKEDIN = ""

__version__ = VERSAO
