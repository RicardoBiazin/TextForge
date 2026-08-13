"""Vigia de alteracao externa (requisito 27).

    .venv\\Scripts\\python.exe tests\\teste_vigia.py

O vigia e' HIBRIDO de proposito: `QFileSystemWatcher` mais uma consulta periodica
a tamanho e mtime. O watcher perde eventos em compartilhamento de rede (o caso do
`Y:`) e solta o caminho quando o arquivo e' substituido em vez de reescrito -- que
e' justamente o que a gravacao atomica do TextForge faz.

Estes testes exercitam o caminho da CONSULTA (`verificar_agora`), que e' o
determinista. O caminho do watcher depende de notificacao do sistema de arquivos e
nao e' reproduzivel num teste.
"""

from __future__ import annotations

import os
import sys
import time

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge.arquivos import Assinatura                       # noqa: E402
from textforge.vigia import Vigia                                # noqa: E402


def mexer(caminho, conteudo: bytes) -> None:
    """Escreve garantindo que o mtime mude de verdade.

    Em disco rapido, duas escritas no mesmo instante podem ficar com o MESMO
    mtime. O sha256 da assinatura pega isso, mas o teste fica mais claro se a
    alteracao for inequivoca.
    """
    time.sleep(0.02)
    caminho.write_bytes(conteudo)
    agora = time.time_ns() + 2_000_000_000
    os.utime(caminho, ns=(agora, agora))


# ---------------------------------------------------------------------------
secao("1 - deteccao por consulta")

with pasta_temporaria() as pasta:
    alvo = pasta / "vigiado.txt"
    alvo.write_bytes(b"versao 1")

    avisos: list[tuple[str, object]] = []
    removidos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, a: avisos.append((c, a)))
    vigia.removido.connect(removidos.append)
    vigia.acompanhar(alvo, Assinatura.de_caminho(alvo))

    checa_igual(vigia.vigiados(), [str(alvo)], "o arquivo entra na lista")

    vigia.verificar_agora()
    checa_igual(avisos, [], "sem mudanca, nao avisa nada")

    mexer(alvo, b"versao 2, mexida por outro programa")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "a alteracao externa dispara UM aviso")
    checa_igual(avisos[0][0], str(alvo), "e o aviso traz o caminho")

    # Nao repetir o aviso a cada consulta: o vigia guarda o novo estado. Sem
    # isto, um dialogo por segundo enquanto o usuario le' o primeiro.
    vigia.verificar_agora()
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "NAO repete o aviso da mesma alteracao")

    mexer(alvo, b"versao 3")
    vigia.verificar_agora()
    checa_igual(len(avisos), 2, "mas uma alteracao NOVA avisa de novo")

    vigia.parar()

# ---------------------------------------------------------------------------
secao("2 - confirmar apos salvar nao gera falso alarme")

with pasta_temporaria() as pasta:
    alvo = pasta / "salvo.txt"
    alvo.write_bytes(b"inicial")

    avisos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, a: avisos.append(c))
    vigia.acompanhar(alvo, Assinatura.de_caminho(alvo))

    # O proprio TextForge grava. Sem `confirmar`, a gravacao dele mesmo
    # dispararia "alterado externamente" -- e um aviso que sempre aparece nao
    # protege ninguem, porque o usuario aprende a ignorar.
    mexer(alvo, b"gravado pelo proprio editor")
    vigia.confirmar(alvo, Assinatura.de_caminho(alvo))
    vigia.verificar_agora()
    checa_igual(avisos, [],
                "gravacao propria seguida de confirmar() NAO gera aviso")

    mexer(alvo, b"agora sim foi outro programa")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "e uma alteracao de terceiro continua avisando")

    vigia.parar()

# ---------------------------------------------------------------------------
secao("3 - pausar e retomar")

with pasta_temporaria() as pasta:
    alvo = pasta / "pausado.txt"
    alvo.write_bytes(b"a")

    avisos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, a: avisos.append(c))
    vigia.acompanhar(alvo, Assinatura.de_caminho(alvo))

    # O usuario escolheu "manter a minha versao": nao queremos insistir.
    vigia.pausar(alvo)
    mexer(alvo, b"b")
    vigia.verificar_agora()
    checa_igual(avisos, [], "pausado, nao avisa")

    # Mas continua VIGIANDO: retomar volta a avisar na proxima alteracao. Parar
    # de vigiar de vez faria a segunda alteracao externa passar batida.
    vigia.retomar(alvo)
    mexer(alvo, b"c")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "retomado, volta a avisar")

    vigia.parar()

# ---------------------------------------------------------------------------
secao("4 - arquivo apagado")

with pasta_temporaria() as pasta:
    alvo = pasta / "apagado.txt"
    alvo.write_bytes(b"existe")

    removidos: list[str] = []
    avisos: list[str] = []
    vigia = Vigia()
    vigia.removido.connect(removidos.append)
    vigia.mudou.connect(lambda c, a: avisos.append(c))
    vigia.acompanhar(alvo, Assinatura.de_caminho(alvo))

    alvo.unlink()
    vigia.verificar_agora()
    checa_igual(len(removidos), 1, "apagar o arquivo emite 'removido'")
    checa_igual(avisos, [], "e NAO emite 'mudou' (sao situacoes diferentes)")

    vigia.verificar_agora()
    checa_igual(len(removidos), 1, "e nao repete o aviso de removido")

    vigia.parar()

# ---------------------------------------------------------------------------
secao("5 - esquecer e parar")

with pasta_temporaria() as pasta:
    a = pasta / "a.txt"
    b = pasta / "b.txt"
    a.write_bytes(b"1")
    b.write_bytes(b"1")

    avisos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, _a: avisos.append(c))
    vigia.acompanhar(a, Assinatura.de_caminho(a))
    vigia.acompanhar(b, Assinatura.de_caminho(b))
    checa_igual(len(vigia.vigiados()), 2, "dois arquivos vigiados")

    vigia.esquecer(a)
    checa_igual(vigia.vigiados(), [str(b)], "esquecer remove um so'")

    mexer(a, b"2")
    mexer(b, b"2")
    vigia.verificar_agora()
    checa_igual(avisos, [str(b)],
                "so' o arquivo ainda vigiado gera aviso")

    vigia.parar()
    checa_igual(vigia.vigiados(), [], "parar() limpa a lista")
    mexer(b, b"3")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "depois de parar(), nada mais avisa")

# ---------------------------------------------------------------------------
secao("6 - arquivo que nunca existiu nao gera aviso")

with pasta_temporaria() as pasta:
    fantasma = pasta / "nunca-existiu.txt"
    avisos: list[str] = []
    removidos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, _a: avisos.append(c))
    vigia.removido.connect(removidos.append)
    vigia.acompanhar(fantasma, Assinatura.de_caminho(fantasma))

    vigia.verificar_agora()
    checa_igual(removidos, [],
                "arquivo que nunca existiu nao dispara 'removido'")

    # Mas se ele PASSAR a existir, isso e' uma alteracao: e' o caso de "Salvar
    # como" para um caminho que outro programa criou no meio do caminho.
    fantasma.write_bytes(b"apareceu")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "o arquivo aparecer no disco conta como mudanca")

    vigia.parar()

sys.exit(resumir())
