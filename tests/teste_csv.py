"""Deteccao de dialeto, divisao em registros e modo tabela do CSV (etapa 9).

    .\\.venv\\Scripts\\python.exe tests\\teste_csv.py

O teste CENTRAL desta suite e' `para_texto()` sem edicao devolvendo o texto de
ENTRADA identico -- inclusive as aspas desnecessarias, os espacos depois do
delimitador e o quoting exatamente como estava. Um modo tabela que reconstroi o CSV
com `csv.writer` altera o arquivo so' por ter sido aberto, e num arquivo de
integracao isso e' destruicao silenciosa (requisito 38).

A parte de grade PULA se o PySide6 nao estiver instalado; a parte de analise roda
sempre, porque `analisadores/de_csv.py` nao depende de Qt.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, preparar_qt, resumir, secao

# ANTES de qualquer import do projeto: `preparar_qt` define QT_QPA_PLATFORM, e
# `documento.py` (arrastado por qualquer import de interface) importa Qt.
TEM_QT = preparar_qt()

from textforge.analisadores import de_csv                     # noqa: E402
from textforge.analisadores.de_csv import Dialeto             # noqa: E402


# ===========================================================================
# Deteccao de dialeto
# ===========================================================================


def testar_deteccao() -> None:
    secao("Deteccao de delimitador")

    casos = (
        ("virgula", "nome,idade,cidade\nAna,33,Blumenau\nBruno,41,Joinville", ","),
        ("ponto e virgula", "nome;idade;cidade\nAna;33;Blumenau\n"
                            "Bruno;41;Joinville", ";"),
        ("TAB", "nome\tidade\tcidade\nAna\t33\tBlumenau\nBruno\t41\tJoinville",
         "\t"),
        ("barra vertical", "nome|idade|cidade\nAna|33|Blumenau\n"
                           "Bruno|41|Joinville", "|"),
    )
    for rotulo, texto, esperado in casos:
        checa_igual(de_csv.detectar(texto).delimitador, esperado,
                    f"detectar acha o delimitador: {rotulo}")

    # O caso brasileiro: ";" separa as colunas e a virgula e' o DECIMAL. Por
    # FREQUENCIA a virgula ganharia (aparece 3x por linha contra 3x do ";"); por
    # CONSISTENCIA da contagem, tambem empata -- o desempate pela maior contagem e'
    # que nao resolve sozinho. O que resolve e' a ordem dos candidatos e o teste
    # abaixo prova o resultado, que e' o que importa.
    brasileiro = ("produto;preco;peso;desconto\n"
                  "Cimento;32,90;50,0;1,50\n"
                  "Areia;120,00;1000,0;5,25\n"
                  "Brita;98,75;900,5;3,00\n")
    dialeto = de_csv.detectar(brasileiro)
    checa_igual(dialeto.delimitador, ";",
                "CSV brasileiro: ';' vence a virgula decimal")
    checa_igual(dialeto.colunas, 4, "CSV brasileiro: 4 colunas")

    # ";" DENTRO de aspas nao conta como delimitador. Aqui a virgula e' o
    # separador real e o ";" so' aparece dentro de um campo citado.
    com_aspas = ('nome,observacao,uf\n'
                 'Ana,"rua A; numero 3; fundos",SC\n'
                 'Bruno,"casa; ao lado",SC\n'
                 'Carla,"apto; bloco B",SC\n')
    dialeto = de_csv.detectar(com_aspas)
    checa_igual(dialeto.delimitador, ",",
                "';' dentro de aspas nao vira delimitador")
    checa_igual(dialeto.colunas, 3, "campo citado com ';' nao inventa colunas")

    # Arquivo de UMA linha: `csv.Sniffer().sniff` levanta csv.Error aqui. A
    # heuristica propria tem de responder mesmo assim.
    uma_linha = "a;b;c;d"
    dialeto = de_csv.detectar(uma_linha)
    checa_igual(dialeto.delimitador, ";",
                "arquivo de uma linha nao estoura (onde o Sniffer levanta)")
    checa_igual(dialeto.colunas, 4, "arquivo de uma linha: 4 colunas")

    # Texto que nao e' tabela nenhuma.
    prosa = ("Este e' um paragrafo comum.\n"
             "Ele nao tem delimitador nenhum.\n"
             "Nem sequer uma virgula por linha.\n")
    checa(not de_csv.parece_csv(prosa), "prosa nao e' oferecida como tabela")
    checa(de_csv.parece_csv(brasileiro), "CSV de verdade e' oferecido como tabela")
    checa_igual(de_csv.detectar("").colunas, 0, "arquivo vazio nao estoura")

    secao("Cabecalho")
    checa(de_csv.detectar(brasileiro).tem_cabecalho,
          "primeira linha so' com texto e dados com numero: e' cabecalho")
    sem_cabecalho = "Ana;33;SC\nBruno;41;SC\nCarla;28;PR\n"
    checa(not de_csv.detectar(sem_cabecalho).tem_cabecalho,
          "primeira linha com numero nao e' cabecalho")


# ===========================================================================
# Registros (o campo entre aspas que atravessa linhas)
# ===========================================================================


def testar_registros() -> None:
    secao("Registro nao e' linha")

    d = Dialeto(delimitador=";", colunas=3)
    # O endereco tem uma quebra de linha DENTRO das aspas. Dividir por "\n" daria
    # 4 pedacos e deslocaria a tabela inteira dali para a frente.
    texto = ('nome;endereco;uf\n'
             'Ana;"Rua A, 33\nApto 12";SC\n'
             'Bruno;Rua B;SC')
    registros = de_csv.dividir_registros(texto, d)
    checa_igual(len(registros), 3,
                "campo com quebra de linha continua sendo UM registro")
    checa_igual(texto.count("\n"), 3,
                "  (o texto tem mesmo 3 quebras -- 4 linhas fisicas)")
    checa_igual("\n".join(registros), texto,
                "juntar os registros com '\\n' reconstroi o texto exato")
    checa_igual(de_csv.campos_de(registros[1], d),
                ["Ana", "Rua A, 33\nApto 12", "SC"],
                "os campos do registro multi-linha saem inteiros")

    # Aspa DOBRADA e' o escape do CSV, e nao o fim do campo.
    dobrada = 'a;"ele disse ""oi"" e saiu";c'
    checa_igual(de_csv.dividir_registros(dobrada, d), [dobrada],
                'aspa dobrada nao fecha o campo')
    checa_igual(de_csv.campos_de(dobrada, d),
                ["a", 'ele disse "oi" e saiu', "c"],
                "aspa dobrada vira uma aspa so' no campo")

    # Registro malformado: aspas abertas e nunca fechadas. Perder a linha seria
    # pior do que mostra-la crua numa coluna.
    torto = 'a;"sem fechar;c'
    campos = de_csv.campos_de(torto, d)
    checa(campos and campos[0] == "a" or campos == [torto],
          "registro com aspas desbalanceadas nao derruba o analisador")

    secao("Montagem de registro")
    checa_igual(de_csv.montar_registro(["a", "b", "c"], d), "a;b;c",
                "campos simples nao ganham aspas")
    checa_igual(de_csv.montar_registro(["a", "x;y", "c"], d), 'a;"x;y";c',
                "campo com o delimitador ganha aspas")
    checa_igual(de_csv.montar_registro(["a", 'diz "oi"', "c"], d),
                'a;"diz ""oi""";c',
                "campo com aspas ganha aspas e as internas sao dobradas")
    checa_igual(de_csv.montar_registro(["a", "linha1\nlinha2", "c"], d),
                'a;"linha1\nlinha2";c',
                "campo com quebra de linha ganha aspas")


