"""Gravar um arquivo grande editado sem nunca te-lo inteiro na memoria.

O truque e' o mesmo do `planilha/gravador.py`, e pela mesma razao: **o que nao
foi editado nao e' reconstruido, e' COPIADO**. La' sao entradas de um ZIP; aqui
sao faixas de bytes do mmap. Um trecho ORIGINAL de 12 milhoes de linhas vai do
arquivo velho para o novo sem virar `str` uma unica vez -- sem decodificar,
recodificar nem alocar. So' as linhas editadas passam por codificacao.

O pico de memoria e' UM bloco (`BLOCO_DE_COPIA`), e nao o arquivo. Salvar um
arquivo de 240 MB com tres linhas alteradas custa 240 MB de DISCO e alguns MB de
RAM.

TRES COISAS QUE PARECEM DETALHE E NAO SAO:

1. **O modelo de linhas e' `EOL.join(linhas)`.** Um arquivo terminado em quebra
   produz uma ultima linha VAZIA (a convencao de `split("\\n")`, seguida por toda
   a `fonte.py`), e e' ela que representa a quebra final. Por isso o gravador nao
   precisa de nenhum caso especial para "termina com nova linha": copiar as
   linhas na ordem ja' reproduz o arquivo exato.

2. **Copiar a faixa de bytes de um trecho inclui o terminador de cada linha.**
   E' o que preserva CRLF, LF e ate' fim de linha MISTO nas partes intocadas --
   sem que o gravador precise saber qual e' qual. Ele so' garante que exista um
   terminador na emenda entre dois trechos.

3. **A ordem no Windows e' fechar o mmap, trocar, reabrir.** Um mmap aberto
   SEGURA o arquivo, e a troca atomica falharia. Quem conduz isso e'
   `documento.py`; aqui esta' so' a escrita.

O indice do arquivo novo NAO e' construido aqui. Ele poderia ser -- as posicoes
sao conhecidas enquanto se grava --, mas seria aritmetica de offset delicada para
economizar uma varredura de poucos segundos que ja' roda em thread, com
progresso, e que e' o mesmo codigo testado de toda abertura. Reindexar depois de
salvar e' mais barato em risco do que em tempo.
"""

from __future__ import annotations

import pathlib

from textforge import arquivos, log_interno
from textforge.grande.edicao import EDITADO, FonteEditavel

log = log_interno.obter(__name__)

#: Quanto se copia do mmap por vez. Grande o bastante para o custo por byte ser
#: o do memcpy, pequeno o bastante para o pico de memoria ser irrelevante.
BLOCO_DE_COPIA = 4 * 1024 * 1024

#: Folga exigida alem do tamanho do arquivo, para o temporario caber com sobra.
FOLGA_DE_DISCO = 16 * 1024 * 1024


class SemEspaco(OSError):
    """Nao ha' espaco na unidade para o arquivo temporario da troca atomica."""


def conferir_espaco(caminho, tamanho_previsto: int) -> None:
    """Levanta `SemEspaco` ANTES de comecar a escrever.

    O temporario nasce na mesma pasta do destino (ver `arquivos.gravar_atomico`),
    entao salvar 240 MB exige 240 MB livres ali. Descobrir isso depois de
    escrever 200 MB e' o pior momento possivel: o usuario espera minutos para
    receber um erro que era conhecido no primeiro segundo.
    """
    livre = arquivos.espaco_livre(caminho)
    if livre < 0:
        return                      # unidade que nao sabe informar: seguir
    if livre < tamanho_previsto + FOLGA_DE_DISCO:
        raise SemEspaco(
            f"faltam {(tamanho_previsto + FOLGA_DE_DISCO - livre) // (1024*1024)} "
            f"MB livres em {pathlib.Path(caminho).drive or 'disco'} para gravar "
            f"com seguranca (a gravacao atomica escreve um arquivo temporario "
            f"do mesmo tamanho ao lado do original)")


