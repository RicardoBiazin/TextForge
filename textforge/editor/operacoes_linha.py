"""Operacoes sobre linhas (requisito 22).

Funcoes puras sobre `list[str]`: recebem linhas, devolvem linhas. Nenhuma delas
conhece Qt, cursor ou documento -- quem aplica ao editor e' o `widget.py`, que
envolve tudo num `beginEditBlock`/`endEditBlock` para o conjunto virar UM passo
de desfazer.

Essa separacao e' o que permite testar "remover linhas duplicadas preserva a
primeira ocorrencia" sem abrir janela nenhuma, e e' o que vai permitir que a
Command Palette e um plugin usem as mesmas operacoes.

Cuidado que atravessa o arquivo: estas operacoes servem a arquivos TECNICOS. Um
`.dat` de largura fixa, um `.csv` e um `.log` tem espaco significativo, entao
nada apara, reordena nem normaliza mais do que a operacao pedida diz.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Duplicar, mover, excluir
# ---------------------------------------------------------------------------


def duplicar(linhas: list[str]) -> list[str]:
    """Repete o bloco logo abaixo dele mesmo."""
    return list(linhas) + list(linhas)


def mover_para_cima(todas: list[str], inicio: int, fim: int) -> tuple[list[str], int]:
    """Troca o bloco [inicio, fim) com a linha de cima.

    Devolve (linhas novas, deslocamento) -- o deslocamento e' quanto o cursor
    precisa andar para continuar sobre o mesmo texto. Sem devolver isso, mover
    uma linha faria o cursor "escorregar" e a repeticao do atalho moveria outra
    linha.
    """
    if inicio <= 0 or inicio >= fim or fim > len(todas):
        return list(todas), 0
    novas = list(todas)
    bloco = novas[inicio:fim]
    acima = novas[inicio - 1]
    novas[inicio - 1:fim] = bloco + [acima]
    return novas, -1


def mover_para_baixo(todas: list[str], inicio: int,
                     fim: int) -> tuple[list[str], int]:
    """Troca o bloco [inicio, fim) com a linha de baixo."""
    if inicio < 0 or inicio >= fim or fim >= len(todas):
        return list(todas), 0
    novas = list(todas)
    bloco = novas[inicio:fim]
    abaixo = novas[fim]
    novas[inicio:fim + 1] = [abaixo] + bloco
    return novas, 1


# ---------------------------------------------------------------------------
# Ordenar
# ---------------------------------------------------------------------------


def ordenar(linhas: list[str], *, ignorar_caixa: bool = False,
            invertido: bool = False, numerico: bool = False) -> list[str]:
    """Ordena as linhas.

    `numerico=True` ordena pelo primeiro numero que aparece na linha, o que e' o
    que se quer num log ou num relatorio -- a ordenacao alfabetica poe "10"
    antes de "9".
    """
    if numerico:
        return sorted(linhas, key=lambda l: (_primeiro_numero(l), l),
                      reverse=invertido)
    if ignorar_caixa:
        # A chave secundaria mantem a ordenacao ESTAVEL e previsivel entre linhas
        # que diferem so' na caixa: sem ela, "Erro" e "erro" sairiam em ordem
        # arbitraria conforme a ordem de entrada.
        return sorted(linhas, key=lambda l: (l.casefold(), l),
                      reverse=invertido)
    return sorted(linhas, reverse=invertido)


def _primeiro_numero(linha: str) -> float:
    numero = ""
    for ch in linha:
        if ch.isdigit() or (ch in "-+" and not numero):
            numero += ch
        elif ch == "." and numero and "." not in numero:
            numero += ch
        elif numero:
            break
    try:
        return float(numero)
    except ValueError:
        # Linha sem numero vai para o fim, e nao para o comeco: numa lista de
        # itens numerados, o cabecalho ou o rodape sem numero atrapalha menos la'.
        return float("inf")


def inverter(linhas: list[str]) -> list[str]:
    return list(reversed(linhas))


# ---------------------------------------------------------------------------
# Remover
# ---------------------------------------------------------------------------


def remover_duplicadas(linhas: list[str], *,
                       ignorar_caixa: bool = False) -> list[str]:
    """Remove repeticoes preservando a PRIMEIRA ocorrencia e a ordem.

    Nao ordena de proposito. Ordenar para deduplicar (o truque do `sort -u`)
    destruiria a ordem cronologica de um log, que costuma ser a informacao mais
    importante do arquivo.
    """
    vistas: set[str] = set()
    saida: list[str] = []
    for linha in linhas:
        chave = linha.casefold() if ignorar_caixa else linha
        if chave not in vistas:
            vistas.add(chave)
            saida.append(linha)
    return saida


def remover_vazias(linhas: list[str], *, so_consecutivas: bool = False
                   ) -> list[str]:
    """Remove linhas em branco (inclusive as que so' tem espaco/TAB).

    `so_consecutivas=True` colapsa varias em branco numa unica, em vez de tirar
    todas -- e' o que se quer em texto legivel, onde a linha em branco separa
    paragrafos.
    """
    if not so_consecutivas:
        return [l for l in linhas if l.strip()]
    saida: list[str] = []
    anterior_vazia = False
    for linha in linhas:
        vazia = not linha.strip()
        if not (vazia and anterior_vazia):
            saida.append(linha)
        anterior_vazia = vazia
    return saida


# ---------------------------------------------------------------------------
# Aparar e acrescentar
# ---------------------------------------------------------------------------


def aparar_inicio(linhas: list[str]) -> list[str]:
    return [l.lstrip() for l in linhas]


def aparar_fim(linhas: list[str]) -> list[str]:
    return [l.rstrip() for l in linhas]


def aparar_ambos(linhas: list[str]) -> list[str]:
    return [l.strip() for l in linhas]


def prefixar(linhas: list[str], texto: str, *,
             pular_vazias: bool = True) -> list[str]:
    """Insere `texto` no inicio de cada linha.

    `pular_vazias` por padrao: prefixar uma linha em branco cria espaco no fim da
    linha, que e' ruido no diff e reclamacao garantida em revisao de codigo.
    """
    return [l if (pular_vazias and not l.strip()) else texto + l for l in linhas]


def sufixar(linhas: list[str], texto: str, *,
            pular_vazias: bool = True) -> list[str]:
    return [l if (pular_vazias and not l.strip()) else l + texto for l in linhas]


def numerar(linhas: list[str], inicio: int = 1, formato: str = "{n}: ") -> list[str]:
    """Prefixa cada linha com seu numero. Util em log e em lista de dados."""
    largura = len(str(inicio + len(linhas) - 1))
    return [formato.format(n=str(inicio + i).rjust(largura)) + linha
            for i, linha in enumerate(linhas)]


# ---------------------------------------------------------------------------
# Juntar e dividir
# ---------------------------------------------------------------------------


def juntar(linhas: list[str], separador: str = " ") -> list[str]:
    """Une as linhas numa so'. Devolve lista de um elemento, por consistencia."""
    return [separador.join(l.strip() for l in linhas if l.strip())]
