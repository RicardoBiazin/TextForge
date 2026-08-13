"""Dialogos pequenos e reutilizaveis.

Cada funcao aqui e' sincrona e devolve o que o usuario escolheu, ou `None` se
cancelou. Nenhuma delas altera nada: quem age e' quem chamou. Isso mantem os
dialogos testaveis e impede que um "cancelar" deixe metade de uma operacao feita.
"""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from textforge import APP


def pedir_linha(parent: QWidget, total: int,
                atual: int = 0) -> tuple[int, int] | None:
    """Ctrl+G. Aceita "125" e tambem "125:40" (linha e coluna).

    Recebe e devolve em BASE ZERO, como o resto do nucleo, mas mostra ao usuario
    a numeracao de 1 -- que e' a que ele ve na barra de status e nas mensagens de
    erro que ele esta' tentando alcancar.
    """
    texto, ok = QInputDialog.getText(
        parent, "Ir para linha",
        f"Linha (1 a {total}), ou linha:coluna:", text=str(atual + 1))
    if not ok or not texto.strip():
        return None

    partes = texto.replace(",", ":").split(":", 1)
    try:
        linha = int(partes[0].strip()) - 1
    except ValueError:
        QMessageBox.warning(parent, APP,
                            f"'{texto.strip()}' nao e' um numero de linha.")
        return None
    coluna = 0
    if len(partes) > 1 and partes[1].strip():
        try:
            coluna = max(0, int(partes[1].strip()) - 1)
        except ValueError:
            coluna = 0
    # Recortar em vez de recusar: quem digita 99999 quer o fim do arquivo.
    return max(0, min(linha, total - 1)), coluna


def pedir_texto(parent: QWidget, titulo: str, rotulo: str,
                inicial: str = "") -> str | None:
    """Texto livre. Devolve None se cancelado -- e string vazia se ele apagou.

    A distincao importa: "inserir texto no fim de cada linha" com string vazia e'
    uma operacao valida (nao faz nada), e cancelar nao e' a mesma coisa.
    """
    texto, ok = QInputDialog.getText(parent, titulo, rotulo, text=inicial)
    return texto if ok else None


def escolher(parent: QWidget, titulo: str, rotulo: str, opcoes: list[str],
             atual: int = 0) -> str | None:
    escolha, ok = QInputDialog.getItem(parent, titulo, rotulo, opcoes,
                                       max(0, atual), False)
    return escolha if ok else None


def confirmar(parent: QWidget, titulo: str, pergunta: str,
             *, perigoso: bool = False) -> bool:
    """Sim/Nao. Em operacao perigosa, o botao padrao e' NAO.

    O padrao "Nao" em operacao destrutiva e' deliberado: um Enter distraido nao
    pode apagar o trabalho de ninguem.
    """
    caixa = QMessageBox(parent)
    caixa.setWindowTitle(titulo)
    caixa.setText(pergunta)
    caixa.setIcon(QMessageBox.Icon.Warning if perigoso
                  else QMessageBox.Icon.Question)
    caixa.setStandardButtons(QMessageBox.StandardButton.Yes
                             | QMessageBox.StandardButton.No)
    caixa.setDefaultButton(QMessageBox.StandardButton.No if perigoso
                           else QMessageBox.StandardButton.Yes)
    return caixa.exec() == QMessageBox.StandardButton.Yes


def avisar(parent: QWidget, texto: str, detalhe: str = "") -> None:
    caixa = QMessageBox(parent)
    caixa.setWindowTitle(APP)
    caixa.setIcon(QMessageBox.Icon.Information)
    caixa.setText(texto)
    if detalhe:
        caixa.setInformativeText(detalhe)
    caixa.exec()
