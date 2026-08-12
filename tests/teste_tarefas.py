"""Tarefas em background: progresso, cancelamento, erro capturado.

    .venv\\Scripts\\python.exe tests\\teste_tarefas.py

O que este teste realmente protege: uma excecao dentro de um QRunnable NAO sobe
para o excepthook do processo -- o Qt aborta o programa sem mensagem. Se o
`except BaseException` do `Tarefa.run` for removido algum dia, o teste 4 quebra.
"""

from __future__ import annotations

import sys
import time

from ajudantes import checa, checa_igual, preparar_qt, pular, resumir, secao

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtCore import QEventLoop, QTimer      # noqa: E402

from textforge import tarefas                       # noqa: E402


def esperar(tarefa: tarefas.Tarefa, limite_ms: int = 5000) -> bool:
    """Roda o laco de eventos ate' a tarefa terminar. False se estourou o tempo.

    Sem laco de eventos os sinais do worker nunca seriam entregues -- eles ficam
    na fila da thread da interface, que num teste sem `exec()` esta' parada.
    """
    laco = QEventLoop()
    estourou = {"sim": True}
    tarefa.sinais.terminou.connect(lambda: (estourou.update(sim=False),
                                            laco.quit()))
    QTimer.singleShot(limite_ms, laco.quit)
    laco.exec()
    return not estourou["sim"]


# ---------------------------------------------------------------------------
secao("1 - tarefa que termina bem")

def somar(t: tarefas.Tarefa, quantos: int) -> int:
    total = 0
    for i in range(quantos):
        t.checar_cancelamento()
        total += i
        t.progresso(i + 1, quantos)
    return total


recebido: dict = {}
t = tarefas.Tarefa("somar", somar, 100)
t.sinais.concluido.connect(lambda v: recebido.update(valor=v))
t.sinais.erro.connect(lambda texto: recebido.update(erro=texto))
tarefas.rodar(t)
checa(esperar(t), "a tarefa terminou dentro do tempo")
checa_igual(recebido.get("valor"), 4950, "o valor de retorno chega por sinal")
checa("erro" not in recebido, "nenhum sinal de erro numa tarefa que deu certo")

# ---------------------------------------------------------------------------
secao("2 - progresso e' limitado na origem")

# Emitir um sinal por iteracao custa mais que o trabalho. A tarefa limita a
# 10 Hz, entao 3000 chamadas em ~0,3 s tem de virar um punhado de sinais.
contagem = {"n": 0}


def muitas_chamadas(t: tarefas.Tarefa) -> int:
    for i in range(3000):
        t.progresso(i, 3000)
        time.sleep(0.0001)
    return 0


t = tarefas.Tarefa("progresso", muitas_chamadas)
t.sinais.progresso.connect(lambda f, tot: contagem.update(n=contagem["n"] + 1))
tarefas.rodar(t)
checa(esperar(t), "a tarefa de progresso terminou")
checa(contagem["n"] < 60,
      f"3000 chamadas de progresso viraram {contagem['n']} sinais (limitado a 10 Hz)")
checa(contagem["n"] > 0, "mas ao menos um sinal de progresso foi emitido")

# `forcar=True` tem de furar o limite: o 100% final nao pode ser engolido.
forcados = {"n": 0}
t = tarefas.Tarefa("forcar", lambda tt: [tt.progresso(i, 3, forcar=True)
                                         for i in range(3)])
t.sinais.progresso.connect(lambda f, tot: forcados.update(n=forcados["n"] + 1))
tarefas.rodar(t)
esperar(t)
checa_igual(forcados["n"], 3, "progresso(forcar=True) nao e' limitado")

# ---------------------------------------------------------------------------
secao("3 - cancelamento e' cooperativo")

marcas = {"cancelado": False, "concluido": False, "voltas": 0}


def longa(t: tarefas.Tarefa) -> str:
    for _ in range(100_000):
        t.checar_cancelamento()
        marcas["voltas"] += 1
        time.sleep(0.0002)
    return "terminei"


t = tarefas.Tarefa("longa", longa)
t.sinais.cancelado.connect(lambda: marcas.update(cancelado=True))
t.sinais.concluido.connect(lambda v: marcas.update(concluido=True))
tarefas.rodar(t)
QTimer.singleShot(150, t.cancelar)
checa(esperar(t), "a tarefa cancelada terminou (nao ficou pendurada)")
checa(marcas["cancelado"], "emitiu o sinal 'cancelado'")
checa(not marcas["concluido"], "NAO emitiu 'concluido' depois de cancelar")
checa(marcas["voltas"] < 100_000, "parou antes de completar o trabalho")
checa(t.cancelada(), "cancelada() reflete o estado")

# ---------------------------------------------------------------------------
secao("4 - erro no worker vira sinal, nao aborta o processo")

capturado: dict = {}


def estourar(t: tarefas.Tarefa) -> None:
    raise ValueError("falha proposital do teste")


t = tarefas.Tarefa("estourar", estourar)
t.sinais.erro.connect(lambda texto: capturado.update(texto=texto))
t.sinais.concluido.connect(lambda v: capturado.update(concluido=True))
tarefas.rodar(t)
checa(esperar(t), "a tarefa que estourou terminou normalmente")
checa("texto" in capturado, "a excecao chegou pelo sinal 'erro'")
checa("falha proposital do teste" in capturado.get("texto", ""),
      "a mensagem original esta' no traceback enviado")
checa("ValueError" in capturado.get("texto", ""),
      "o tipo da excecao esta' no traceback enviado")
checa("concluido" not in capturado, "nao emitiu 'concluido' apos o erro")

# ---------------------------------------------------------------------------
secao("5 - os dois pools sao separados")

checa(tarefas.POOL_DISCO is not tarefas.POOL_CPU,
      "existem dois pools distintos")
checa_igual(tarefas.POOL_DISCO.maxThreadCount(), 1,
            "o pool de disco tem UMA thread (somar threads num disco nao ajuda)")
checa(tarefas.POOL_CPU.maxThreadCount() >= 2,
      "o pool de CPU tem pelo menos duas threads")

marca_disco = {"ok": False}
t = tarefas.Tarefa("no disco", lambda tt: marca_disco.update(ok=True))
tarefas.rodar(t, disco=True)
checa(esperar(t) and marca_disco["ok"], "rodar(disco=True) executa a tarefa")

checa(tarefas.esperar_tudo(5000), "esperar_tudo() esvazia os dois pools")

sys.exit(resumir())
