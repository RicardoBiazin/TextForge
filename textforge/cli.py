"""Linha de comando (requisito 32).

    textforge arquivo.xml
    textforge C:\\Projetos\\config.php
    textforge arquivo.txt --line 850
    textforge --nova-janela a.txt b.txt

Um caminho vindo da linha de comando ou do Explorer e' entrada NAO CONFIAVEL.
`normalizar_alvos` resolve o caminho e recusa o que nao for arquivo regular:
abrir um pipe nomeado ou um caminho de dispositivo (\\\\.\\PhysicalDrive0, CON,
NUL) pendura o processo na leitura, ou pior.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass, field

from textforge import APP, VERSAO

# Nomes reservados de dispositivo no Windows. Abrir qualquer um deles como
# arquivo tem comportamento surpreendente; alguns nunca terminam de ler.
DISPOSITIVOS = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
})


@dataclass
class Alvo:
    caminho: pathlib.Path
    linha: int = 0            # 0 = nao posicionar
    coluna: int = 0


@dataclass
class Argumentos:
    alvos: list[Alvo] = field(default_factory=list)
    nova_janela: bool = False
    autoverificacao: bool = False
    recusados: list[tuple[str, str]] = field(default_factory=list)

    def como_pedido(self) -> dict:
        """Forma serializavel, para mandar a outra instancia por QLocalSocket."""
        return {
            "arquivos": [{"caminho": str(a.caminho), "linha": a.linha,
                          "coluna": a.coluna} for a in self.alvos],
        }


def _seguro(bruto: str) -> tuple[pathlib.Path | None, str]:
    """Valida um caminho da linha de comando. (caminho, motivo_da_recusa)."""
    if not bruto or bruto.strip() == "":
        return None, "caminho vazio"
    if bruto.split(":")[0].strip().lower() in DISPOSITIVOS:
        return None, "nome reservado de dispositivo do Windows"
    if pathlib.PurePath(bruto).stem.lower() in DISPOSITIVOS:
        return None, "nome reservado de dispositivo do Windows"
    try:
        # strict=False: um caminho inexistente e' valido (o usuario quer criar).
        # O que interessa aqui e' resolver ".." e links antes de julgar.
        alvo = pathlib.Path(bruto).expanduser().resolve(strict=False)
    except (OSError, ValueError) as exc:
        return None, f"caminho invalido ({exc.__class__.__name__})"
    if alvo.exists() and not alvo.is_file():
        # Pasta, pipe nomeado, dispositivo de bloco: nada disso e' documento.
        return None, "nao e' um arquivo"
    return alvo, ""


def normalizar_alvos(caminhos: list[str], linha: int = 0,
                     coluna: int = 0) -> tuple[list[Alvo], list[tuple[str, str]]]:
    """Devolve (alvos aceitos, [(caminho, motivo) recusados])."""
    alvos: list[Alvo] = []
    recusados: list[tuple[str, str]] = []
    for bruto in caminhos:
        alvo, motivo = _seguro(bruto)
        if alvo is None:
            recusados.append((bruto, motivo))
        else:
            alvos.append(Alvo(caminho=alvo, linha=linha, coluna=coluna))
    # --line vale so' para o primeiro arquivo: pedir a linha 850 de cinco
    # arquivos diferentes nao quer dizer nada.
    for extra in alvos[1:]:
        extra.linha = 0
        extra.coluna = 0
    return alvos, recusados


def analisar(argv: list[str] | None = None) -> Argumentos:
    p = argparse.ArgumentParser(
        prog="textforge",
        description=f"{APP} {VERSAO} - editor de arquivos tecnicos.",
        epilog="Abrir um arquivo nunca executa o conteudo dele.")
    p.add_argument("arquivos", nargs="*", help="arquivos a abrir")
    p.add_argument("--line", "-l", type=int, default=0, dest="linha",
                   metavar="N", help="posicionar o cursor na linha N")
    p.add_argument("--col", "-c", type=int, default=0, dest="coluna",
                   metavar="N", help="coluna, usado junto com --line")
    p.add_argument("--nova-janela", action="store_true",
                   help="abrir numa janela nova em vez de reusar a existente")
    # Flag interna, usada pelo build.bat: sobe a interface em modo invisivel,
    # confere que os imports tardios resolvem, e sai. Serve para o build falhar
    # quando um `exclude` do .spec quebra o app -- que e' um erro que so'
    # aparece em tempo de execucao.
    p.add_argument("--autoverificacao", action="store_true",
                   help=argparse.SUPPRESS)
    p.add_argument("--versao", "-V", action="version",
                   version=f"{APP} {VERSAO}")

    ns = p.parse_args(argv)
    alvos, recusados = normalizar_alvos(ns.arquivos, max(0, ns.linha),
                                        max(0, ns.coluna))
    return Argumentos(alvos=alvos, nova_janela=ns.nova_janela,
                      autoverificacao=ns.autoverificacao, recusados=recusados)
