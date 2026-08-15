"""Vigia de alteracao externa (requisito 27) e base do tail de log (requisito 26).

`QFileSystemWatcher` sozinho NAO serve, e isto e' conhecido:

  * em compartilhamento de rede (SMB, o caso do `Y:`) ele perde eventos, porque
    depende de notificacao do sistema de arquivos que o servidor pode nao mandar;
  * alguns programas gravam substituindo o arquivo (o mesmo `ReplaceFileW` que o
    TextForge usa), e o watcher solta o caminho depois disso -- para de vigiar
    sem avisar;
  * ele nao diz O QUE mudou: um `fileChanged` pode ser append num log ou
    reescrita completa.

Por isso o vigia e' HIBRIDO: watcher (rapido, quando funciona) mais uma consulta
periodica a tamanho e mtime (lenta, mas nao mente). O intervalo padrao de 2 s e'
folgado o bastante para nao pesar e curto o bastante para o usuario nao editar
muito sobre uma versao velha.

O que este modulo NAO faz: decidir. Ele emite `mudou` e `removido`; quem abre o
dialogo Recarregar / Manter o meu / Comparar e' a janela. Nunca ha' recarga
automatica -- o requisito 27 proibe sobrescrever ou descartar em silencio.
"""

from __future__ import annotations

import codecs
import contextlib
import os
import pathlib
import threading

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Signal

from textforge import log_interno
from textforge.arquivos import Assinatura

log = log_interno.obter(__name__)

INTERVALO_DE_CONSULTA_MS = 2000

# Quanto o leitor incremental consome por volta. Um teto e' obrigatorio: um
# processo que despeja 50 MB de uma vez num log nao pode fazer a interface receber
# um sinal com 600 mil linhas dentro.
BLOCO_DO_TAIL = 1024 * 1024

# Quanto se le' do FIM do arquivo para montar as linhas de contexto ao ligar o
# acompanhamento. 256 KB dao centenas de linhas em qualquer log realista.
CAUDA_PARA_CONTEXTO = 256 * 1024


