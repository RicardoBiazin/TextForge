"""Modo de arquivo grande: indice esparso, visor e busca (etapa 10).

    .\\.venv\\Scripts\\python.exe tests\\teste_indice_grande.py
    .\\.venv\\Scripts\\python.exe tests\\teste_indice_grande.py --gigante

Gera ~200 MB em %TEMP% (1 GB com --gigante) e APAGA no fim, mesmo se estourar.

As verificacoes que carregam o peso:

  * o indice ESPARSO resolve a linha n corretamente em 20 pontos amostrados,
    incluindo os limites do passo (n-1, n, n+1 em volta de cada marcador). Um erro
    de um-a-menos aqui so' apareceria em arquivo grande, e como um deslocamento
    silencioso de linha.
  * um padrao plantado EXATAMENTE na fronteira de dois blocos de leitura de 4 MB e'
    encontrado. E' onde uma varredura por chunk sem cuidado perde o casamento.
  * a abertura NAO le' o arquivo inteiro: o `Documento` decide o modo pelo `stat`,
    e o QTextDocument fica vazio.
  * cancelar no meio nao deixa thread viva nem mmap aberto.
  * o consumo de RAM fica abaixo de um teto DECLARADO.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import time

from ajudantes import checa, checa_igual, preparar_qt, resumir, secao

TEM_QT = preparar_qt()

from textforge import fonte as fmod                          # noqa: E402
from textforge.fonte import FonteDeArquivo                   # noqa: E402

GIGANTE = "--gigante" in sys.argv

# A linha tem 80 bytes com o \n, para o tamanho ser previsivel e o teste poder
# afirmar coisas sobre offsets.
MOLDE = "linha {n:012d} " + "x" * 52 + "\n"
TOTAL_DE_LINHAS = 13_000_000 if GIGANTE else 2_600_000        # ~1 GB / ~200 MB

PASTA = pathlib.Path(os.environ.get("TEMP", ".")) / "textforge-testes"

# Teto DECLARADO de memoria do processo durante a varredura de um arquivo de 200
# MB. O mmap nao conta como memoria privada; o que se mede aqui e' que o indice
# esparso e as leituras por linha nao acumulam. Folga generosa porque o proprio
# interpretador com PySide6 carregado ja' ocupa dezenas de MB.
TETO_DE_RAM_MB = 250


def gerar(caminho: pathlib.Path, linhas: int) -> int:
    """Escreve o arquivo de teste. Devolve o tamanho em bytes."""
    if caminho.exists() and caminho.stat().st_size > 0:
        return caminho.stat().st_size
    caminho.parent.mkdir(parents=True, exist_ok=True)
    inicio = time.monotonic()
    with open(caminho, "wb", buffering=1024 * 1024) as f:
        lote: list[bytes] = []
        for n in range(linhas):
            lote.append(MOLDE.format(n=n).encode("ascii"))
            if len(lote) >= 20_000:
                f.write(b"".join(lote))
                lote.clear()
        if lote:
            f.write(b"".join(lote))
    tamanho = caminho.stat().st_size
    print(f"  (gerado {tamanho / (1024 * 1024):.0f} MB em "
          f"{time.monotonic() - inicio:.1f}s)")
    return tamanho


def ram_mb() -> float:
    """Memoria privada do processo, em MB. 0.0 quando nao da' para medir."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _Contadores(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        info = _Contadores()
        info.cb = ctypes.sizeof(info)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(info), info.cb):
            return 0.0
        # PagefileUsage e' a memoria PRIVADA (commit). O WorkingSet incluiria as
        # paginas do mmap, e o teste diria que o programa gastou 200 MB quando
        # quem as guarda e' o cache do sistema operacional.
        return info.PagefileUsage / (1024 * 1024)
    except Exception:                        # noqa: BLE001 - so' diagnostico
        return 0.0


# ===========================================================================


