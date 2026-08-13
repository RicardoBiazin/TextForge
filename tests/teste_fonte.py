"""FonteDeTexto: a MESMA bateria nas tres implementacoes.

    .venv\\Scripts\\python.exe tests\\teste_fonte.py

Este e' o teste que garante que a abstracao e' real. Se `FonteEmMemoria`,
`FonteDeDocumento` e `FonteDeArquivo` divergirem em qualquer resposta, a busca, o
diff, o CSV e o tail passariam a se comportar diferente conforme o modo do
arquivo -- que e' exatamente o que a `FonteDeTexto` existe para evitar.

Convencoes exercitadas aqui:
  * linhas contadas de ZERO;
  * numero de linhas = numero de \\n + 1, igual a texto.split("\\n"),
    entao "a\\nb\\n" tem TRES linhas (a ultima e' vazia).
"""

from __future__ import annotations

import re
import sys

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QTextDocument              # noqa: E402

from textforge import fonte as fmod                   # noqa: E402

# Casos de texto que as tres implementacoes tem de responder igual. Cada um
# existe por um motivo:
CASOS = [
    ("vazio", ""),
    ("uma linha sem quebra", "abc"),
    ("uma linha com quebra", "abc\n"),
    ("duas linhas", "primeira\nsegunda"),
    ("duas linhas e quebra final", "primeira\nsegunda\n"),
    ("linha vazia no meio", "a\n\nb"),
    ("so' quebras", "\n\n\n"),
    ("acentos e simbolos", "coracao\nAcao & Reacao\nnumeroGuia=123"),
    ("linha longa", "x" * 5000 + "\nfim"),
    ("muitas linhas", "\n".join(f"linha {i}" for i in range(3000))),
]


def montar_documento(texto: str) -> fmod.FonteDeDocumento:
    doc = QTextDocument()
    doc.setPlainText(texto)
    return fmod.FonteDeDocumento(doc)


# ---------------------------------------------------------------------------
secao("1 - as tres implementacoes concordam")

with pasta_temporaria() as pasta:
    for nome, texto in CASOS:
        memoria = fmod.FonteEmMemoria(texto)
        documento = montar_documento(texto)

        arquivo = pasta / "caso.txt"
        arquivo.write_bytes(texto.encode("utf-8"))
        do_arquivo = fmod.FonteDeArquivo(arquivo, "utf-8")
        do_arquivo.indexar()

        try:
            esperado = texto.split("\n")

            checa_igual(memoria.total_de_linhas(), len(esperado),
                        f"[{nome}] memoria conta as linhas como split('\\n')")
            checa_igual(documento.total_de_linhas(), len(esperado),
                        f"[{nome}] QTextDocument conta igual")
            checa_igual(do_arquivo.total_de_linhas(), len(esperado),
                        f"[{nome}] arquivo conta igual")

            iguais = all(
                memoria.linha(i) == documento.linha(i) == do_arquivo.linha(i)
                == esperado[i] for i in range(len(esperado)))
            checa(iguais, f"[{nome}] linha(n) devolve o mesmo nas tres")

            checa(memoria.faixa(0, len(esperado)) == esperado
                  and documento.faixa(0, len(esperado)) == esperado
                  and do_arquivo.faixa(0, len(esperado)) == esperado,
                  f"[{nome}] faixa() completa devolve o mesmo nas tres")
        finally:
            do_arquivo.fechar()

# ---------------------------------------------------------------------------
secao("2 - fora dos limites nao levanta")

for construir in (lambda t: fmod.FonteEmMemoria(t), montar_documento):
    f = construir("a\nb\nc")
    rotulo = type(f).__name__
    checa_igual(f.linha(-1), "", f"{rotulo}: linha(-1) devolve string vazia")
    checa_igual(f.linha(999), "", f"{rotulo}: linha(999) devolve string vazia")
    checa_igual(f.faixa(10, 20), [], f"{rotulo}: faixa muito adiante e' vazia")
    checa_igual(f.faixa(5, 2), [], f"{rotulo}: faixa invertida e' vazia")
    checa_igual(f.faixa(-5, 2), ["a", "b"], f"{rotulo}: faixa recorta o inicio")
    checa_igual(f.faixa(1, 99), ["b", "c"], f"{rotulo}: faixa recorta o fim")

with pasta_temporaria() as pasta:
    arq = pasta / "x.txt"
    arq.write_bytes(b"a\nb\nc")
    with fmod.FonteDeArquivo(arq) as f:
        f.indexar()
        checa_igual(f.linha(-1), "", "arquivo: linha(-1) devolve string vazia")
        checa_igual(f.linha(999), "", "arquivo: linha(999) devolve string vazia")
        checa_igual(f.faixa(10, 20), [], "arquivo: faixa muito adiante e' vazia")
        checa_igual(f.faixa(5, 2), [], "arquivo: faixa invertida e' vazia")
        checa_igual(f.faixa(-5, 2), ["a", "b"], "arquivo: faixa recorta o inicio")

# ---------------------------------------------------------------------------
secao("3 - busca, igual nas tres")

