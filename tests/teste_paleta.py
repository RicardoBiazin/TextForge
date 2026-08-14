"""Paleta de comandos, abertura rapida e comentar/descomentar (etapa 12).

    .\\.venv\\Scripts\\python.exe tests\\teste_paleta.py

A verificacao que carrega o peso: a busca e' por SUBSEQUENCIA, e "fdoc" tem de
achar "Formatar documento". Uma busca por substring exigiria digitar o rotulo
inteiro, e a paleta perderia a razao de existir.

E a segunda: comandos SEM tratador nao aparecem. No menu, um comando futuro
desabilitado INFORMA; numa lista de busca ele so' desperdica o tempo de quem
digitou.
"""

from __future__ import annotations

import sys

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import configuracao                             # noqa: E402
from textforge.interface import paleta_de_comandos as pal      # noqa: E402
from textforge.interface.janela import JanelaPrincipal         # noqa: E402


def testar_pontuacao() -> None:
    secao("*** Busca por SUBSEQUENCIA ***")

    checa(pal.pontuar("fdoc", "Formatar documento") >= 0,
          "'fdoc' acha 'Formatar documento'")
    checa(pal.pontuar("frm", "Formatar documento") >= 0,
          "'frm' tambem (letras espalhadas, na ordem)")
    checa_igual(pal.pontuar("xyz", "Formatar documento"), -1,
                "letra que nao existe nao casa")
    checa_igual(pal.pontuar("tof", "Formatar"), -1,
                "e a ORDEM importa: 'tof' nao casa (nao ha' 'o' depois do 't')")
    checa_igual(pal.pontuar("", "qualquer"), 0, "consulta vazia casa com tudo")

    secao("Casar no COMECO de palavra vale mais")
    inicio = pal.pontuar("fd", "Formatar documento")     # duas iniciais
    meio = pal.pontuar("fd", "Perfil dado")              # 'f' no meio de Perfil
    checa(inicio > meio,
          f"'fd' pontua mais quando as duas letras iniciam palavra "
          f"({inicio}) do que quando uma cai no meio ({meio})")
    # LIMITE CONHECIDO, escrito para nao virar surpresa: dois alvos em que as
    # letras iniciam palavra empatam ("Formatar documento" e "Fim de linha" para
    # "fd"), e o desempate e' alfabetico. Distinguir exigiria pesar tamanho ou
    # frequencia de uso, que e' estado que a paleta hoje nao guarda.
    checa_igual(pal.pontuar("fd", "Formatar documento"),
                pal.pontuar("fd", "Fim de linha"),
                "  (dois casamentos em inicio de palavra EMPATAM — limite "
                "conhecido, desempatado alfabeticamente)")

    secao("Consecutivos valem mais que espalhados")
    junto = pal.pontuar("form", "Formatar")
    solto = pal.pontuar("form", "Fantastico ornamento rustico moderno")
    checa(junto > solto,
          f"'form' junto em 'Formatar' ({junto}) vence espalhado ({solto})")

    checa(pal.pontuar("FDOC", "Formatar documento") >= 0,
          "a busca ignora a caixa")
    checa(pal.pontuar("f doc", "Formatar documento") >= 0,
          "espaco na consulta e' ignorado")


