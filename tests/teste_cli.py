"""Linha de comando: --line, multiplos arquivos, caminhos recusados.

    .venv\\Scripts\\python.exe tests\\teste_cli.py

A parte que importa aqui e' a recusa: um caminho vindo do Explorer ou da linha de
comando e' entrada nao confiavel, e abrir um dispositivo como se fosse arquivo
pendura o processo.
"""

from __future__ import annotations

import pathlib
import sys

from ajudantes import checa, checa_igual, pasta_temporaria, resumir, secao

from textforge import cli

# ---------------------------------------------------------------------------
secao("1 - o basico")

a = cli.analisar([])
checa_igual(a.alvos, [], "sem argumentos, nenhum alvo")
checa_igual(a.nova_janela, False, "--nova-janela desligado por padrao")
checa_igual(a.autoverificacao, False, "--autoverificacao desligado por padrao")

a = cli.analisar(["--nova-janela"])
checa_igual(a.nova_janela, True, "--nova-janela e' reconhecido")

# ---------------------------------------------------------------------------
secao("2 - arquivos e --line")

with pasta_temporaria() as pasta:
    um = pasta / "config.xml"
    um.write_text("<a/>", encoding="utf-8")
    dois = pasta / "com espaco.txt"
    dois.write_text("oi", encoding="utf-8")

    a = cli.analisar([str(um)])
    checa_igual(len(a.alvos), 1, "um arquivo existente e' aceito")
    checa_igual(a.alvos[0].linha, 0, "sem --line, linha 0 (nao posicionar)")

    a = cli.analisar([str(um), "--line", "850"])
    checa_igual(a.alvos[0].linha, 850, "--line 850 chega no alvo")

    a = cli.analisar([str(um), "-l", "12", "-c", "5"])
    checa(a.alvos[0].linha == 12 and a.alvos[0].coluna == 5,
          "--line e --col juntos")

    a = cli.analisar([str(um), str(dois), "--line", "42"])
    checa_igual(len(a.alvos), 2, "dois arquivos, dois alvos")
    checa_igual(a.alvos[0].linha, 42, "--line vale para o primeiro arquivo")
    checa_igual(a.alvos[1].linha, 0,
                "--line NAO vale para os demais (nao faria sentido)")

    a = cli.analisar([str(um), "--line", "-5"])
    checa_igual(a.alvos[0].linha, 0, "linha negativa e' saneada para 0")

    # Caminho relativo tem de virar absoluto, senao a comparacao de "esta aba
    # ja' tem este arquivo?" falharia dependendo da pasta atual.
    a = cli.analisar(["."])
    checa_igual(len(a.alvos), 0, "uma PASTA e' recusada, nao aberta como arquivo")

    a = cli.analisar([str(pasta / ".." / pasta.name / "config.xml")])
    checa(len(a.alvos) == 1 and ".." not in str(a.alvos[0].caminho),
          "caminho com '..' e' resolvido para absoluto")

# ---------------------------------------------------------------------------
secao("3 - arquivo inexistente e' aceito (o usuario quer criar)")

with pasta_temporaria() as pasta:
    novo = pasta / "ainda-nao-existe.txt"
    a = cli.analisar([str(novo)])
    checa_igual(len(a.alvos), 1, "caminho inexistente e' aceito para criacao")
    checa_igual(a.recusados, [], "e nao aparece na lista de recusados")

# ---------------------------------------------------------------------------
secao("4 - recusas de seguranca")

RECUSAR = [
    ("CON", "dispositivo CON"),
    ("con", "dispositivo con em minusculas"),
    ("NUL", "dispositivo NUL"),
    ("COM1", "porta serial COM1"),
    ("LPT1", "porta paralela LPT1"),
    ("PRN", "dispositivo PRN"),
    (r"C:\pasta\aux.txt", "dispositivo AUX mesmo com extensao e pasta"),
    ("", "caminho vazio"),
    ("   ", "caminho so' com espacos"),
]
for bruto, descricao in RECUSAR:
    a = cli.analisar([bruto])
    checa(len(a.alvos) == 0 and len(a.recusados) == 1,
          f"recusa {descricao}")

a = cli.analisar(["CON", "NUL"])
checa_igual(len(a.recusados), 2, "recusa varios de uma vez")
checa(all(motivo for _, motivo in a.recusados),
      "cada recusa vem com um motivo escrito (vai para o log)")

with pasta_temporaria() as pasta:
    bom = pasta / "ok.txt"
    bom.write_text("x", encoding="utf-8")
    a = cli.analisar(["CON", str(bom)])
    checa(len(a.alvos) == 1 and len(a.recusados) == 1,
          "um caminho ruim nao derruba os bons da mesma linha")

# ---------------------------------------------------------------------------
secao("5 - forma serializavel para a outra instancia")

with pasta_temporaria() as pasta:
    arq = pasta / "x.log"
    arq.write_text("linha", encoding="utf-8")
    a = cli.analisar([str(arq), "--line", "7"])
    pedido = a.como_pedido()
    checa("arquivos" in pedido, "como_pedido() tem a chave 'arquivos'")
    checa_igual(pedido["arquivos"][0]["linha"], 7, "a linha viaja no pedido")
    checa(isinstance(pedido["arquivos"][0]["caminho"], str),
          "o caminho viaja como str (Path nao e' serializavel em JSON)")

    import json
    json.dumps(pedido)      # estoura se algo nao for serializavel
    checa(True, "o pedido inteiro passa por json.dumps sem erro")

sys.exit(resumir())
