"""Janela principal: sobe, monta os menus, faz zoom e lembra a geometria.

    .venv\\Scripts\\python.exe tests\\teste_janela.py

Roda com QT_QPA_PLATFORM=offscreen, entao NAO prova que a aparencia esta' certa.
Prova o que da' para provar sem olhos: que a janela constroi sem excecao, que os
menus saem do registro, que os comandos ligados funcionam, e que fechar grava as
preferencias -- que e' onde um `closeEvent` quebrado passaria despercebido.
"""

from __future__ import annotations

import sys

from ajudantes import (appdata_temporario, checa, checa_igual, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import configuracao                            # noqa: E402
from textforge.interface import acoes                          # noqa: E402
from textforge.interface.janela import JanelaPrincipal         # noqa: E402

# ---------------------------------------------------------------------------
secao("1 - a janela constroi")

with appdata_temporario():
    cfg = configuracao.padrao()
    janela = JanelaPrincipal(cfg)

    checa(janela.windowTitle().startswith("TextForge"),
          "o titulo da janela traz o nome do programa")
    checa(janela.acceptDrops(),
          "a janela aceita arrastar e soltar (requisito 19)")
    checa(janela.centralWidget() is not None, "existe um widget central")
    checa(janela.statusBar() is not None, "existe barra de status")

    titulos = [a.text().replace("&", "") for a in janela.menuBar().actions()]
    checa_igual(titulos, list(acoes.ORDEM_DOS_MENUS),
                "os 8 menus do requisito 2, na ordem")

    checa(len(janela.ferramentas.actions()) > 0,
          "a barra de ferramentas foi preenchida")

    # ---------------------------------------------------------------------
    secao("2 - comandos ligados e desligados")

    checa(janela.vinculos.tem_tratador("arquivo.sair"),
          "'Sair' esta' ligado nesta etapa")
    checa(janela.vinculos.tem_tratador("exibir.aumentar_zoom"),
          "'Aumentar zoom' esta' ligado nesta etapa")
    checa(not janela.vinculos.tem_tratador("arquivo.abrir"),
          "'Abrir' ainda NAO esta' ligado (entra na etapa 3)")

    qa = janela.vinculos.qacao("arquivo.abrir")
    checa(qa is not None and not qa.isEnabled(),
          "e por isso aparece desabilitado, em vez de fingir funcionar")

    # Todo comando com atalho tem QAction anexado a' janela; sem isso o atalho
    # simplesmente nao dispara, e a falha e' silenciosa.
    com_atalho = [c for c in acoes.REGISTRO.comandos if c.atalho]
    sem_qacao = [c.id for c in com_atalho if janela.vinculos.qacao(c.id) is None]
    checa_igual(sem_qacao, [], "todo comando com atalho virou QAction")

    # ---------------------------------------------------------------------
    secao("3 - zoom")

    cfg["fonte_tamanho"] = 11
    janela.ajustar_zoom(+2)
    checa_igual(cfg["fonte_tamanho"], 13, "aumentar zoom soma ao tamanho")
    janela.ajustar_zoom(-5)
    checa_igual(cfg["fonte_tamanho"], 8, "diminuir zoom subtrai")
    janela.zoom_normal()
    checa_igual(cfg["fonte_tamanho"], configuracao.padrao()["fonte_tamanho"],
                "zoom normal volta ao padrao")

    # Os limites existem para o usuario nao conseguir zerar a fonte com o
    # Ctrl+roda e ficar sem conseguir ler o menu para desfazer.
    for _ in range(50):
        janela.ajustar_zoom(-1)
    checa(cfg["fonte_tamanho"] >= 6, "o zoom tem piso")
    for _ in range(200):
        janela.ajustar_zoom(+1)
    checa(cfg["fonte_tamanho"] <= 48, "o zoom tem teto")

    # ---------------------------------------------------------------------
    secao("4 - barra de ferramentas e tema")

    visivel = janela.ferramentas.isVisible()
    janela.alternar_barra_de_ferramentas()
    checa_igual(cfg["mostrar_barra_de_ferramentas"], not visivel,
                "alternar a barra de ferramentas grava a preferencia")

    from textforge.interface import tema as tmod               # noqa: E402
    janela.aplicar_tema(tmod.embutido("escuro"))
    checa_igual(janela.tema.tipo, "escuro", "aplicar_tema troca o tema escuro")
    janela.aplicar_tema(tmod.embutido("claro"))
    checa_igual(janela.tema.tipo, "claro", "e troca de volta para o claro")

    from PySide6.QtWidgets import QApplication                 # noqa: E402
    paleta = QApplication.instance().palette()
    checa_igual(paleta.window().color().name(),
                janela.tema.cor("janela.fundo").name(),
                "a paleta vai para a QApplication (senao os dialogos nao seguem)")

    # ---------------------------------------------------------------------
    secao("5 - fechar grava as preferencias")

    janela.resize(900, 600)
    janela.close()

    gravado = configuracao.carregar()
    checa(gravado.get("geometria"), "a geometria foi gravada ao fechar")
    checa_igual(gravado.get("fonte_tamanho"), cfg["fonte_tamanho"],
                "o tamanho da fonte foi gravado ao fechar")

    # ---------------------------------------------------------------------
    secao("6 - a geometria e' restaurada, e uma corrompida nao derruba")

    outra = JanelaPrincipal(configuracao.carregar())
    checa(outra.width() > 0 and outra.height() > 0,
          "a janela reabre com a geometria gravada")
    outra.close()

    ruim = configuracao.padrao()
    ruim["geometria"] = "isso nao e base64 valido de QByteArray !!!"
    terceira = JanelaPrincipal(ruim)
    checa(terceira.width() > 0,
          "geometria corrompida no config cai no tamanho padrao, sem estourar")
    terceira.close()

sys.exit(resumir())
