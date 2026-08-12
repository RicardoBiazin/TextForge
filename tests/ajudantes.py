"""Utilidades comuns as suites de teste.

Formato de saida, identico ao do Sincronizador -- o `rodar_todos.py` conta as
ocorrencias de "\\n  OK   " e "\\n  FALHA" na saida de cada suite, entao os
espacos importam:

    checa(cond, "descricao do que foi verificado")

No fim da suite, `resumir()` imprime o total e devolve o codigo de saida.

Importante: `preparar_qt()` define QT_QPA_PLATFORM=offscreen ANTES de importar
PySide6. Se algum modulo importar Qt antes disso, a plataforma ja' esta' escolhida
e o teste abriria janelas de verdade -- por isso toda suite de interface chama
`preparar_qt()` na primeira linha executavel, antes de qualquer outro import do
projeto que arraste Qt.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Iterator

# Deixa `import textforge` funcionar rodando `python tests/teste_x.py` de
# qualquer pasta, sem precisar instalar o pacote nem mexer no PYTHONPATH.
RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

falhas: list[str] = []
_total = 0


def checa(condicao: object, mensagem: str) -> bool:
    """Registra uma verificacao. Devolve o booleano, para poder encadear."""
    global _total
    _total += 1
    ok = bool(condicao)
    print(("  OK   " if ok else "  FALHA") + " " + mensagem)
    if not ok:
        falhas.append(mensagem)
    return ok


def checa_igual(obtido: object, esperado: object, mensagem: str) -> bool:
    """Como `checa`, mas mostra os valores quando falha -- economiza um ciclo
    inteiro de "rodar de novo com print no meio"."""
    ok = obtido == esperado
    if ok:
        return checa(True, mensagem)
    return checa(False, f"{mensagem}\n         esperado: {esperado!r}"
                        f"\n         obtido:   {obtido!r}")


def checa_levanta(excecao: type[BaseException], funcao, mensagem: str,
                  *args, **kwargs) -> bool:
    try:
        funcao(*args, **kwargs)
    except excecao:
        return checa(True, mensagem)
    except BaseException as exc:      # noqa: BLE001 - o teste quer saber qual foi
        return checa(False, f"{mensagem} (levantou {exc.__class__.__name__})")
    return checa(False, f"{mensagem} (nao levantou nada)")


def secao(titulo: str) -> None:
    print(f"\n[{titulo}]")


def resumir() -> int:
    print()
    if falhas:
        print("FALHAS: %d de %d verificacoes" % (len(falhas), _total))
        for f in falhas:
            print("  - " + f.splitlines()[0])
    else:
        print("TODOS OS TESTES PASSARAM (%d verificacoes)" % _total)
    return 1 if falhas else 0


# -- ambiente ---------------------------------------------------------------


def preparar_qt() -> bool:
    """Prepara uma QApplication invisivel. False se PySide6 nao esta' instalado.

    Uma suite que precisa de Qt e nao o encontra deve imprimir PULADO e sair com
    0, nao falhar: assim o runner continua util numa maquina onde o venv ainda
    nao foi montado.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return False
    if QApplication.instance() is None:
        QApplication([])
    return True


def pular(motivo: str) -> int:
    print(f"PULADO: {motivo}")
    return 0


@contextlib.contextmanager
def pasta_temporaria(prefixo: str = "textforge-teste-") -> Iterator[pathlib.Path]:
    """Pasta temporaria apagada no fim, mesmo se o teste estourar."""
    caminho = pathlib.Path(tempfile.mkdtemp(prefix=prefixo))
    try:
        yield caminho
    finally:
        shutil.rmtree(caminho, ignore_errors=True)


@contextlib.contextmanager
def appdata_temporario() -> Iterator[pathlib.Path]:
    """Aponta %APPDATA% para uma pasta descartavel.

    Sem isto os testes de configuracao e de sessao escreveriam no
    %APPDATA%\\TextForge de verdade e apagariam as preferencias do usuario --
    exatamente o tipo de dano colateral que um teste nunca deve causar.
    """
    anterior = os.environ.get("APPDATA")
    with pasta_temporaria("textforge-appdata-") as pasta:
        os.environ["APPDATA"] = str(pasta)
        try:
            yield pasta
        finally:
            if anterior is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = anterior


def escrever_bytes(caminho: pathlib.Path, dados: bytes) -> pathlib.Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    return caminho