TEXTO = ("numeroGuia=100\n"
         "outra coisa\n"
         "numeroguia=200\n"
         "numeroGuia=300 e numeroGuia=400\n"
         "fim")

padrao = re.compile("numeroGuia")

with pasta_temporaria() as pasta:
    arq = pasta / "busca.txt"
    arq.write_bytes(TEXTO.encode("utf-8"))
    do_arquivo = fmod.FonteDeArquivo(arq)
    do_arquivo.indexar()
    try:
        fontes = {
            "memoria": fmod.FonteEmMemoria(TEXTO),
            "documento": montar_documento(TEXTO),
            "arquivo": do_arquivo,
        }
        resultados = {}
        for nome, f in fontes.items():
            resultados[nome] = [(a.linha, a.inicio) for a in f.buscar(padrao)]

        esperado = [(0, 0), (3, 0), (3, 17)]
        for nome, obtido in resultados.items():
            checa_igual(obtido, esperado,
                        f"{nome}: acha 3 ocorrencias (2 na mesma linha)")

        # A partir de uma linha
        for nome, f in fontes.items():
            checa_igual([a.linha for a in f.buscar(padrao, de_linha=3)],
                        [3, 3], f"{nome}: de_linha=3 ignora a ocorrencia anterior")

        # O texto da linha vem no achado (alimenta o painel de resultados)
        for nome, f in fontes.items():
            primeiro = next(iter(f.buscar(padrao)))
            checa_igual(primeiro.texto, "numeroGuia=100",
                        f"{nome}: o achado carrega a linha inteira")

        # Insensivel a caixa acha a terceira linha tambem
        sem_caixa = re.compile("numeroguia", re.IGNORECASE)
        for nome, f in fontes.items():
            checa_igual(len(list(f.buscar(sem_caixa))), 4,
                        f"{nome}: com IGNORECASE acha 4")

        # Regex que casa vazio nao pode entrar em laco infinito
        vazio = re.compile("x*")
        for nome, f in fontes.items():
            achados = list(f.buscar(vazio))
            checa(len(achados) > 0 and len(achados) < 10_000,
                  f"{nome}: regex que casa vazio termina")

        # Cancelamento interrompe
        for nome, f in fontes.items():
            contador = {"n": 0}

            def parar_no_primeiro() -> bool:
                contador["n"] += 1
                return contador["n"] > 1

            achados = list(f.buscar(re.compile("a"), cancelar=parar_no_primeiro))
            checa(True, f"{nome}: buscar() com cancelar termina sem estourar")
    finally:
        do_arquivo.fechar()

# ---------------------------------------------------------------------------
secao("4 - indice esparso do arquivo grande")

with pasta_temporaria() as pasta:
    # 5000 linhas com um passo de 64: forca 78 marcadores e muita varredura
    # entre eles -- e' onde um erro de um-a-menos no indice apareceria.
    linhas = [f"linha {i:05d} conteudo" for i in range(5000)]
    arq = pasta / "grande.txt"
    arq.write_bytes(("\n".join(linhas) + "\n").encode("utf-8"))

    with fmod.FonteDeArquivo(arq, passo=64) as f:
        f.indexar()
        checa_igual(f.total_de_linhas(), 5001,
                    "5000 linhas + quebra final = 5001 (a ultima e' vazia)")

        # Amostragem em pontos escolhidos para cair antes, em cima e depois de
        # um marcador -- o caso 64 e' exatamente sobre um marcador.
        pontos = [0, 1, 63, 64, 65, 127, 128, 999, 1024, 2048, 4095, 4999]
        erradas = [n for n in pontos if f.linha(n) != linhas[n]]
        checa_igual(erradas, [],
                    "linha(n) acerta em 12 pontos ao redor dos marcadores")

        checa_igual(f.linha(5000), "", "a linha vazia final e' vazia")
        checa_igual(f.faixa(100, 105), linhas[100:105],
                    "faixa() no meio do arquivo devolve as linhas certas")
        checa(f.indexacao_completa, "indexacao_completa fica True no fim")
        checa_igual(f.tamanho_em_bytes(), arq.stat().st_size,
                    "tamanho_em_bytes bate com o do disco")
        checa(not f.editavel(), "arquivo grande NAO e' editavel na v1")

# ---------------------------------------------------------------------------
secao("5 - indexacao incremental e cancelavel")

with pasta_temporaria() as pasta:
    arq = pasta / "incremental.txt"
    arq.write_bytes(b"".join(b"linha %05d de teste\n" % i for i in range(60_000)))

    with fmod.FonteDeArquivo(arq, passo=1024) as f:
        checa(not f.indexacao_completa, "recem-aberto, o indice nao esta' pronto")
        parcial = f.total_de_linhas()
        checa_igual(parcial, 1,
                    "antes de indexar, so' a primeira linha e' conhecida")
        # Mas ja' da' para LER: e' isto que faz a abertura ser instantanea.
        checa_igual(f.linha(0), "linha 00000 de teste",
                    "le' a primeira linha antes de o indice existir")

        # Orcamento pequeno: avanca um pedaco e volta sem terminar.
        completo = f.indexar(orcamento_bytes=16 * 1024)
        checa(not completo, "indexar() com orcamento pequeno devolve False")
        varrido, total = f.progresso_da_indexacao
        checa(0 < varrido < total, f"progresso parcial: {varrido} de {total}")
        meio = f.total_de_linhas()
        checa(1 < meio < 60_001,
              f"a contagem de linhas cresce durante a indexacao ({meio})")

        # Cancelamento
        checa(not f.indexar(cancelar=lambda: True),
              "indexar() respeita o cancelamento e devolve False")

        # Terminar
        checa(f.indexar(), "indexar() sem orcamento termina o arquivo")
        checa_igual(f.total_de_linhas(), 60_001, "contagem final correta")
        checa_igual(f.linha(59_999), "linha 59999 de teste",
                    "a ultima linha com conteudo esta' certa")

