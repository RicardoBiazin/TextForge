"""Processo auxiliar do `teste_instancia_unica.py`: envia um pedido e sai.

    python tests/ajudante_enviar.py <caminho> [linha]

Sai com 0 se a instancia existente confirmou o recebimento, 1 se nao.

Existe como processo separado de proposito. O envio bloqueia esperando a
confirmacao do outro lado, entao um teste no mesmo processo travaria: o servidor
so' responde quando o laco de eventos dele gira, e ele esta' parado esperando.
Mais importante, dois processos e' o cenario de verdade -- e' o que acontece ao
selecionar varios arquivos no Explorer e mandar abrir.

Nao cria QApplication, tambem de proposito: e' assim que o `app.py` faz. O envio
acontece ANTES de subir o Qt, para o processo redundante morrer barato.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from textforge import instancia_unica       # noqa: E402


def main() -> int:
    caminho = sys.argv[1] if len(sys.argv) > 1 else r"C:\sem-nome.txt"
    linha = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    pedido = {"arquivos": [{"caminho": caminho, "linha": linha, "coluna": 0}]}
    return 0 if instancia_unica.enviar_para_instancia_existente(pedido) else 1


if __name__ == "__main__":
    sys.exit(main())
