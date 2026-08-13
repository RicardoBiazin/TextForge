"""Pesquisar em arquivos (requisito 8): varredura, filtros, robustez.

    .venv\\Scripts\\python.exe tests\\teste_busca_em_arquivos.py

Nao precisa de Qt: a varredura recebe um objeto com `checar_cancelamento`,
`progresso` e `dizer`, e o teste passa um duble. E' o que permite testar a busca em
pasta sem subir uma QApplication nem uma thread.

As tres verificacoes de robustez que importam mais:

  * uma junction/link apontando para um ANCESTRAL nao faz a varredura rodar para
    sempre;
  * arquivo BINARIO e' pulado (procurar "guia" num .exe de 80 MB gasta o tempo do
    usuario e nao acha nada util);
  * o cancelamento interrompe de verdade, no meio da varredura.
"""

from __future__ import annotations

import os
import pathlib
import sys

from ajudantes import (checa, checa_igual, pasta_temporaria, resumir, secao)

from textforge import busca_em_arquivos as bfa
from textforge.busca import Criterio


class TarefaFalsa:
    """Duble da `Tarefa`: registra o que foi reportado e pode cancelar."""

    def __init__(self, cancelar_apos: int | None = None) -> None:
        self.progressos: list[tuple[int, int]] = []
        self.mensagens: list[str] = []
        self.checagens = 0
        self._cancelar_apos = cancelar_apos

    def checar_cancelamento(self) -> None:
        self.checagens += 1
        if (self._cancelar_apos is not None
                and self.checagens > self._cancelar_apos):
            from textforge.tarefas import Cancelado
            raise Cancelado

    def progresso(self, feito: int, total: int = -1, **_k) -> None:
        self.progressos.append((feito, total))

    def dizer(self, texto: str) -> None:
        self.mensagens.append(texto)


def montar_arvore(raiz: pathlib.Path) -> None:
    """Uma arvore parecida com um projeto de verdade."""
    (raiz / "src").mkdir()
    (raiz / "src" / "guia.py").write_text(
        "def numeroGuia():\n    return 'numeroGuia'\n", encoding="utf-8")
    (raiz / "src" / "outro.py").write_text(
        "def nada():\n    pass\n", encoding="utf-8")
    (raiz / "src" / "pagina.php").write_text(
        "<?php\n$numeroGuia = 1;\necho $numeroGuia;\n", encoding="utf-8")
    (raiz / "config.xml").write_text(
        '<config><numeroGuia>7</numeroGuia></config>\n', encoding="utf-8")
    (raiz / "leia.txt").write_text("sem o termo aqui\n", encoding="utf-8")

    # Pasta gerada, que deve ser ignorada por padrao.
    (raiz / "node_modules").mkdir()
    (raiz / "node_modules" / "lixo.js").write_text(
        "var numeroGuia = 1;\n", encoding="utf-8")
    (raiz / ".git").mkdir()
    (raiz / ".git" / "config").write_text("numeroGuia\n", encoding="utf-8")

    # Arquivo binario.
    (raiz / "programa.exe").write_bytes(b"MZ" + bytes(range(256)) * 20
                                       + b"numeroGuia")
    # Arquivo em codificacao legada com acento, para conferir a deteccao.
    (raiz / "legado.txt").write_bytes(
        "Coração e numeroGuia\n".encode("cp1252"))


CRITERIO = Criterio(texto="numeroGuia")

# ---------------------------------------------------------------------------
secao("1 - varredura basica")

with pasta_temporaria() as raiz:
    montar_arvore(raiz)
    tarefa = TarefaFalsa()
    resultados, resumo = bfa.procurar(tarefa, raiz, CRITERIO)

    caminhos = {r.caminho.name for r in resultados}
    checa("guia.py" in caminhos, "acha no .py")
    checa("pagina.php" in caminhos, "acha no .php")
    checa("config.xml" in caminhos, "acha no .xml")
    checa("legado.txt" in caminhos,
          "acha em arquivo cp1252 (a deteccao de codificacao e' aplicada)")
    checa("leia.txt" not in caminhos, "e nao lista arquivo sem o termo")

    checa("lixo.js" not in caminhos,
          "node_modules e' ignorado por padrao (varre-lo multiplicaria o tempo)")
    checa("config" not in caminhos, ".git tambem e' ignorado")
    checa("programa.exe" not in caminhos, "e arquivo BINARIO e' pulado")
    checa("binarios" in resumo.motivos_de_pulo,
          f"o resumo diz por que pulou: {resumo.motivos_de_pulo}")

    checa(resumo.ocorrencias >= 5, f"{resumo.ocorrencias} ocorrencias no total")
    checa(resumo.arquivos_com_ocorrencia >= 4,
          f"em {resumo.arquivos_com_ocorrencia} arquivos")
    checa(resumo.arquivos_lidos >= 4, "e conta os arquivos lidos")
    checa(not resumo.cortado, "sem corte de resultados")
    checa("ocorrencia" in resumo.descrever(),
          f"o resumo e' legivel: {resumo.descrever()}")

    # Cada resultado traz o necessario para o painel abrir na linha.
    guia = next(r for r in resultados if r.caminho.name == "guia.py")
    checa_igual(guia.linha, 0, "a linha e' BASE ZERO")
    checa("numeroGuia" in guia.trecho, "o trecho contem o termo")
    checa_igual(guia.rotulo, "guia.py:1",
                "o rotulo mostra a linha em base 1 (como o usuario ve)")
    checa(guia.coluna >= 0 and guia.tamanho == len("numeroGuia"),
          "e a coluna e o tamanho permitem selecionar a ocorrencia")

    checa(tarefa.progressos, "o progresso foi reportado")
    checa(tarefa.mensagens, "e a pasta atual foi informada")