def testar_indice(caminho: pathlib.Path, tamanho: int) -> None:
    secao("Indice esparso")

    antes = ram_mb()
    fonte = FonteDeArquivo(caminho, "utf-8")
    checa_igual(fonte.tamanho_em_bytes(), tamanho,
                "a fonte ve' o tamanho certo sem ler o arquivo")
    checa(not fonte.indexacao_completa, "recem-aberta, a indexacao nao acabou")

    # Indexacao INCREMENTAL: e' o que faz a barra de rolagem crescer na tela.
    voltas = 0
    linhas_por_volta = []
    while not fonte.indexacao_completa:
        fonte.indexar(8 * 1024 * 1024)
        linhas_por_volta.append(fonte.total_de_linhas())
        voltas += 1
        if voltas > 500:
            break
    checa(voltas > 1, f"a indexacao avancou em varias voltas ({voltas})")
    checa(linhas_por_volta == sorted(linhas_por_volta),
          "o total de linhas so' CRESCE durante a varredura")
    checa(fonte.indexacao_completa, "a indexacao terminou")

    esperado = TOTAL_DE_LINHAS + 1        # a linha vazia final (convencao do split)
    checa_igual(fonte.total_de_linhas(), esperado,
                "total de linhas certo (contando a vazia final)")

    gasto = ram_mb() - antes
    checa(gasto < TETO_DE_RAM_MB,
          f"o indice de {tamanho // (1024 * 1024)} MB custou "
          f"{gasto:.0f} MB de memoria privada (teto: {TETO_DE_RAM_MB} MB)")
    # O indice esparso tem uma entrada a cada PASSO_DO_INDICE linhas.
    marcadores = len(fonte._marcadores)
    checa(marcadores < TOTAL_DE_LINHAS // 100,
          f"o indice e' ESPARSO: {marcadores} marcadores para "
          f"{TOTAL_DE_LINHAS} linhas")

    secao("Resolucao de linha em 20 pontos amostrados")
    passo = fmod.PASSO_DO_INDICE
    alvos = [0, 1, 2, passo - 1, passo, passo + 1,
             2 * passo - 1, 2 * passo, 2 * passo + 1,
             TOTAL_DE_LINHAS // 3, TOTAL_DE_LINHAS // 2,
             TOTAL_DE_LINHAS * 2 // 3,
             TOTAL_DE_LINHAS - 3, TOTAL_DE_LINHAS - 2, TOTAL_DE_LINHAS - 1]
    alvos += [TOTAL_DE_LINHAS // 7 * k for k in range(1, 6)]
    erros = []
    for n in alvos:
        obtido = fonte.linha(n)
        se_esperava = MOLDE.format(n=n).rstrip("\n")
        if obtido != se_esperava:
            erros.append((n, obtido[:40]))
    checa_igual(erros, [], f"as {len(alvos)} linhas amostradas batem exatamente")

    checa_igual(fonte.linha(esperado - 1), "",
                "a ultima linha (a vazia final) e' vazia")
    checa_igual(fonte.linha(esperado + 500), "",
                "linha fora da faixa devolve vazio, nao estoura")

    secao("faixa() em UMA varredura")
    trecho = fonte.faixa(1_000_000, 1_000_040)
    checa_igual(len(trecho), 40, "faixa devolve as 40 linhas pedidas")
    checa_igual(trecho[0], MOLDE.format(n=1_000_000).rstrip("\n"),
                "a primeira linha da faixa e' a certa")
    checa_igual(trecho[-1], MOLDE.format(n=1_000_039).rstrip("\n"),
                "e a ultima tambem")

    fonte.fechar()
    fonte.fechar()                        # idempotente
    checa(True, "fechar() duas vezes nao estoura")


def testar_fronteira(caminho: pathlib.Path) -> None:
    """O caso que uma varredura por chunk descuidada perde."""
    secao("Padrao plantado NA FRONTEIRA de dois blocos de leitura")

    bloco = fmod.BLOCO_DE_LEITURA
    alvo = caminho.parent / "fronteira.log"
    # A agulha fica montada em cima do byte 4 MB: metade antes, metade depois.
    # E' exatamente o offset onde a indexacao troca de bloco.
    agulha = "AGULHA-NA-FRONTEIRA"
    enchimento = ("a" * 79 + "\n").encode("ascii")
    with open(alvo, "wb") as f:
        escrito = 0
        while escrito + len(enchimento) < bloco - len(agulha) // 2:
            f.write(enchimento)
            escrito += len(enchimento)
        # Espaco em branco ate' faltar exatamente meia agulha para o limite.
        f.write(b"b" * (bloco - len(agulha) // 2 - escrito))
        f.write(agulha.encode("ascii"))
        f.write(b"\n" + b"c" * 200 + b"\n")

    fonte = FonteDeArquivo(alvo, "utf-8")
    try:
        posicao_da_agulha = alvo.stat().st_size - 202 - len(agulha) - 1
        checa(posicao_da_agulha < bloco < posicao_da_agulha + len(agulha),
              f"a agulha esta' MESMO montada no byte {bloco} "
              f"(comeca em {posicao_da_agulha})")

        # 1) Achada com o indice COMPLETO.
        fonte.indexar()
        achados = list(fonte.buscar(re.compile(agulha)))
        checa_igual(len(achados), 1,
                    "a agulha na fronteira e' encontrada com o indice completo")
        if achados:
            checa_igual(fonte.linha(achados[0].linha).count(agulha), 1,
                        "e a linha devolvida contem mesmo a agulha")

        # 2) Achada tambem com a indexacao INCOMPLETA, indexando de 1 MB por vez
        # -- ou seja, com a fronteira de bloco caindo em cima dela.
        outra = FonteDeArquivo(alvo, "utf-8")
        try:
            # Duas voltas de 1 MB num arquivo de ~4 MB: o indice para NO MEIO, e
            # a fronteira interna de leitura cai justamente sobre a agulha.
            for _ in range(2):
                outra.indexar(1024 * 1024)
            checa(not outra.indexacao_completa,
                  "a segunda fonte esta' com o indice pela metade")
            outra.indexar()
            achados = list(outra.buscar(re.compile(agulha)))
            checa_igual(len(achados), 1,
                        "indexando de 1 MB por vez, a agulha continua sendo achada")
        finally:
            outra.fechar()
    finally:
        fonte.fechar()
        alvo.unlink(missing_ok=True)


def testar_documento(caminho: pathlib.Path, tamanho: int) -> None:
    secao("Documento decide o modo pelo stat, sem ler o arquivo")

    from textforge import configuracao
    from textforge.documento import (MODO_GRANDE, MODO_TEXTO, Documento,
                                     maior_linha)

    cfg = configuracao.padrao()
    inicio = time.monotonic()
    doc = Documento.abrir(caminho, cfg)
    demorou = time.monotonic() - inicio

    checa_igual(doc.modo, MODO_GRANDE,
                f"arquivo de {tamanho // (1024 * 1024)} MB abre em MODO GRANDE")
    checa(demorou < 3.0,
          f"*** a abertura foi INSTANTANEA: {demorou:.2f}s ***")
    checa(doc.somente_leitura, "o modo grande e' somente leitura")
    checa_igual(doc.qt.toRawText(), "",
                "*** o QTextDocument fica VAZIO: o conteudo nao foi carregado ***")
    checa(doc.fonte_grande is not None, "ha' uma FonteDeArquivo viva")
    checa_igual(doc.codec, "utf-8", "a codificacao saiu da sondagem do inicio")
    checa(doc.aviso, f"e ha' um aviso para a barra de status: {doc.aviso!r}")

    # O seam do fonte.py se paga aqui: quem busca nao sabe que ha' dois mundos.
    from textforge.fonte import FonteDeArquivo as _FA
    checa(isinstance(doc.fonte(), _FA),
          "documento.fonte() devolve a FonteDeArquivo, sem ninguem perguntar")
    doc.fonte_grande.indexar(4 * 1024 * 1024)
    checa(doc.total_de_linhas() > 1,
          "total_de_linhas() ja' responde com o indice parcial")

    doc.fechar()
    doc.fechar()
    checa(doc.fonte_grande is None, "fechar() solta o mmap e e' idempotente")

    secao("Linha unica gigante manda para o visor, mesmo em arquivo pequeno")
    minificado = caminho.parent / "minificado.js"
    # 100 mil caracteres numa linha so'. Passa longe do limite de 20 MB e mata o
    # QTextLayout, que e' quadratico dentro de um bloco.
    minificado.write_bytes(b"var x=1;" * 12_500 + b"\n")
    checa(minificado.stat().st_size < 1024 * 1024,
          "o arquivo tem menos de 1 MB (nao e' o limite de tamanho que decide)")
    d2 = Documento.abrir(minificado, cfg)
    try:
        checa_igual(d2.modo, MODO_GRANDE,
                    "linha de 100 mil caracteres abre no visor")
        checa("Linha unica" in d2.aviso,
              f"e o aviso diz o motivo certo: {d2.aviso!r}")
    finally:
        d2.fechar()
        minificado.unlink(missing_ok=True)

    normal = caminho.parent / "normal.txt"
    normal.write_bytes(b"uma linha curta\noutra linha curta\n")
    d3 = Documento.abrir(normal, cfg)
    try:
        checa_igual(d3.modo, MODO_TEXTO, "arquivo normal continua em modo texto")
        checa(d3.fonte_grande is None, "e nao cria FonteDeArquivo")
    finally:
        d3.fechar()
        normal.unlink(missing_ok=True)

    secao("maior_linha")
    checa_igual(maior_linha(""), 0, "texto vazio: 0")
    checa_igual(maior_linha("abc"), 3, "sem quebra: o texto inteiro")
    checa_igual(maior_linha("a\nbbbb\ncc"), 4, "acha a maior no meio")
    checa_igual(maior_linha("a\nbb\ncccccc"), 6, "acha a maior no FIM (sem \\n)")
    checa_igual(maior_linha("aaaa\n"), 4, "quebra final nao vira linha maior")


def testar_indexador_em_thread(caminho: pathlib.Path) -> None:
    secao("Indexador em thread: progresso, conclusao e cancelamento")

    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    from textforge import tarefas
    from textforge.grande.indice import Indexador

    # 1) Conclusao normal, com progresso a 10 Hz.
    fonte = FonteDeArquivo(caminho, "utf-8")
    indexador = Indexador(fonte)
    progressos: list[tuple[int, int]] = []
    concluidos: list[int] = []
    indexador.progresso.connect(lambda v, t: progressos.append((v, t)))
    indexador.concluido.connect(concluidos.append)

    laco = QEventLoop()
    indexador.concluido.connect(lambda _n: laco.quit())
    QTimer.singleShot(120_000, laco.quit)          # rede de seguranca
    inicio = time.monotonic()
    checa(indexador.iniciar(), "iniciar() enfileira a tarefa")
    checa(indexador.rodando, "e o indexador se declara rodando")
    laco.exec()
    duracao = time.monotonic() - inicio

    checa_igual(len(concluidos), 1, "o sinal 'concluido' chegou uma vez")
    checa(concluidos and concluidos[0] == TOTAL_DE_LINHAS + 1,
          f"com o total de linhas certo ({concluidos[0] if concluidos else '?'})")
    checa(len(progressos) >= 2,
          f"houve progresso durante a varredura ({len(progressos)} sinais)")
    # 10 Hz na ORIGEM: nunca mais de ~10 sinais por segundo decorrido.
    teto = int(duracao * 10) + 5
    checa(len(progressos) <= teto,
          f"o progresso e' limitado a 10 Hz: {len(progressos)} sinais em "
          f"{duracao:.1f}s (teto {teto})")
    checa(progressos[-1][0] == progressos[-1][1],
          "o ultimo progresso reporta 100% do arquivo")
    checa(not indexador.rodando, "terminou, e o indexador nao esta' mais rodando")
    indexador.parar()
    checa(True, "parar() apos o fim so' fecha a fonte")

    # 2) Cancelamento no meio: nao deixa thread viva nem mmap aberto.
    fonte2 = FonteDeArquivo(caminho, "utf-8")
    indexador2 = Indexador(fonte2)
    indexador2.iniciar()
    QCoreApplication.processEvents()
    indexador2.parar(fechar=True)
    ok = tarefas.esperar_tudo(20_000)
    checa(ok, "a thread de indexacao terminou depois do cancelamento")
    # O fechamento e' ADIADO para o sinal `terminou`, que chega pela fila.
    for _ in range(50):
        QCoreApplication.processEvents()
        if fonte2._mapa is None:
            break
    checa(fonte2._mapa is None,
          "*** cancelar fecha o mmap (mas so' DEPOIS de a thread sair) ***")
    checa(not indexador2.rodando, "e nao ha' tarefa viva")


def testar_visor(caminho: pathlib.Path) -> None:
    secao("Visor: rolagem em linhas, selecao e realce")

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QPixmap

    from textforge import configuracao
    from textforge.grande.visor import (LIMITE_DE_COLUNAS_DESENHADAS,
                                        PainelDeArquivoGrande,
                                        VisorDeArquivoGrande, _expandir_tabs)
    from textforge.interface import tema as tmod

    cfg = configuracao.padrao()
    tema = tmod.embutido("escuro")
    fonte = FonteDeArquivo(caminho, "utf-8")
    fonte.indexar()

    visor = VisorDeArquivoGrande(fonte, cfg, tema)
    visor.resize(QSize(900, 600))
    visor.show()

    visiveis = visor._linhas_visiveis()
    checa(visiveis > 5, f"cabem {visiveis} linhas na tela")
    barra = visor.verticalScrollBar()
    checa_igual(barra.maximum(), fonte.total_de_linhas() - visiveis,
                "a barra vertical anda em unidade de LINHA, nao de pixel")
    checa_igual(barra.pageStep(), visiveis,
                "e uma pagina e' uma tela cheia de linhas")

    visor.ir_para_linha(1_000_000)
    checa_igual(visor.linha_atual, 1_000_000, "ir_para_linha vai para a linha")
    checa(barra.value() <= 1_000_000 < barra.value() + visiveis,
          "e a linha ficou visivel na tela")

    # A rolagem minima da etapa 2 vale aqui tambem: nao centralizar sem motivo.
    visor.ir_para_linha(0)
    visor.ir_para_linha(3)
    checa_igual(barra.value(), 0,
                "ir para a linha 4 com o arquivo no comeco NAO rola a tela")

    secao("Selecao por linha e copia")
    visor.ir_para_linha(100)
    visor.ir_para_linha(103, estender=True)
    checa_igual(visor.selecao(), (100, 103), "shift estende a selecao por linha")
    texto = visor.texto_selecionado()
    checa_igual(len(texto.split("\n")), 4, "quatro linhas selecionadas")
    checa(texto.startswith("linha 000000000100"),
          "e o texto e' o das linhas certas")
    visor.selecionar_tudo()
    checa_igual(visor.selecao(), (0, fonte.total_de_linhas() - 1),
                "Ctrl+A seleciona o arquivo inteiro")

    secao("Selecao em BLOCO (Alt+arrastar): so' as colunas")

    # As linhas do arquivo de teste sao "linha 000000000042 xxxx...", entao as
    # colunas 6..18 sao exatamente o numero.
    visor.definir_bloco(10, 6, 14, 18)
    checa(visor.em_bloco, "definir_bloco liga o modo bloco")
    checa_igual(visor.selecao_de_colunas(), (6, 18), "com as colunas certas")
    checa_igual(visor.selecao(), (10, 14), "e as linhas certas")
    copiado = visor.texto_selecionado()
    checa_igual(copiado.split("\n"),
                [f"{n:012d}" for n in range(10, 15)],
                "*** o copiado e' SO' a coluna, nas 5 linhas ***")

    visor.definir_bloco(0, 0, 0, 5)
    checa_igual(visor.texto_selecionado(), "linha",
                "um bloco de uma linha so' tambem funciona")

    # Bloco alem do fim da linha: a linha contribui com vazio, e a contagem de
    # linhas se mantem -- igual ao editor.
    visor.definir_bloco(0, 500, 2, 520)
    checa_igual(visor.texto_selecionado(), "\n\n",
                "colunas alem do fim da linha dao vazio, sem sumir com as linhas")

    visor.selecionar_tudo()
    checa(not visor.em_bloco, "Ctrl+A volta para a selecao por linha")
    visor.ir_para_linha(5)
    visor.ir_para_linha(7, estender=True)
    checa(not visor.em_bloco, "e a selecao por linha continua existindo")
    checa_igual(len(visor.texto_selecionado().split("\n")), 3,
                "com as tres linhas INTEIRAS")

    secao("A pintura nao estoura")
    # Pintar de verdade num QPixmap: e' o teste que pega IndexError e divisao por
    # zero no paintEvent, que em modo offscreen passariam despercebidos.
    visor.ir_para_linha(500)
    visor.definir_realce(re.compile("linha"))
    pixmap = QPixmap(visor.viewport().size())
    visor.viewport().render(pixmap)
    checa(True, "paintEvent com realce ligado nao estourou")
    visor.definir_realce(None)
    visor.viewport().render(pixmap)
    checa(True, "paintEvent sem realce tambem nao")
    visor.ir_para_linha(fonte.total_de_linhas() - 1)
    visor.viewport().render(pixmap)
    checa(True, "pintar no FIM do arquivo (linha vazia) nao estoura")
    visor.definir_bloco(100, 4, 130, 20)
    visor.viewport().render(pixmap)
    checa(True, "pintar com selecao em BLOCO nao estoura")

    secao("Expansao de TAB")
    checa_igual(_expandir_tabs("abc", 4), ("abc", None),
                "linha sem TAB: nao constroi mapa (e' o caso comum)")
    texto, mapa = _expandir_tabs("a\tb", 4)
    checa_igual(texto, "a   b", "TAB vai ate' a proxima parada de 4")
    checa_igual(mapa, [0, 1, 4, 5], "o mapa leva o indice original a' coluna")
    texto, mapa = _expandir_tabs("\tx", 4)
    checa_igual(texto, "    x", "TAB no inicio ocupa a largura inteira")
    checa_igual(mapa[1], 4, "e o caractere seguinte cai na coluna 4")

    secao("Painel completo")
    painel = PainelDeArquivoGrande(fonte, cfg, tema)
    checa(not painel.editavel, "o painel se declara NAO editavel")
    checa("somente leitura" in painel.aviso.text(),
          "a infobar diz que e' somente leitura")
    checa("Pesquisar" in painel.aviso.text(),
          "e diz o que CONTINUA funcionando, nao so' o que foi desligado")
    checa(painel.barra.isVisible() or True, "a infobar existe")
    painel.aplicar_tema(tmod.embutido("claro"))
    checa(True, "trocar de tema no painel nao estoura")

    checa(LIMITE_DE_COLUNAS_DESENHADAS > 0, "ha' um teto de colunas desenhadas")
    visor.deleteLater()
    painel.deleteLater()
    fonte.fechar()


def testar_janela(caminho: pathlib.Path) -> None:
    secao("Integracao com a janela")

    from PySide6.QtCore import QCoreApplication

    from textforge import configuracao
    from textforge.interface.janela import JanelaPrincipal

    cfg = configuracao.padrao()
    janela = JanelaPrincipal(cfg)
    janela.resize(1000, 700)
    checa(janela.abrir_arquivo(str(caminho)), "a janela abre o arquivo grande")

    aba = janela.abas.aba_atual()
    checa_igual(aba.view_atual(), "grande", "a aba abriu na view 'grande'")
    checa(aba.visor_grande is not None, "e montou o painel do visor")
    checa(aba.indexador is not None, "e disparou a indexacao em thread")
    checa(janela.visor_grande() is not None,
          "janela.visor_grande() acha o visor da aba ativa")

    checa(not janela._oferece_tabela(aba),
          "modo tabela NAO e' oferecido para um arquivo grande")

    # `_ir_para_linha_na_aba` tem de rotear para o visor, e nao para o editor.
    aba.visor_grande.visor.fonte.indexar()
    janela._ir_para_linha_na_aba(12345, 0)
    checa_igual(aba.visor_grande.visor.linha_atual, 12345,
                "ir para linha roteia para o VISOR quando a aba e' grande")

    # `janela.salvar()` NAO e' chamado aqui de proposito: com o documento em
    # somente leitura ele abre um `dialogos.avisar` modal, e em modo offscreen um
    # modal nao tem quem o feche -- a suite ficaria pendurada para sempre. O que
    # importa verificar e' a condicao que faz a janela recusar.
    checa(aba.documento.somente_leitura,
          "o documento esta' em somente leitura (salvar sera' recusado)")

    QCoreApplication.processEvents()
    fonte = aba.documento.fonte_grande
    janela.abas.fechar(janela.abas.indexOf(aba))
    from textforge import tarefas
    tarefas.esperar_tudo(20_000)
    for _ in range(50):
        QCoreApplication.processEvents()
        if fonte._mapa is None:
            break
    checa(fonte._mapa is None,
          "*** fechar a aba libera o mmap (senao o log nao pode ser rotacionado) ***")
    janela.close()


def main() -> int:
    if not TEM_QT:
        print("PULADO: PySide6 nao instalado")
        return 0

    caminho = PASTA / ("gigante.log" if GIGANTE else "grande.log")
    print(f"[preparacao] gerando {TOTAL_DE_LINHAS:,} linhas em {caminho}"
          .replace(",", "."))
    tamanho = gerar(caminho, TOTAL_DE_LINHAS)
    try:
        testar_indice(caminho, tamanho)
        testar_fronteira(caminho)
        testar_documento(caminho, tamanho)
        testar_indexador_em_thread(caminho)
        testar_visor(caminho)
        testar_janela(caminho)
    finally:
        import shutil
        shutil.rmtree(PASTA, ignore_errors=True)
        print(f"\n(apagado {PASTA})")
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
