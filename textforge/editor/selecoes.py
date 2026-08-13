"""Camadas de `ExtraSelection` no editor.

`QPlainTextEdit.setExtraSelections()` recebe UMA lista e substitui tudo o que
havia. Como varios recursos desenham fundo ao mesmo tempo -- linha atual, todas
as ocorrencias da busca, a ocorrencia sob o cursor, o par de parenteses casado,
os cursores secundarios, as linhas do diff -- quem chamasse `setExtraSelections`
diretamente apagaria o desenho dos outros.

Este gerenciador guarda camadas NOMEADAS e concatena na ordem certa. Cada recurso
mexe so' na camada dele:

    self.selecoes.definir("linha_atual", [sel])
    self.selecoes.limpar("busca")

Ordem importa: quem vem depois pinta por cima. A `PRIORIDADES` abaixo e' a
resposta a "por que a ocorrencia atual aparece sobre o realce das outras".
"""

from __future__ import annotations

from PySide6.QtWidgets import QTextEdit

# Menor pinta primeiro (fica por baixo).
PRIORIDADES = {
    "linha_atual": 10,
    "coluna_limite": 15,
    "diff": 20,
    "ocorrencias": 30,        # todas as ocorrencias da busca
    "ocorrencia_atual": 40,   # a que o F3 acabou de alcancar
    "selecao_extra": 50,      # selecoes dos cursores secundarios
    "pares": 60,              # ( ) [ ] { } casados
    "erro": 70,               # sublinhado ondulado da validacao
}
PRIORIDADE_PADRAO = 35


class GerenciadorDeSelecoes:
    def __init__(self, editor) -> None:      # QPlainTextEdit
        self._editor = editor
        self._camadas: dict[str, list[QTextEdit.ExtraSelection]] = {}

    def definir(self, camada: str,
                selecoes: list[QTextEdit.ExtraSelection]) -> None:
        """Substitui o conteudo de UMA camada e repinta."""
        if selecoes:
            self._camadas[camada] = list(selecoes)
        else:
            self._camadas.pop(camada, None)
        self.aplicar()

    def limpar(self, camada: str) -> None:
        if self._camadas.pop(camada, None) is not None:
            self.aplicar()

    def limpar_tudo(self) -> None:
        self._camadas.clear()
        self.aplicar()

    def tem(self, camada: str) -> bool:
        return camada in self._camadas

    def quantas(self, camada: str) -> int:
        return len(self._camadas.get(camada, ()))

    def camadas(self) -> list[str]:
        return sorted(self._camadas, key=self._ordem)

    def _ordem(self, camada: str) -> int:
        return PRIORIDADES.get(camada, PRIORIDADE_PADRAO)

    def aplicar(self) -> None:
        todas: list[QTextEdit.ExtraSelection] = []
        for camada in sorted(self._camadas, key=self._ordem):
            todas.extend(self._camadas[camada])
        self._editor.setExtraSelections(todas)
