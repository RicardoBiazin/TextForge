"""Instancia unica: canal, servidor, entrega entre processos, pipe orfao.

    .venv\\Scripts\\python.exe tests\\teste_instancia_unica.py

Por que isto e' testado tao cedo: sem instancia unica, selecionar 12 arquivos no
Explorer e mandar abrir dispara 12 processos, e no modo um-arquivo do PyInstaller
sao 12 descompactacoes de ~70 MB em %TEMP% ao mesmo tempo. E' pre-requisito do
"Abrir com TextForge", nao um refinamento.

O teste usa PROCESSOS SEPARADOS (`ajudante_enviar.py`) porque o envio bloqueia
esperando confirmacao -- no mesmo processo o servidor nunca responderia. E
porque dois processos e' o cenario real.

Regressao que este arquivo guarda: neste Qt (6.11 no Windows) destruir o
QLocalSocket antes de os bytes drenarem DESCARTA os bytes. Numa versao anterior
deste modulo, tres envios seguidos entregavam UM pedido so'. Se a espera pela
confirmacao em `enviar_para_instancia_existente` for removida, a secao 4 quebra.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

from ajudantes import checa, checa_igual, preparar_qt, pular, resumir, secao

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtCore import QEventLoop, QTimer            # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402

from textforge import instancia_unica                     # noqa: E402

AQUI = pathlib.Path(__file__).resolve().parent
AJUDANTE = AQUI / "ajudante_enviar.py"


def girar(ms: int) -> None:
    """Deixa o laco de eventos rodar, para os sinais serem entregues."""
    laco = QEventLoop()
    QTimer.singleShot(ms, laco.quit)
    laco.exec()


def _abrir_ajudante(caminho: str, linha: int = 0) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-u", str(AJUDANTE), caminho,
                             str(linha)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, errors="replace")


def _esperar_girando(procs: list[subprocess.Popen], limite_s: int = 20) -> list[int]:
    """Espera os processos filhos SEM bloquear o laco de eventos deste processo.

    Isto nao e' detalhe de teste, e' o modelo de execucao real: o filho fica
    parado esperando a confirmacao, e a confirmacao so' sai quando o laco de
    eventos de quem recebe gira. Um `subprocess.run()` aqui congelaria o laco e
    os dois lados esperariam um pelo outro -- foi exatamente o impasse que a
    primeira versao deste teste criou.
    """
    fim = time.monotonic() + limite_s
    while any(p.poll() is None for p in procs) and time.monotonic() < fim:
        girar(50)
    codigos = []
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait(5)
            codigos.append(-1)          # estourou o tempo
        else:
            codigos.append(p.returncode)
    girar(150)                          # deixa o ultimo readyRead ser entregue
    return codigos


def enviar_de_outro_processo(caminho: str, linha: int = 0,
                             limite_s: int = 20) -> int:
    """Roda o ajudante num processo separado. 0 = entrega confirmada."""
    return _esperar_girando([_abrir_ajudante(caminho, linha)], limite_s)[0]


# ---------------------------------------------------------------------------
secao("1 - nome do canal")

nome = instancia_unica.nome_do_canal()
checa(nome.startswith("TextForge-"), "o canal comeca com o nome do app")
checa(all(c.isalnum() or c in "-_" for c in nome),
      "o nome do canal so' tem caracteres seguros para um named pipe")
checa_igual(nome, instancia_unica.nome_do_canal(),
            "o nome e' estavel entre chamadas")
checa(len(nome) > len("TextForge-"),
      "inclui o usuario (dois usuarios na mesma maquina nao se atropelam)")

# ---------------------------------------------------------------------------
secao("2 - sem ninguem escutando, nao ha' a quem entregar")

QLocalServer.removeServer(nome)
checa_igual(enviar_de_outro_processo(r"C:\x.txt"), 1,
            "outro processo devolve 1 quando nao existe instancia rodando")

# ---------------------------------------------------------------------------
secao("3 - servidor sobe e recebe o pedido de outro processo")

recebidos: list[dict] = []
servidor = instancia_unica.preparar(recebidos.append)
checa(servidor is not None, "preparar() consegue escutar quando o canal esta' livre")

codigo = enviar_de_outro_processo(r"C:\x\config.xml", 850)
checa_igual(codigo, 0, "o outro processo confirma a entrega (codigo 0)")

girar(300)
checa_igual(len(recebidos), 1, "o servidor recebeu exatamente um pedido")
if recebidos:
    checa_igual(recebidos[0]["arquivos"][0]["linha"], 850,
                "a linha atravessou o pipe intacta")
    checa_igual(recebidos[0]["arquivos"][0]["caminho"], r"C:\x\config.xml",
                "a barra invertida do caminho do Windows sobreviveu ao JSON")

# ---------------------------------------------------------------------------
secao("4 - varios envios (regressao: chegava so' um)")

recebidos.clear()
codigos = [enviar_de_outro_processo(f"C:\\a{i}.txt") for i in range(3)]
checa_igual(codigos, [0, 0, 0], "tres processos em sequencia confirmam a entrega")
checa_igual(len(recebidos), 3,
            "os TRES pedidos chegaram (nao apenas o ultimo)")
caminhos = sorted(p["arquivos"][0]["caminho"] for p in recebidos)
checa_igual(caminhos, [r"C:\a0.txt", r"C:\a1.txt", r"C:\a2.txt"],
            "chegaram os tres caminhos distintos, nenhum perdido")

# O caso real do requisito 33: selecionar varios arquivos no Explorer e mandar
# abrir dispara os processos TODOS DE UMA VEZ, disputando o mesmo pipe.
recebidos.clear()
juntos = [_abrir_ajudante(f"C:\\lote{i}.txt") for i in range(5)]
codigos = _esperar_girando(juntos, limite_s=30)
checa_igual(codigos, [0] * 5,
            "cinco processos SIMULTANEOS confirmam a entrega (caso do Explorer)")
checa_igual(len(recebidos), 5, "os cinco pedidos simultaneos chegaram")
checa_igual(sorted(p["arquivos"][0]["caminho"] for p in recebidos),
            [f"C:\\lote{i}.txt" for i in range(5)],
            "nenhum dos cinco caminhos foi perdido nem duplicado")

# ---------------------------------------------------------------------------
secao("5 - lixo no canal nao derruba o servidor")

# Uma mensagem que nao e' JSON tem de ser descartada com aviso no log. Se
# estourasse dentro do handler, o Qt abortaria o processo inteiro.
s = QLocalSocket()
s.connectToServer(nome)
if s.waitForConnected(2000):
    s.write(b"isso nao e json\n")
    s.flush()
    girar(200)
    s.abort()
girar(200)
checa(True, "mensagem ilegivel nao derrubou o servidor")

recebidos.clear()
checa_igual(enviar_de_outro_processo(r"C:\depois-do-lixo.txt"), 0,
            "o servidor continua confirmando depois do lixo")
girar(300)
checa_igual(len(recebidos), 1, "e continua entregando o pedido")

# Uma conexao que abre e fecha sem mandar nada nao pode vazar estado.
for _ in range(3):
    morto = QLocalSocket()
    morto.connectToServer(nome)
    morto.waitForConnected(1000)
    morto.abort()
girar(200)
recebidos.clear()
checa_igual(enviar_de_outro_processo(r"C:\vivo.txt"), 0,
            "conexoes abandonadas sem dados nao afetam as seguintes")
girar(300)
checa_igual(len(recebidos), 1, "o pedido seguinte chega normalmente")

# ---------------------------------------------------------------------------
secao("6 - parar() libera o canal")

servidor.parar()
girar(200)
checa_igual(enviar_de_outro_processo(r"C:\x.txt"), 1,
            "depois de parar(), nao ha' mais quem receba")

# Um processo morto de forma abrupta deixa o named pipe orfao. O
# `Servidor.__init__` chama removeServer() justamente para o listen() nao
# falhar para sempre depois de um travamento.
outro = instancia_unica.preparar(recebidos.append)
checa(outro is not None, "um servidor novo consegue reassumir o mesmo canal")
if outro:
    recebidos.clear()
    checa_igual(enviar_de_outro_processo(r"C:\reassumido.txt"), 0,
                "e o canal reassumido funciona")
    girar(300)
    checa_igual(len(recebidos), 1, "entregando de verdade apos reassumir")
    outro.parar()

sys.exit(resumir())
