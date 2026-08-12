"""Localiza os arquivos de `textforge/recursos/` com e sem PyInstaller.

Sem este modulo os temas e os provedores declarativos desaparecem no .exe: o
PyInstaller descompacta os `datas` em `sys._MEIPASS`, que nao e' a pasta do
pacote nem a pasta do executavel. Todo acesso a recurso passa por aqui, e o
`teste_empacotamento.py` confere que cada arquivo de recursos/ esta' declarado
no `datas` do .spec.
"""

from __future__ import annotations

import pathlib
import sys


def raiz() -> pathlib.Path:
    """Pasta que contem `textforge/recursos`."""
    interna = getattr(sys, "_MEIPASS", None)
    if interna:
        return pathlib.Path(interna)
    return pathlib.Path(__file__).resolve().parent.parent


def caminho(*partes: str) -> pathlib.Path:
    """Caminho de um recurso embutido, ex.: caminho("temas", "escuro.json")."""
    return raiz().joinpath("textforge", "recursos", *partes)


def ler_texto(*partes: str) -> str:
    return caminho(*partes).read_text(encoding="utf-8")


def listar(subpasta: str, padrao: str = "*") -> list[pathlib.Path]:
    """Arquivos de uma subpasta de recursos. Lista vazia se ela nao existir."""
    pasta = caminho(subpasta)
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.glob(padrao) if p.is_file())
