"""Pesquisar em arquivos (requisito 8).

Varre uma pasta e devolve arquivo, linha e trecho, para o painel de resultados
abrir direto na linha.

Roda numa `Tarefa` (thread), com progresso e cancelamento -- varrer `C:\\Projetos`
inteiro leva minutos, e travar a interface durante isso nao e' opcao. Os resultados
saem em LOTES por sinal, e nao um por um: 5 mil sinais atravessando a fila de
eventos da interface custam mais que a leitura dos arquivos.

Tres cuidados de robustez que a varredura de pasta exige, e que um `os.walk` ingenuo
nao tem:

  * `followlinks=False` mais um conjunto de identidades ja' visitadas. Uma junction
    do Windows apontando para um ancestral faz a varredura nunca terminar.
  * arquivo BINARIO e' pulado. Procurar "guia" dentro de um .exe de 80 MB gasta o
    tempo do usuario e nao produz nada util.
  * arquivo GRANDE demais e' pulado, com aviso. Ler um .log de 2 GB para memoria
    durante uma busca em pasta derrubaria o processo.
"""

from __future__ import annotations

import fnmatch
import os
import pathlib
from dataclasses import dataclass, field

from textforge import arquivos, codificacao, log_interno
from textforge.busca import Criterio

log = log_interno.obter(__name__)

# Padroes ignorados sempre. Sao pastas geradas: varrer node_modules ou .git
# multiplica o tempo da busca por dez e nao devolve nada que o usuario queira.
PASTAS_IGNORADAS = frozenset({
    ".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist",
    "build", ".idea", ".vs", "bin", "obj", ".next", ".nuxt", "vendor",
})

# Acima disto o arquivo e' pulado durante a busca EM PASTA (abrir o arquivo
# diretamente continua funcionando, com o Large File Mode).
LIMITE_POR_ARQUIVO = 32 * 1024 * 1024

# Tamanho do lote de resultados entregues por sinal.
TAMANHO_DO_LOTE = 50

# Teto de resultados. Sem ele, procurar "e" em C:\ enche a memoria.
LIMITE_DE_RESULTADOS = 20_000


@dataclass(frozen=True)
class Resultado:
    caminho: pathlib.Path
    linha: int                     # BASE ZERO
    coluna: int
    tamanho: int
    trecho: str                    # a linha inteira, aparada

    @property
    def rotulo(self) -> str:
        return f"{self.caminho.name}:{self.linha + 1}"


@dataclass
class Resumo:
    arquivos_lidos: int = 0
    arquivos_pulados: int = 0
    ocorrencias: int = 0
    arquivos_com_ocorrencia: int = 0
    cortado: bool = False
    motivos_de_pulo: dict[str, int] = field(default_factory=dict)

    def pular(self, motivo: str) -> None:
        self.arquivos_pulados += 1
        self.motivos_de_pulo[motivo] = self.motivos_de_pulo.get(motivo, 0) + 1

    def descrever(self) -> str:
        partes = [f"{self.ocorrencias} ocorrencia(s) em "
                  f"{self.arquivos_com_ocorrencia} arquivo(s)",
                  f"{self.arquivos_lidos} lido(s)"]
        if self.arquivos_pulados:
            detalhe = ", ".join(f"{n} {m}" for m, n
                                in sorted(self.motivos_de_pulo.items()))
            partes.append(f"{self.arquivos_pulados} pulado(s): {detalhe}")
        if self.cortado:
            partes.append(f"lista cortada em {LIMITE_DE_RESULTADOS}")
        return " · ".join(partes)


def filtros_de(texto: str) -> list[str]:
    """Traduz "*.php; *.py, *.xml" numa lista de padroes.

    Aceita ponto e virgula, virgula e espaco como separadores -- e' o que as
    pessoas digitam, e recusar uma das formas so' geraria busca vazia sem
    explicacao.
    """
    bruto = texto.replace(";", " ").replace(",", " ")
    padroes = [p.strip() for p in bruto.split() if p.strip()]
    return padroes or ["*"]


def _casa_algum(nome: str, padroes: list[str]) -> bool:
    minusculo = nome.lower()
    return any(fnmatch.fnmatch(minusculo, p.lower()) for p in padroes)


def _identidade(caminho: pathlib.Path):
    """Identidade do sistema de arquivos, para detectar caminho ja' visitado.

    (st_dev, st_ino) e' o par canonico. No Windows o `st_ino` do Python funciona em
    NTFS, o que basta para pegar junction e link simbolico apontando para um
    ancestral -- o caso que faz a varredura nunca terminar.
    """
    try:
        info = caminho.stat()
        return (info.st_dev, info.st_ino)
    except OSError:
        return None


