"""Linguagens embutidas umas nas outras, e o pareamento (requisitos 9 e 14).

    .venv\\Scripts\\python.exe tests\\teste_realce_embutido.py

Os casos que separam uma implementacao correta de uma decorativa:

  * `<?php` dentro de HTML entra no contexto PHP e `?>` volta ao HTML;
  * `</script>` DENTRO de uma string JavaScript fecha o bloco (e' o que o navegador
    faz de verdade), mas `<` dentro de string nao vira tag;
  * o comentario `/* */` do CSS atravessa tres linhas;
  * heredoc `<<<SQL` do PHP atravessa linhas;
  * a template string do JS produz uma pilha de TRES niveis, com `${}` voltando a
    ser codigo;
  * a estrutura do PHP ignora o JavaScript de dentro de <script>.

O realce e' verificado por MEDICAO (lendo os papeis dos `DadosDoBloco`), e nunca por
inspecao de captura de tela.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, preparar_qt, pular, resumir, secao

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QTextDocument                       # noqa: E402

from textforge import configuracao, linguagens                 # noqa: E402
from textforge.interface import tema as tmod                    # noqa: E402
from textforge.realce.dados_do_bloco import DadosDoBloco        # noqa: E402
from textforge.realce.pintor import Pintor                      # noqa: E402

TEMA = tmod.embutido("escuro")
CFG = configuracao.padrao()
linguagens.carregar_embutidos()
REG = linguagens.REGISTRO


def pintar(texto: str, nome_da_linguagem: str) -> tuple[QTextDocument, Pintor]:
    provedor = REG.por_nome(nome_da_linguagem)
    doc = QTextDocument()
    doc.setPlainText(texto)
    return doc, Pintor(doc, provedor, TEMA, CFG)


def papeis(doc: QTextDocument, linha: int) -> set[str]:
    dados = doc.findBlockByNumber(linha).userData()
    if not isinstance(dados, DadosDoBloco):
        return set()
    return {t.papel for t in dados.tokens}


def pilha(doc: QTextDocument, linha: int) -> tuple[str, ...]:
    dados = doc.findBlockByNumber(linha).userData()
    return dados.pilha_ao_terminar if isinstance(dados, DadosDoBloco) else ()


def papel_em(doc: QTextDocument, linha: int, coluna: int) -> str:
    dados = doc.findBlockByNumber(linha).userData()
    return dados.papel_em(coluna) if isinstance(dados, DadosDoBloco) else ""


# ---------------------------------------------------------------------------
secao("1 - PHP dentro de HTML")

PHP = """<html>
<body>
<?php
$x = 10;
echo "ola";
?>
<div>texto html</div>
</body>
</html>"""

doc, _ = pintar(PHP, "PHP")

checa("tag" in papeis(doc, 0), "linha 0: <html> e' pintado como tag")
checa("preprocessador" in papeis(doc, 2), "linha 2: <?php e' preprocessador")
checa("php:raiz" in pilha(doc, 2),
      f"e a pilha entra no contexto do PHP: {pilha(doc, 2)}")
checa("variavel" in papeis(doc, 3),
      "linha 3: $x e' pintado como variavel do PHP")
checa("php:raiz" in pilha(doc, 3), "e continua no contexto do PHP")
checa("palavra_chave" in papeis(doc, 4), "linha 4: 'echo' e' palavra-chave")
checa("texto_literal" in papeis(doc, 4), "e a string e' texto literal")
checa("preprocessador" in papeis(doc, 5), "linha 5: ?> e' preprocessador")
checa_igual(pilha(doc, 5), ("raiz",),
            "e a pilha VOLTA ao HTML depois do ?>")
checa("tag" in papeis(doc, 6),
      "linha 6: depois do ?>, <div> volta a ser tag de HTML")
checa("variavel" not in papeis(doc, 6),
      "e nada da linha 6 e' interpretado como PHP")

# Um .php que comeca direto com <?php.
doc2, _ = pintar("<?php\n$y = 1;\n", "PHP")
checa("php:raiz" in pilha(doc2, 0),
      "arquivo que comeca com <?php entra no PHP na primeira linha")
checa("variavel" in papeis(doc2, 1), "e a variavel da linha 1 e' reconhecida")

# ---------------------------------------------------------------------------
secao("2 - JavaScript dentro de <script>")

HTML_JS = """<html>
<script>
const x = 1;
function f() { return "texto"; }
</script>
<div>html de novo</div>"""

doc, _ = pintar(HTML_JS, "HTML")
checa("palavra_chave" in papeis(doc, 2),
      "'const' dentro de <script> e' palavra-chave do JS")
# O corpo do <script> recebe as REGRAS do JS (por `com_prefixo`), e a pilha se
# chama "corpo_do_script". O que importa e' que as regras do JS estao ativas ali --
# o nome do contexto e' detalhe de implementacao.
checa_igual(pilha(doc, 2), ("raiz", "tag_de_script", "corpo_do_script"),
            "e a pilha esta' no corpo do script (dois niveis acima da raiz)")
checa("definicao" in papeis(doc, 3),
      "o nome da funcao JS ganha papel de definicao")
checa("tag_fechamento" in papeis(doc, 4), "</script> fecha o bloco")
checa("tag" in papeis(doc, 5),
      "e a linha seguinte volta a ser HTML")

# LIMITE CONHECIDO, medido e aceito: "</script>" dentro de uma string JS NAO fecha
# o bloco aqui, embora o navegador feche. A alternancia do contexto escolhe o
# casamento mais a' ESQUERDA, e a string comeca uma coluna antes. Ver o cabecalho
# de html.py para o custo da correcao.
DENTRO = """<script>
var s = "</script>";
</script>"""
doc, _ = pintar(DENTRO, "HTML")
checa("texto_literal" in papeis(doc, 1),
      "'</script>' dentro de string JS conta como parte da STRING "
      "(limite conhecido: o navegador fecharia o bloco ali)")
checa_igual(pilha(doc, 2), ("raiz",),
            "e o </script> da linha seguinte fecha o bloco normalmente")

# O inverso NAO pode acontecer: "<" dentro de string nao vira tag.
doc, _ = pintar('<script>\nvar s = "a < b";\n</script>', "HTML")
checa("tag" not in papeis(doc, 1),
      "'<' dentro de string JS NAO e' interpretado como abertura de tag")

# ---------------------------------------------------------------------------
secao("3 - CSS dentro de <style>, com comentario de 3 linhas")

HTML_CSS = """<style>
.classe { color: red; }
/* comentario
   que atravessa
   tres linhas */
