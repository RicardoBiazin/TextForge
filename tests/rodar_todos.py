"""Roda todas as suites e resume o resultado.

    .venv\\Scripts\\python.exe tests\\rodar_todos.py

Cada suite imprime uma linha por verificacao. Veja tests/README.md para o que
cada uma cobre, quanto ocupa em %TEMP% e quais sao os limites conhecidos.

Nao usa pytest de proposito -- o padrao dos outros projetos desta maquina e' o
runner caseiro, e ele tem a vantagem de rodar cada suite num processo separado:
um travamento de Qt numa suite nao leva as outras.
"""

from __future__ import annotations

import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

# (arquivo, descricao). A lista cresce a cada etapa do projeto.
SUITES = [
    ("teste_configuracao.py", "config.json, pastas de dados, recentes"),
    ("teste_cli.py", "linha de comando, --line, caminhos recusados"),
    ("teste_tarefas.py", "pool, progresso, cancelamento, erro em worker"),
    ("teste_instancia_unica.py", "canal, servidor, entrega de pedido"),
]


def main() -> int:
    total_ok = total_falhas = 0
    quebradas: list[tuple[str, str]] = []

    ambiente = dict(os.environ)
    # A suite tambem faz isto por conta propria, mas garantir aqui evita que uma
    # suite nova esqueca e abra janelas de verdade no meio da rodada.
    ambiente.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Sem isto, print de caractere acentuado quebra no console do Windows com
    # UnicodeEncodeError e a suite "falha" por um motivo que nao e' o dela.
    ambiente["PYTHONIOENCODING"] = "utf-8"
    ambiente["PYTHONPATH"] = RAIZ + os.pathsep + ambiente.get("PYTHONPATH", "")

    for arquivo, descricao in SUITES:
        caminho = os.path.join(AQUI, arquivo)
        if not os.path.isfile(caminho):
            print("%-28s AUSENTE  %s" % (arquivo, descricao))
            quebradas.append((arquivo, "arquivo de teste nao encontrado"))
            continue
        proc = subprocess.run([sys.executable, "-u", caminho],
                              capture_output=True, text=True,
                              errors="replace", env=ambiente, cwd=RAIZ)
        saida = proc.stdout + proc.stderr
        ok = saida.count("\n  OK   ")
        falhas = saida.count("\n  FALHA")
        total_ok += ok
        total_falhas += falhas
        if "PULADO:" in saida and ok == 0 and falhas == 0:
            estado = "pulado"
        else:
            estado = "ok" if proc.returncode == 0 else "PROBLEMA"
        print("%-28s %3d ok  %d falhas  [%-8s]  %s"
              % (arquivo, ok, falhas, estado, descricao))
        if proc.returncode != 0:
            quebradas.append((arquivo, saida))

    print("-" * 78)
    print("TOTAL: %d verificacoes ok, %d falhas" % (total_ok, total_falhas))
    for arquivo, saida in quebradas:
        print("\n===== saida de %s =====" % arquivo)
        print(saida[-4000:])
    return 1 if (total_falhas or quebradas) else 0


if __name__ == "__main__":
    sys.exit(main())