def procurar(tarefa, pasta: str | os.PathLike[str], criterio: Criterio,
             filtros: list[str] | None = None, *,
             subpastas: bool = True,
             ignorar_geradas: bool = True,
             limite_por_arquivo: int = LIMITE_POR_ARQUIVO
             ) -> tuple[list[Resultado], Resumo]:
    """Varre `pasta`. Feita para rodar dentro de uma `Tarefa`.

    `tarefa` fornece `checar_cancelamento()`, `progresso()` e `dizer()`. Em teste,
    qualquer objeto com esses tres metodos serve -- e' o que permite testar a
    varredura sem Qt.
    """
    padrao = criterio.compilar()
    padroes = filtros or ["*"]
    raiz = pathlib.Path(pasta)
    resultados: list[Resultado] = []
    resumo = Resumo()
    visitados: set = set()

    for pasta_atual, subdiretorios, nomes in os.walk(raiz, followlinks=False):
        tarefa.checar_cancelamento()
        atual = pathlib.Path(pasta_atual)

        # Junction/link apontando para um ancestral: sem esta guarda, a varredura
        # nao termina.
        identidade = _identidade(atual)
        if identidade is not None:
            if identidade in visitados:
                log.warning("pasta ja' visitada, laco evitado: %s", atual)
                subdiretorios[:] = []
                continue
            visitados.add(identidade)

        if ignorar_geradas:
            # Alterar `subdiretorios` NO LUGAR e' o que faz o os.walk nao descer
            # nelas -- construir uma lista nova nao teria efeito.
            subdiretorios[:] = [d for d in subdiretorios
                                if d.lower() not in PASTAS_IGNORADAS]
        if not subpastas:
            subdiretorios[:] = []

        tarefa.dizer(str(atual))
        for nome in sorted(nomes):
            tarefa.checar_cancelamento()
            if not _casa_algum(nome, padroes):
                continue
            caminho = atual / nome
            achados = _procurar_no_arquivo(caminho, padrao, resumo,
                                           limite_por_arquivo)
            if achados:
                resumo.arquivos_com_ocorrencia += 1
                resumo.ocorrencias += len(achados)
                resultados.extend(achados)
                if len(resultados) >= LIMITE_DE_RESULTADOS:
                    resumo.cortado = True
                    log.info("busca cortada em %d resultados",
                             LIMITE_DE_RESULTADOS)
                    return resultados[:LIMITE_DE_RESULTADOS], resumo
            tarefa.progresso(resumo.arquivos_lidos, -1)

    return resultados, resumo


def _procurar_no_arquivo(caminho: pathlib.Path, padrao, resumo: Resumo,
                         limite: int) -> list[Resultado]:
    try:
        tamanho = caminho.stat().st_size
    except OSError:
        resumo.pular("sem acesso")
        return []
    if tamanho > limite:
        resumo.pular("grandes demais")
        return []

    try:
        dados = arquivos.ler_bytes(caminho)
    except OSError:
        resumo.pular("sem acesso")
        return []

    if codificacao.parece_binario(dados):
        resumo.pular("binarios")
        return []

    perfil = codificacao.detectar(dados)
    if perfil.binario:
        resumo.pular("binarios")
        return []

    resumo.arquivos_lidos += 1
    achados: list[Resultado] = []
    for numero, linha in enumerate(perfil.texto.split("\n")):
        for casamento in padrao.finditer(linha):
            achados.append(Resultado(
                caminho=caminho, linha=numero, coluna=casamento.start(),
                tamanho=casamento.end() - casamento.start(),
                # A linha e' aparada e cortada: o painel mostra uma coluna, e uma
                # linha de 8000 caracteres de JS minificado o tornaria inutil.
                trecho=linha.strip()[:300]))
            if casamento.end() == casamento.start():
                break            # padrao que casa vazio: uma vez por linha basta
    return achados


def montar_tarefa(pasta, criterio: Criterio, filtros: list[str] | None = None,
                  **opcoes):
    """Cria a `Tarefa` pronta para `tarefas.rodar(..., disco=True)`."""
    from textforge import tarefas

    return tarefas.Tarefa(
        f"buscar {criterio.texto!r} em {pasta}",
        procurar, pasta, criterio, filtros, **opcoes)