#id { font-size: 12px; }
</style>
<p>texto</p>"""

doc, _ = pintar(HTML_CSS, "HTML")
checa("tipo" in papeis(doc, 1), ".classe e' pintada como seletor")
checa("chave" in papeis(doc, 1), "e 'color' como propriedade")
for linha in (2, 3, 4):
    checa("comentario" in papeis(doc, linha),
          f"linha {linha} do comentario CSS e' comentario")
checa("chave" in papeis(doc, 5),
      "depois do comentario, 'font-size' volta a ser propriedade")
checa("tag" in papeis(doc, 7), "e depois de </style> volta a ser HTML")

# ---------------------------------------------------------------------------
secao("4 - template string do JS: pilha de tres niveis")

TEMPLATE = """const s = `antes ${valor + 1} depois`;
const t = `linha 1
linha 2`;"""

doc, _ = pintar(TEMPLATE, "JavaScript")
checa("texto_literal" in papeis(doc, 0), "a template string e' texto literal")
checa("interpolacao" in papeis(doc, 0), "e o ${} tem papel proprio")
# Dentro de ${}: e' codigo de novo. O "+" tem de ser operador.
checa("operador" in papeis(doc, 0),
      "dentro de ${} o codigo volta a ser realcado (o '+' e' operador)")

checa("template" in pilha(doc, 1),
      f"template string de varias linhas continua aberta: {pilha(doc, 1)}")
checa("texto_literal" in papeis(doc, 1),
      "e a linha do meio e' toda texto literal")
checa_igual(pilha(doc, 2), ("raiz",), "a crase de fechamento fecha o contexto")

# ---------------------------------------------------------------------------
secao("5 - heredoc do PHP")

HEREDOC = """<?php
$sql = <<<SQL
    SELECT * FROM guias
    WHERE numero = 1
