"""`FonteDeTexto`: a unica interface entre as views e os dados.

Este e' o modulo do qual todo o resto depende, e existe por um motivo concreto.
O TextForge tem DOIS mundos de dados:

  * o `QTextDocument`, para arquivo normal, editavel, com undo do Qt;
  * o arquivo mapeado por mmap com indice de linhas, para arquivo grande --
    porque um `QTextDocument` de 1 GB consome varios GB de RAM e congela a
    interface durante o layout.

Se a busca, o diff, o hex, o CSV e o tail falassem direto com um deles, adicionar
o outro exigiria refatorar o nucleo. Falando todos com `FonteDeTexto`, cada um
funciona nos dois mundos sem saber qual esta' por baixo.

CONVENCAO DE NUMERACAO, valida em todo o modulo: as linhas sao contadas de ZERO.
A conversao para a numeracao de 1 que o usuario ve acontece na interface, num
lugar so'. Misturar as duas e' a fonte classica de erro de um-a-menos em
"ir para linha".

CONVENCAO DE CONTAGEM: o numero de linhas e' `numero de \\n + 1`, igual a
`texto.split("\\n")`. Ou seja, "a\\nb\\n" tem TRES linhas: "a", "b" e a linha
vazia final onde o cursor pode ficar. E' tambem a convencao do `QTextDocument`,
o que faz as duas implementacoes concordarem sem conversao.
"""

from __future__ import annotations

import mmap
import os
import pathlib
import re
from typing import Callable, Iterator, NamedTuple, Protocol, runtime_checkable

from textforge import log_interno

log = log_interno.obter(__name__)

# Uma linha do indice a cada 1024 linhas do arquivo. O indice completo de um
# arquivo de 1 GB com linhas de 80 bytes teria ~13 milhoes de entradas (~100 MB
# de RAM); esparso, sao ~13 mil (~100 KB). Para achar a linha n, salta-se ao
# marcador n // 1024 e varre-se no maximo 1023 linhas -- imperceptivel.
PASSO_DO_INDICE = 1024

# Quanto se le' do mmap por vez ao indexar. Grande o bastante para o custo por
# byte ser o do memcpy, pequeno o bastante para o cancelamento responder rapido.
BLOCO_DE_LEITURA = 4 * 1024 * 1024

# Teto de tamanho de uma unica linha ao ler para exibicao. Um arquivo binario
# aberto por engano pode nao ter nenhum \n em 1 GB, e decodificar isso de uma vez
# derrubaria o processo por falta de memoria.
LIMITE_DE_LINHA_LIDA = 1024 * 1024


class Achado(NamedTuple):
    """Uma ocorrencia encontrada. `inicio`/`fim` sao offsets DENTRO da linha."""

    linha: int
    inicio: int
    fim: int
    texto: str          # a linha inteira, para o painel de resultados


@runtime_checkable
class FonteDeTexto(Protocol):
    """O contrato. Ver o cabecalho do modulo para as convencoes."""

    def total_de_linhas(self) -> int: ...

    def linha(self, n: int) -> str:
        """Linha `n` (base zero), SEM o terminador. String vazia fora da faixa."""

    def faixa(self, inicio: int, fim: int) -> list[str]:
        """Linhas [inicio, fim). Recortado nos limites, nunca levanta."""

    def buscar(self, padrao: re.Pattern[str], de_linha: int = 0,
               cancelar: Callable[[], bool] | None = None) -> Iterator[Achado]:
        """Ocorrencias de `padrao`, linha por linha, a partir de `de_linha`.

        Quem monta o `padrao` e' o `busca.py` -- e' la' que 'diferenciar
        maiusculas', 'palavra inteira' e 'expressao regular' viram flags e
        ancoras. A fonte so' aplica.
        """

    def editavel(self) -> bool: ...

    def tamanho_em_bytes(self) -> int: ...


# ---------------------------------------------------------------------------
# Implementacao 1: texto em memoria
# ---------------------------------------------------------------------------


