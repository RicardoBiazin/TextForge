"""Operacoes de linha (requisito 22) e conversao de caixa (requisito 40).

    .venv\\Scripts\\python.exe tests\\teste_operacoes_linha.py

Funcoes puras, sem Qt.

Duas verificacoes valem mais que as outras aqui:

  * `remover_duplicadas` preserva a PRIMEIRA ocorrencia e NAO ordena. Deduplicar
    ordenando (o truque do `sort -u`) destruiria a ordem cronologica de um log,
    que costuma ser a informacao mais importante do arquivo.
  * `snake("numeroXMLGuia")` da' "numero_xml_guia", e nao "numero_x_m_l_guia".
    O segundo e' o resultado tipico de quem separa palavras so' pela transicao
    de minuscula para maiuscula, e estraga qualquer nome com sigla.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, resumir, secao

from textforge.editor import caixa
from textforge.editor import operacoes_linha as ops

# ---------------------------------------------------------------------------
secao("1 - duplicar, mover e excluir")

checa_igual(ops.duplicar(["a"]), ["a", "a"], "duplicar uma linha")
checa_igual(ops.duplicar(["a", "b"]), ["a", "b", "a", "b"],
            "duplicar um bloco repete o bloco inteiro")
checa_igual(ops.duplicar([]), [], "duplicar bloco vazio nao estoura")

todas = ["a", "b", "c", "d"]
novas, desloc = ops.mover_para_cima(todas, 2, 3)
checa_igual(novas, ["a", "c", "b", "d"], "mover 'c' para cima troca com 'b'")
checa_igual(desloc, -1, "e o cursor precisa subir uma linha")

novas, desloc = ops.mover_para_baixo(todas, 1, 2)
checa_igual(novas, ["a", "c", "b", "d"], "mover 'b' para baixo troca com 'c'")
checa_igual(desloc, 1, "e o cursor precisa descer uma linha")

novas, desloc = ops.mover_para_cima(todas, 1, 3)
checa_igual(novas, ["b", "c", "a", "d"], "mover um bloco de 2 linhas para cima")
checa_igual(desloc, -1, "o deslocamento do bloco tambem e' -1")

# Nos limites, nada acontece -- e o deslocamento zero avisa o chamador para nao
# mexer no cursor.
novas, desloc = ops.mover_para_cima(todas, 0, 1)
checa_igual((novas, desloc), (todas, 0), "a primeira linha nao sobe")
novas, desloc = ops.mover_para_baixo(todas, 3, 4)
checa_igual((novas, desloc), (todas, 0), "a ultima linha nao desce")
novas, desloc = ops.mover_para_cima([], 0, 0)
checa_igual(desloc, 0, "lista vazia nao estoura")

# ---------------------------------------------------------------------------
secao("2 - ordenar")

checa_igual(ops.ordenar(["c", "a", "b"]), ["a", "b", "c"], "ordem alfabetica")
checa_igual(ops.ordenar(["c", "a", "b"], invertido=True), ["c", "b", "a"],
            "ordem invertida")
# Sem ignorar caixa, maiusculas vem antes por causa do codigo ASCII.
checa_igual(ops.ordenar(["b", "A", "a"]), ["A", "a", "b"],
            "sem ignorar caixa, 'A' vem antes de 'a'")
checa_igual(ops.ordenar(["b", "A", "a"], ignorar_caixa=True), ["A", "a", "b"],
            "ignorando caixa, 'A' e 'a' ficam juntos, em ordem estavel")
checa_igual(ops.ordenar(["Erro", "aviso", "Debug"], ignorar_caixa=True),
            ["aviso", "Debug", "Erro"],
            "ignorando caixa, ordena pela palavra e nao pelo ASCII")

# O caso em que a ordenacao alfabetica engana: "10" vem antes de "9".
checa_igual(ops.ordenar(["9", "10", "2"]), ["10", "2", "9"],
            "alfabeticamente, '10' vem antes de '2' (comportamento correto)")
checa_igual(ops.ordenar(["9", "10", "2"], numerico=True), ["2", "9", "10"],
            "numericamente, a ordem e' 2, 9, 10")
checa_igual(ops.ordenar(["linha 100 x", "linha 20 y"], numerico=True),
            ["linha 20 y", "linha 100 x"],
            "ordem numerica usa o primeiro numero da linha")
sem_numero = ops.ordenar(["cabecalho", "5", "3"], numerico=True)
checa_igual(sem_numero[-1], "cabecalho",
            "linha sem numero vai para o fim, nao para o comeco")

checa_igual(ops.inverter(["a", "b", "c"]), ["c", "b", "a"], "inverter a ordem")
checa_igual(ops.inverter([]), [], "inverter lista vazia")

# ---------------------------------------------------------------------------
secao("3 - remover duplicadas e vazias")

entrada = ["b", "a", "b", "c", "a"]
checa_igual(ops.remover_duplicadas(entrada), ["b", "a", "c"],
            "preserva a PRIMEIRA ocorrencia e a ORDEM (nao ordena)")
checa_igual(ops.remover_duplicadas(["A", "a"]), ["A", "a"],
            "por padrao, caixa diferente sao linhas diferentes")
checa_igual(ops.remover_duplicadas(["A", "a"], ignorar_caixa=True), ["A"],
            "ignorando caixa, 'a' e' duplicata de 'A'")
checa_igual(ops.remover_duplicadas([]), [], "lista vazia nao estoura")
checa_igual(ops.remover_duplicadas(["", "", "a"]), ["", "a"],
            "linhas vazias tambem sao deduplicadas")

vazias = ["a", "", "b", "   ", "c", "\t"]
checa_igual(ops.remover_vazias(vazias), ["a", "b", "c"],
            "remove vazias, inclusive as que so' tem espaco ou TAB")
checa_igual(ops.remover_vazias(["a", "", "", "b"], so_consecutivas=True),
            ["a", "", "b"],
            "so_consecutivas colapsa varias em branco numa unica")
checa_igual(ops.remover_vazias(["a", "", "b"], so_consecutivas=True),
            ["a", "", "b"],
            "so_consecutivas preserva uma linha em branco isolada")

# ---------------------------------------------------------------------------
secao("4 - aparar, prefixar, sufixar, numerar")

checa_igual(ops.aparar_inicio(["  a", "\tb"]), ["a", "b"], "aparar o inicio")
checa_igual(ops.aparar_fim(["a  ", "b\t"]), ["a", "b"], "aparar o fim")
checa_igual(ops.aparar_ambos(["  a  "]), ["a"], "aparar os dois lados")
checa_igual(ops.aparar_fim(["  a  "]), ["  a"],
            "aparar o fim NAO mexe na indentacao")

checa_igual(ops.prefixar(["a", "b"], "> "), ["> a", "> b"], "prefixar")
checa_igual(ops.sufixar(["a", "b"], ";"), ["a;", "b;"], "sufixar")
# Prefixar linha em branco criaria espaco no fim da linha: ruido no diff.
checa_igual(ops.prefixar(["a", "", "b"], "# "), ["# a", "", "# b"],
            "por padrao, linha em branco NAO recebe prefixo")
checa_igual(ops.prefixar(["a", "", "b"], "# ", pular_vazias=False),
            ["# a", "# ", "# b"],
            "com pular_vazias=False, a linha em branco tambem recebe")
checa_igual(ops.sufixar(["a", "", "b"], ","), ["a,", "", "b,"],
            "sufixar tambem pula a linha em branco por padrao")

numeradas = ops.numerar(["x", "y", "z"])
checa_igual(numeradas, ["1: x", "2: y", "3: z"], "numerar a partir de 1")
alinhadas = ops.numerar(["a"] * 10)
checa(alinhadas[0].startswith(" 1"),
      "numerar alinha a direita quando passa de 9 (' 1:' e nao '1:')")

# ---------------------------------------------------------------------------
secao("5 - juntar")

checa_igual(ops.juntar(["a", "b", "c"]), ["a b c"], "juntar com espaco")
checa_igual(ops.juntar(["a", "b"], ", "), ["a, b"], "juntar com separador")
checa_igual(ops.juntar(["  a  ", "b"]), ["a b"], "juntar apara cada pedaco")
checa_igual(ops.juntar(["a", "", "b"]), ["a b"], "juntar ignora linhas vazias")

# ---------------------------------------------------------------------------
secao("6 - separar palavras de um identificador")

checa_igual(caixa.separar_palavras("numero_guia"), ["numero", "guia"],
            "separa por sublinhado")
checa_igual(caixa.separar_palavras("numero-guia"), ["numero", "guia"],
            "separa por hifen")
checa_igual(caixa.separar_palavras("numero guia"), ["numero", "guia"],
            "separa por espaco")
checa_igual(caixa.separar_palavras("numeroGuia"), ["numero", "Guia"],
            "separa na transicao minuscula -> maiuscula")
checa_igual(caixa.separar_palavras("NumeroGuia"), ["Numero", "Guia"],
            "separa PascalCase")
# O caso decisivo: sigla no meio do nome.
checa_igual(caixa.separar_palavras("numeroXMLGuia"), ["numero", "XML", "Guia"],
            "sigla no meio vira UMA palavra ('XML', nao 'X','M','L')")
checa_igual(caixa.separar_palavras("guiaXML"), ["guia", "XML"],
            "sigla no fim vira uma palavra")
checa_igual(caixa.separar_palavras("guia2Via"), ["guia", "2", "Via"],
            "numero forma palavra propria")
checa_igual(caixa.separar_palavras(""), [], "string vazia nao estoura")
checa_igual(caixa.separar_palavras("___"), [], "so' separadores: nenhuma palavra")

# ---------------------------------------------------------------------------
secao("7 - conversao de caixa")

checa_igual(caixa.maiusculas("acao"), "ACAO", "maiusculas")
checa_igual(caixa.minusculas("ACAO"), "acao", "minusculas")
checa_igual(caixa.alternar("aBc"), "AbC", "alternar a caixa")

checa_igual(caixa.titulo("numero da guia"), "Numero Da Guia", "cada palavra")
# str.title() erraria estes dois:
checa_igual(caixa.titulo("don't stop"), "Don't Stop",
            "titulo NAO capitaliza depois do apostrofo (str.title() erra)")
checa_igual(caixa.titulo("arquivo.txt"), "Arquivo.txt",
            "titulo NAO capitaliza depois do ponto (str.title() erra)")

for origem in ("numero_guia", "numero-guia", "numeroGuia", "NumeroGuia",
               "numero guia"):
    checa_igual(caixa.camel(origem), "numeroGuia", f"camel de {origem!r}")
    checa_igual(caixa.pascal(origem), "NumeroGuia", f"pascal de {origem!r}")
    checa_igual(caixa.snake(origem), "numero_guia", f"snake de {origem!r}")
    checa_igual(caixa.kebab(origem), "numero-guia", f"kebab de {origem!r}")

checa_igual(caixa.snake("numeroXMLGuia"), "numero_xml_guia",
            "snake com sigla: numero_xml_guia, NAO numero_x_m_l_guia")
checa_igual(caixa.pascal("numero_xml_guia"), "NumeroXmlGuia",
            "pascal a partir de snake com sigla")
checa_igual(caixa.snake_maiusculo("numeroGuia"), "NUMERO_GUIA",
            "snake maiusculo, o formato de .env")

# Ida e volta entre as formas de identificador tem de ser estavel.
checa_igual(caixa.camel(caixa.snake("numeroGuia")), "numeroGuia",
            "camel -> snake -> camel volta ao original")

# String sem palavra nenhuma nao pode virar string vazia: o usuario perderia o
# texto selecionado.
checa_igual(caixa.camel("___"), "___", "sem palavras, camel devolve o original")
checa_igual(caixa.snake(""), "", "string vazia sobrevive")

# ---------------------------------------------------------------------------
secao("8 - o mapa de comandos aponta para funcoes de verdade")

from textforge.interface.acoes import REGISTRO                # noqa: E402

for id_comando, funcao in caixa.POR_COMANDO.items():
    checa(REGISTRO.por_id(id_comando) is not None,
          f"{id_comando} existe no registro de comandos")
    checa(callable(funcao), f"{id_comando} aponta para uma funcao chamavel")

sys.exit(resumir())
