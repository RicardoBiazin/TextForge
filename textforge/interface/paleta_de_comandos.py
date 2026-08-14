"""Paleta de comandos (Ctrl+Shift+P) e abertura rapida (Ctrl+P).

As duas sao o MESMO widget com listas diferentes -- e' o que o registro unico de
comandos (`acoes.py`) torna possivel: a paleta nao conhece nenhum comando, ela
pergunta ao registro quais tem tratador e monta a lista.

DUAS DECISOES QUE DEFINEM A UTILIDADE DELA:

1. **Busca por subsequencia, e nao por substring.** Digitar "fdoc" acha "Formatar
   documento"; "abx" acha "Abrir" em nenhum lugar, mas acha "A&brir com XML"... o
   ponto e' que ninguem lembra o rotulo exato, e sim as iniciais. Uma busca por
   substring exigiria "formatar doc" inteiro e a paleta perderia a razao de existir.

2. **Comandos SEM tratador nao aparecem.** O menu mostra o que o programa VAI ter,
   desabilitado, porque ali isso informa. Numa lista de busca, um item que nao faz
   nada so' desperdica o tempo de quem digitou.

A pontuacao premia casamento no INICIO de palavra, que e' como a memoria funciona:
para "fd", "Formatar documento" ganha de "Fim de linha".
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from textforge import log_interno

log = log_interno.obter(__name__)

# Quantos itens a lista mostra. Mais que isso ninguem le' -- e a rolagem de uma
# lista de 200 itens e' mais lenta que digitar mais uma letra.
MAXIMO_NA_LISTA = 40


def pontuar(consulta: str, alvo: str) -> int:
    """Quanto `alvo` casa com `consulta` como SUBSEQUENCIA. -1 = nao casa.

    Regras da pontuacao, em ordem de peso:

      * casar no comeco de uma PALAVRA vale muito ("fd" -> "Formatar documento");
      * caracteres CONSECUTIVOS valem mais que espalhados;
      * casar cedo no texto vale um pouco mais que casar tarde.

    Sem a primeira regra, "fd" daria a mesma nota para "Formatar documento" e para
    "Fim de linha", e a paleta pareceria aleatoria.
    """
    if not consulta:
        return 0
    alvo_baixo = alvo.lower()
    nota = 0
    posicao = 0
    anterior = -2
    for ch in consulta.lower():
        if ch == " ":
            continue
        achou = alvo_baixo.find(ch, posicao)
        if achou < 0:
            return -1
        # Inicio de palavra: comeco do texto, ou depois de espaco/pontuacao.
        if achou == 0 or not alvo_baixo[achou - 1].isalnum():
            nota += 10
        if achou == anterior + 1:
            nota += 5
        nota += max(0, 3 - achou // 10)
        anterior = achou
        posicao = achou + 1
    return nota


class PaletaDeComandos(QDialog):
    """Caixa de busca com lista. Serve tanto a comandos quanto a arquivos."""

    escolhido = Signal(str)          # o `dado` do item escolhido

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setModal(True)
        self._itens: list[tuple[str, str, str]] = []   # (dado, titulo, detalhe)

        self.campo = QLineEdit(self)
        self.campo.textChanged.connect(self._filtrar)
        self.campo.installEventFilter(self)

        self.lista = QListWidget(self)
        self.lista.itemActivated.connect(self._ao_ativar)
        self.lista.itemClicked.connect(self._ao_ativar)

        self.rodape = QLabel("", self)
        self.rodape.setObjectName("rodapeDaPaleta")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)
        layout.addWidget(self.campo)
        layout.addWidget(self.lista, 1)
        layout.addWidget(self.rodape)
        self.resize(680, 420)

    # ==================================================================
    # Conteudo
    # ==================================================================

    def definir_itens(self, itens: list[tuple[str, str, str]], *,
                      dica: str = "", texto_inicial: str = "") -> None:
        """`itens` e' (dado, titulo, detalhe). `dado` volta no sinal `escolhido`."""
        self._itens = itens
        self.rodape.setText(dica)
        self.campo.setText(texto_inicial)
        self._filtrar(texto_inicial)

    def _filtrar(self, consulta: str) -> None:
        pontuados = []
        for dado, titulo, detalhe in self._itens:
            # A consulta e' casada contra o titulo E o detalhe: procurar por
            # "csv" tem de achar "Modo tabela (CSV)" pelo rotulo e tambem o
            # comando cujo caminho de menu cita CSV.
            nota = max(pontuar(consulta, titulo),
                       pontuar(consulta, detalhe) - 2)
            if nota >= 0:
                pontuados.append((nota, titulo, dado, detalhe))
        # Empate resolvido pelo TITULO, e nao pela ordem de declaracao: com nota
        # igual, a lista precisa ser estavel entre uma tecla e a proxima, senao os
        # itens dancam sob o cursor enquanto o usuario digita.
        pontuados.sort(key=lambda p: (-p[0], p[1]))

        self.lista.clear()
        for _nota, titulo, dado, detalhe in pontuados[:MAXIMO_NA_LISTA]:
            item = QListWidgetItem(f"{titulo}\n{detalhe}" if detalhe else titulo)
            item.setData(Qt.ItemDataRole.UserRole, dado)
            self.lista.addItem(item)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def dados_visiveis(self) -> list[str]:
        """O que esta' na lista agora. Usado pelos testes."""
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.lista.count())]

    # ==================================================================
    # Interacao
    # ==================================================================

    def eventFilter(self, objeto, evento) -> bool:            # noqa: N802 - Qt
        """Setas e Enter no CAMPO controlam a LISTA.

        Sem isto o usuario teria de sair do campo com Tab para escolher, e a
        paleta perderia o unico gesto que ela existe para oferecer: digitar e
        apertar Enter.
        """
        if objeto is self.campo and evento.type() == QEvent.Type.KeyPress:
            tecla = evento.key()
            if tecla in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                         Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                self.lista.keyPressEvent(QKeyEvent(evento))
                return True
            if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._confirmar()
                return True
        return super().eventFilter(objeto, evento)

    def _ao_ativar(self, _item) -> None:
        self._confirmar()

    def _confirmar(self) -> None:
        item = self.lista.currentItem()
        if item is None:
            return
        dado = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        # Emitido DEPOIS do accept: o comando escolhido pode abrir outro dialogo,
        # e a paleta precisa ter saido da tela antes disso.
        self.escolhido.emit(dado)

    def mostrar(self) -> None:
        self.campo.setFocus()
        self.campo.selectAll()
        self.exec()