# ---------------------------------------------------------------------------
secao("2 - filtros de extensao")

with pasta_temporaria() as raiz:
    montar_arvore(raiz)
    tarefa = TarefaFalsa()
    resultados, _ = bfa.procurar(tarefa, raiz, CRITERIO, ["*.py"])
    extensoes = {r.caminho.suffix for r in resultados}
    checa_igual(extensoes, {".py"}, "com filtro *.py, so' vem .py")

    resultados, _ = bfa.procurar(tarefa, raiz, CRITERIO, ["*.php", "*.xml"])
    extensoes = {r.caminho.suffix for r in resultados}
    checa_igual(extensoes, {".php", ".xml"}, "dois filtros trazem os dois tipos")

    resultados, _ = bfa.procurar(tarefa, raiz, CRITERIO, ["*.inexistente"])
    checa_igual(resultados, [], "filtro sem correspondencia devolve lista vazia")

    # Sem subpastas.
    resultados, _ = bfa.procurar(tarefa, raiz, CRITERIO, subpastas=False)
    checa(all(r.caminho.parent == raiz for r in resultados),
          "com subpastas=False, so' a pasta raiz e' varrida")

    # Incluindo as pastas geradas.
    resultados, _ = bfa.procurar(tarefa, raiz, CRITERIO,
                                 ignorar_geradas=False)
    nomes = {r.caminho.name for r in resultados}
    checa("lixo.js" in nomes,
          "com ignorar_geradas=False, node_modules tambem e' varrido")

# ---------------------------------------------------------------------------
secao("3 - filtros_de aceita as formas que as pessoas digitam")

checa_igual(bfa.filtros_de("*.php"), ["*.php"], "um filtro")
checa_igual(bfa.filtros_de("*.php *.py"), ["*.php", "*.py"], "separado por espaco")
checa_igual(bfa.filtros_de("*.php;*.py"), ["*.php", "*.py"],
            "separado por ponto e virgula")
checa_igual(bfa.filtros_de("*.php, *.py"), ["*.php", "*.py"],
            "separado por virgula e espaco")
checa_igual(bfa.filtros_de("*.php; *.py, *.xml"),
            ["*.php", "*.py", "*.xml"], "misturando os separadores")
checa_igual(bfa.filtros_de(""), ["*"], "vazio vira 'todos'")
checa_igual(bfa.filtros_de("   "), ["*"], "so' espacos tambem")

# A extensao no filtro nao diferencia caixa: .PY tem de casar com *.py.
with pasta_temporaria() as raiz:
    (raiz / "MAIUSCULO.PY").write_text("numeroGuia\n", encoding="utf-8")
    resultados, _ = bfa.procurar(TarefaFalsa(), raiz, CRITERIO, ["*.py"])
    checa_igual(len(resultados), 1,
                "o filtro *.py casa com um arquivo .PY (caixa ignorada)")

# ---------------------------------------------------------------------------
secao("4 - cancelamento")

with pasta_temporaria() as raiz:
    for i in range(60):
        (raiz / f"arquivo{i:03d}.txt").write_text("numeroGuia\n",
                                                 encoding="utf-8")
    from textforge.tarefas import Cancelado

    tarefa = TarefaFalsa(cancelar_apos=5)
    try:
        bfa.procurar(tarefa, raiz, CRITERIO)
        checa(False, "a varredura deveria ter sido cancelada")
    except Cancelado:
        checa(True, "o cancelamento interrompe a varredura de verdade")
    checa(tarefa.checagens <= 10,
          f"e para logo ({tarefa.checagens} checagens, nao 60)")