class Vigia(QObject):
    """Vigia um conjunto de arquivos e avisa quando algum muda no disco.

    Uso:
        vigia = Vigia()
        vigia.mudou.connect(...)
        vigia.acompanhar(caminho, assinatura)
        vigia.confirmar(caminho, nova_assinatura)   # depois de salvar
    """

    mudou = Signal(str, object)          # caminho, Assinatura encontrada
    removido = Signal(str)               # caminho

    def __init__(self, parent: QObject | None = None,
                 intervalo_ms: int = INTERVALO_DE_CONSULTA_MS) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._ao_notificar)
        self._esperadas: dict[str, Assinatura] = {}
        self._pausados: set[str] = set()
        # Caminhos cujo aviso ESTA' SENDO RESOLVIDO agora (o dialogo esta' na
        # tela). Ver `em_resolucao`.
        self._resolvendo: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(max(250, intervalo_ms))
        self._timer.timeout.connect(self.verificar_agora)

    # ==================================================================
    # Registro
    # ==================================================================

    def acompanhar(self, caminho: str | pathlib.Path,
                   assinatura: Assinatura) -> None:
        """Passa a vigiar `caminho`, tomando `assinatura` como o estado atual."""
        texto = str(pathlib.Path(caminho))
        self._esperadas[texto] = assinatura
        self._watcher.addPath(texto)
        if not self._timer.isActive():
            self._timer.start()

    def esquecer(self, caminho: str | pathlib.Path) -> None:
        texto = str(pathlib.Path(caminho))
        self._esperadas.pop(texto, None)
        self._pausados.discard(texto)
        self._watcher.removePath(texto)
        if not self._esperadas:
            self._timer.stop()

    def confirmar(self, caminho: str | pathlib.Path,
                  assinatura: Assinatura) -> None:
        """Registra o novo estado esperado -- chamado DEPOIS de salvar.

        Sem isto, a propria gravacao do TextForge dispararia o aviso de "alterado
        externamente" no salvamento seguinte, e o usuario aprenderia a ignorar o
        aviso. Um aviso que sempre aparece nao protege ninguem.
        """
        texto = str(pathlib.Path(caminho))
        if texto in self._esperadas:
            self._esperadas[texto] = assinatura
        # ReplaceFileW substitui o arquivo, e o watcher solta o caminho depois
        # disso: readicionar e' o que mantem a vigilancia viva apos cada
        # salvamento.
        if texto not in self._watcher.files():
            self._watcher.addPath(texto)

    def pausar(self, caminho: str | pathlib.Path) -> None:
        """Suspende o aviso para um arquivo (o usuario escolheu "manter o meu").

        Continua vigiando: se o arquivo mudar DE NOVO, o aviso volta. Parar de
        vigiar de vez faria a segunda alteracao externa passar despercebida.
        """
        self._pausados.add(str(pathlib.Path(caminho)))

    def retomar(self, caminho: str | pathlib.Path) -> None:
        self._pausados.discard(str(pathlib.Path(caminho)))

    @contextlib.contextmanager
    def em_resolucao(self, caminho: str | pathlib.Path):
        """Enquanto o aviso deste caminho esta' sendo resolvido, nao emitir outro.

        SEM ISTO O PROGRAMA TRAVA, e nao e' hipotese: o dialogo de alteracao
        externa e' modal, e `exec()` roda um laco de eventos ANINHADO. O timer
        daqui continua disparando dentro desse laco; num arquivo que cresce -- um
        log sendo escrito por outro programa, ou o proprio textforge.log aberto no
        editor -- cada disparo ve' um estado novo, emite de novo, e a janela abre
        OUTRO modal dentro do primeiro.

        Medido antes da correcao: 47 modais aninhados em 4 segundos, com o
        aninhamento crescendo sem limite ate' o programa morrer.

        Um `set` em vez de um booleano porque o aviso e' POR ARQUIVO: dois
        arquivos podem mudar, e resolver um nao pode calar o outro para sempre.
        """
        alvo = str(pathlib.Path(caminho))
        self._resolvendo.add(alvo)
        try:
            yield
        finally:
            self._resolvendo.discard(alvo)
            # A assinatura e' reconferida DEPOIS: o arquivo pode ter mudado mais
            # enquanto o dialogo estava aberto, e o proximo aviso deve partir do
            # estado atual, e nao disparar na hora por causa do que passou.
            atual = Assinatura.de_caminho(pathlib.Path(alvo))
            if alvo in self._esperadas:
                self._esperadas[alvo] = atual

    def vigiados(self) -> list[str]:
        return sorted(self._esperadas)

    def parar(self) -> None:
        self._timer.stop()
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        self._esperadas.clear()
        self._pausados.clear()

    # ==================================================================
    # Deteccao
    # ==================================================================

    def _ao_notificar(self, caminho: str) -> None:
        """Reacao ao sinal do watcher: confere de verdade antes de avisar.

        O `fileChanged` dispara tambem quando o arquivo e' aberto para escrita sem
        mudar nada. Comparar a assinatura evita o falso alarme.
        """
        self._checar(caminho)

    def verificar_agora(self) -> None:
        """A consulta periodica. E' a rede de seguranca do watcher."""
        for caminho in list(self._esperadas):
            self._checar(caminho)

    def _checar(self, caminho: str) -> None:
        esperada = self._esperadas.get(caminho)
        if esperada is None:
            return
        if caminho in self._resolvendo:
            # Ha' um dialogo aberto para este arquivo. Sair AQUI, antes de
            # atualizar a assinatura esperada, e' o que faz a mudanca continuar
            # pendente: quando o usuario responder, `em_resolucao` reconfere o
            # estado atual e a decisao dele vale para o que estiver no disco.
            return
        atual = Assinatura.de_caminho(pathlib.Path(caminho))

        if not atual.existe:
            if esperada.existe:
                # Guarda o estado para nao repetir o aviso a cada 2 s.
                self._esperadas[caminho] = atual
                log.info("arquivo desapareceu do disco: %s", caminho)
                if caminho not in self._pausados:
                    self.removido.emit(caminho)
            return

        if esperada.compativel_com(atual):
            return

        # Atualiza ANTES de emitir: se o usuario deixar o dialogo aberto, a
        # consulta seguinte nao vai empilhar outro dialogo em cima.
        self._esperadas[caminho] = atual
        log.info("alteracao externa em %s (%s)", caminho,
                 esperada.descrever_diferenca(atual))
        if caminho in self._pausados:
            return
        self.mudou.emit(caminho, atual)