# ===========================================================================
# O modelo da tabela
# ===========================================================================


def testar_modelo() -> None:
    from PySide6.QtCore import Qt

    from textforge.visualizadores.tabela_csv import ModeloCsv

    secao("para_texto() sem edicao devolve a entrada IDENTICA")

    # Deliberadamente cheio de coisas que um `csv.writer` "arrumaria": aspas
    # desnecessarias em "Ana", espaco depois do delimitador, campo vazio no fim,
    # numero citado, e um campo multi-linha.
    entrada = ('nome;valor;obs\n'
               '"Ana";10,50; texto com espaco\n'
               'Bruno;"1500";"linha 1\nlinha 2"\n'
               'Carla;0;\n')
    dialeto = de_csv.detectar(entrada)
    modelo = ModeloCsv(entrada, dialeto)

    checa_igual(modelo.para_texto(), entrada,
                "*** TESTE CENTRAL: sem edicao, para_texto() == entrada ***")
    checa('"Ana"' in modelo.para_texto(),
          "  aspas desnecessarias em \"Ana\" sobrevivem")
    checa("; texto com espaco" in modelo.para_texto(),
          "  espaco depois do delimitador sobrevive")
    checa('"1500"' in modelo.para_texto(),
          "  numero citado continua citado")

    checa_igual(modelo.rowCount(), 3, "3 linhas de dados (cabecalho fora)")
    checa_igual(modelo.columnCount(), 3, "3 colunas")
    checa_igual(modelo.headerData(0, Qt.Orientation.Horizontal), "nome",
                "o cabecalho vira o titulo da coluna")
    checa_igual(modelo.data(modelo.index(1, 2)), "linha 1\nlinha 2",
                "a celula multi-linha aparece inteira")
    checa(not modelo.alterado, "sem edicao, o modelo nao esta' alterado")

    secao("Editar uma celula toca SO' aquela linha")
    modelo.setData(modelo.index(0, 1), "99,99")
    saida = modelo.para_texto()
    linhas_antes = entrada.split("\n")
    linhas_depois = saida.split("\n")
    checa_igual(linhas_depois[0], linhas_antes[0], "o cabecalho nao foi tocado")
    checa_igual(linhas_depois[1], 'Ana;99,99; texto com espaco',
                "a linha editada foi reescrita (e perdeu o quoting dela)")
    checa("linha 1\nlinha 2" in saida,
          "a linha NAO editada manteve o campo multi-linha")
    checa(saida.endswith("Carla;0;\n"),
          "a ultima linha e a quebra final continuam como estavam")
    checa(modelo.alterado, "depois de editar, o modelo esta' alterado")

    # Um segundo `para_texto()` tem de dar o mesmo: chamar duas vezes nao pode
    # acumular reescrita.
    checa_igual(modelo.para_texto(), saida, "para_texto() e' idempotente")

    secao("Requoting de celula com caractere especial")
    m2 = ModeloCsv("a;b\n1;2\n", de_csv.Dialeto(delimitador=";", colunas=2,
                                                tem_cabecalho=True))
    m2.setData(m2.index(0, 0), "x;y")
    checa('"x;y"' in m2.para_texto(), "celula com o delimitador vira citada")
    m2.setData(m2.index(0, 0), 'diz "oi"')
    checa('"diz ""oi"""' in m2.para_texto(),
          "celula com aspas vira citada com aspas dobradas")
    m2.setData(m2.index(0, 0), "uma\nduas")
    saida = m2.para_texto()
    checa('"uma\nduas"' in saida, "celula com quebra de linha vira citada")
    checa_igual(len(de_csv.dividir_registros(saida, m2.dialeto)),
                len(de_csv.dividir_registros("a;b\n1;2\n", m2.dialeto)),
                "a quebra dentro da celula nao criou um registro novo")

    secao("Gravacao confirmada nao reverte a edicao anterior")
    m3 = ModeloCsv("a;b\n1;2\n3;4\n", de_csv.Dialeto(delimitador=";", colunas=2,
                                                     tem_cabecalho=True))
    m3.setData(m3.index(0, 0), "X")
    m3.confirmar_gravacao()                       # e' o que o salvar faz
    checa(not m3.alterado, "confirmar_gravacao limpa a lista de sujos")
    m3.setData(m3.index(1, 0), "Y")
    checa_igual(m3.para_texto(), "a;b\nX;2\nY;4\n",
                "a edicao ja' gravada continua no texto (nao volta ao original)")

    secao("Linha com menos campos que o cabecalho")
    # A linha curta e' minoria: com so' tres linhas ela seria 33% do arquivo e o
    # detector recusaria o delimitador inteiro (a regra dos 80% de concordancia),
    # que e' o comportamento certo dele e nao o que se quer exercitar aqui.
    curta = "a;b;c\n1;2;3\n4;5;6\n7;8;9\n10;11;12\n9\n"
    m4 = ModeloCsv(curta, de_csv.detectar(curta))
    checa_igual(m4.rowCount(), 5, "a linha curta continua sendo uma linha")
    checa_igual(m4.data(m4.index(4, 2)), "",
                "coluna inexistente devolve vazio, nao IndexError")
    m4.setData(m4.index(4, 2), "novo")
    checa("9;;novo" in m4.para_texto(),
          "editar a coluna 3 de uma linha curta completa os campos que faltam")

    secao("Parse LAZY")
    muitas = "a;b;c\n" + "".join(f"{i};{i};{i}\n" for i in range(5000))
    m5 = ModeloCsv(muitas, de_csv.detectar(muitas))
    analisados_no_inicio = sum(1 for c in m5.campos if c is not None)
    # So' o cabecalho pode ter sido analisado na construcao.
    checa(analisados_no_inicio <= 1,
          f"5000 registros abrem com <=1 analisado (foram {analisados_no_inicio})")
    for linha in range(40):                       # a "tela" pinta 40 linhas
        m5.data(m5.index(linha, 0))
    analisados = sum(1 for c in m5.campos if c is not None)
    checa(analisados <= 45,
          f"pintar 40 linhas analisa <=45 registros (foram {analisados})")
    checa_igual(m5.para_texto(), muitas,
                "com 5000 registros, para_texto() sem edicao ainda e' identico")

    secao("Inserir e remover")
    m6 = ModeloCsv("a;b\n1;2\n3;4\n", de_csv.Dialeto(delimitador=";", colunas=2,
                                                     tem_cabecalho=True))
    m6.inserir_linha(0)
    checa_igual(m6.rowCount(), 3, "inserir linha aumenta a contagem")
    checa_igual(m6.para_texto(), "a;b\n1;2\n;\n3;4\n",
                "a linha nova entra DEPOIS da atual, vazia")
    m6.remover_linha(1)
    checa_igual(m6.para_texto(), "a;b\n1;2\n3;4\n",
                "remover a linha inserida devolve o texto original")

    m7 = ModeloCsv("a;b\n1;2\n", de_csv.Dialeto(delimitador=";", colunas=2,
                                                tem_cabecalho=True))
    m7.inserir_coluna(0)
    checa_igual(m7.columnCount(), 3, "inserir coluna aumenta a contagem")
    checa_igual(m7.para_texto(), "a;;b\n1;;2\n",
                "a coluna nova entra em TODAS as linhas, cabecalho incluso")
    m7.remover_coluna(1)
    checa_igual(m7.para_texto(), "a;b\n1;2\n",
                "remover a coluna inserida devolve o texto original")

    secao("Sem cabecalho")
    m8 = ModeloCsv("1;2\n3;4\n", de_csv.Dialeto(delimitador=";", colunas=2,
                                                tem_cabecalho=False))
    checa_igual(m8.rowCount(), 2, "sem cabecalho, a primeira linha e' dado")
    checa_igual(m8.headerData(0, Qt.Orientation.Horizontal), "Coluna 1",
                "sem cabecalho, as colunas sao numeradas")
    checa_igual(m8.data(m8.index(0, 0)), "1", "a primeira linha aparece na grade")


