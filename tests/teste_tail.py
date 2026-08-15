"""Acompanhar log ao vivo: leitura incremental, truncamento, rotacao (etapa 11).

    .\\.venv\\Scripts\\python.exe tests\\teste_tail.py

As verificacoes que carregam o peso:

  * um caractere UTF-8 MULTIBYTE cortado na fronteira do bloco e' montado certo. E'
    o teste central: sem o decodificador incremental, o primeiro byte de um "c"
    viraria um U+FFFD PERMANENTE, e o log mostraria lixo no lugar de um caractere
    que chegou inteiro no milissegundo seguinte.
  * a linha parcial (ainda sem "\\n") NAO e' emitida como linha completa, e completa
    no append seguinte. Um log e' escrito em pedacos.
  * truncar o arquivo recarrega do inicio; ROTACIONAR (renomear e criar outro com o
    mesmo nome) tambem -- inclusive quando o arquivo novo ja' esta' MAIOR que o
    offset atual, caso em que so' o tamanho nao denunciaria nada.
  * pausar para de consumir, e retomar continua do offset -- sem perder nem repetir.
  * `setMaximumBlockCount` limita a memoria da view.

A parte de logica (`LeitorIncremental`) roda sem Qt.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt,
                       resumir, secao)

TEM_QT = preparar_qt()

from textforge.vigia import LeitorIncremental                # noqa: E402


def escrever(caminho: pathlib.Path, dados: bytes) -> None:
    """Acrescenta bytes CRUS, como um processo que grava um log faria."""
    with open(caminho, "ab") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())


# ===========================================================================


def testar_leitura_incremental(pasta: pathlib.Path) -> None:
    secao("Append em pedacos entrega as linhas na ordem")

    alvo = pasta / "app.log"
    alvo.write_bytes(b"")
    leitor = LeitorIncremental(alvo, "utf-8")

    checa_igual(leitor.ler(), ([], False), "arquivo vazio: nada a ler")

    escrever(alvo, b"primeira\nsegunda\n")
    linhas, recomecou = leitor.ler()
    checa_igual(linhas, ["primeira", "segunda"], "as duas linhas chegaram")
    checa(not recomecou, "e nao houve recomeco")
    checa_igual(leitor.ler(), ([], False), "reler sem novidade devolve vazio")

    escrever(alvo, b"terceira\n")
    linhas, _ = leitor.ler()
    checa_igual(linhas, ["terceira"], "o append seguinte traz so' o que e' novo")

    # Ordem preservada em lote grande.
    escrever(alvo, b"".join(f"L{n}\n".encode() for n in range(500)))
    linhas, _ = leitor.ler()
    checa_igual(len(linhas), 500, "500 linhas de uma vez chegam todas")
    checa_igual(linhas[0], "L0", "na ordem certa (primeira)")
    checa_igual(linhas[-1], "L499", "na ordem certa (ultima)")

    secao("CRLF")
    crlf = pasta / "crlf.log"
    crlf.write_bytes(b"")
    l2 = LeitorIncremental(crlf, "utf-8")
    escrever(crlf, b"linha um\r\nlinha dois\r\n")
    linhas, _ = l2.ler()
    checa_igual(linhas, ["linha um", "linha dois"],
                "o \\r do CRLF nao sobra no fim da linha")


def testar_multibyte_na_fronteira(pasta: pathlib.Path) -> None:
    secao("*** Caractere UTF-8 multibyte CORTADO na fronteira do bloco ***")

    alvo = pasta / "acentos.log"
    alvo.write_bytes(b"")
    leitor = LeitorIncremental(alvo, "utf-8")

    # "transacao concluida" com c-cedilha e i-agudo: dois bytes cada em UTF-8.
    texto = "transação concluída\n"
    bruto = texto.encode("utf-8")
    meio = bruto.index("ç".encode("utf-8")) + 1     # NO MEIO do c-cedilha

    checa(bruto[meio - 1] >= 0x80 and bruto[meio] >= 0x80,
          "o corte cai MESMO no meio de uma sequencia multibyte")

    escrever(alvo, bruto[:meio])
    linhas, _ = leitor.ler()
    checa_igual(linhas, [],
                "com meio caractere no arquivo, nenhuma linha e' emitida")
    checa("�" not in leitor.resto,
          "*** e o meio-caractere NAO virou U+FFFD: o decodificador o segurou ***")
    checa_igual(leitor.resto, "transa",
                "a parcial vai so' ate' onde os bytes estao completos")

    escrever(alvo, bruto[meio:])
    linhas, _ = leitor.ler()
    checa_igual(linhas, [texto.rstrip("\n")],
                "*** com o resto dos bytes, a linha sai INTEIRA e correta ***")
    checa("ç" in linhas[0] and "í" in linhas[0],
          "os acentos estao la', e nao substituidos")

    secao("Corte byte a byte: o caso extremo")
    alvo2 = pasta / "bytea byte.log"
    alvo2.write_bytes(b"")
    l3 = LeitorIncremental(alvo2, "utf-8")
    frase = "ação é aú\n"
    completas: list[str] = []
    for byte in frase.encode("utf-8"):
        escrever(alvo2, bytes([byte]))
        linhas, _ = l3.ler()
        completas.extend(linhas)
        checa_bruto = "�" in l3.resto
        if checa_bruto:
            break
    checa(not checa_bruto,
          "gravando UM BYTE por vez, nenhum U+FFFD aparece na parcial")
    checa_igual(completas, [frase.rstrip("\n")],
                "e no fim a linha sai exatamente como foi escrita")

    secao("cp1252 tambem funciona (um byte por caractere)")
    alvo3 = pasta / "legado.log"
    alvo3.write_bytes(b"")
    l4 = LeitorIncremental(alvo3, "cp1252")
    escrever(alvo3, "opera\xe7\xe3o conclu\xedda\n".encode("cp1252"))
    linhas, _ = l4.ler()
    checa_igual(linhas, ["operação concluída"],
                "log em cp1252 e' decodificado com o codec do documento")


def testar_linha_parcial(pasta: pathlib.Path) -> None:
    secao("Linha parcial fica no resto e completa no append seguinte")

    alvo = pasta / "parcial.log"
    alvo.write_bytes(b"")
    leitor = LeitorIncremental(alvo, "utf-8")

    escrever(alvo, b"2026-08-13 ERRO: fal")
    linhas, _ = leitor.ler()
    checa_igual(linhas, [],
                "um pedaco sem '\\n' NAO vira linha completa")
    checa_igual(leitor.resto, "2026-08-13 ERRO: fal",
                "ele fica esperando no resto")

    escrever(alvo, b"ha critica\n")
    linhas, _ = leitor.ler()
    checa_igual(linhas, ["2026-08-13 ERRO: falha critica"],
                "*** e sai como UMA linha, e nao duas erradas ***")
    checa_igual(leitor.resto, "", "o resto ficou vazio")

    # Varias linhas, com a ultima incompleta.
    escrever(alvo, b"completa 1\ncompleta 2\nincompl")
    linhas, _ = leitor.ler()
    checa_igual(linhas, ["completa 1", "completa 2"],
                "so' as completas saem do lote")
    checa_igual(leitor.resto, "incompl", "e a ultima fica pendente")


def testar_truncamento_e_rotacao(pasta: pathlib.Path) -> None:
    secao("Truncamento (`> log.txt`)")

    alvo = pasta / "trunca.log"
    alvo.write_bytes(b"")
    leitor = LeitorIncremental(alvo, "utf-8")
    escrever(alvo, b"velha 1\nvelha 2\nvelha 3\n")
    leitor.ler()
    checa(leitor.offset > 0, "o leitor avancou o offset")

    alvo.write_bytes(b"")                       # truncou
    escrever(alvo, b"nova 1\n")
    linhas, recomecou = leitor.ler()
    checa(recomecou, "*** truncar o arquivo e' detectado como recomeco ***")
    checa_igual(linhas, ["nova 1"],
                "e a leitura volta do inicio, sem emendar no conteudo velho")

    secao("Rotacao com o arquivo novo JA MAIOR que o offset")
    # O caso que so' o tamanho NAO pega: renomeiam o log e criam outro com o mesmo
    # nome, e quando o leitor consulta, o novo ja' cresceu alem do offset antigo.
    girado = pasta / "gira.log"
    girado.write_bytes(b"")
    l2 = LeitorIncremental(girado, "utf-8")
    escrever(girado, b"antiga\n" * 5)           # 35 bytes
    l2.ler()
    offset_antes = l2.offset

    girado.rename(pasta / "gira.log.1")
    girado.write_bytes(b"nova de outro arquivo\n" * 5)    # 110 bytes: MAIOR
    checa(girado.stat().st_size > offset_antes,
          "o arquivo novo e' MAIOR que o offset antigo (o tamanho nao denuncia)")

    linhas, recomecou = l2.ler()
    checa(recomecou,
          "*** a rotacao e' detectada pela IDENTIDADE do arquivo, nao pelo tamanho ***")
    checa_igual(len(linhas), 5, "e as 5 linhas do arquivo novo saem inteiras")
    checa_igual(linhas[0], "nova de outro arquivo",
                "comecando pela PRIMEIRA linha dele, e nao do meio")

    secao("Arquivo que some no meio da rotacao")
    sumido = pasta / "some.log"
    sumido.write_bytes(b"a\n")
    l3 = LeitorIncremental(sumido, "utf-8")
    l3.ler()
    sumido.unlink()
    checa_igual(l3.ler(), ([], False),
                "arquivo ausente nao levanta -- a proxima volta o acha de novo")
    sumido.write_bytes(b"voltou\n")
    linhas, recomecou = l3.ler()
    checa(recomecou and linhas == ["voltou"],
          "e quando ele volta, a leitura recomeca do inicio")


def testar_contexto(pasta: pathlib.Path) -> None:
    secao("ir_para_o_fim: o `-n N` do tail")

    alvo = pasta / "contexto.log"
    alvo.write_bytes(b"".join(f"linha {n}\n".encode() for n in range(1000)))

    leitor = LeitorIncremental(alvo, "utf-8")
    contexto = leitor.ir_para_o_fim(20)
    checa_igual(len(contexto), 20, "devolve as 20 ultimas linhas")
    checa_igual(contexto[-1], "linha 999", "terminando na ultima do arquivo")
    checa_igual(contexto[0], "linha 980", "e comecando 20 antes")
    checa_igual(leitor.offset, alvo.stat().st_size,
                "o offset ficou no FIM: as linhas de contexto nao serao repetidas")

    escrever(alvo, b"linha 1000\n")
    linhas, _ = leitor.ler()
    checa_igual(linhas, ["linha 1000"],
                "*** e a linha nova sai UMA vez so' (sem repetir o contexto) ***")

    l2 = LeitorIncremental(alvo, "utf-8")
    checa_igual(l2.ir_para_o_fim(0), [],
                "sem contexto pedido, nao devolve nada")
    checa_igual(l2.offset, alvo.stat().st_size, "mas posiciona no fim do mesmo jeito")

    vazio = pasta / "vazio.log"
    vazio.write_bytes(b"")
    l3 = LeitorIncremental(vazio, "utf-8")
    checa_igual(l3.ir_para_o_fim(20), [], "arquivo vazio: nenhum contexto")

    curto = pasta / "curto.log"
    curto.write_bytes(b"so uma\n")
    l4 = LeitorIncremental(curto, "utf-8")
    checa_igual(l4.ir_para_o_fim(20), ["so uma"],
                "pedindo 20 linhas de um arquivo com 1, devolve a unica")


# ===========================================================================
# Parte com Qt
# ===========================================================================


def esperar(condicao, limite_s: float = 10.0) -> bool:
    """Bombeia a fila de eventos ate' a condicao valer (ou o tempo acabar)."""
    from PySide6.QtCore import QCoreApplication

    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        QCoreApplication.processEvents()
        if condicao():
            return True
        time.sleep(0.02)
    QCoreApplication.processEvents()
    return bool(condicao())


