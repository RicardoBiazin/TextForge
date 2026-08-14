"""Barra de status: Ln 125, Col 42 | UTF-8 | CRLF | Python | INS.

Requisito 4. Os campos de codificacao, fim de linha e linguagem sao CLICAVEIS --
e' por eles que o usuario troca cada coisa, sem procurar em menu. O clique emite
um sinal; quem decide o que fazer e' a janela.

A posicao do cursor chega aqui em base ZERO (a convencao interna do projeto,
ver `fonte.py`) e e' exibida em base 1. Esta e' a UNICA conversao entre as duas
numeracoes no programa inteiro -- e' de proposito: espalhar `+1` pelo codigo e'
como se garante um erro de um-a-menos no "ir para linha".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QLabel, QProgressBar, QPushButton, QSizePolicy,
                               QStatusBar, QWidget)


class _Clicavel(QPushButton):
    """Rotulo que parece texto e responde a clique."""

    def __init__(self, texto: str = "", dica: str = "") -> None:
        super().__init__(texto)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(dica)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Sem isto o botao ganha a altura de um botao de dialogo e a barra de
        # status fica com o dobro da altura necessaria.
        self.setSizePolicy(QSizePolicy.Policy.Maximum,
                           QSizePolicy.Policy.Preferred)


class BarraDeStatus(QStatusBar):
    codificacao_clicada = Signal()
    fim_de_linha_clicado = Signal()
    linguagem_clicada = Signal()
    indentacao_clicada = Signal()
    posicao_clicada = Signal()
    visualizador_clicado = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        # Sem a margem a' direita, o ultimo campo (INS/OVR) encosta na borda da
        # janela e fica cortado -- o Qt nao reserva espaco para ele sozinho.
        self.setContentsMargins(6, 0, 10, 0)
        self._tema = None
        self._codificacao_suspeita = False

        # Esquerda: mensagem temporaria (showMessage) e progresso.
        self._progresso = QProgressBar()
        self._progresso.setMaximumWidth(160)
        self._progresso.setMaximumHeight(14)
        self._progresso.setTextVisible(False)
        self._progresso.hide()
        self.addWidget(self._progresso)

        self._aviso = QLabel("")
        self._aviso.setObjectName("avisoDaBarra")
        self.addWidget(self._aviso)

        # Direita, na ordem do requisito 4.
        self._posicao = _Clicavel("Ln 1, Col 1", "Clique para ir para uma linha")
        self._posicao.clicked.connect(self.posicao_clicada)
        self.addPermanentWidget(self._posicao)

        self._selecao = QLabel("")
        self._selecao.setToolTip("Caracteres e linhas selecionados")
        self.addPermanentWidget(self._selecao)

        self._indentacao = _Clicavel("", "Clique para trocar a indentacao")
        self._indentacao.clicked.connect(self.indentacao_clicada)
        self.addPermanentWidget(self._indentacao)

        self._codificacao = _Clicavel("", "Clique para converter a codificacao")
        self._codificacao.clicked.connect(self.codificacao_clicada)
        self.addPermanentWidget(self._codificacao)

        self._fim_de_linha = _Clicavel("", "Clique para trocar o fim de linha")
        self._fim_de_linha.clicked.connect(self.fim_de_linha_clicado)
        self.addPermanentWidget(self._fim_de_linha)

        # Alternancia Texto <-> Tabela. Fica ESCONDIDO quando o documento nao
        # oferece outra view: um campo permanentemente inerte na barra e' ruido, e
        # a maioria dos arquivos so' tem o modo texto.
        self._visualizador = _Clicavel("", "Clique para alternar a visualizacao")
        self._visualizador.clicked.connect(self.visualizador_clicado)
        self._visualizador.hide()
        self.addPermanentWidget(self._visualizador)

        self._linguagem = _Clicavel("", "Clique para trocar a linguagem")
        self._linguagem.clicked.connect(self.linguagem_clicada)
        self.addPermanentWidget(self._linguagem)

        self._insercao = QLabel("INS")
        self._insercao.setToolTip("INS = inserir, OVR = sobrescrever (tecla Insert)")
        self.addPermanentWidget(self._insercao)

        self.limpar()

    # -- tema --------------------------------------------------------------

    def aplicar_tema(self, tema) -> None:
        """Pinta a barra com as cores do tema, pedindo cada uma por NOME.

        Precisa ser explicito: um QPushButton plano com folha de estilo nao
        volta a resolver `palette(...)` quando a paleta troca com a janela
        aberta -- ao ir do tema escuro para o claro, os campos ficavam cinza
        claro sobre fundo claro, ilegiveis.
        """
        self._tema = tema
        fundo = tema.cor("janela.fundo").name()
        texto = tema.cor("janela.texto").name()
        realce = tema.cor("janela.borda").name()
        apagado = tema.cor("janela.texto_apagado").name()
        self.setStyleSheet(f"""
            QStatusBar {{ background: {fundo}; color: {texto}; }}
            QStatusBar::item {{ border: none; }}
            QStatusBar QLabel {{ color: {texto}; padding: 1px 6px; }}
            QStatusBar QLabel#avisoDaBarra {{ color: {apagado}; }}
            QStatusBar QPushButton {{
                border: none; padding: 1px 8px; color: {texto};
                background: transparent;
            }}
            QStatusBar QPushButton:hover {{ background: {realce}; }}
        """)
        # Reaplica o destaque de codificacao suspeita, que tem cor propria.
        self.definir_codificacao(self._codificacao.text(),
                                 suspeita=self._codificacao_suspeita)

    # -- atualizacao -------------------------------------------------------

    def definir_posicao(self, linha: int, coluna: int) -> None:
        """`linha` e `coluna` em base ZERO. A exibicao soma 1."""
        self._posicao.setText(f"Ln {linha + 1}, Col {coluna + 1}")

    def definir_selecao(self, caracteres: int, linhas: int) -> None:
        if caracteres <= 0:
            self._selecao.setText("")
        elif linhas <= 1:
            self._selecao.setText(f"{caracteres} sel.")
        else:
            self._selecao.setText(f"{caracteres} sel. em {linhas} linhas")

    def definir_codificacao(self, nome: str, *, suspeita: bool = False) -> None:
        """`suspeita=True` quando a leitura produziu U+FFFD.

        Nesse caso o texto vai em destaque de erro: o arquivo NAO foi lido
        corretamente, e salvar em cima dele destruiria dados. A aba tambem entra
        em somente leitura -- ver `codificacao.py`.
        """
        self._codificacao.setText(nome)
        self._codificacao_suspeita = suspeita
        if suspeita:
            cor = (self._tema.cor("janela.erro").name() if self._tema
                   else "#c74a4a")
            self._codificacao.setToolTip(
                "A leitura produziu caracteres invalidos. Escolha a codificacao "
                "correta antes de editar: salvar assim destruiria dados.")
            self._codificacao.setStyleSheet(
                "QPushButton { border: none; padding: 1px 8px; "
                f"font-weight: bold; color: {cor}; }}")
        else:
            self._codificacao.setToolTip("Clique para converter a codificacao")
            # Folha vazia devolve o botao ao estilo geral da barra.
            self._codificacao.setStyleSheet("")

    def definir_fim_de_linha(self, rotulo: str, *, misto: bool = False) -> None:
        self._fim_de_linha.setText(rotulo + (" (misto)" if misto else ""))
        self._fim_de_linha.setToolTip(
            "O arquivo tem fins de linha misturados. Ao salvar, o TextForge "
            "mantem o dominante e nao altera o resto sem que voce peca."
            if misto else "Clique para trocar o fim de linha")

    def definir_linguagem(self, nome: str) -> None:
        self._linguagem.setText(nome)

    def definir_visualizador(self, atual: str, *, disponivel: bool = True) -> None:
        """Mostra a view em uso ("Texto" ou "Tabela") e o que o clique fara'.

        `disponivel=False` esconde o campo: o arquivo nao tem outra forma de ser
        visto, e um botao que nao leva a lugar nenhum e' pior que nenhum botao.
        """
        if not disponivel:
            self._visualizador.hide()
            return
        rotulos = {"texto": "Texto", "tabela": "Tabela", "hex": "Hex",
                   "grande": "Arquivo grande"}
        outro = "Tabela" if atual == "texto" else "Texto"
        self._visualizador.setText(rotulos.get(atual, atual.capitalize()))
        self._visualizador.setToolTip(f"Clique para ver como {outro}")
        self._visualizador.show()

    def definir_indentacao(self, usa_espacos: bool, largura: int) -> None:
        self._indentacao.setText(
            f"{'Espacos' if usa_espacos else 'TAB'}: {largura}")

    def definir_insercao(self, inserindo: bool) -> None:
        self._insercao.setText("INS" if inserindo else "OVR")

    def definir_aviso(self, texto: str) -> None:
        """Aviso persistente (nao e' o showMessage temporario)."""
        self._aviso.setText(texto)

    # -- progresso de tarefa longa (requisito 34) ---------------------------

    def mostrar_progresso(self, feito: int = 0, total: int = -1) -> None:
        if total <= 0:
            # Total desconhecido: barra em movimento continuo.
            self._progresso.setRange(0, 0)
        else:
            self._progresso.setRange(0, total)
            self._progresso.setValue(feito)
        self._progresso.show()

    def esconder_progresso(self) -> None:
        self._progresso.hide()

    # -- estado sem documento ----------------------------------------------

    def limpar(self) -> None:
        """Estado sem nenhuma aba aberta: os campos ficam vazios, nao zerados.

        Mostrar "Ln 1, Col 1 | UTF-8 | CRLF" sem documento aberto seria informar
        algo que nao existe.
        """
        self._posicao.setText("")
        self._selecao.setText("")
        self._indentacao.setText("")
        self._fim_de_linha.setText("")
        self._linguagem.setText("")
        self._visualizador.hide()
        self._aviso.setText("")
        self.definir_codificacao("")
        self.esconder_progresso()
