"""Dialogos pequenos e reutilizaveis.

Cada funcao aqui e' sincrona e devolve o que o usuario escolheu, ou `None` se
cancelou. Nenhuma delas altera nada: quem age e' quem chamou. Isso mantem os
dialogos testaveis e impede que um "cancelar" deixe metade de uma operacao feita.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
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


def confirmar_perda_de_caracteres(parent: QWidget, codec: str,
                                  perdas: list) -> str:
    """Aviso antes de uma conversao destrutiva (requisito 5).

    Devolve "cancelar", "substituir" ou "utf8".

    Tres detalhes deliberados:
      * CANCELAR e' o botao padrao. Um Enter distraido nao pode comer os acentos
        de um arquivo.
      * a tabela mostra linha, coluna, o caractere E o nome Unicode dele. So' o
        caractere nao ajuda: metade deles e' invisivel ou parecido com outro.
      * "Salvar em UTF-8" existe porque quase sempre e' o que o usuario quer de
        verdade -- ele so' nao sabia que a codificacao atual nao cabia.
    """
    from textforge import codificacao

    caixa = QMessageBox(parent)
    caixa.setWindowTitle("Conversao com perda de caracteres")
    caixa.setIcon(QMessageBox.Icon.Warning)
    rotulo = codificacao.ROTULOS.get(codec, codec)
    caixa.setText(
        f"<b>{len(perdas)} caractere(s) nao existem em {rotulo}.</b>")
    caixa.setInformativeText(
        f"Converter para {rotulo} substituiria esses caracteres e "
        f"a informacao original seria perdida.<br><br>"
        f"Encontrados: {codificacao.resumir_perdas(perdas)}")

    linhas = ["Linha  Coluna  Caractere  Nome Unicode",
              "-----  ------  ---------  ------------"]
    for p in perdas[:80]:
        linhas.append(f"{p.linha:>5}  {p.coluna:>6}  {p.caractere:^9}  "
                      f"{p.nome_unicode}")
    if len(perdas) > 80:
        linhas.append(f"... e mais {len(perdas) - 80}")
    caixa.setDetailedText("\n".join(linhas))

    cancelar = caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    utf8 = caixa.addButton("Salvar em UTF-8 em vez disso",
                           QMessageBox.ButtonRole.ActionRole)
    substituir = caixa.addButton("Converter e perder os caracteres",
                                 QMessageBox.ButtonRole.DestructiveRole)
    caixa.setDefaultButton(cancelar)
    caixa.exec()

    escolhido = caixa.clickedButton()
    if escolhido is utf8:
        return "utf8"
    if escolhido is substituir:
        return "substituir"
    return "cancelar"


def alteracao_externa(parent: QWidget, nome: str, descricao: str,
                      modificado: bool) -> str:
    """O dialogo do requisito 27. Devolve "recarregar", "manter" ou "comparar".

    Nunca ha' opcao "sobrescrever sem olhar": as tres saidas sao explicitas, e o
    padrao muda conforme o risco -- se o usuario NAO tem alteracoes locais,
    recarregar e' seguro e vira o padrao; se tem, o padrao e' manter o trabalho
    dele.
    """
    caixa = QMessageBox(parent)
    caixa.setWindowTitle("Arquivo alterado externamente")
    caixa.setIcon(QMessageBox.Icon.Warning)
    caixa.setText(f"<b>{nome}</b> foi alterado por outro programa.")
    detalhe = descricao or "o arquivo mudou no disco"
    if modificado:
        detalhe += ("<br><br><b>Voce tem alteracoes nao salvas nesta aba.</b> "
                    "Recarregar vai descarta-las.")
    caixa.setInformativeText(detalhe)

    recarregar = caixa.addButton("Recarregar do disco",
                                 QMessageBox.ButtonRole.AcceptRole)
    manter = caixa.addButton("Manter a minha versao",
                             QMessageBox.ButtonRole.RejectRole)
    comparar = caixa.addButton("Comparar", QMessageBox.ButtonRole.ActionRole)
    caixa.setDefaultButton(manter if modificado else recarregar)
    caixa.exec()

    escolhido = caixa.clickedButton()
    if escolhido is recarregar:
        return "recarregar"
    if escolhido is comparar:
        return "comparar"
    return "manter"


def propriedades(parent: QWidget, info: dict) -> None:
    """Arquivo > Propriedades (requisito 25)."""
    import datetime

    def data(chave: str) -> str:
        valor = info.get(chave)
        if not valor:
            return "-"
        return datetime.datetime.fromtimestamp(valor).strftime(
            "%d/%m/%Y %H:%M:%S")

    def numero(n: object) -> str:
        try:
            return f"{int(n):,}".replace(",", ".")
        except (TypeError, ValueError):
            return str(n)

    eol = info.get("fim_de_linha", "-")
    if info.get("fim_de_linha_misto"):
        eol += " (misto)"

    campos = [
        ("Nome", info.get("nome", "-")),
        ("Caminho", info.get("caminho", "-")),
        ("Extensao", info.get("extensao") or "(sem extensao)"),
        ("Tamanho", f"{numero(info.get('tamanho', 0))} bytes"),
        ("Linhas", numero(info.get("linhas", 0))),
        ("Caracteres", numero(info.get("caracteres", 0))),
        ("Caracteres sem espaco", numero(info.get("caracteres_sem_espaco", 0))),
        ("Palavras", numero(info.get("palavras", 0))),
        ("Codificacao", info.get("codificacao", "-")),
        ("Como foi detectada", info.get("como_detectou") or "-"),
        ("Fim de linha", eol),
        ("Indentacao", info.get("indentacao", "-")),
        ("Criado em", data("criado_em")),
        ("Alterado em", data("alterado_em")),
        ("Somente leitura", "sim" if info.get("somente_leitura") else "nao"),
        ("Modificado", "sim" if info.get("modificado") else "nao"),
    ]
    corpo = "<table cellspacing='6'>" + "".join(
        f"<tr><td align='right'><b>{rotulo}</b></td>"
        f"<td>{valor}</td></tr>" for rotulo, valor in campos) + "</table>"

    caixa = QMessageBox(parent)
    caixa.setWindowTitle("Propriedades")
    caixa.setIcon(QMessageBox.Icon.Information)
    caixa.setTextFormat(Qt.TextFormat.RichText)
    caixa.setText(corpo)
    caixa.exec()


def avisar(parent: QWidget, texto: str, detalhe: str = "") -> None:
    caixa = QMessageBox(parent)
    caixa.setWindowTitle(APP)
    caixa.setIcon(QMessageBox.Icon.Information)
    caixa.setText(texto)
    if detalhe:
        caixa.setInformativeText(detalhe)
    caixa.exec()