def testar_acompanhador(pasta: pathlib.Path) -> None:
    secao("Acompanhador em thread propria")

    from textforge.vigia import Acompanhador

    alvo = pasta / "vivo.log"
    alvo.write_bytes(b"antiga 1\nantiga 2\n")

    recebidas: list[str] = []
    parciais: list[str] = []
    recomecos: list[int] = []
    acompanhador = Acompanhador(alvo, "utf-8", intervalo_ms=50,
                                linhas_de_contexto=5)
    acompanhador.linhas_novas.connect(recebidas.extend)
    acompanhador.parcial.connect(parciais.append)
    acompanhador.recomecou.connect(lambda: recomecos.append(1))
    acompanhador.start()

    checa(esperar(lambda: len(recebidas) >= 2),
          "as linhas de contexto chegam ao ligar")
    checa_igual(recebidas[:2], ["antiga 1", "antiga 2"],
                "e sao as que ja' estavam no arquivo")

    escrever(alvo, b"nova 1\nnova 2\n")
    checa(esperar(lambda: len(recebidas) >= 4),
          "as linhas gravadas depois tambem chegam")
    checa_igual(recebidas[2:4], ["nova 1", "nova 2"], "na ordem certa")

    secao("Pausar para de consumir; retomar continua do offset")
    from PySide6.QtCore import QCoreApplication

    acompanhador.pausar()
    checa(acompanhador.pausado, "o acompanhador se declara pausado")
    # Drena o que ja' tinha saido antes da pausa. `pausar()` garante que nenhuma
    # leitura NOVA comeca, mas um lote lido no instante anterior ainda pode estar
    # na fila de eventos -- e ele chega de proposito, porque descarta-lo perderia
    # linhas para sempre (o offset ja' avancou).
    time.sleep(0.2)
    QCoreApplication.processEvents()
    quantas = len(recebidas)

    escrever(alvo, b"durante a pausa 1\ndurante a pausa 2\n")
    time.sleep(0.5)                             # 10 voltas do intervalo de 50 ms
    QCoreApplication.processEvents()
    checa_igual(len(recebidas), quantas,
                "*** pausado, nenhuma leitura NOVA acontece ***")

    acompanhador.retomar()
    checa(not acompanhador.pausado, "retomado")
    checa(esperar(lambda: len(recebidas) >= quantas + 2),
          "*** e as linhas da pausa aparecem: retomar continua do offset ***")
    checa_igual(recebidas[quantas:quantas + 2],
                ["durante a pausa 1", "durante a pausa 2"],
                "sem perder nem repetir nenhuma")
    checa_igual(len(recebidas), len(set(recebidas)) + recebidas.count(""),
                "nenhuma linha foi entregue DUAS vezes")

    secao("Truncamento visto pelo acompanhador")
    alvo.write_bytes(b"")
    escrever(alvo, b"depois do truncamento\n")
    checa(esperar(lambda: recomecos and "depois do truncamento" in recebidas),
          "o sinal 'recomecou' e a linha nova chegam")

    secao("Encerrar")
    checa(acompanhador.encerrar(3000),
          "*** encerrar() para a thread em menos de 3 s ***")
    checa(not acompanhador.isRunning(), "e a thread nao esta' mais rodando")
    acompanhador.encerrar(1000)
    checa(True, "encerrar() duas vezes nao estoura")