SQL;
$depois = 1;"""

doc, _ = pintar(HEREDOC, "PHP")
checa("texto_literal" in papeis(doc, 1), "o <<<SQL abre um texto literal")
checa(any("heredoc" in c for c in pilha(doc, 1)),
      f"e a pilha entra no contexto de heredoc: {pilha(doc, 1)}")
for linha in (2, 3):
    checa("texto_literal" in papeis(doc, linha),
          f"linha {linha} do heredoc e' texto literal")
    checa("palavra_chave" not in papeis(doc, linha),
          f"e o SQL da linha {linha} NAO e' realcado como PHP")
checa("variavel" in papeis(doc, 5),
      "depois do heredoc, a variavel volta a ser reconhecida")

# ---------------------------------------------------------------------------
secao("6 - SQL: a string usa aspa DOBRADA como escape")

# Tratar como C faria a string parecer nao fechada, e o resto do arquivo ficaria
# pintado como texto literal.
doc, _ = pintar("SELECT 'ABC''123' AS x;\nSELECT 1;", "SQL")
checa("texto_literal" in papeis(doc, 0), "a string com '' e' texto literal")
checa("palavra_chave" in papeis(doc, 1),
      "e a linha seguinte NAO ficou dentro da string (o SELECT e' realcado)")

doc, _ = pintar("select * from guias where x = 1", "SQL")
checa("palavra_chave" in papeis(doc, 0),
      "SQL em minusculas tambem e' realcado (a caixa nao importa)")
doc, _ = pintar("SELECT * FROM GUIAS", "SQL")
checa("palavra_chave" in papeis(doc, 0), "e em maiusculas tambem")

# ---------------------------------------------------------------------------
secao("7 - estrutura ignora outra linguagem embutida")

PHP_COM_JS = """<?php
class Guia {
    public function total() {
        return 1;
    }
}
?>
<script>
function formatarNoJs(v) { return v; }
</script>"""

php = REG.por_nome("PHP")
arvore = php.estrutura(PHP_COM_JS)
checa_igual(len(arvore), 1, "so' a classe PHP esta' na estrutura")
checa_igual(arvore[0].rotulo, "Guia", "e ela e' a Guia")
metodos = [f.rotulo for f in arvore[0].filhos]
checa_igual(metodos, ["total"],
            f"apenas o metodo PHP e' filho da classe ({metodos}) -- a funcao "
            f"JavaScript de dentro de <script> NAO entra")

# ---------------------------------------------------------------------------
secao("8 - estrutura de HTML, CSS, JS, YAML e shell")

html = REG.por_nome("HTML")
arvore = html.estrutura(
    '<div id="topo"><br><span class="a b">x</span><img src="i"></div>')
checa_igual(len(arvore), 1, "HTML: uma raiz")
checa_igual(arvore[0].rotulo, "div", "e ela e' a div")
checa("#topo" in arvore[0].detalhe, "com o id no detalhe")
filhos = [f.rotulo for f in arvore[0].filhos]
checa_igual(filhos, ["br", "span", "img"],
            f"os tres filhos sao IRMAOS ({filhos}) -- <br> e <img> nao "
            f"abrem nivel")

# Tag nao fechada nao pode desalinhar o resto do documento.
arvore = html.estrutura("<div><p>sem fechar</div><span>depois</span>")
checa_igual(len(arvore), 2,
            "HTML: fechar uma tag nao correspondente ainda deixa <span> na raiz")

css = REG.por_nome("CSS")
arvore = css.estrutura(".a { color: red; }\n@media print {\n  .b { x: 1; }\n}")
rotulos = [n.rotulo for n in arvore]
checa(".a" in rotulos and "@media print" in rotulos,
      f"CSS: seletores e blocos @ aparecem ({rotulos})")

js = REG.por_nome("JavaScript")
arvore = js.estrutura(
    "class A {\n  metodo() {}\n}\nfunction solta() {}\n"
    "const arrow = (x) => x;\n")
tipos = {n.rotulo: n.tipo for n in arvore}
checa("A" in tipos and tipos["A"] == "classe", "JS: a classe e' achada")
checa("solta" in tipos and tipos["solta"] == "funcao", "JS: a funcao tambem")
checa("arrow" in tipos, "JS: e a arrow function nomeada")
checa("metodo" in tipos and tipos["metodo"] == "metodo", "JS: e o metodo")

ya = REG.por_nome("YAML")
arvore = ya.estrutura("servicos:\n  web:\n    porta: 80\n  banco:\n    porta: 5432\n")
checa_igual([n.rotulo for n in arvore], ["servicos"], "YAML: uma raiz")
checa_igual([f.rotulo for f in arvore[0].filhos], ["web", "banco"],
            "YAML: aninhado pela INDENTACAO")

ps = REG.por_nome("PowerShell")
arvore = ps.estrutura("function Get-Guia {\n  param($x)\n}\nfunction Set-Guia {}")
checa_igual([n.rotulo for n in arvore], ["Get-Guia", "Set-Guia"],
            "PowerShell: as duas funcoes")

bat = REG.por_nome("Batch")
arvore = bat.estrutura("@echo off\n:inicio\necho oi\ngoto inicio\n:fim\n")
checa_igual([n.rotulo for n in arvore], ["inicio", "fim"],
            "Batch: os rotulos de goto")

# ---------------------------------------------------------------------------
secao("9 - pareamento de delimitadores (requisito 14)")

from textforge.editor import pareamento                        # noqa: E402

doc, _ = pintar("def f(a, (b, c)):\n    return [1, {2: 3}]\n", "Python")

par = pareamento.casar_delimitador(doc, 0, 5)      # o "(" de f(
checa(par is not None, "acha o par do '(' externo")
if par:
    origem, destino = par
    checa_igual((origem.bloco, origem.coluna), (0, 5), "a origem e' o '(' de f(")
    checa_igual((destino.bloco, destino.coluna), (0, 15),
                "e o par e' o ')' EXTERNO, nao o interno (contagem de saldo)")

par = pareamento.casar_delimitador(doc, 0, 15)     # o ")" externo
checa(par is not None and par[1].coluna == 5,
      "a partir do fechamento, acha a abertura correspondente")

par = pareamento.casar_delimitador(doc, 1, 11)     # o "[" da linha 1
checa(par is not None and par[1].bloco == 1,
      "acha o par de '[' na mesma linha")

# Parentese sem par nao pode inventar um.
doc, _ = pintar("x = (1 + 2\ny = 3\n", "Python")
checa(pareamento.casar_delimitador(doc, 0, 4) is None,
      "parentese sem fechamento nao tem par (e nao estoura)")

# Delimitador dentro de string nao e' pareado.
doc, _ = pintar('x = "texto ( aqui"\ny = (1)\n', "Python")
checa(pareamento.casar_delimitador(doc, 0, 11) is None,
      "'(' dentro de string nao e' um delimitador pareavel")

# Par em blocos DIFERENTES.
doc, _ = pintar("def f(\n    a,\n    b\n):\n    pass\n", "Python")
par = pareamento.casar_delimitador(doc, 0, 5)
checa(par is not None and par[1].bloco == 3,
      "acha o par que esta' TRES linhas abaixo")

checa(pareamento.casar_delimitador(doc, 999, 0) is None,
      "bloco inexistente devolve None em vez de estourar")

# ---------------------------------------------------------------------------
secao("10 - pareamento de tags (requisito 14)")

XML = """<config>
    <servidor>
        <nome>x</nome>
    </servidor>