# ===========================================================================
# Integracao com a janela
# ===========================================================================


def testar_integracao() -> None:
    from textforge import configuracao, linguagens
    from textforge.documento import Documento
    from textforge.interface.janela import JanelaPrincipal
    from textforge.linguagens.registro import REGISTRO

    secao("Provedor de CSV")
    linguagens.carregar_embutidos()
    provedor = REGISTRO.por_caminho("dados.csv", "a;b\n1;2\n")
    checa_igual(provedor.nome if provedor else None, "CSV",
                ".csv resolve para o provedor CSV")
    checa_igual(provedor.visualizador_preferido(), "tabela",
                "o provedor de CSV pede o modo tabela")
    checa_igual(REGISTRO.por_caminho("dados.tsv", "").nome, "CSV",
                ".tsv tambem e' CSV")
    # O realce do CSV tem de compilar e citar papeis que o tema declara.
    from textforge.interface import tema as tema_mod
    tema = tema_mod.embutido("escuro")
    regras = provedor.regras(tema)
    checa(not regras.problemas_de_desempenho(),
          "o realce do CSV nao tem quantificador aninhado")
    faltando = [p for p in regras.papeis_usados() if not tema.tem_papel(p)]
    checa(not faltando, f"todo papel do CSV existe no tema (faltando: {faltando})")

    secao("Chave de ordenacao (coluna numerica nao ordena como texto)")
    br = de_csv.Dialeto(delimitador=";")
    en = de_csv.Dialeto(delimitador=",")
    checa_igual(de_csv.chave_de_ordenacao("10", br), 10.0, "'10' vira 10.0")
    checa(de_csv.chave_de_ordenacao("10", br)
          > de_csv.chave_de_ordenacao("9", br),
          "10 ordena DEPOIS de 9 (como texto viria antes)")
    checa_igual(de_csv.chave_de_ordenacao("32,90", br), 32.90,
                "num arquivo com ';' a virgula e' decimal")
    checa_igual(de_csv.chave_de_ordenacao("1.234,56", br), 1234.56,
                "os dois separadores: o ultimo e' o decimal (pt-BR)")
    checa_igual(de_csv.chave_de_ordenacao("1,234.56", en), 1234.56,
                "os dois separadores: o ultimo e' o decimal (en-US)")
    checa_igual(de_csv.chave_de_ordenacao("32.90", en), 32.90,
                "num arquivo com ',' o ponto e' decimal")
    checa_igual(de_csv.chave_de_ordenacao("Blumenau", br), "Blumenau",
                "campo de texto ordena como texto")
    checa_igual(de_csv.chave_de_ordenacao("1.2.3", br), "1.2.3",
                "'1.2.3' nao vira numero, e nao derruba nada")

    secao("Realce: o campo entre aspas atravessa linhas")
    from PySide6.QtGui import QTextDocument

    from textforge.realce.dados_do_bloco import DadosDoBloco
    from textforge.realce.pintor import Pintor

    qt_doc = QTextDocument()
    qt_doc.setPlainText('nome;endereco\n'
                        'Ana;"Rua A, 33\n'
                        'Apto 12"\n'
                        'Bruno;Rua B\n')
    Pintor(qt_doc, provedor, tema, configuracao.padrao())

    def pilha_em(linha: int):
        dados = qt_doc.findBlockByNumber(linha).userData()
        return dados.pilha_ao_terminar if isinstance(dados, DadosDoBloco) else ()

    checa_igual(pilha_em(0), ("raiz",), "linha sem aspas termina fora do campo")
    checa_igual(pilha_em(1), ("raiz", "campo"),
                "a aspa aberta na linha 2 deixa o realce DENTRO do campo")
    checa_igual(pilha_em(2), ("raiz",),
                "a aspa fechada na linha 3 devolve o realce a' raiz")
    checa_igual(pilha_em(3), ("raiz",),
                "e a linha 4 volta ao normal (nao ficou tudo pintado de string)")

    secao("Alternar Texto <-> Tabela na janela")
    cfg = configuracao.padrao()
    janela = JanelaPrincipal(cfg)
    entrada = 'nome;valor\n"Ana";10,50\nBruno;20,00\n'
    doc = Documento.novo(cfg)
    doc.definir_texto(entrada)
    doc.provedor = REGISTRO.por_nome("CSV")
    aba = janela.abas.adicionar(doc)

    checa_igual(aba.view_atual(), "texto", "a aba comeca em modo texto")
    checa(janela.abrir_modo_tabela(), "abrir_modo_tabela funciona num CSV")
    checa_igual(aba.view_atual(), "tabela", "a aba passou para a grade")
    checa(aba.tem_view("tabela"), "a view 'tabela' ficou registrada")

    # Ida e volta SEM editar: nem o texto nem a marca de modificado mudam.
    checa(janela.voltar_ao_modo_texto(), "voltar_ao_modo_texto funciona")
    checa_igual(aba.view_atual(), "texto", "a aba voltou para o texto")
    checa_igual(doc.texto(), entrada,
                "*** ida e volta SEM editar nao altera um caractere ***")
    checa(not doc.modificado,
          "ida e volta sem editar NAO marca o documento como modificado")
    checa(not aba.tem_view("tabela"),
          "a tabela e' descartada ao voltar (nao mostra conteudo velho depois)")

    # Agora editando: um unico passo de desfazer.
    janela.abrir_modo_tabela()
    vista = aba.view("tabela")
    vista.modelo.setData(vista.modelo.index(1, 1), "99,99")
    janela.voltar_ao_modo_texto()
    checa_igual(doc.texto(), 'nome;valor\n"Ana";10,50\nBruno;99,99\n',
                "a edicao na grade chegou ao texto, so' na linha editada")
    checa(doc.modificado, "editar na grade marca o documento como modificado")
    aba.editor.undo()
    checa_igual(doc.texto(), entrada,
                "UM Ctrl+Z desfaz a sessao inteira de edicao na tabela")

    secao("Recusa quando nao e' tabela")
    doc2 = Documento.novo(cfg)
    doc2.definir_texto("uma linha de prosa\noutra linha de prosa\n")
    aba2 = janela.abas.adicionar(doc2)
    # `abrir_modo_tabela` avisa por dialogo; em modo offscreen o `dialogos.avisar`
    # abriria um modal e penduraria a suite -- por isso e' o ANALISADOR que se
    # verifica aqui, que e' quem toma a decisao.
    checa(de_csv.detectar(doc2.texto()).colunas < 2,
          "prosa nao chega a duas colunas, entao o modo tabela e' recusado")
    checa_igual(aba2.view_atual(), "texto", "a aba de prosa continua em texto")

    janela.close()


def main() -> int:
    testar_deteccao()
    testar_registros()
    if TEM_QT:
        testar_modelo()
        testar_integracao()
    else:
        print("\nPULADO: PySide6 nao instalado — so' a analise foi verificada")
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
