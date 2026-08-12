"""Operacoes longas fora da thread de interface (requisito 34).

REGRA DE OURO deste projeto, valida desde a primeira linha de codigo:

    So' a thread da interface toca QTextDocument, QWidget e QSyntaxHighlighter.

Um worker recebe dados imutaveis, devolve dados imutaveis por sinal, e nunca
guarda referencia para widget. Violar isso funciona por meses e depois quebra de
formas impossiveis de reproduzir -- e o preco de consertar cresce a cada modulo
novo que copia o padrao errado.

Vao para background: indexar arquivo grande, acompanhar log, pesquisar em pasta,
calcular hash, comparar arquivos e formatar arquivo grande.

Dois pools de proposito:

  POOL_DISCO  I/O de arquivo. Concorrencia baixa -- somar threads num disco nao
              o deixa mais rapido, so' aumenta o tempo de resposta de cada uma.
  POOL_CPU    parse, formatacao, diff, hash.

Se os dois compartilhassem o mesmo pool, indexar um log de 1 GB poderia ocupar
todos os slots e a formatacao de um JSON pequeno ficaria na fila atras dele.
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from textforge import log_interno

log = log_interno.obter(__name__)

# Intervalo minimo entre dois sinais de progresso da MESMA tarefa. Emitir
# progresso por byte lido custa mais que ler o arquivo: cada sinal atravessa a
# fila de eventos da interface. 10 Hz e' imperceptivel para o usuario e
# praticamente gratuito.
INTERVALO_DE_PROGRESSO_S = 0.1


class Cancelado(Exception):
    """Levantada de dentro do trabalho quando o usuario cancela."""


class SinaisTarefa(QObject):
    """Os sinais de uma tarefa.

    QRunnable nao e' QObject e nao pode ter sinais, por isso este objeto
    separado -- e' o padrao recomendado pela documentacao do Qt.
    """

    # (feito, total). total <= 0 quando o total ainda nao e' conhecido.
    progresso = Signal(int, int)
    mensagem = Signal(str)
    concluido = Signal(object)      # o valor de retorno do trabalho
    erro = Signal(str)              # traceback formatado
    cancelado = Signal()
    terminou = Signal()             # sempre emitido, em qualquer desfecho


class Tarefa(QRunnable):
    """Envolve uma funcao para rodar num pool, com progresso e cancelamento.

    A funcao recebe a propria Tarefa como primeiro argumento, e usa
    `t.checar_cancelamento()` nos pontos onde faz sentido parar, e
    `t.progresso(feito, total)` para reportar. Assim o cancelamento e' cooperativo
    -- nao existe forma segura de matar uma thread no meio de uma escrita.
    """

    def __init__(self, nome: str, trabalho: Callable[..., Any],
                 *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.nome = nome
        self.sinais = SinaisTarefa()
        self._trabalho = trabalho
        self._args = args
        self._kwargs = kwargs
        self._cancelar = threading.Event()
        self._ultimo_progresso = 0.0
        self.setAutoDelete(True)

    # -- API para quem chama (thread da interface) --------------------------

    def cancelar(self) -> None:
        self._cancelar.set()

    def cancelada(self) -> bool:
        return self._cancelar.is_set()

    # -- API para o trabalho (thread de fundo) ------------------------------

    def checar_cancelamento(self) -> None:
        if self._cancelar.is_set():
            raise Cancelado

    def progresso(self, feito: int, total: int = -1, *, forcar: bool = False) -> None:
        agora = time.monotonic()
        if not forcar and agora - self._ultimo_progresso < INTERVALO_DE_PROGRESSO_S:
            return
        self._ultimo_progresso = agora
        self.sinais.progresso.emit(feito, total)

    def dizer(self, texto: str) -> None:
        self.sinais.mensagem.emit(texto)

    # -- QRunnable ---------------------------------------------------------

    def run(self) -> None:                                  # noqa: D102
        try:
            resultado = self._trabalho(self, *self._args, **self._kwargs)
        except Cancelado:
            log.info("tarefa cancelada: %s", self.nome)
            self.sinais.cancelado.emit()
        except BaseException:       # noqa: BLE001 - nada pode escapar do pool
            # Excecao num QRunnable nao sobe para o excepthook do processo: se
            # nao capturarmos aqui, o Qt aborta o programa sem mensagem.
            texto = traceback.format_exc()
            log.error("tarefa falhou: %s\n%s", self.nome, texto)
            self.sinais.erro.emit(texto)
        else:
            self.sinais.concluido.emit(resultado)
        finally:
            self.sinais.terminou.emit()


def _pool(nome: str, maximo: int) -> QThreadPool:
    pool = QThreadPool()
    pool.setMaxThreadCount(maximo)
    pool.setObjectName(nome)
    return pool


# Um so' worker de disco por vez, e um limite baixo de CPU: este e' um editor,
# nao um processador em lote -- a prioridade e' a interface continuar respondendo.
POOL_DISCO = _pool("textforge-disco", 1)
POOL_CPU = _pool("textforge-cpu", max(2, min(4, (QThreadPool.globalInstance()
                                                 .maxThreadCount() or 4) - 1)))


def rodar(tarefa: Tarefa, *, disco: bool = False) -> Tarefa:
    """Enfileira `tarefa`. Devolve a propria tarefa, para poder cancelar."""
    (POOL_DISCO if disco else POOL_CPU).start(tarefa)
    return tarefa


def esperar_tudo(ms: int = 30_000) -> bool:
    """Espera os dois pools esvaziarem. Usado ao fechar o app e nos testes."""
    ok_disco = POOL_DISCO.waitForDone(ms)
    ok_cpu = POOL_CPU.waitForDone(ms)
    return ok_disco and ok_cpu
