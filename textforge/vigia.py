"""Vigia de alteracao externa (requisito 27) e base do tail de log (requisito 26).

`QFileSystemWatcher` sozinho NAO serve, e isto e' conhecido:

  * em compartilhamento de rede (SMB, o caso do `Y:`) ele perde eventos, porque
    depende de notificacao do sistema de arquivos que o servidor pode nao mandar;
  * alguns programas gravam substituindo o arquivo (o mesmo `ReplaceFileW` que o
    TextForge usa), e o watcher solta o caminho depois disso -- para de vigiar
    sem avisar;
  * ele nao diz O QUE mudou: um `fileChanged` pode ser append num log ou
    reescrita completa.

Por isso o vigia e' HIBRIDO: watcher (rapido, quando funciona) mais uma consulta
periodica a tamanho e mtime (lenta, mas nao mente). O intervalo padrao de 2 s e'
folgado o bastante para nao pesar e curto o bastante para o usuario nao editar
muito sobre uma versao velha.

O que este modulo NAO faz: decidir. Ele emite `mudou` e `removido`; quem abre o
dialogo Recarregar / Manter o meu / Comparar e' a janela. Nunca ha' recarga
automatica -- o requisito 27 proibe sobrescrever ou descartar em silencio.
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from textforge import log_interno
from textforge.arquivos import Assinatura

log = log_interno.obter(__name__)

INTERVALO_DE_CONSULTA_MS = 2000


class Vigia(QObject):
    """Vigia um conjunto de arquivos e avisa quando algum muda no disco.

    Uso:
        vigia = Vigia()
        vigia.mudou.connect(...)
        vigia.acompanhar(caminho, assinatura)
        vigia.confirmar(caminho, nova_assinatura)   # depois de salvar
    """

    mudou = Signal(str, object)          # caminho, Assinatura encontrada
    removido = Signal(str)               # caminho

    def __init__(self, parent: QObject | None = None,
                 intervalo_ms: int = INTERVALO_DE_CONSULTA_MS) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._ao_notificar)
        self._esperadas: dict[str, Assinatura] = {}
        self._pausados: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(max(250, intervalo_ms))
        self._timer.timeout.connect(self.verificar_agora)

    # ==================================================================
    # Registro
    # ==================================================================

    def acompanhar(self, caminho: str | pathlib.Path,
                   assinatura: Assinatura) -> None:
        """Passa a vigiar `caminho`, tomando `assinatura` como o estado atual."""
        texto = str(pathlib.Path(caminho))
        self._esperadas[texto] = assinatura
        self._watcher.addPath(texto)
        if not self._timer.isActive():
            self._timer.start()

    def esquecer(self, caminho: str | pathlib.Path) -> None:
        texto = str(pathlib.Path(caminho))
        self._esperadas.pop(texto, None)
        self._pausados.discard(texto)
        self._watcher.removePath(texto)
        if not self._esperadas:
            self._timer.stop()

    def confirmar(self, caminho: str | pathlib.Path,
                  assinatura: Assinatura) -> None:
        """Registra o novo estado esperado -- chamado DEPOIS de salvar.

        Sem isto, a propria gravacao do TextForge dispararia o aviso de "alterado
        externamente" no salvamento seguinte, e o usuario aprenderia a ignorar o
        aviso. Um aviso que sempre aparece nao protege ninguem.
        """
        texto = str(pathlib.Path(caminho))
        if texto in self._esperadas:
            self._esperadas[texto] = assinatura
        # ReplaceFileW substitui o arquivo, e o watcher solta o caminho depois
        # disso: readicionar e' o que mantem a vigilancia viva apos cada
        # salvamento.
        if texto not in self._watcher.files():
            self._watcher.addPath(texto)

    def pausar(self, caminho: str | pathlib.Path) -> None:
        """Suspende o aviso para um arquivo (o usuario escolheu "manter o meu").

        Continua vigiando: se o arquivo mudar DE NOVO, o aviso volta. Parar de
        vigiar de vez faria a segunda alteracao externa passar despercebida.
        """
        self._pausados.add(str(pathlib.Path(caminho)))

    def retomar(self, caminho: str | pathlib.Path) -> None:
        self._pausados.discard(str(pathlib.Path(caminho)))

    def vigiados(self) -> list[str]:
        return sorted(self._esperadas)

    def parar(self) -> None:
        self._timer.stop()
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        self._esperadas.clear()
        self._pausados.clear()

    # ==================================================================
    # Deteccao
    # ==================================================================

    def _ao_notificar(self, caminho: str) -> None:
        """Reacao ao sinal do watcher: confere de verdade antes de avisar.

        O `fileChanged` dispara tambem quando o arquivo e' aberto para escrita sem
        mudar nada. Comparar a assinatura evita o falso alarme.
        """
        self._checar(caminho)

    def verificar_agora(self) -> None:
        """A consulta periodica. E' a rede de seguranca do watcher."""
        for caminho in list(self._esperadas):
            self._checar(caminho)

    def _checar(self, caminho: str) -> None:
        esperada = self._esperadas.get(caminho)
        if esperada is None:
            return
        atual = Assinatura.de_caminho(pathlib.Path(caminho))

        if not atual.existe:
            if esperada.existe:
                # Guarda o estado para nao repetir o aviso a cada 2 s.
                self._esperadas[caminho] = atual
                log.info("arquivo desapareceu do disco: %s", caminho)
                if caminho not in self._pausados:
                    self.removido.emit(caminho)
            return

        if esperada.compativel_com(atual):
            return

        # Atualiza ANTES de emitir: se o usuario deixar o dialogo aberto, a
        # consulta seguinte nao vai empilhar outro dialogo em cima.
        self._esperadas[caminho] = atual
        log.info("alteracao externa em %s (%s)", caminho,
                 esperada.descrever_diferenca(atual))
        if caminho in self._pausados:
            return
        self.mudou.emit(caminho, atual)