</config>"""

doc, _ = pintar(XML, "XML")
par = pareamento.casar_tag(doc, 0, 2)
checa(par is not None, "acha o par de <config>")
if par:
    checa_igual(par[1].bloco, 4, "e o </config> esta' na linha 4")

par = pareamento.casar_tag(doc, 1, 6)
checa(par is not None and par[1].bloco == 3,
      "<servidor> casa com </servidor> na linha 3")

par = pareamento.casar_tag(doc, 3, 8)
checa(par is not None and par[1].bloco == 1,
      "e a partir do fechamento acha a abertura")

# Tag ANINHADA de mesmo nome: o par tem de ser o do nivel certo.
doc, _ = pintar("<a>\n  <a>\n  </a>\n</a>", "XML")
par = pareamento.casar_tag(doc, 0, 1)
checa(par is not None and par[1].bloco == 3,
      "<a> externo casa com o </a> EXTERNO (contagem de aninhamento)")
par = pareamento.casar_tag(doc, 1, 4)
checa(par is not None and par[1].bloco == 2,
      "e o <a> interno com o </a> interno")

# Tag vazia nao tem par.
doc, _ = pintar("<a><br/></a>", "XML")
checa(pareamento.casar_tag(doc, 0, 5) is None,
      "tag vazia (<br/>) nao tem par")

# `casar` tenta delimitador e depois tag.
doc, _ = pintar("<a>{x}</a>", "XML")
checa(pareamento.casar(doc, 0, 1) is not None,
      "casar() acha a tag quando o cursor esta' nela")

sys.exit(resumir())