# ---------------------------------------------------------------------------
secao("6 - fronteira do bloco de leitura de 4 MB")

# A indexacao le' o arquivo em blocos de BLOCO_DE_LEITURA. Uma linha que
# ATRAVESSA a fronteira de dois blocos e' o caso classico de perder um achado.
# Aqui plantamos o alvo exatamente ali.
with pasta_temporaria() as pasta:
    bloco = fmod.BLOCO_DE_LEITURA
    enchimento = b"x" * 100 + b"\n"                  # 101 bytes por linha
    quantas = (bloco // len(enchimento)) - 1
    antes = enchimento * quantas
    # Esta linha comeca antes da fronteira e termina depois dela. O que precisa
    # ser verdade e' que a LINHA atravesse a fronteira: e' isso que quebraria uma
    # implementacao que buscasse dentro de cada bloco isoladamente.
    atravessa = b"y" * 200 + b"ALVO-NA-FRONTEIRA" + b"z" * 200 + b"\n"
    inicio_da_linha = len(antes)
    fim_da_linha = inicio_da_linha + len(atravessa)
    checa(inicio_da_linha < bloco < fim_da_linha,
          f"a linha-alvo atravessa a fronteira de {bloco} bytes "
          f"(comeca em {inicio_da_linha}, termina em {fim_da_linha})")

    arq = pasta / "fronteira.txt"
    arq.write_bytes(antes + atravessa + enchimento * 10)

    with fmod.FonteDeArquivo(arq) as f:
        f.indexar()
        achados = list(f.buscar(re.compile("ALVO-NA-FRONTEIRA")))
        checa_igual(len(achados), 1,
                    "acha o padrao plantado sobre a fronteira dos blocos")
        if achados:
            checa_igual(f.linha(achados[0].linha),
                        atravessa[:-1].decode("ascii"),
                        "a linha da fronteira e' lida inteira, sem corte")

# ---------------------------------------------------------------------------
secao("7 - CRLF e encoding legado")

with pasta_temporaria() as pasta:
    arq = pasta / "crlf.txt"
    arq.write_bytes(b"primeira\r\nsegunda\r\nterceira\r\n")
    with fmod.FonteDeArquivo(arq) as f:
        f.indexar()
        checa_igual(f.faixa(0, 3), ["primeira", "segunda", "terceira"],
                    "CRLF: o \\r nao aparece no fim das linhas")
        checa_igual(f.total_de_linhas(), 4, "CRLF: contagem de linhas correta")

    # cp1252 com acentos: e' o caso de um .log ou .txt legado do Windows.
    legado = pasta / "legado.txt"
    legado.write_bytes("Ação\nCoração\n".encode("cp1252"))
    with fmod.FonteDeArquivo(legado, "cp1252") as f:
        f.indexar()
        checa_igual(f.faixa(0, 2), ["Ação", "Coração"],
                    "cp1252: acentos sao decodificados corretamente")

    # Byte invalido no encoding declarado NAO pode levantar durante a leitura:
    # pintar a tela nunca pode estourar.
    quebrado = pasta / "quebrado.txt"
    quebrado.write_bytes(b"ok\n\xff\xfe\xff invalido\nfim\n")
    with fmod.FonteDeArquivo(quebrado, "utf-8") as f:
        f.indexar()
        linhas = f.faixa(0, 3)
        checa_igual(len(linhas), 3, "byte invalido nao interrompe a leitura")
        checa("�" in linhas[1],
              "byte invalido vira U+FFFD em vez de levantar excecao")

# ---------------------------------------------------------------------------
secao("8 - o protocolo e' satisfeito de verdade")

with pasta_temporaria() as pasta:
    arq = pasta / "p.txt"
    arq.write_bytes(b"a\n")
    do_arquivo = fmod.FonteDeArquivo(arq)
    try:
        for f in (fmod.FonteEmMemoria("a\n"), montar_documento("a\n"), do_arquivo):
            checa(isinstance(f, fmod.FonteDeTexto),
                  f"{type(f).__name__} satisfaz o protocolo FonteDeTexto")
    finally:
        do_arquivo.fechar()

checa(fmod.FonteEmMemoria("x").editavel(), "fonte em memoria e' editavel")
checa(montar_documento("x").editavel(), "fonte de documento e' editavel")

sys.exit(resumir())