def testar_view(pasta: pathlib.Path) -> None:
    secao("View ao vivo: teto de memoria e rolagem")

    from textforge import configuracao
    from textforge.interface import tema as tmod
    from textforge.visualizadores.registro_ao_vivo import VisualizadorAoVivo

    alvo = pasta / "view.log"
    alvo.write_bytes(b"")
    cfg = configuracao.padrao()
    cfg["tail_linhas_maximas"] = 300
    cfg["tail_intervalo_ms"] = 50
    vista = VisualizadorAoVivo(alvo, "utf-8", cfg, tmod.embutido("escuro"))
    vista.resize(800, 400)
    vista.show()

    checa(not vista.editavel, "a view ao vivo se declara NAO editavel")
    checa(vista.texto.isReadOnly(), "e o campo de texto e' somente leitura")
    checa_igual(vista.texto.maximumBlockCount(), 300,
                "o teto de blocos vem da configuracao")

    vista.acrescentar([f"linha {n}" for n in range(1000)])
    checa(vista.texto.blockCount() <= 300,
          f"*** 1000 linhas nao passam do teto de 300 blocos "
          f"(ficaram {vista.texto.blockCount()}) ***")
    conteudo = vista.texto.toPlainText()
    checa("linha 999" in conteudo, "a linha mais RECENTE esta' na tela")
    checa("linha 0" not in conteudo.split("\n")[0],
          "e a mais antiga foi descartada")

    secao("Rolagem automatica so' quando o usuario esta' no fim")
    barra = vista.texto.verticalScrollBar()
    barra.setValue(barra.maximum())
    vista.acrescentar(["chegou agora"])
    checa(barra.value() >= barra.maximum() - 4,
          "estando no fim, a tela acompanha a linha nova")

    barra.setValue(0)                       # o usuario rolou para o TOPO
    vista.acrescentar([f"mais {n}" for n in range(20)])
    checa_igual(barra.value(), 0,
                "*** rolado para cima, a linha nova NAO puxa a tela de volta ***")

    secao("Parcial e limpar")
    vista.definir_parcial("2026-08-13 ERRO: fal")
    checa(vista.parcial.isVisible(), "a linha parcial aparece separada")
    checa_igual(vista.parcial.text(), "2026-08-13 ERRO: fal", "com o texto certo")
    checa("2026-08-13 ERRO: fal" not in vista.texto.toPlainText(),
          "e NAO entra no corpo do log (viraria uma linha errada no historico)")
    vista.definir_parcial("")
    checa(not vista.parcial.isVisible(), "some quando a linha completa")

    # O ARQUIVO, e nao a tela. A condicao anterior era
    # `alvo.exists() and st_size == 0 or True`: o `st_size == 0` era FALSO (o
    # arquivo tem conteudo), e o `or True` escondia isso -- ela nunca verificou o
    # que o rotulo prometia.
    antes_de_limpar = alvo.read_bytes()
    vista.limpar()
    checa_igual(vista.texto.toPlainText(), "", "limpar esvazia a TELA")
    checa_igual(alvo.read_bytes(), antes_de_limpar,
                "*** e o ARQUIVO fica byte a byte igual (limpar e' so' da view) ***")

    secao("Pausar pelo botao")
    vista.iniciar()
    checa(not vista.pausado, "comeca acompanhando")
    vista.alternar()
    checa(vista.pausado, "o botao pausa")
    checa_igual(vista.botao.text(), "Retomar", "e o rotulo vira 'Retomar'")
    vista.alternar()
    checa(not vista.pausado, "e retoma")
    vista.encerrar()
    checa(not vista.acompanhador.isRunning(), "encerrar() para a thread da view")
    vista.deleteLater()


