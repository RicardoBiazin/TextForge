"""Indexacao de arquivo grande numa thread, com progresso e cancelamento.

A `FonteDeArquivo` ja' sabe indexar de forma INCREMENTAL (`indexar(orcamento)`
avanca um pedaco e volta). Este modulo e' o que transforma isso em abertura
instantanea: a varredura vai para o `POOL_DISCO`, o progresso sai a 10 Hz, e a
interface pinta o comeco do arquivo enquanto o fim ainda esta' sendo varrido.

E' por isso que a barra de rolagem CRESCE durante a abertura em vez de o usuario
esperar por um arquivo de 1 GB antes de ver a primeira linha.

SOBRE AS DUAS THREADS TOCAREM A MESMA FONTE. A thread de disco escreve
`_marcadores`, `_quebras` e `_varrido`; a thread da interface le' esses tres e
chama `faixa()`. Isso e' seguro, e nao por acaso:

  * `_marcadores` so' CRESCE (append). Ler `len()` e depois indexar continua valido
    mesmo que um append aconteca entre as duas operacoes -- a lista nunca encolhe
    nem reordena, e as duas operacoes sao atomicas sob o GIL.
  * `_quebras` e `_varrido` sao inteiros: a leitura pode ser de um valor anterior,
    e o efeito e' apenas uma linha a menos na barra de rolagem por um instante.
  * `mmap.find(sub, inicio, fim)` e o fatiamento `mapa[a:b]` NAO usam a posicao
    interna do mmap, entao nao ha' estado compartilhado entre as chamadas.

O que NAO e' seguro, e por isso existe o `parar()`: fechar o mmap enquanto o worker
esta' lendo dele. Por isso o fechamento e' ADIADO para depois do fim da tarefa, em
vez de bloquear a interface esperando a thread.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from textforge import log_interno, tarefas
from textforge.fonte import FonteDeArquivo

log = log_interno.obter(__name__)

# Quanto o worker varre entre duas checagens de cancelamento. 8 MB leva alguns
# milissegundos num SSD: pequeno o bastante para o cancelamento responder na hora,
# grande o bastante para o custo por byte continuar sendo o do memcpy.
ORCAMENTO_POR_VOLTA = 8 * 1024 * 1024


def _trabalho(tarefa: tarefas.Tarefa, fonte: FonteDeArquivo) -> int:
    """Roda no POOL_DISCO. Devolve o total de linhas encontrado."""
    while not fonte.indexacao_completa:
        tarefa.checar_cancelamento()
        fonte.indexar(ORCAMENTO_POR_VOLTA, cancelar=tarefa.cancelada)
        varrido, total = fonte.progresso_da_indexacao
        # O `progresso` da Tarefa ja' limita a 10 Hz na ORIGEM: emitir um sinal por
        # bloco de 8 MB num arquivo de 1 GB seriam 128 sinais atravessando a fila
        # de eventos, e num arquivo de 100 MB com blocos menores seriam milhares.
        tarefa.progresso(varrido, total)
    tarefa.progresso(*fonte.progresso_da_indexacao, forcar=True)
    return fonte.total_de_linhas()


class Indexador(QObject):
    """Conduz a indexacao de UMA fonte e e' dono do ciclo de vida dela.

    Vive na thread da interface. Os sinais sao emitidos da thread de disco e
    chegam aqui pela fila de eventos do Qt -- que e' o unico jeito seguro de um
    worker falar com a interface.
    """

    #: (bytes varridos, bytes totais). Sempre a 10 Hz, no maximo.
    progresso = Signal(int, int)
    #: total de linhas, quando o arquivo inteiro foi varrido.
    concluido = Signal(int)
    falhou = Signal(str)

    def __init__(self, fonte: FonteDeArquivo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.fonte = fonte
        self._tarefa: tarefas.Tarefa | None = None
        self._fechar_ao_terminar = False

    # -- ciclo de vida -----------------------------------------------------

    @property
    def rodando(self) -> bool:
        return self._tarefa is not None

    def iniciar(self) -> bool:
        """Comeca a varredura. False se ja' estava rodando ou ja' terminou."""
        if self._tarefa is not None:
            return False
        if self.fonte.indexacao_completa:
            self.concluido.emit(self.fonte.total_de_linhas())
            return False

        tarefa = tarefas.Tarefa(f"indexar {self.fonte.caminho.name}",
                                _trabalho, self.fonte)
        tarefa.sinais.progresso.connect(self.progresso)
        tarefa.sinais.concluido.connect(self._ao_concluir)
        tarefa.sinais.erro.connect(self._ao_falhar)
        tarefa.sinais.terminou.connect(self._ao_terminar)
        self._tarefa = tarefa
        # `disco=True`: um pool separado, com UMA thread. Indexar um log de 1 GB
        # nao pode ocupar os slots que a formatacao de um JSON pequeno usa.
        tarefas.rodar(tarefa, disco=True)
        return True

    def cancelar(self) -> None:
        if self._tarefa is not None:
            self._tarefa.cancelar()

    def parar(self, *, fechar: bool = True) -> None:
        """Cancela e (por padrao) fecha a fonte quando for seguro.

        O fechamento e' ADIADO para o fim da tarefa. Fechar o mmap agora, com o
        worker lendo dele, produziria um ValueError na thread de disco -- e
        BLOQUEAR a interface ate' a thread terminar deixaria o programa travado ao
        fechar uma aba, que e' justamente o que o modo de arquivo grande existe
        para evitar.
        """
        if self._tarefa is None:
            if fechar:
                self.fonte.fechar()
            return
        self._fechar_ao_terminar = fechar
        self._tarefa.cancelar()

    # -- reacoes (thread da interface) --------------------------------------

    def _ao_concluir(self, total_de_linhas: object) -> None:
        log.info("indice completo: %s, %s linhas", self.fonte.caminho.name,
                 total_de_linhas)
        self.concluido.emit(int(total_de_linhas or 0))

    def _ao_falhar(self, texto: object) -> None:
        log.error("indexacao falhou: %s", texto)
        # So' a primeira linha do traceback vai para a interface: o traceback
        # inteiro e' do log, e mostrar caminho de arquivo do usuario num dialogo
        # nao ajuda ninguem.
        self.falhou.emit(str(texto).strip().splitlines()[-1:][0]
                         if texto else "erro desconhecido")

    def _ao_terminar(self) -> None:
        self._tarefa = None
        if self._fechar_ao_terminar:
            self._fechar_ao_terminar = False
            self.fonte.fechar()
