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

from textforge import configuracao                               # noqa: E402
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

# ---------------------------------------------------------------------------
secao("7 - *** enquanto o dialogo esta' aberto, o vigia CALA (regressao) ***")

# O defeito: o dialogo de alteracao externa e' modal, e `exec()` roda um laco de
# eventos ANINHADO. O timer do vigia continua disparando dentro dele; num arquivo
# que CRESCE -- um log sendo escrito por outro programa -- cada disparo via um
# estado novo, emitia de novo, e a janela abria outro modal por cima. Medido antes
# da correcao: 47 modais aninhados em 4 segundos, sem limite, ate' travar.

with pasta_temporaria() as pasta:
    crescendo = pasta / "cresce.log"
    crescendo.write_bytes(b"linha 0\n")
    avisos: list[str] = []
    vigia = Vigia()
    vigia.mudou.connect(lambda c, _a: avisos.append(c))
    vigia.acompanhar(crescendo, Assinatura.de_caminho(crescendo))

    mexer(crescendo, b"linha 1\n")
    vigia.verificar_agora()
    checa_igual(len(avisos), 1, "a primeira mudanca avisa normalmente")

    # Dentro do `em_resolucao` -- que e' onde o dialogo estaria na tela -- o
    # arquivo continua crescendo, e NENHUM aviso novo pode sair.
    with vigia.em_resolucao(crescendo):
        for n in range(2, 12):
            mexer(crescendo, f"linha {n}\n".encode())
            vigia.verificar_agora()
        checa_igual(len(avisos), 1,
                    "*** 10 mudancas com o dialogo aberto: NENHUM aviso novo ***")

    # Ao sair, a assinatura e' reconferida: a decisao do usuario vale para o que
    # esta' no disco AGORA, e o aviso nao dispara na hora por causa do passado.
    vigia.verificar_agora()
    checa_igual(len(avisos), 1,
                "*** e ao fechar o dialogo ele nao dispara pelo que ja' passou ***")

    # Mas uma mudanca NOVA, depois disso, volta a avisar.
    mexer(crescendo, b"depois do dialogo\n")
    vigia.verificar_agora()
    checa_igual(len(avisos), 2,
                "uma mudanca NOVA depois do dialogo volta a avisar")

    # O silencio e' POR ARQUIVO: resolver um nao pode calar o outro.
    outro = pasta / "outro.txt"
    outro.write_bytes(b"a")
    vigia.acompanhar(outro, Assinatura.de_caminho(outro))
    with vigia.em_resolucao(crescendo):
        mexer(outro, b"b")
        vigia.verificar_agora()
        checa_igual(len(avisos), 3,
                    "*** resolver um arquivo nao cala o aviso de OUTRO ***")
    vigia.parar()

# ---------------------------------------------------------------------------
secao("8 - o proprio log do TextForge nao e' vigiado")

# Abrir o textforge.log no editor e' util (ha' um item de menu para isso), e fazia
# o vigia disparar a cada linha gravada -- avisando de uma alteracao "externa" que
# na verdade era nossa.
from textforge.interface.janela import JanelaPrincipal                # noqa: E402

eh_nosso = JanelaPrincipal._escrito_pelo_proprio_programa
checa(eh_nosso(configuracao.caminho_log()),
      "o textforge.log e' reconhecido como escrito pelo proprio programa")
checa(eh_nosso(configuracao.caminho_erro()),
      "o erro.log tambem")
with pasta_temporaria() as pasta:
    qualquer = pasta / "textforge.log"      # mesmo NOME, outro lugar
    qualquer.write_bytes(b"x")
    checa(not eh_nosso(qualquer),
          "*** mas um arquivo com o mesmo NOME em outra pasta NAO e' o nosso "
          "(a comparacao e' por caminho resolvido, e nao por nome) ***")

sys.exit(resumir())