class FonteEmMemoria:
    """Fonte sobre uma `str`. Sem Qt, o que a torna a referencia dos testes.

    Usada de verdade tambem pelo diff e pelo CSV, que trabalham sobre um texto
    ja' carregado e nao precisam de um QTextDocument para isso.
    """

    def __init__(self, texto: str) -> None:
        self._linhas = texto.split("\n")

    def total_de_linhas(self) -> int:
        return len(self._linhas)

    def linha(self, n: int) -> str:
        if 0 <= n < len(self._linhas):
            return self._linhas[n]
        return ""

    def faixa(self, inicio: int, fim: int) -> list[str]:
        inicio = max(0, inicio)
        fim = min(len(self._linhas), fim)
        if fim <= inicio:
            return []
        return self._linhas[inicio:fim]

    def buscar(self, padrao: re.Pattern[str], de_linha: int = 0,
               cancelar: Callable[[], bool] | None = None) -> Iterator[Achado]:
        yield from _buscar_por_linha(self, padrao, de_linha, cancelar)

    def editavel(self) -> bool:
        return True

    def tamanho_em_bytes(self) -> int:
        return len(self.texto().encode("utf-8", "replace"))

    def texto(self) -> str:
        return "\n".join(self._linhas)


# ---------------------------------------------------------------------------
# Implementacao 2: QTextDocument vivo
# ---------------------------------------------------------------------------


class FonteDeDocumento:
    """Fonte sobre um `QTextDocument` que esta' sendo editado.

    Le' sempre o estado atual do documento -- nao guarda copia. E' o que permite
    a busca e o painel Estrutura verem o que o usuario acabou de digitar.
    """

    def __init__(self, documento) -> None:      # QTextDocument
        self._doc = documento

    def total_de_linhas(self) -> int:
        return self._doc.blockCount()

    def linha(self, n: int) -> str:
        bloco = self._doc.findBlockByNumber(n)
        if not bloco.isValid():
            return ""
        # `QTextBlock.text()` ja' devolve o texto do bloco sem separador. Note
        # que ele NAO faz a substituicao de nbsp que `toPlainText()` faz -- por
        # isso ler bloco a bloco tambem e' seguro para arquivo tecnico.
        return bloco.text()

    def faixa(self, inicio: int, fim: int) -> list[str]:
        inicio = max(0, inicio)
        fim = min(self._doc.blockCount(), fim)
        if fim <= inicio:
            return []
        saida: list[str] = []
        bloco = self._doc.findBlockByNumber(inicio)
        # Percorrer com next() e' O(k) para k blocos; chamar
        # findBlockByNumber() num laco seria O(k * log n) ou pior.
        while bloco.isValid() and len(saida) < fim - inicio:
            saida.append(bloco.text())
            bloco = bloco.next()
        return saida

    def buscar(self, padrao: re.Pattern[str], de_linha: int = 0,
               cancelar: Callable[[], bool] | None = None) -> Iterator[Achado]:
        yield from _buscar_por_linha(self, padrao, de_linha, cancelar)

    def editavel(self) -> bool:
        return True

    def tamanho_em_bytes(self) -> int:
        # Aproximacao em CARACTERES, nao em bytes: os bytes de verdade dependem
        # do encoding e do BOM, que sao do `Documento`, nao do QTextDocument.
        # Quem precisa do tamanho exato do arquivo pergunta ao Documento.
        return self._doc.characterCount()


# ---------------------------------------------------------------------------
# Implementacao 3: arquivo grande, mmap + indice esparso
# ---------------------------------------------------------------------------