# ---------------------------------------------------------------------------
# Montagem das duas listas
# ---------------------------------------------------------------------------


def itens_de_comandos(vinculos) -> list[tuple[str, str, str]]:
    """Os comandos DISPONIVEIS (declarados e com tratador), com o atalho no fim."""
    itens = []
    for comando in vinculos.comandos_disponiveis():
        qacao = vinculos.qacao(comando.id)
        if qacao is not None and not qacao.isEnabled():
            continue
        atalho = comando.atalho
        titulo = f"{comando.rotulo_limpo}    {atalho}" if atalho \
            else comando.rotulo_limpo
        itens.append((comando.id, titulo, comando.caminho_na_palette))
    return itens


def itens_de_arquivos(recentes: list[str], abertos: list[str],
                      pasta: pathlib.Path | None = None,
                      limite: int = 400) -> list[tuple[str, str, str]]:
    """Arquivos para a abertura rapida: abertos, recentes e os da pasta atual.

    A pasta e' varrida com um TETO e sem entrar em `.git`, `node_modules` e afins:
    `Ctrl+P` numa pasta de projeto com 200 mil arquivos nao pode congelar a
    interface enquanto o usuario espera para digitar tres letras.
    """
    IGNORADAS = {".git", ".svn", "node_modules", "__pycache__", ".venv",
                 "venv", "dist", "build", ".idea", ".vs"}
    vistos: set[str] = set()
    itens: list[tuple[str, str, str]] = []

    def por(caminho: str, marca: str) -> None:
        chave = caminho.lower()
        if chave in vistos:
            return
        vistos.add(chave)
        alvo = pathlib.Path(caminho)
        itens.append((caminho, f"{alvo.name}   {marca}", str(alvo.parent)))

    for caminho in abertos:
        por(caminho, "· aberto")
    for caminho in recentes:
        por(caminho, "· recente")

    if pasta is not None and pasta.is_dir():
        import os
        contados = 0
        for raiz, pastas, arquivos in os.walk(pasta, followlinks=False):
            pastas[:] = [p for p in pastas if p not in IGNORADAS
                         and not p.startswith(".")]
            for nome in arquivos:
                por(str(pathlib.Path(raiz) / nome), "")
                contados += 1
                if contados >= limite:
                    log.info("abertura rapida: parou em %d arquivos", limite)
                    return itens
    return itens
