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

# Teto por suite. A mais lenta hoje (instancia unica, que dispara processos
# filhos) leva ~25 s; 180 s e' folga suficiente e ainda pega um travamento rapido.
LIMITE_POR_SUITE_S = 180

# (arquivo, descricao). A lista cresce a cada etapa do projeto.
SUITES = [
    # etapa 0 -- fundacao
    ("teste_configuracao.py", "config.json, pastas de dados, recentes"),
    ("teste_cli.py", "linha de comando, --line, caminhos recusados"),
    ("teste_tarefas.py", "pool, progresso, cancelamento, erro em worker"),
    ("teste_instancia_unica.py", "canal, servidor, entrega de pedido"),
    # etapa 1 -- fonte de texto e interface
    ("teste_fonte.py", "a mesma bateria nas 3 implementacoes de FonteDeTexto"),
    ("teste_acoes.py", "registro de comandos, atalhos, menus, palette"),
    ("teste_tema.py", "papeis, cores, merge do tema do usuario, contraste"),
    # etapa 2 -- editor
    ("teste_indentacao.py", "deteccao por arquivo, largura visual, conversoes"),
    ("teste_operacoes_linha.py", "requisito 22 (linhas) e 40 (caixa)"),
    ("teste_editor.py", "margem, linha atual, Tab em bloco, undo, marcadores"),
    ("teste_janela.py", "janela, menus, comandos ligados ao editor"),
    # etapa 3 -- documento, encoding, gravacao
    ("teste_codificacao.py", "BOM, cascata, binario, EOL, perdas"),
    ("teste_documento.py", "round-trip byte a byte, salvar atomico, req. 27"),
    ("teste_vigia.py", "alteracao externa: watcher + consulta periodica"),
    # etapa 4 -- abas, sessao, recuperacao
    ("teste_abas.py", "identidade por arquivo, asterisco, menu de contexto"),
    ("teste_sessao.py", "sessao, trava por rename, recuperacao com codec"),
    # etapa 5 -- realce de sintaxe
    ("teste_realce.py", "regras combinadas, pilha internada, multi-linha"),
    ("teste_linguagens.py", "registro, resolucao, provedores, estrutura"),
    # etapa 6 -- linguagens embutidas, painel Estrutura, pareamento
    ("teste_realce_embutido.py", "PHP em HTML, JS/CSS em tag, heredoc, pares"),
    ("teste_painel_estrutura.py", "arvore, filtro, navegacao, desempenho"),
    # etapa 7 -- pesquisa
    ("teste_busca.py", "criterio, offsets, substituir todos em 1 undo"),
    ("teste_busca_em_arquivos.py", "varredura, filtros, laco de link, cancelar"),
    # etapa 8 -- formatadores e seguranca
    ("teste_seguranca.py", "XXE, billion laughs, varredura estatica do fonte"),
    ("teste_formatadores.py", "XML/JSON/SQL/CSS/HTML/Python: fidelidade"),
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
        try:
            proc = subprocess.run([sys.executable, "-u", caminho],
                                  capture_output=True, text=True,
                                  errors="replace", env=ambiente, cwd=RAIZ,
                                  timeout=LIMITE_POR_SUITE_S)
        except subprocess.TimeoutExpired as expirou:
            # Um limite por suite e' obrigatorio num projeto de interface: um
            # QMessageBox modal aberto sem ninguem para clicar bloqueia PARA
            # SEMPRE, e sem o limite a rodada inteira ficaria pendurada em vez de
            # apontar a suite culpada.
            parcial = (expirou.stdout or "") + (expirou.stderr or "")
            print("%-28s  TRAVOU apos %ds  [PROBLEMA]  %s"
                  % (arquivo, LIMITE_POR_SUITE_S, descricao))
            quebradas.append((arquivo,
                              "A SUITE TRAVOU. Causa mais comum: um dialogo "
                              "modal (QMessageBox / QFileDialog) aberto em modo "
                              "offscreen, onde nao ha' ninguem para fecha-lo.\n"
                              + parcial))
            continue
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