# ---------------------------------------------------------------------------
# Leitura incremental (a base do tail -- requisito 26)
# ---------------------------------------------------------------------------


class LeitorIncremental:
    """Le' o que FOI ACRESCENTADO a um arquivo desde a ultima leitura.

    Sem Qt de proposito: e' logica pura, e a suite exercita todos os casos dificeis
    sem subir uma QApplication.

    TRES ARMADILHAS, e cada uma tem um teste:

    1. **Nunca mmap.** O arquivo CRESCE debaixo do mapeamento; o tamanho mapeado
       fica congelado no instante do `mmap()`, e as linhas novas simplesmente nao
       existem para quem le'. Aqui e' `open`/`seek`/`read`, sempre.

    2. **Caractere multibyte cortado na fronteira do bloco.** Um `ç` em UTF-8 sao
       dois bytes; se o processo gravou o primeiro e ainda nao o segundo, decodificar
       o bloco com `bytes.decode` produziria um U+FFFD PERMANENTE no lugar de um
       caractere que vai chegar inteiro no milissegundo seguinte. O
       `IncrementalDecoder` guarda os bytes incompletos e so' os emite quando
       completam -- e' exatamente para isso que ele existe.

    3. **A linha ainda sem `\\n`.** Um log e' escrito em pedacos: a mensagem pode
       chegar antes da quebra de linha. Emitir "2026-08-13 ERRO: fal" como linha
       completa e depois "ha critica" como outra produziria duas linhas erradas. O
       pedaco fica em `_resto` ate' a quebra chegar.

    E ainda: TRUNCAMENTO e ROTACAO. `size < offset` e' truncamento (`> log.txt`);
    identidade de arquivo diferente e' rotacao (renomearam o antigo e criaram outro
    com o mesmo nome). Os dois recomecam a leitura do zero.
    """

    def __init__(self, caminho: str | os.PathLike[str],
                 codec: str = "utf-8") -> None:
        self.caminho = pathlib.Path(caminho)
        self.codec = codec
        self.offset = 0
        self._resto = ""
        self._decodificador = self._novo_decodificador()
        self._identidade = self._identidade_atual()

    # -- estado ------------------------------------------------------------

    def _novo_decodificador(self):
        # `errors="replace"`: acompanhar um log NUNCA pode levantar excecao. Um
        # byte invalido no meio de um log nao pode interromper o acompanhamento --
        # e, ao contrario do caso do bloco cortado, aqui o byte e' invalido mesmo.
        return codecs.getincrementaldecoder(self.codec)("replace")

    def _identidade_atual(self) -> tuple[int, int] | None:
        """(dispositivo, indice do arquivo). Muda quando o arquivo e' ROTACIONADO.

        Sem isto, uma rotacao que ja' tivesse escrito mais bytes que o offset atual
        passaria despercebida: o tamanho seria MAIOR, e o leitor continuaria de
        onde parou -- pulando o comeco do arquivo novo e emendando no meio de uma
        linha do arquivo anterior.
        """
        try:
            info = self.caminho.stat()
        except OSError:
            return None
        return (info.st_dev, info.st_ino)

    @property
    def resto(self) -> str:
        """A linha parcial, ainda sem quebra. Vazia quando nao ha' nenhuma."""
        return self._resto

    def reiniciar(self) -> None:
        """Volta ao inicio do arquivo, com decodificador e resto limpos."""
        self.offset = 0
        self._resto = ""
        self._decodificador = self._novo_decodificador()
        self._identidade = self._identidade_atual()

    def ir_para_o_fim(self, linhas_de_contexto: int = 0) -> list[str]:
        """Posiciona no fim e devolve as ultimas `linhas_de_contexto` linhas.

        E' o `tail -n N -f`: acompanhar um log de 1 GB comecando com a tela vazia,
        esperando a proxima linha aparecer, e' desnorteante -- o usuario nao sabe
        se ligou o acompanhamento ou se o programa travou.
        """
        try:
            tamanho = self.caminho.stat().st_size
        except OSError:
            return []
        self.offset = tamanho
        self._resto = ""
        self._decodificador = self._novo_decodificador()
        self._identidade = self._identidade_atual()
        if linhas_de_contexto <= 0 or tamanho == 0:
            return []

        inicio = max(0, tamanho - CAUDA_PARA_CONTEXTO)
        try:
            with open(self.caminho, "rb") as f:
                f.seek(inicio)
                bruto = f.read(tamanho - inicio)
        except OSError:
            return []
        # Decodificacao AVULSA aqui, e nao pelo decodificador vivo: este trecho
        # comeca num offset arbitrario e pode partir um caractere no INICIO. O
        # `replace` marca o pedaco partido, e a primeira linha e' descartada logo
        # abaixo justamente porque ela pode estar cortada.
        texto = bruto.decode(self.codec, errors="replace")
        linhas = texto.split("\n")
        if inicio > 0 and linhas:
            linhas.pop(0)            # a primeira pode estar cortada ao meio
        if linhas and linhas[-1] == "":
            linhas.pop()             # a quebra final nao e' uma linha
        return [self._sem_cr(l) for l in linhas[-linhas_de_contexto:]]

    # -- leitura -----------------------------------------------------------

    def ler(self, maximo: int = BLOCO_DO_TAIL) -> tuple[list[str], bool]:
        """Le' o que chegou. Devolve (linhas COMPLETAS, recomecou).

        `recomecou=True` quando o arquivo foi truncado ou rotacionado -- quem chama
        deve limpar a tela antes de mostrar as linhas devolvidas, senao o conteudo
        do arquivo novo apareceria emendado no do antigo.
        """
        try:
            info = self.caminho.stat()
        except OSError:
            # O arquivo sumiu (rotacao em andamento, por exemplo). Nao e' erro:
            # a proxima volta o encontra de novo.
            return [], False

        identidade = (info.st_dev, info.st_ino)
        recomecou = False
        if info.st_size < self.offset or (self._identidade is not None
                                          and identidade != self._identidade):
            log.info("tail: %s recomecou (tamanho %d, offset %d)",
                     self.caminho.name, info.st_size, self.offset)
            self.reiniciar()
            self._identidade = identidade
            recomecou = True
        elif info.st_size == self.offset:
            return [], False

        try:
            with open(self.caminho, "rb") as f:
                f.seek(self.offset)
                bruto = f.read(maximo)
        except OSError as exc:
            log.warning("tail: nao foi possivel ler %s: %s", self.caminho, exc)
            return [], recomecou
        if not bruto:
            return [], recomecou

        self.offset += len(bruto)
        # `final=False` e' o ponto inteiro: o decodificador SEGURA os bytes de um
        # caractere incompleto ate' o resto chegar, em vez de emitir U+FFFD.
        texto = self._resto + self._decodificador.decode(bruto, False)

        pedacos = texto.split("\n")
        # O ULTIMO pedaco nao terminou em "\n": e' linha parcial, e volta a esperar.
        self._resto = pedacos.pop()
        return [self._sem_cr(l) for l in pedacos], recomecou

    @staticmethod
    def _sem_cr(linha: str) -> str:
        """Tira o \\r que sobra ao quebrar um arquivo CRLF pelo \\n."""
        return linha[:-1] if linha.endswith("\r") else linha