def testar_paleta_de_comandos(janela: JanelaPrincipal) -> None:
    secao("A lista de comandos")

    itens = pal.itens_de_comandos(janela.vinculos)
    checa(len(itens) > 40, f"ha' {len(itens)} comandos disponiveis na paleta")

    ids = {i[0] for i in itens}
    checa("formatar.documento" in ids, "um comando ligado aparece")
    checa("ferramentas.comparar" not in ids,
          "*** um comando SEM tratador (v2) NAO aparece ***")
    checa("arquivo.sair" not in ids,
          "e um comando marcado 'fora_da_palette' tambem nao")

    # O atalho entra no titulo: quem usa a paleta acaba aprendendo os atalhos.
    com_atalho = [i for i in itens if i[0] == "arquivo.salvar"]
    checa(com_atalho and "Ctrl+S" in com_atalho[0][1],
          "o atalho aparece no titulo do item")
    checa(com_atalho and ">" in com_atalho[0][2],
          "e o caminho no menu aparece como detalhe (contexto na lista plana)")

    secao("Filtrar")
    paleta = pal.PaletaDeComandos(janela)
    paleta.definir_itens(itens)
    checa(len(paleta.dados_visiveis()) > 0, "sem consulta, a lista vem cheia")
    checa(len(paleta.dados_visiveis()) <= pal.MAXIMO_NA_LISTA,
          f"mas limitada a {pal.MAXIMO_NA_LISTA} itens")

    paleta.campo.setText("fdoc")
    visiveis = paleta.dados_visiveis()
    checa("formatar.documento" in visiveis,
          "*** digitar 'fdoc' acha 'Formatar documento' ***")
    checa_igual(visiveis[0], "formatar.documento",
                "e ele vem em PRIMEIRO lugar")

    secao("Comentar e descomentar em sequencia")
    # A selecao tem de sobreviver ao comando: sem isso, o segundo Ctrl+/ atuaria
    # so' na ultima linha e o bloco ficaria pela metade.
    checa(True, "  (verificado em 'Comentar / descomentar', abaixo)")

    paleta.campo.setText("salvar")
    checa("arquivo.salvar" in paleta.dados_visiveis(), "'salvar' acha Salvar")

    paleta.campo.setText("zzzqqq")
    checa_igual(paleta.dados_visiveis(), [],
                "consulta sem casamento deixa a lista vazia (nao estoura)")

    secao("Estabilidade da ordem")
    paleta.campo.setText("a")
    primeira = paleta.dados_visiveis()
    paleta.campo.setText("a")
    checa_igual(paleta.dados_visiveis(), primeira,
                "a mesma consulta da' sempre a mesma ordem "
                "(senao os itens dancam sob o cursor)")
    paleta.deleteLater()


def testar_abertura_rapida() -> None:
    secao("Abertura rapida")

    with pasta_temporaria("textforge-paleta-") as pasta:
        (pasta / "alpha.txt").write_text("a", encoding="utf-8")
        (pasta / "beta.log").write_text("b", encoding="utf-8")
        sub = pasta / "sub"
        sub.mkdir()
        (sub / "gamma.xml").write_text("<a/>", encoding="utf-8")
        # Pastas que precisam ser ignoradas.
        for ignorada in (".git", "node_modules", "__pycache__"):
            alvo = pasta / ignorada
            alvo.mkdir()
            (alvo / "lixo.txt").write_text("x", encoding="utf-8")

        itens = pal.itens_de_arquivos([], [], pasta)
        nomes = [i[1].split()[0] for i in itens]
        checa("alpha.txt" in nomes, "acha arquivo na raiz da pasta")
        checa("gamma.xml" in nomes, "e em subpasta")
        checa("lixo.txt" not in nomes,
              "*** mas NAO entra em .git, node_modules nem __pycache__ ***")

        secao("Abertos e recentes vem primeiro, e sem repetir")
        aberto = str(pasta / "alpha.txt")
        itens = pal.itens_de_arquivos([str(pasta / "beta.log")], [aberto], pasta)
        checa_igual(itens[0][0], aberto, "o arquivo ABERTO vem em primeiro")
        checa("aberto" in itens[0][1], "e vem marcado como aberto")
        checa("recente" in itens[1][1], "o recente vem em seguida, marcado")
        caminhos = [i[0] for i in itens]
        checa_igual(len(caminhos), len(set(caminhos)),
                    "nenhum caminho aparece duas vezes "
                    "(o mesmo arquivo pode ser aberto E recente E da pasta)")

        secao("Teto na varredura")
        muitos = pasta / "muitos"
        muitos.mkdir()
        for n in range(50):
            (muitos / f"f{n}.txt").write_text("x", encoding="utf-8")
        itens = pal.itens_de_arquivos([], [], pasta, limite=10)
        checa(len(itens) <= 12,
              f"*** com limite=10, a varredura para ({len(itens)} itens) — "
              f"Ctrl+P numa pasta de 200 mil arquivos nao pode congelar ***")


