"""Visor de arquivo grande: pinta as linhas visiveis, e mais nada.

Um `QAbstractScrollArea` com `paintEvent` proprio e barra de rolagem em unidade de
LINHA. Nao existe `QTextDocument` aqui, e e' o ponto inteiro do modulo: um
QTextDocument de 1 GB consome varios GB de RAM e congela a interface durante o
layout, mesmo que nada seja editado.

O que isso custa, e esta' escrito na infobar para o usuario nao descobrir sozinho:
sem edicao, sem realce de sintaxe com estado multi-linha, sem minimapa, sem
autocomplete e sem painel Estrutura. O que continua funcionando e' o que importa
num log gigante: rolar, ir para uma linha, PESQUISAR e copiar o que achou.

TRES DECISOES QUE VALEM SER LIDAS ANTES DE MEXER:

1. **A largura maxima e' ESTIMADA, e cresce.** Medir a linha mais longa de um
   arquivo de 1 GB exigiria le-lo inteiro -- ou seja, exatamente o que o modo
   evita. A barra horizontal se ajusta a' maior linha JA VISTA. O efeito e' que ela
   cresce conforme o usuario rola, o que e' honesto: o programa nao sabe o que nao
   leu.

2. **A selecao e' por LINHA, e nao por caractere.** Selecao de caractere exigiria
   mapeamento de coordenada para offset em texto que nao esta' na memoria, com
   ancora sobrevivendo a' rolagem. O gesto real num log e' "pegar estas linhas e
   colar num chamado", e isso a selecao por linha atende inteiro.

3. **A linha desenhada e' CORTADA.** Um arquivo binario aberto por engano pode ter
   200 mil caracteres numa linha; desenhar isso trava a pintura sem mostrar mais
   nada ao usuario, porque nao cabe na tela de qualquer jeito.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QKeyEvent, QPainter,
                           QPaintEvent, QResizeEvent)
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QHBoxLayout,
                               QLabel, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from textforge import log_interno
from textforge.fonte import FonteDeArquivo

log = log_interno.obter(__name__)

# Quantos caracteres de uma linha chegam a ser desenhados. Ver a decisao 3 no
# cabecalho: alem disto nada de novo aparece na tela, so' custo.
LIMITE_DE_COLUNAS_DESENHADAS = 20_000

# Folga entre o numero da linha e a borda da margem, em pixels.
MARGEM_INTERNA = 8


def _expandir_tabs(texto: str, largura: int) -> tuple[str, list[int] | None]:
    """Troca TAB por espacos ate' a proxima parada. Devolve (texto, mapa).

    `QPainter.drawText` nao expande TAB -- desenha um retangulo vazio, e um `.dat`
    de largura fixa perderia justamente o alinhamento que o torna legivel.

    O `mapa` leva o indice do caractere ORIGINAL para a coluna na tela, e e' o que
    permite realcar uma ocorrencia da busca no lugar certo numa linha com TAB. Ele
    e' `None` quando nao ha' TAB nenhum, que e' o caso da esmagadora maioria das
    linhas -- construir uma lista de 20 mil inteiros por linha desenhada, 50 linhas
    por repintura, seria caro por nada.
    """
    if "\t" not in texto:
        return texto, None
    saida: list[str] = []
    mapa: list[int] = []
    coluna = 0
    for ch in texto:
        mapa.append(coluna)
        if ch == "\t":
            passos = largura - (coluna % largura)
            saida.append(" " * passos)
            coluna += passos
        else:
            saida.append(ch)
            coluna += 1
    mapa.append(coluna)                 # posicao final, para o fim de um casamento
    return "".join(saida), mapa


class VisorDeArquivoGrande(QAbstractScrollArea):
    """A grade de linhas. Somente leitura."""

    #: linha atual, em BASE ZERO (a convencao do nucleo -- ver `fonte.py`).
    linha_atual_mudou = Signal(int)

    def __init__(self, fonte: FonteDeArquivo, cfg: dict, tema,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fonte = fonte
        self.cfg = cfg
        self.tema = tema

        self._linha_atual = 0
        self._ancora = 0                 # inicio da selecao por linha
        self._maior_largura_vista = 0    # em pixels; ver a decisao 1
        self._padrao: re.Pattern[str] | None = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.verticalScrollBar().valueChanged.connect(
            lambda _v: self.viewport().update())
        self.horizontalScrollBar().valueChanged.connect(
            lambda _v: self.viewport().update())

        self.aplicar_configuracao(cfg)
        self.aplicar_tema(tema)

    # ==================================================================
    # Aparencia
    # ==================================================================

    def aplicar_configuracao(self, cfg: dict) -> None:
        self.cfg = cfg
        fonte = QFont(str(cfg.get("fonte", "Consolas")),
                      int(cfg.get("fonte_tamanho", 11)))
        fonte.setFixedPitch(True)
        fonte.setStyleHint(QFont.StyleHint.Monospace,
                           QFont.StyleStrategy.PreferDefault)
        self.setFont(fonte)
        metricas = QFontMetrics(fonte)
        # Inteiro, e nao float: linha em posicao fracionaria produz baseline
        # tremida ao rolar, porque cada repintura arredonda de um jeito.
        self._altura_da_linha = max(1, metricas.height())
        self._largura_do_digito = max(1, metricas.horizontalAdvance("0"))
        self._largura_do_tab = int(cfg.get("tabulacao", 4))
        self.atualizar_barras()

    def aplicar_tema(self, tema) -> None:
        self.tema = tema
        self.viewport().setStyleSheet(
            f"background: {tema.cor('editor.fundo').name()};")
        self.viewport().update()

    def _largura_da_margem(self) -> int:
        digitos = max(3, len(str(max(1, self.fonte.total_de_linhas()))))
        return digitos * self._largura_do_digito + 2 * MARGEM_INTERNA

    def _linhas_visiveis(self) -> int:
        return max(1, self.viewport().height() // self._altura_da_linha)

    # ==================================================================
    # Barras de rolagem (em unidade de LINHA)
    # ==================================================================

    def atualizar_barras(self) -> None:
        """Reajusta as barras. Chamado tambem a cada avanco da indexacao.

        E' o que faz a barra de rolagem CRESCER durante a abertura de um arquivo
        de 1 GB, em vez de o usuario esperar a varredura inteira para ver a
        primeira linha.
        """
        total = self.fonte.total_de_linhas()
        visiveis = self._linhas_visiveis()
        vertical = self.verticalScrollBar()
        vertical.setRange(0, max(0, total - visiveis))
        vertical.setPageStep(visiveis)
        vertical.setSingleStep(1)

        util = max(0, self.viewport().width() - self._largura_da_margem())
        horizontal = self.horizontalScrollBar()
        horizontal.setRange(0, max(0, self._maior_largura_vista - util))
        horizontal.setPageStep(max(1, util))
        horizontal.setSingleStep(self._largura_do_digito * 4)

    def resizeEvent(self, evento: QResizeEvent) -> None:      # noqa: N802 - Qt
        super().resizeEvent(evento)
        self.atualizar_barras()

    # ==================================================================
    # Navegacao
    # ==================================================================

    @property
    def linha_atual(self) -> int:
        return self._linha_atual

    def primeira_linha_visivel(self) -> int:
        return self.verticalScrollBar().value()

    def ir_para_linha(self, n: int, *, estender: bool = False) -> None:
        """Leva o cursor de linha para `n` (BASE ZERO) e rola se preciso."""
        total = self.fonte.total_de_linhas()
        n = max(0, min(n, total - 1))
        self._linha_atual = n
        if not estender:
            self._ancora = n
        self.garantir_visivel(n)
        self.viewport().update()
        self.linha_atual_mudou.emit(n)

    def garantir_visivel(self, n: int) -> None:
        """Rola o minimo necessario. Nao centraliza quando ja' esta' na tela.

        Centralizar sempre e' o defeito que a etapa 2 ja' corrigiu no editor: "ir
        para a linha 6" num arquivo aberto no comeco empurraria as linhas 1 a 5
        para fora da tela sem motivo.
        """
        primeira = self.verticalScrollBar().value()
        visiveis = self._linhas_visiveis()
        if n < primeira:
            self.verticalScrollBar().setValue(n)
        elif n >= primeira + visiveis:
            self.verticalScrollBar().setValue(n - visiveis + 1)

    def selecao(self) -> tuple[int, int]:
        """(primeira, ultima) linha selecionada, ambas inclusivas."""
        return (min(self._ancora, self._linha_atual),
                max(self._ancora, self._linha_atual))

    def texto_selecionado(self) -> str:
        inicio, fim = self.selecao()
        return "\n".join(self.fonte.faixa(inicio, fim + 1))

    def selecionar_tudo(self) -> None:
        self._ancora = 0
        self._linha_atual = max(0, self.fonte.total_de_linhas() - 1)
        self.viewport().update()

    def copiar(self) -> bool:
        """Copia as linhas selecionadas. False se o usuario recusou o tamanho.

        O teto existe porque selecionar tudo num arquivo de 1 GB e copiar
        derrubaria a sessao do Windows -- a area de transferencia nao e' o lugar
        para um gigabyte.
        """
        inicio, fim = self.selecao()
        limite = int(self.cfg.get("limite_copia_mb", 64)) * 1024 * 1024
        # Estimativa pelo TAMANHO DO ARQUIVO, e nao lendo as linhas: ler para
        # descobrir que e' grande demais ja' seria o dano que se quer evitar.
        total = max(1, self.fonte.total_de_linhas())
        estimado = self.fonte.tamanho_em_bytes() * (fim - inicio + 1) // total
        if estimado > limite:
            from textforge.interface import dialogos
            if not dialogos.confirmar(
                    self, "Copiar um trecho grande",
                    f"A selecao tem cerca de {estimado // (1024 * 1024)} MB.<br><br>"
                    "Copiar tudo isso para a area de transferencia pode deixar o "
                    "Windows lento por varios segundos. Continuar?",
                    perigoso=True):
                return False
        QApplication.clipboard().setText(self.texto_selecionado())
        return True

    def definir_realce(self, padrao: re.Pattern[str] | None) -> None:
        """Padrao a realcar nas linhas visiveis (a busca chama isto)."""
        self._padrao = padrao
        self.viewport().update()

    # ==================================================================
    # Teclado e mouse
    # ==================================================================

    def keyPressEvent(self, evento: QKeyEvent) -> None:       # noqa: N802 - Qt
        tecla = evento.key()
        mods = evento.modifiers()
        estender = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        pagina = self._linhas_visiveis()
        ultimo = max(0, self.fonte.total_de_linhas() - 1)

        if ctrl and tecla == Qt.Key.Key_C:
            self.copiar()
        elif ctrl and tecla == Qt.Key.Key_A:
            self.selecionar_tudo()
        elif tecla == Qt.Key.Key_Up:
            self.ir_para_linha(self._linha_atual - 1, estender=estender)
        elif tecla == Qt.Key.Key_Down:
            self.ir_para_linha(self._linha_atual + 1, estender=estender)
        elif tecla == Qt.Key.Key_PageUp:
            self.ir_para_linha(self._linha_atual - pagina, estender=estender)
        elif tecla == Qt.Key.Key_PageDown:
            self.ir_para_linha(self._linha_atual + pagina, estender=estender)
        elif tecla == Qt.Key.Key_Home:
            if ctrl:
                self.ir_para_linha(0, estender=estender)
            else:
                self.horizontalScrollBar().setValue(0)
        elif tecla == Qt.Key.Key_End and ctrl:
            self.ir_para_linha(ultimo, estender=estender)
        else:
            super().keyPressEvent(evento)
            return
        evento.accept()

    def mousePressEvent(self, evento) -> None:                # noqa: N802 - Qt
        if evento.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(evento)
            return
        alvo = (self.verticalScrollBar().value()
                + int(evento.position().y()) // self._altura_da_linha)
        self.ir_para_linha(
            alvo,
            estender=bool(evento.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        self.setFocus()

    def mouseMoveEvent(self, evento) -> None:                 # noqa: N802 - Qt
        if evento.buttons() & Qt.MouseButton.LeftButton:
            alvo = (self.verticalScrollBar().value()
                    + int(evento.position().y()) // self._altura_da_linha)
            self.ir_para_linha(alvo, estender=True)

    # ==================================================================
    # Pintura
    # ==================================================================

    def paintEvent(self, _evento: QPaintEvent) -> None:       # noqa: N802 - Qt
        pintor = QPainter(self.viewport())
        pintor.setFont(self.font())
        tema = self.tema

        largura_margem = self._largura_da_margem()
        altura = self._altura_da_linha
        primeira = self.verticalScrollBar().value()
        # +1 para a linha parcialmente visivel no rodape nao ficar em branco.
        quantas = self._linhas_visiveis() + 1
        deslocamento = self.horizontalScrollBar().value()

        pintor.fillRect(self.viewport().rect(), tema.cor("editor.fundo"))
        pintor.fillRect(QRect(0, 0, largura_margem, self.viewport().height()),
                        tema.cor("editor.margem_fundo"))

        # UMA chamada a `faixa()` para todas as linhas da tela: uma busca no
        # indice, e nao uma por linha.
        linhas = self.fonte.faixa(primeira, primeira + quantas)
        sel_inicio, sel_fim = self.selecao()
        tem_selecao = sel_inicio != sel_fim
        metricas = QFontMetrics(self.font())

        largura_antes = self._maior_largura_vista
        for i, texto in enumerate(linhas):
            numero = primeira + i
            topo = i * altura
            area = QRect(largura_margem, topo,
                         self.viewport().width() - largura_margem, altura)

            if sel_inicio <= numero <= sel_fim:
                cor = ("editor.selecao" if tem_selecao else "editor.linha_atual")
                pintor.fillRect(area, tema.cor(cor))

            # -- numero da linha ---------------------------------------------
            eh_atual = numero == self._linha_atual
            pintor.setPen(tema.cor("editor.margem_texto_atual" if eh_atual
                                   else "editor.margem_texto"))
            pintor.drawText(
                QRect(0, topo, largura_margem - MARGEM_INTERNA, altura),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                str(numero + 1))

            # -- o texto ------------------------------------------------------
            recorte = texto[:LIMITE_DE_COLUNAS_DESENHADAS]
            exibido, mapa = _expandir_tabs(recorte, self._largura_do_tab)
            x = largura_margem - deslocamento
            self._maior_largura_vista = max(
                self._maior_largura_vista, metricas.horizontalAdvance(exibido))

            if self._padrao is not None:
                self._pintar_ocorrencias(pintor, recorte, mapa, x, topo, altura)

            pintor.setPen(tema.cor("editor.texto_da_selecao" if tem_selecao
                                   and sel_inicio <= numero <= sel_fim
                                   else "editor.texto"))
            pintor.drawText(x, topo + metricas.ascent(), exibido)

        pintor.setPen(tema.cor("editor.margem_borda"))
        pintor.drawLine(largura_margem - 1, 0,
                        largura_margem - 1, self.viewport().height())
        pintor.end()

        # A maior largura pode ter crescido nesta pintura (decisao 1). Reajustar
        # SO' a barra horizontal, e SO' quando ela cresceu de fato.
        #
        # Chamar `atualizar_barras()` inteiro aqui seria pedir repintura em
        # cascata: ele mexe tambem na barra VERTICAL, cujo maximo cresce a cada
        # avanco da indexacao -- pintar, mudar a faixa, repintar, mudar de novo. A
        # barra vertical e' atualizada pelos sinais do indexador e pelo resize, que
        # sao eventos de fora da pintura.
        if self._maior_largura_vista > largura_antes:
            util = max(0, self.viewport().width() - largura_margem)
            self.horizontalScrollBar().setRange(
                0, max(0, self._maior_largura_vista - util))

    def _pintar_ocorrencias(self, pintor: QPainter, texto: str,
                            mapa: list[int] | None, x: int, topo: int,
                            altura: int) -> None:
        cor = QColor(self.tema.cor("editor.ocorrencia"))
        largura = self._largura_do_digito     # monoespacada: um caractere = um digito
        for m in self._padrao.finditer(texto):
            inicio = mapa[m.start()] if mapa else m.start()
            fim = mapa[min(m.end(), len(mapa) - 1)] if mapa else m.end()
            if fim <= inicio:
                continue          # casamento vazio: nao ha' o que pintar
            pintor.fillRect(QRect(x + inicio * largura, topo,
                                  (fim - inicio) * largura, altura), cor)


# ---------------------------------------------------------------------------
# O painel completo: infobar + visor
# ---------------------------------------------------------------------------


class PainelDeArquivoGrande(QWidget):
    """O que a `Aba` registra como a view "grande".

    Existe separado do visor por um motivo pratico: a infobar precisa poder ser
    fechada pelo usuario sem que isso mexa em nada da rolagem.
    """

    editavel = False                    # ver visualizadores/base.py

    def __init__(self, fonte: FonteDeArquivo, cfg: dict, tema,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.visor = VisorDeArquivoGrande(fonte, cfg, tema, self)

        self.aviso = QLabel(self._texto_do_aviso(fonte), self)
        self.aviso.setWordWrap(True)
        self.aviso.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Minimum)

        fechar = QToolButton(self)
        fechar.setText("×")
        fechar.setToolTip("Ocultar este aviso")
        fechar.setAutoRaise(True)
        fechar.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.barra = QWidget(self)
        linha = QHBoxLayout(self.barra)
        linha.setContentsMargins(8, 4, 4, 4)
        linha.addWidget(self.aviso, 1)
        linha.addWidget(fechar)
        fechar.clicked.connect(self.barra.hide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.barra)
        layout.addWidget(self.visor, 1)

        self.aplicar_tema(tema)

    @staticmethod
    def _texto_do_aviso(fonte: FonteDeArquivo) -> str:
        """Diz o que esta' desligado E POR QUE.

        Uma infobar que so' anuncia "modo somente leitura" deixa o usuario
        procurando o menu que ligaria a edicao. Dizer o motivo e o que CONTINUA
        funcionando e' a diferenca entre um aviso e um obstaculo.
        """
        mb = fonte.tamanho_em_bytes() / (1024 * 1024)
        return (f"<b>Modo de arquivo grande</b> ({mb:,.0f} MB) — somente leitura. "
                "Edicao, realce de sintaxe, painel Estrutura e minimapa estao "
                "desligados: manter um arquivo deste tamanho na memoria consumiria "
                "varios GB de RAM. Rolar, <b>Ir para linha</b>, <b>Pesquisar</b> e "
                "copiar continuam funcionando."
                .replace(",", "."))

    # -- repasses ----------------------------------------------------------

    @property
    def fonte(self) -> FonteDeArquivo:
        return self.visor.fonte

    def ir_para_linha(self, n: int, _coluna: int = 0) -> None:
        self.visor.ir_para_linha(n)

    def atualizar_barras(self) -> None:
        self.visor.atualizar_barras()
        self.visor.viewport().update()

    def aplicar_configuracao(self, cfg: dict) -> None:
        self.visor.aplicar_configuracao(cfg)

    def aplicar_tema(self, tema) -> None:
        self.visor.aplicar_tema(tema)
        self.barra.setStyleSheet(
            f"background: {tema.cor('janela.campo_fundo').name()};"
            f"border-bottom: 1px solid {tema.cor('janela.borda').name()};")
        self.aviso.setStyleSheet(f"color: {tema.cor('janela.texto').name()};"
                                 "background: transparent; border: none;")

    def setFocus(self) -> None:                               # noqa: N802 - Qt
        self.visor.setFocus()