class FonteDeArquivo:
    """Fonte somente leitura sobre um arquivo grande, sem carrega-lo na memoria.

    Estrategia: mmap para o sistema operacional cuidar da paginacao, mais um
    indice ESPARSO de offsets de inicio de linha (ver `PASSO_DO_INDICE`). So' as
    linhas que a tela pede sao decodificadas.

    A indexacao e' INCREMENTAL de proposito: `indexar(orcamento)` avanca um
    pedaco e volta. Assim a abertura e' instantanea -- a etapa 10 chama isso de
    uma QThread com progresso e cancelamento, e a barra de rolagem cresce
    conforme o indice avanca, enquanto o usuario ja' le' o comeco do arquivo.

    Somente leitura na v1. O motivo: editar exigiria undo virtualizado e
    reescrever 1 GB no disco a cada salvamento. O caso real de um arquivo desses
    e' ler e pesquisar dentro de um log gigante, e isso funciona inteiro aqui.
    """

    def __init__(self, caminho: str | os.PathLike[str],
                 codificacao: str = "utf-8",
                 passo: int = PASSO_DO_INDICE) -> None:
        self.caminho = pathlib.Path(caminho)
        self.codificacao = codificacao
        self._passo = max(1, passo)
        self._arquivo = open(self.caminho, "rb")
        self._tamanho = os.fstat(self._arquivo.fileno()).st_size
        # mmap de tamanho zero levanta ValueError no Windows.
        self._mapa: mmap.mmap | None = None
        if self._tamanho > 0:
            self._mapa = mmap.mmap(self._arquivo.fileno(), 0,
                                   access=mmap.ACCESS_READ)

        # marcadores[k] = offset em bytes onde comeca a linha k * passo.
        self._marcadores: list[int] = [0]
        self._quebras = 0        # quantos \n foram contados ate' agora
        self._varrido = 0        # ate' que offset o indice esta' construido
        self._fechada = False

    # -- ciclo de vida -----------------------------------------------------

    def fechar(self) -> None:
        if self._fechada:
            return
        self._fechada = True
        if self._mapa is not None:
            self._mapa.close()
            self._mapa = None
        self._arquivo.close()

    def __enter__(self) -> "FonteDeArquivo":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fechar()

    # -- indexacao ---------------------------------------------------------

    @property
    def indexacao_completa(self) -> bool:
        return self._varrido >= self._tamanho

    @property
    def progresso_da_indexacao(self) -> tuple[int, int]:
        return self._varrido, self._tamanho

    def indexar(self, orcamento_bytes: int | None = None,
                cancelar: Callable[[], bool] | None = None) -> bool:
        """Avanca o indice. Devolve True quando terminou o arquivo inteiro.

        `orcamento_bytes=None` indexa tudo de uma vez -- util em teste e em
        arquivo pequeno. A etapa 10 passa um orcamento para poder reportar
        progresso e atender ao cancelamento entre os pedacos.
        """
        if self._mapa is None:
            self._varrido = self._tamanho
            return True

        gasto = 0
        while self._varrido < self._tamanho:
            if cancelar is not None and cancelar():
                return False
            if orcamento_bytes is not None and gasto >= orcamento_bytes:
                return False

            # O bloco lido e' limitado TAMBEM pelo orcamento que ainda resta.
            # Sem isso, um orcamento menor que BLOCO_DE_LEITURA nao teria efeito
            # nenhum -- a primeira leitura ja' consumiria 4 MB, e a granularidade
            # do progresso e do cancelamento passaria a ser o bloco, nao o
            # orcamento pedido por quem chamou.
            quanto = BLOCO_DE_LEITURA
            if orcamento_bytes is not None:
                quanto = min(quanto, max(1, orcamento_bytes - gasto))
            fim = min(self._varrido + quanto, self._tamanho)
            # Cortar o bloco num offset arbitrario e' seguro: procuramos o byte
            # 0x0A, e em UTF-8 (como em cp1252 e latin-1) ele nunca aparece
            # dentro de uma sequencia multibyte. Uma linha partida entre dois
            # blocos continua sendo contada uma vez so'.
            trecho = self._mapa[self._varrido:fim]
            base = self._varrido
            posicao = 0
            while True:
                achou = trecho.find(b"\n", posicao)
                if achou < 0:
                    break
                self._quebras += 1
                inicio_da_proxima = base + achou + 1
                # A linha que comeca aqui tem indice `self._quebras`. Se for
                # multiplo do passo, e' um marcador.
                if self._quebras % self._passo == 0:
                    self._marcadores.append(inicio_da_proxima)
                posicao = achou + 1

            gasto += fim - self._varrido
            self._varrido = fim

        return True

    # -- FonteDeTexto ------------------------------------------------------

    def total_de_linhas(self) -> int:
        """Linhas conhecidas ate' agora. Cresce durante a indexacao.

        Enquanto o indice nao esta' completo este numero e' PARCIAL, e e'
        exatamente isso que faz a barra de rolagem crescer na tela em vez de o
        usuario esperar por um arquivo de 1 GB antes de ver a primeira linha.
        """
        return self._quebras + 1

    def linha(self, n: int) -> str:
        resultado = self.faixa(n, n + 1)
        return resultado[0] if resultado else ""

    def faixa(self, inicio: int, fim: int) -> list[str]:
        """Linhas [inicio, fim). UMA varredura sequencial, nao uma por linha.

        E' o caminho que o `paintEvent` do visor usa: pedir as ~40 linhas
        visiveis de uma vez custa uma busca no indice, e nao 40.
        """
        inicio = max(0, inicio)
        if self._mapa is None or fim <= inicio:
            # Arquivo vazio tem uma linha vazia, pela convencao do split("\n").
            return [""] if (self._tamanho == 0 and inicio == 0 and fim > 0) else []

        total = self.total_de_linhas()
        fim = min(fim, total)
        if fim <= inicio:
            return []

        posicao = self._offset_da_linha(inicio)
        if posicao is None:
            return []

        saida: list[str] = []
        for _ in range(fim - inicio):
            if posicao > self._tamanho:
                break
            quebra = self._mapa.find(b"\n", posicao,
                                     min(posicao + LIMITE_DE_LINHA_LIDA,
                                         self._tamanho))
            if quebra < 0:
                # Sem \n a' vista: ou e' a ultima linha, ou uma linha absurda
                # (arquivo binario sem quebras). O teto evita decodificar 1 GB.
                termino = min(posicao + LIMITE_DE_LINHA_LIDA, self._tamanho)
                saida.append(self._decodificar(self._mapa[posicao:termino]))
                posicao = self._tamanho + 1
            else:
                saida.append(self._decodificar(self._mapa[posicao:quebra]))
                posicao = quebra + 1
        return saida

    def buscar(self, padrao: re.Pattern[str], de_linha: int = 0,
               cancelar: Callable[[], bool] | None = None) -> Iterator[Achado]:
        """Busca em lotes de linhas, para nao pagar uma busca no indice por linha.

        A leitura em lote e' o que torna a busca segura na fronteira dos blocos
        internos de leitura: uma linha e' sempre lida inteira, de um \\n ao
        proximo, independentemente de onde ficaram as fronteiras de 4 MB da
        indexacao.
        """
        LOTE = 4096
        n = max(0, de_linha)
        while True:
            if cancelar is not None and cancelar():
                return
            linhas = self.faixa(n, n + LOTE)
            if not linhas:
                return
            for deslocamento, texto in enumerate(linhas):
                for m in padrao.finditer(texto):
                    yield Achado(n + deslocamento, m.start(), m.end(), texto)
            n += len(linhas)
            if len(linhas) < LOTE and self.indexacao_completa:
                return

    def editavel(self) -> bool:
        return False

    def tamanho_em_bytes(self) -> int:
        return self._tamanho

    # -- internos ----------------------------------------------------------

    def _offset_da_linha(self, n: int) -> int | None:
        """Offset em bytes onde a linha `n` comeca."""
        if self._mapa is None:
            return None
        marcador = min(n // self._passo, len(self._marcadores) - 1)
        posicao = self._marcadores[marcador]
        faltam = n - marcador * self._passo
        while faltam > 0:
            quebra = self._mapa.find(b"\n", posicao, self._tamanho)
            if quebra < 0:
                return None
            posicao = quebra + 1
            faltam -= 1
        return posicao

    def _decodificar(self, bruto: bytes) -> str:
        # errors="replace": pintar a tela NUNCA pode levantar excecao. Num
        # arquivo grande o encoding e' um palpite, e um byte invalido no meio de
        # um log de 1 GB nao pode impedir de ver o resto.
        texto = bruto.decode(self.codificacao, errors="replace")
        # O indice quebra em \n; num arquivo CRLF sobra o \r no fim da linha.
        return texto[:-1] if texto.endswith("\r") else texto


# ---------------------------------------------------------------------------


def _buscar_por_linha(fonte: FonteDeTexto, padrao: re.Pattern[str],
                      de_linha: int, cancelar: Callable[[], bool] | None
                      ) -> Iterator[Achado]:
    """Busca generica: serve a qualquer fonte que saiba dar `faixa()`."""
    LOTE = 4096
    total = fonte.total_de_linhas()
    n = max(0, de_linha)
    while n < total:
        if cancelar is not None and cancelar():
            return
        linhas = fonte.faixa(n, min(n + LOTE, total))
        if not linhas:
            return
        for deslocamento, texto in enumerate(linhas):
            for m in padrao.finditer(texto):
                yield Achado(n + deslocamento, m.start(), m.end(), texto)
        n += len(linhas)
