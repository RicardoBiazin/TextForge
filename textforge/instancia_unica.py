"""Uma instancia so', para o "Abrir com TextForge" reusar a janela aberta.

Sem isto, selecionar 12 arquivos no Explorer e mandar abrir dispara 12
processos. No modo um-arquivo do PyInstaller sao 12 descompactacoes de ~70 MB em
%TEMP% ao mesmo tempo -- a maquina engasga e o usuario conclui, com razao, que o
editor e' lento. Por isso a instancia unica e' pre-requisito do requisito 33, nao
um refinamento.

Como funciona: o primeiro processo escuta um QLocalServer (named pipe no
Windows). O segundo tenta conectar; se conseguir, manda os caminhos em JSON e
sai com codigo 0. Se nao conseguir, assume o papel de primeiro.

Isto vive em PySide6.QtNetwork -- que por isso NAO pode entrar nos `excludes` do
.spec, apesar de parecer um modulo de rede dispensavel.
"""

from __future__ import annotations

import getpass
import json
from typing import Callable

from PySide6.QtCore import QByteArray, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from textforge import APP_ARQUIVO, log_interno

log = log_interno.obter(__name__)

TEMPO_LIMITE_MS = 1000


def nome_do_canal() -> str:
    """Canal por usuario: dois usuarios na mesma maquina nao se atropelam."""
    try:
        usuario = getpass.getuser()
    except Exception:            # noqa: BLE001 - getuser depende do ambiente
        usuario = "desconhecido"
    seguro = "".join(c if c.isalnum() else "_" for c in usuario)
    return f"{APP_ARQUIVO}-{seguro}"


def enviar_para_instancia_existente(pedido: dict) -> bool:
    """Tenta entregar `pedido` a uma instancia ja' rodando.

    Devolve True se entregou (o chamador deve sair). False se nao havia
    ninguem escutando, ou se a entrega falhou -- nesse caso e' melhor abrir uma
    janela nova do que deixar o usuario sem nada.
    """
    socket = QLocalSocket()
    socket.connectToServer(nome_do_canal())
    if not socket.waitForConnected(TEMPO_LIMITE_MS):
        return False

    dados = QByteArray((json.dumps(pedido, ensure_ascii=False) + "\n").encode("utf-8"))
    if socket.write(dados) != dados.size():
        log.warning("instancia existente encontrada mas nao aceitou os dados")
        socket.abort()
        return False
    socket.flush()

    # ESPERAR O "ok" NAO E' OPCIONAL, por dois motivos medidos neste Qt (6.11 no
    # Windows), e nao por precaucao teorica:
    #
    #  1. bytesToWrite() nao zera e flush()/waitForBytesWritten() devolvem False
    #     mesmo quando a escrita deu certo -- entao nao ha' como confirmar a
    #     entrega olhando o socket.
    #  2. Destruir o QLocalSocket antes de os bytes drenarem DESCARTA os bytes.
    #     Sem esta espera, tres processos enviando em sequencia entregavam um so'
    #     pedido: e' exatamente o caso de selecionar varios arquivos no Explorer
    #     e mandar abrir.
    #
    # Se a confirmacao nao vier, devolvemos False e este processo abre a propria
    # janela. Falhar assim custa uma janela a mais; falhar para o outro lado
    # (dizer "entregue" sem ter entregue) faria o duplo-clique do usuario nao
    # abrir nada -- e nao ha' nada pior num programa registrado em "Abrir com".
    resposta = QByteArray()
    while b"\n" not in bytes(resposta):
        if not socket.waitForReadyRead(TEMPO_LIMITE_MS):
            log.warning("instancia existente nao confirmou o pedido; "
                        "abrindo janela propria")
            socket.abort()
            return False
        resposta.append(socket.readAll())

    socket.disconnectFromServer()
    if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        socket.waitForDisconnected(TEMPO_LIMITE_MS)
    log.info("pedido entregue a instancia existente: %d arquivo(s)",
             len(pedido.get("arquivos", [])))
    return True


class Servidor(QObject):
    """Escuta pedidos de outras instancias.

    Emite `pedido_recebido` com o dicionario enviado. A janela conecta esse
    sinal para abrir os arquivos em novas abas e se trazer para a frente.
    """

    pedido_recebido = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._servidor = QLocalServer(self)
        # Se o processo anterior morreu de forma abrupta, o named pipe pode
        # ficar orfao e o listen() falharia para sempre. Isto limpa o restos.
        QLocalServer.removeServer(nome_do_canal())
        self._parciais: dict[QLocalSocket, bytes] = {}
        self._servidor.newConnection.connect(self._nova_conexao)

    def escutar(self) -> bool:
        if not self._servidor.listen(nome_do_canal()):
            log.warning("nao foi possivel escutar em %s: %s",
                        nome_do_canal(), self._servidor.errorString())
            return False
        log.info("escutando em %s", nome_do_canal())
        return True

    def parar(self) -> None:
        self._servidor.close()
        QLocalServer.removeServer(nome_do_canal())

    def _nova_conexao(self) -> None:
        while self._servidor.hasPendingConnections():
            socket = self._servidor.nextPendingConnection()
            self._parciais[socket] = b""
            socket.readyRead.connect(lambda s=socket: self._ler(s))
            socket.disconnected.connect(lambda s=socket: self._encerrar(s))

    def _ler(self, socket: QLocalSocket) -> None:
        self._parciais[socket] = self._parciais.get(socket, b"") + bytes(socket.readAll())
        # Protocolo: uma mensagem JSON por linha. O laco trata a mensagem
        # chegando em varios pedacos, que e' o normal num pipe.
        while b"\n" in self._parciais[socket]:
            linha, resto = self._parciais[socket].split(b"\n", 1)
            self._parciais[socket] = resto
            try:
                pedido = json.loads(linha.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                log.warning("pedido ilegivel de outra instancia, ignorado")
                continue
            if not isinstance(pedido, dict):
                continue
            # Confirmar ANTES de emitir o sinal: abrir os arquivos pode demorar
            # (arquivo grande, unidade de rede) e o outro processo ficaria preso
            # esperando o "ok" enquanto isso.
            socket.write(b"ok\n")
            socket.flush()
            self.pedido_recebido.emit(pedido)

    def _encerrar(self, socket: QLocalSocket) -> None:
        self._parciais.pop(socket, None)
        socket.deleteLater()


def preparar(ao_receber: Callable[[dict], None],
             parent: QObject | None = None) -> Servidor | None:
    """Sobe o servidor e liga o callback. None se nao conseguiu escutar."""
    servidor = Servidor(parent)
    if not servidor.escutar():
        return None
    servidor.pedido_recebido.connect(ao_receber)
    return servidor