# ---------------------------------------------------------------------------
secao("5 - laco de link simbolico nao trava a varredura")

with pasta_temporaria() as raiz:
    (raiz / "dentro").mkdir()
    (raiz / "dentro" / "a.txt").write_text("numeroGuia\n", encoding="utf-8")

    # Link apontando para um ANCESTRAL: sem a guarda de identidade, a varredura
    # desceria para sempre.
    criou_link = False
    alvo = raiz / "dentro" / "volta"
    try:
        os.symlink(raiz, alvo, target_is_directory=True)
        criou_link = True
    except (OSError, NotImplementedError, AttributeError):
        # No Windows, criar link simbolico exige privilegio ou modo de
        # desenvolvedor. Sem ele, este caso nao pode ser exercitado aqui.
        pass

    if criou_link:
        tarefa = TarefaFalsa()
        resultados, resumo = bfa.procurar(tarefa, raiz, CRITERIO)
        checa(True, "a varredura TERMINOU apesar do link para o ancestral")
        checa(resumo.arquivos_lidos < 50,
              f"e nao leu o mesmo arquivo dezenas de vezes "
              f"({resumo.arquivos_lidos})")
    else:
        checa(True, "PULADO: criar link simbolico exige privilegio no Windows")
        # A guarda em si e' testavel sem link: duas identidades iguais colidem.
        ident = bfa._identidade(raiz)
        checa(ident is not None and ident == bfa._identidade(raiz),
              "a identidade de uma pasta e' estavel (base da guarda de laco)")

# ---------------------------------------------------------------------------
secao("6 - arquivo grande e' pulado")

with pasta_temporaria() as raiz:
    (raiz / "gordo.txt").write_text("numeroGuia\n" * 2000, encoding="utf-8")
    (raiz / "magro.txt").write_text("numeroGuia\n", encoding="utf-8")
    tarefa = TarefaFalsa()
    resultados, resumo = bfa.procurar(tarefa, raiz, CRITERIO,
                                      limite_por_arquivo=100)
    nomes = {r.caminho.name for r in resultados}
    checa("magro.txt" in nomes, "arquivo pequeno e' lido")
    checa("gordo.txt" not in nomes, "arquivo acima do limite e' pulado")
    checa("grandes demais" in resumo.motivos_de_pulo,
          "e o resumo diz o motivo")

# ---------------------------------------------------------------------------
secao("7 - varredura com regex e com palavra inteira")

with pasta_temporaria() as raiz:
    (raiz / "a.txt").write_text("guia123\nguia456\noutra guia\n",
                                encoding="utf-8")
    tarefa = TarefaFalsa()

    resultados, _ = bfa.procurar(
        tarefa, raiz, Criterio(texto=r"guia\d+", expressao_regular=True))
    checa_igual(len(resultados), 2, "regex acha as duas guias numeradas")

    resultados, _ = bfa.procurar(
        tarefa, raiz, Criterio(texto="guia", palavra_inteira=True))
    checa_igual(len(resultados), 1,
                "palavra inteira acha apenas o 'guia' isolado")

    resultados, _ = bfa.procurar(
        tarefa, raiz, Criterio(texto="GUIA", diferenciar_maiusculas=True))
    checa_igual(resultados, [],
                "diferenciando a caixa, 'GUIA' nao acha 'guia'")

# ---------------------------------------------------------------------------
secao("8 - pasta inexistente e pasta vazia")

with pasta_temporaria() as raiz:
    tarefa = TarefaFalsa()
    resultados, resumo = bfa.procurar(tarefa, raiz / "nao_existe", CRITERIO)
    checa_igual(resultados, [],
                "pasta inexistente devolve lista vazia, sem estourar")
    checa_igual(resumo.ocorrencias, 0, "e nenhuma ocorrencia")

    resultados, resumo = bfa.procurar(tarefa, raiz, CRITERIO)
    checa_igual(resultados, [], "pasta vazia devolve lista vazia")

# ---------------------------------------------------------------------------
secao("9 - o trecho e' aparado e cortado")

with pasta_temporaria() as raiz:
    longa = "    " + "x" * 500 + " numeroGuia " + "y" * 500 + "\n"
    (raiz / "longa.txt").write_text(longa, encoding="utf-8")
    resultados, _ = bfa.procurar(TarefaFalsa(), raiz, CRITERIO)
    checa_igual(len(resultados), 1, "acha na linha longa")
    trecho = resultados[0].trecho
    checa(len(trecho) <= 300,
          f"o trecho e' cortado em 300 caracteres ({len(trecho)}) -- uma linha "
          f"de JS minificado tornaria o painel inutil")
    checa(not trecho.startswith(" "), "e e' aparado no inicio")

sys.exit(resumir())