def blocos(editavel: FonteEditavel, eol: bytes, codec: str,
           cancelar=None):
    """Gera os bytes do arquivo novo, na ordem.

    `eol` so' e' usado nas linhas EDITADAS e nas emendas: o texto original
    carrega os proprios terminadores dentro dos bytes copiados.
    """
    fonte = editavel.fonte
    mapa = fonte._mapa
    tamanho = fonte.tamanho_em_bytes()
    pedacos = list(editavel.blocos_para_gravar())
    #: True quando o ultimo byte ja' emitido e' um terminador de linha. Comeca
    #: True para nao abrir o arquivo com uma quebra solta.
    terminado = True

    for indice, (tipo, inicio, quantas) in enumerate(pedacos):
        if cancelar is not None and cancelar():
            return
        ultimo_pedaco = indice == len(pedacos) - 1

        if not terminado:
            # Emenda entre dois trechos: o anterior acabou sem quebra (arquivo
            # sem nova linha final, agora com algo depois). Sem isto, a ultima
            # linha do trecho anterior e a primeira deste virariam UMA linha.
            yield eol
            terminado = True

        if tipo == EDITADO:
            textos = editavel.linhas_adicionadas[inicio:inicio + quantas]
            dados = eol.join(t.encode(codec, errors="replace") for t in textos)
            if not ultimo_pedaco:
                dados += eol
            else:
                terminado = False
            yield dados
            if not ultimo_pedaco:
                terminado = True
            continue

        # ORIGINAL: uma faixa de bytes contigua, copiada sem decodificar.
        principio = fonte._offset_da_linha(inicio)
        if principio is None:
            continue
        fim = _offset_ou_fim(fonte, inicio + quantas, tamanho)
        posicao = principio
        while posicao < fim:
            if cancelar is not None and cancelar():
                return
            ate = min(posicao + BLOCO_DE_COPIA, fim)
            yield mapa[posicao:ate]
            posicao = ate
        if fim > principio:
            terminado = mapa[fim - 1:fim] in (b"\n", b"\r")


def _offset_ou_fim(fonte, linha: int, tamanho: int) -> int:
    """Offset onde a linha comeca, ou o fim do arquivo quando ela nao existe.

    Uma linha alem da ultima nao tem offset -- e e' exatamente o caso do trecho
    que vai ate' o fim. Devolver o tamanho faz a faixa copiada terminar no fim do
    arquivo, inclusive quando ele nao acaba com quebra de linha.
    """
    if linha >= fonte.total_de_linhas():
        return tamanho
    offset = fonte._offset_da_linha(linha)
    return tamanho if offset is None else min(offset, tamanho)


def gravar(caminho, editavel: FonteEditavel, *, eol: str = "\r\n",
           codec: str = "utf-8", cancelar=None) -> int:
    """Grava o documento editado. Devolve quantos bytes foram escritos.

    A troca e' atomica: enquanto o temporario esta' sendo escrito, o arquivo
    original continua intacto no lugar. Uma falha no meio -- disco cheio, energia,
    cancelamento -- nao deixa o arquivo do usuario pela metade.
    """
    alvo = pathlib.Path(caminho)
    conferir_espaco(alvo, editavel.tamanho_em_bytes())
    # O mmap fica ABERTO durante a escrita -- e' de onde vem cada trecho nao
    # editado -- e e' fechado na emenda, imediatamente antes da troca. Fecha-lo
    # antes daria um arquivo vazio; deixa-lo aberto faria a troca falhar.
    escritos = arquivos.gravar_atomico_em_blocos(
        alvo, blocos(editavel, eol.encode(codec, errors="replace"), codec,
                     cancelar),
        antes_de_trocar=editavel.fonte.fechar)
    log.info("arquivo grande gravado: %s (%d bytes, %d edicao(oes))",
             alvo, escritos, editavel.total_de_edicoes)
    return escritos