# ---------------------------------------------------------------------------
# O acompanhador, numa thread propria
# ---------------------------------------------------------------------------


class Acompanhador(QThread):
    """Segue um arquivo numa thread e entrega as linhas novas por sinal.

    Uma QThread PROPRIA, e nao o `POOL_DISCO`: o pool tem UMA thread e as tarefas
    dele terminam. Um acompanhamento dura horas -- ocupar o slot unico do pool
    faria a indexacao do proximo arquivo grande esperar para sempre, e um segundo
    acompanhamento nunca comecaria.

    Todos os sinais atravessam a fila de eventos do Qt, que e' o unico jeito seguro
    de um worker falar com a interface.
    """

    #: lote de linhas completas, na ordem em que foram gravadas.
    linhas_novas = Signal(list)
    #: a linha ainda sem quebra, para poder ser mostrada em cinza no rodape.
    parcial = Signal(str)
    #: o arquivo foi truncado ou rotacionado: limpe a tela antes do proximo lote.
    recomecou = Signal()
    erro = Signal(str)

    def __init__(self, caminho, codec: str = "utf-8", *,
                 intervalo_ms: int = 500, linhas_de_contexto: int = 200,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.leitor = LeitorIncremental(caminho, codec)
        self._intervalo = max(0.05, intervalo_ms / 1000.0)
        self._contexto = linhas_de_contexto
        self._parar = threading.Event()
        # Set == ACOMPANHANDO. Comeca ligado; `pausar()` limpa.
        self._ativo = threading.Event()
        self._ativo.set()
        # Segurado enquanto uma volta de leitura acontece. E' o que faz `pausar()`
        # so' voltar quando o worker esta' de fato parado -- ver o metodo.
        self._lendo = threading.Lock()
        self._ultima_parcial = ""

    # -- controle (thread da interface) ------------------------------------

    @property
    def pausado(self) -> bool:
        return not self._ativo.is_set()

    def pausar(self) -> None:
        """Para de consumir. O offset FICA onde esta'.

        Retomar continua de onde parou -- e' o que faz "pausar para ler com calma"
        nao perder nenhuma linha do intervalo.

        A GARANTIA E' PRECISA, e vale ler: quando este metodo volta, o worker NAO
        esta' no meio de uma leitura e nenhuma nova comecara'. Mas um lote lido no
        instante anterior ao clique ainda pode estar na fila de eventos do Qt e
        chegar depois -- e ele CHEGA de proposito. Descarta-lo perderia linhas para
        sempre, porque o offset ja' avancou; nao ha' como "des-ler" o que foi lido.
        Ou seja: pausar impede leitura NOVA, e nao a entrega do que ja' saiu.

        Sem o lock, "pausar" seria so' baixar uma bandeira, e o worker poderia
        seguir lendo por uma volta inteira depois disso.
        """
        self._ativo.clear()
        # Espera a volta em andamento terminar. Curto por construcao: uma volta e'
        # um `stat` mais uma leitura de no maximo 1 MB.
        with self._lendo:
            pass

    def retomar(self) -> None:
        self._ativo.set()

    def encerrar(self, ms: int = 3000) -> bool:
        """Pede parada e espera. Devolve False se a thread nao saiu a tempo."""
        self._parar.set()
        self._ativo.set()            # solta um `wait` de pausa, se houver
        return self.wait(ms)

    # -- o laco (thread propria) -------------------------------------------

    def run(self) -> None:                                    # noqa: D102
        try:
            contexto = self.leitor.ir_para_o_fim(self._contexto)
            if contexto:
                self.linhas_novas.emit(contexto)
        except Exception as exc:                # noqa: BLE001 - nada escapa
            self.erro.emit(str(exc))

        while not self._parar.is_set():
            if self._ativo.is_set():
                with self._lendo:
                    # Reconferido DENTRO do lock: `pausar()` pode ter entrado
                    # entre o `is_set()` acima e a aquisicao, e nesse caso esta
                    # volta nao deve mais ler nada.
                    if self._ativo.is_set():
                        try:
                            self._uma_volta()
                        except Exception as exc:    # noqa: BLE001
                            log.warning("tail em %s: %s",
                                        self.leitor.caminho, exc)
                            self.erro.emit(str(exc))
            # `Event.wait` com timeout, e nao `sleep`: `encerrar()` acorda a
            # thread na hora, em vez de esperar o intervalo terminar.
            self._parar.wait(self._intervalo)

    def _uma_volta(self) -> None:
        linhas, recomecou = self.leitor.ler()
        if recomecou:
            self._ultima_parcial = ""
            self.recomecou.emit()
        if linhas:
            self.linhas_novas.emit(linhas)
        # A parcial so' e' emitida quando MUDA: um log parado emitiria o mesmo
        # texto duas vezes por segundo, para sempre.
        if self.leitor.resto != self._ultima_parcial:
            self._ultima_parcial = self.leitor.resto
            self.parcial.emit(self._ultima_parcial)