def testar_comentar(janela: JanelaPrincipal) -> None:
    secao("Comentar / descomentar (Ctrl+/)")

    from textforge.documento import Documento
    from textforge.linguagens.registro import REGISTRO

    doc = Documento.novo(janela.cfg)
    doc.definir_texto("def f():\n    a = 1\n    b = 2\n")
    doc.provedor = REGISTRO.por_nome("Python")
    aba = janela.abas.adicionar(doc)
    editor = aba.editor

    from PySide6.QtGui import QTextCursor
    cursor = editor.textCursor()
    cursor.setPosition(doc.qt.findBlockByNumber(1).position())
    cursor.setPosition(doc.qt.findBlockByNumber(2).position() + 5,
                       QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    janela.alternar_comentario()
    checa_igual(doc.texto(), "def f():\n    # a = 1\n    # b = 2\n",
                "*** o '#' entra na INDENTACAO do bloco, e nao na coluna zero ***")

    janela.alternar_comentario()
    checa_igual(doc.texto(), "def f():\n    a = 1\n    b = 2\n",
                "e descomentar devolve o texto exatamente como estava")

    secao("Comenta tudo quando ALGUMA linha nao esta' comentada")
    doc.definir_texto("# ja comentada\nnao comentada\n")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(doc.qt.findBlockByNumber(1).position() + 3,
                       QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    janela.alternar_comentario()
    checa_igual(doc.texto(), "# # ja comentada\n# nao comentada\n",
                "com uma linha solta, COMENTA todas (e nao alterna uma a uma)")

    secao("Uma linha so', sem selecao")
    doc.definir_texto("a = 1\n")
    cursor = editor.textCursor()
    cursor.setPosition(2)
    editor.setTextCursor(cursor)
    janela.alternar_comentario()
    checa_igual(doc.texto(), "# a = 1\n", "comenta a linha do cursor")

    secao("Linha em branco no meio nao ganha comentario")
    doc.definir_texto("a = 1\n\nb = 2\n")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(doc.qt.findBlockByNumber(2).position() + 3,
                       QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    janela.alternar_comentario()
    checa_igual(doc.texto(), "# a = 1\n\n# b = 2\n",
                "a linha vazia fica vazia")

    secao("Um unico passo de desfazer")
    doc.definir_texto("a\nb\nc\n")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(doc.qt.findBlockByNumber(2).position() + 1,
                       QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    janela.alternar_comentario()
    comentado = doc.texto()
    editor.undo()
    checa_igual(doc.texto(), "a\nb\nc\n",
                f"UM Ctrl+Z desfaz as tres linhas (era {comentado!r})")

    janela.abas.fechar(janela.abas.indexOf(aba))


def testar_atalhos(janela: JanelaPrincipal) -> None:
    secao("Lista de atalhos GERADA do registro")

    from textforge.interface import acoes

    com_atalho = [c for c in acoes.REGISTRO.comandos
                  if c.atalho and janela.vinculos.tem_tratador(c.id)]
    checa(len(com_atalho) > 30,
          f"ha' {len(com_atalho)} atalhos ativos, e a lista sai do registro "
          f"(uma lista escrita a mao desatualizaria no primeiro que mudasse)")

    conflitos = acoes.conflitos_de_atalho()
    checa_igual(conflitos, {}, "e nenhum atalho esta' duplicado")


def main() -> int:
    testar_pontuacao()
    testar_abertura_rapida()
    janela = JanelaPrincipal(configuracao.padrao())
    try:
        testar_paleta_de_comandos(janela)
        testar_comentar(janela)
        testar_atalhos(janela)
    finally:
        janela.close()
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