def testar_janela(pasta: pathlib.Path) -> None:
    secao("Integracao com a janela")

    from PySide6.QtCore import QCoreApplication

    from textforge import configuracao
    from textforge.interface.janela import JanelaPrincipal

    alvo = pasta / "janela.log"
    alvo.write_bytes(b"linha inicial\n")

    cfg = configuracao.padrao()
    cfg["tail_intervalo_ms"] = 50
    janela = JanelaPrincipal(cfg)
    janela.resize(900, 600)
    checa(janela.abrir_arquivo(str(alvo)), "a janela abre o log")

    aba = janela.abas.aba_atual()
    checa(janela.iniciar_acompanhamento(), "iniciar_acompanhamento funciona")
    checa(aba.tem_view("tail"), "a view 'tail' foi registrada")
    checa_igual(aba.view_atual(), "tail", "e a aba trocou para ela")

    qacao = janela.vinculos.qacao("ferramentas.acompanhar")
    checa(qacao is not None and qacao.isChecked(),
          "o item de menu ficou MARCADO")
    checa(str(alvo) in [str(pathlib.Path(p)) for p in janela.vigia._pausados],
          "*** o vigia de alteracao externa fica calado durante o tail ***")

    vista = aba.view("tail")
    escrever(alvo, b"chegou pela janela\n")
    checa(esperar(lambda: "chegou pela janela" in vista.texto.toPlainText()),
          "a linha gravada aparece na view")

    janela.parar_acompanhamento()
    QCoreApplication.processEvents()
    checa(not aba.tem_view("tail"), "parar_acompanhamento descarta a view")
    checa_igual(aba.view_atual(), "texto", "e volta para o editor")
    checa(qacao is not None and not qacao.isChecked(),
          "o item de menu foi desmarcado")
    checa(str(alvo) not in [str(pathlib.Path(p))
                            for p in janela.vigia._pausados],
          "e o vigia volta a avisar sobre alteracao externa")

    secao("Fechar a aba com o tail ligado nao deixa thread viva")
    janela.iniciar_acompanhamento()
    vista = aba.view("tail")
    acompanhador = vista.acompanhador
    janela.abas.fechar(janela.abas.indexOf(aba))
    QCoreApplication.processEvents()
    checa(not acompanhador.isRunning(),
          "*** fechar a aba encerra a thread do acompanhamento ***")

    janela.close()


def main() -> int:
    with pasta_temporaria("textforge-tail-") as pasta:
        testar_leitura_incremental(pasta)
        testar_multibyte_na_fronteira(pasta)
        testar_linha_parcial(pasta)
        testar_truncamento_e_rotacao(pasta)
        testar_contexto(pasta)
        if TEM_QT:
            testar_acompanhador(pasta)
            testar_view(pasta)
            testar_janela(pasta)
        else:
            print("\nPULADO: PySide6 nao instalado — so' a leitura foi verificada")
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
