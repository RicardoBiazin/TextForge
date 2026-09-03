"""Edicao por LINHA de um arquivo grande, sem carrega-lo na memoria.

O modo de arquivo grande abre 240 MB instantaneamente porque nao carrega nada: o
mmap deixa a paginacao com o sistema operacional e um indice esparso diz onde
cada linha comeca. Editar NAO exige abandonar isso. Exige apenas parar de dizer
"a linha 1.200.000 esta' no offset X" e passar a dizer "a linha 1.200.000 esta'
NESTE trecho, que por acaso ainda mora no disco".

    trechos = [ (ORIGINAL, 0,         1_200_000),   <- nunca foi lido
                (EDITADO,  buffer[0],         1),   <- o unico texto na RAM
                (ORIGINAL, 1_200_001,    ABERTO) ]

Editar a linha 1.200.000 nao copia nada: parte um trecho em tres e guarda so' o
texto novo. A memoria e' O(edicoes), e nao O(tamanho do arquivo). E' o mesmo
desenho de `visualizadores/tabela_csv.py` (registro nao editado sai verbatim) e
de `planilha/pasta.py` (so' as celulas sujas sao reescritas), um nivel abaixo.

**A INVARIANTE QUE FAZ ISSO FUNCIONAR DURANTE A INDEXACAO.** Ha' no maximo UM
trecho aberto, e ele e' sempre o ultimo. O indexador roda numa thread de disco e
so' faz `append` em `_marcadores` -- o total de linhas CRESCE enquanto o usuario
ja' le' e edita o comeco do arquivo (ver o cabecalho de `grande/indice.py`). O
trecho aberto absorve esse crescimento sozinho, porque ele nao guarda uma
quantidade: guarda "daqui ate' o fim do que existir".

Partir um trecho aberto produz prefixo FECHADO + editado + sufixo ABERTO. A
invariante se preserva em toda operacao, e por isso nenhuma delas precisa saber
que ha' uma segunda thread contando linhas.

Este modulo NAO importa Qt de proposito: e' o que permite testa-lo sem interface
e, depois, reaproveita-lo fora deste programa.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from textforge import log_interno
from textforge.fonte import FonteDeArquivo

log = log_interno.obter(__name__)

ORIGINAL = "original"
EDITADO = "editado"

#: `quantidade` de um trecho que vai ate' o fim do arquivo. Ver a invariante no
#: cabecalho: e' o que permite o total de linhas crescer durante a indexacao.
ABERTO = -1


@dataclass(frozen=True, slots=True)
class Trecho:
    """Um pedaco contiguo do documento.

    ORIGINAL: `inicio` e' a linha no ARQUIVO, e o conteudo continua no disco.
    EDITADO:  `inicio` e' o indice no buffer de linhas adicionadas.
    """

    tipo: str
    inicio: int
    quantidade: int

    @property
    def aberto(self) -> bool:
        return self.quantidade == ABERTO


class ForaDaFaixa(IndexError):
    """Operacao pedida numa linha que nao existe."""


@dataclass(slots=True)
class Operacao:
    """Uma edicao, como DADOS -- o suficiente para refaze-la e para desfaze-la.

    Guardar o que muda, e nao um instantaneo do estado, e' o que mantem a pilha
    proporcional ao numero de edicoes. A primeira versao deste modulo guardava
    `list(self._trechos)` por operacao; com 10 mil edicoes num arquivo de 59 MB
    isso MEDIU 800 MB de RAM, porque cada copia carrega os ~20 mil trechos que
    as edicoes anteriores criaram. O custo era quadratico e apareceu no primeiro
    teste de memoria.

    As inversas sao exatas: substituir se desfaz substituindo de volta, inserir
    se desfaz removendo, remover se desfaz inserindo o texto guardado.
    """

    tipo: str                       # "substituir" | "inserir" | "remover"
    linha: int
    texto: str = ""                 # o valor NOVO (substituir, inserir)
    anterior: str = ""              # o valor ANTIGO (substituir, remover)
    rotulo: str = ""


class FonteEditavel:
    """`FonteDeTexto` gravavel sobre um arquivo grande.

    Embrulha a `FonteDeArquivo` e implementa o mesmo protocolo (`fonte.py`), o
    que faz a busca, o visor e o painel Resultados continuarem falando com uma
    fonte so' -- nenhum deles precisa saber que ha' edicoes pendentes.
    """

    def __init__(self, fonte: FonteDeArquivo) -> None:
        self.fonte = fonte
        # Comeca com um unico trecho ABERTO: o arquivo inteiro, ainda que a
        # indexacao so' conheca as primeiras mil linhas neste instante.
        self._trechos: list[Trecho] = [Trecho(ORIGINAL, 0, ABERTO)]
        self._adicionadas: list[str] = []
        self._feitas: list[Operacao] = []
        self._desfeitas: list[Operacao] = []
        # Ultimo (indice de trecho, primeira linha dele) localizado. Editar e'
        # um gesto SEQUENCIAL -- corrige-se a linha 27, depois a 28 --, e sem
        # este atalho cada busca recomecaria do trecho 0. Medido: 10 mil edicoes
        # em ordem crescente caiam de 32 s para menos de 1 s.
        self._cursor: tuple[int, int] | None = None

    # ==================================================================
    # Protocolo FonteDeTexto
    # ==================================================================

    def total_de_linhas(self) -> int:
        total = 0
        for trecho in self._trechos:
            if trecho.aberto:
                # O trecho aberto vale o que SOBRA do arquivo a partir do ponto
                # em que ele comeca -- e esse "sobra" cresce durante a indexacao.
                total += max(0, self.fonte.total_de_linhas() - trecho.inicio)
            else:
                total += trecho.quantidade
        return max(0, total)

    def linha(self, n: int) -> str:
        resultado = self.faixa(n, n + 1)
        return resultado[0] if resultado else ""

    def faixa(self, inicio: int, fim: int) -> list[str]:
        """Linhas [inicio, fim), atravessando trechos.

        As linhas ORIGINAIS de um mesmo trecho saem numa chamada so' a
        `FonteDeArquivo.faixa`, que e' UMA busca no indice para todas elas -- o
        motivo de `paintEvent` pedir as ~40 linhas visiveis de uma vez.
        """
        inicio = max(0, inicio)
        fim = min(fim, self.total_de_linhas())
        if fim <= inicio:
            return []

        saida: list[str] = []
        for trecho, primeira, quantas in self._percorrer(inicio, fim):
            if trecho.tipo == ORIGINAL:
                saida.extend(self.fonte.faixa(primeira, primeira + quantas))
            else:
                saida.extend(self._adicionadas[primeira:primeira + quantas])
        return saida

    def buscar(self, padrao, de_linha: int = 0, cancelar=None):
        """Busca sobre o conteudo EDITADO, e nao sobre o arquivo do disco.

        Delegar a `FonteDeArquivo.buscar` seria mais rapido e estaria errado:
        acharia texto que o usuario ja' apagou e nao acharia o que ele digitou.
        """
        from textforge.fonte import _buscar_por_linha
        return _buscar_por_linha(self, padrao, de_linha, cancelar)

    def editavel(self) -> bool:
        return True

    def tamanho_em_bytes(self) -> int:
        return self.fonte.tamanho_em_bytes()

    # -- repasses para a fonte de dentro -----------------------------------
    #
    # Depois de habilitar a edicao, o `Documento` guarda ESTE objeto em
    # `fonte_grande`. Tudo o que ja' falava com a `FonteDeArquivo` -- fechar o
    # mmap, trocar a codificacao ao reabrir, ler o progresso da indexacao --
    # continua funcionando sem saber que agora ha' uma camada no meio.

    @property
    def caminho(self):
        return self.fonte.caminho

    @property
    def codificacao(self) -> str:
        return self.fonte.codificacao

    @codificacao.setter
    def codificacao(self, valor: str) -> None:
        self.fonte.codificacao = valor

    @property
    def indexacao_completa(self) -> bool:
        return self.fonte.indexacao_completa

    @property
    def progresso_da_indexacao(self) -> tuple[int, int]:
        return self.fonte.progresso_da_indexacao

    def indexar(self, orcamento_bytes=None, cancelar=None) -> bool:
        return self.fonte.indexar(orcamento_bytes, cancelar)

    def fechar(self) -> None:
        self.fonte.fechar()

    def trocar_fonte(self, fonte: FonteDeArquivo) -> None:
        """Aponta para o arquivo recem-gravado, depois da troca atomica.

        Chamada em par com `confirmar_gravacao()`: primeiro a fonte nova, depois
        o descarte dos trechos. Na ordem inversa os trechos ficariam apontando
        para offsets de um mmap ja' fechado.
        """
        self.fonte = fonte

    # ==================================================================
    # Mapeamento linha -> trecho
    # ==================================================================

    def _quantidade(self, trecho: Trecho) -> int:
        if not trecho.aberto:
            return trecho.quantidade
        return max(0, self.fonte.total_de_linhas() - trecho.inicio)

    def _percorrer(self, inicio: int, fim: int):
        """Gera (trecho, primeira_linha_de_origem, quantas) cobrindo [inicio, fim).

        Comeca no trecho que CONTEM `inicio`, e nao no primeiro da lista. Pintar
        a tela pede ~40 linhas do meio do documento; varrer os 20 mil trechos
        anteriores para chegar la' seria pagar por tudo o que ja' foi editado a
        cada repintura.
        """
        try:
            indice, deslocamento = self._localizar(inicio)
        except ForaDaFaixa:
            return
        posicao = inicio - deslocamento
        while indice < len(self._trechos):
            trecho = self._trechos[indice]
            quantas = self._quantidade(trecho)
            indice += 1
            if quantas <= 0:
                continue
            proximo = posicao + quantas
            if proximo > inicio and posicao < fim:
                salto = max(0, inicio - posicao)
                pega = min(quantas - salto, fim - max(posicao, inicio))
                if pega > 0:
                    yield trecho, trecho.inicio + salto, pega
            posicao = proximo
            if posicao >= fim:
                return

    def _esquecer_cursor(self) -> None:
        self._cursor = None

    def _localizar(self, n: int) -> tuple[int, int]:
        """(indice do trecho, deslocamento dentro dele) para a linha `n`.

        Comeca do cursor guardado quando ele nao passa de `n`. E' o que torna a
        edicao sequencial barata: a lista tem O(edicoes) trechos, e varre-la
        inteira a cada edicao faria o custo total ser quadratico.
        """
        indice, posicao = 0, 0
        if self._cursor is not None and self._cursor[1] <= n:
            indice, posicao = self._cursor
            if indice >= len(self._trechos):
                indice, posicao = 0, 0
        while indice < len(self._trechos):
            quantas = self._quantidade(self._trechos[indice])
            if posicao <= n < posicao + quantas:
                self._cursor = (indice, posicao)
                return indice, n - posicao
            posicao += quantas
            indice += 1
        self._esquecer_cursor()
        raise ForaDaFaixa(f"linha {n} fora do documento ({posicao} linhas)")

    def _partir(self, indice: int, deslocamento: int) -> list[Trecho]:
        """Um trecho em ate' tres: antes, a linha do meio, depois.

        O sufixo herda o "aberto" do original -- e' o que preserva a invariante
        do cabecalho: partir o ultimo trecho continua deixando um aberto no fim.
        """
        trecho = self._trechos[indice]
        quantas = self._quantidade(trecho)
        partes: list[Trecho] = []
        if deslocamento > 0:
            partes.append(replace(trecho, quantidade=deslocamento))
        partes.append(Trecho(trecho.tipo, trecho.inicio + deslocamento, 1))
        sobra = quantas - deslocamento - 1
        if trecho.aberto:
            partes.append(Trecho(trecho.tipo, trecho.inicio + deslocamento + 1,
                                 ABERTO))
        elif sobra > 0:
            partes.append(Trecho(trecho.tipo, trecho.inicio + deslocamento + 1,
                                 sobra))
        return partes

    def _compactar_ao_redor(self, indice: int, quantos: int,
                            ancora: int) -> None:
        """Junta trechos ORIGINAIS vizinhos e contiguos, SO' perto da mudanca.

        A versao anterior varria a lista inteira a cada edicao. Com 20 mil
        trechos e 10 mil edicoes isso e' 2x10^8 passos -- medido em 32 s. Uma
        emenda so' pode aparecer nas bordas do que acabou de ser trocado, entao
        olhar a vizinhanca basta e custa O(1).

        `ancora` e' a linha em que o trecho `indice` comeca. Com ela o cursor e'
        REPOSICIONADO em vez de esquecido -- esquece-lo fazia toda edicao
        seguinte varrer a lista desde o inicio, e o ganho do cursor sumia.
        """
        primeiro = max(0, indice - 1)
        inicio_da_janela = ancora
        if primeiro < indice:
            inicio_da_janela -= self._quantidade(self._trechos[primeiro])
        ultimo = min(len(self._trechos), indice + quantos + 1)
        janela: list[Trecho] = []
        for trecho in self._trechos[primeiro:ultimo]:
            if self._quantidade(trecho) <= 0 and not trecho.aberto:
                continue
            if janela:
                anterior = janela[-1]
                contiguo = (anterior.tipo == trecho.tipo
                            and not anterior.aberto
                            and anterior.inicio + anterior.quantidade
                            == trecho.inicio)
                if contiguo:
                    janela[-1] = replace(
                        anterior,
                        quantidade=(ABERTO if trecho.aberto
                                    else anterior.quantidade + trecho.quantidade))
                    continue
            janela.append(trecho)
        self._trechos[primeiro:ultimo] = janela
        if not self._trechos:
            self._trechos = [Trecho(ORIGINAL, 0, ABERTO)]
        self._cursor = (primeiro, max(0, inicio_da_janela))

    # ==================================================================
    # Edicao
    # ==================================================================

    @property
    def alterado(self) -> bool:
        return bool(self._feitas)

    @property
    def total_de_edicoes(self) -> int:
        return len(self._feitas)

    # -- primitivas: mudam os trechos e NAO registram nada -----------------
    #
    # Sao elas que desfazer e refazer chamam. Se registrassem, desfazer uma
    # edicao empilharia uma edicao nova e a pilha nunca esvaziaria.

    def _prim_substituir(self, n: int, texto: str) -> None:
        indice, deslocamento = self._localizar(n)
        partes = self._partir(indice, deslocamento)
        meio = 1 if deslocamento > 0 else 0
        self._adicionadas.append(texto)
        partes[meio] = Trecho(EDITADO, len(self._adicionadas) - 1, 1)
        self._trechos[indice:indice + 1] = partes
        self._compactar_ao_redor(indice, len(partes), n - deslocamento)

    def _prim_inserir(self, n: int, texto: str) -> None:
        self._adicionadas.append(texto)
        nova = Trecho(EDITADO, len(self._adicionadas) - 1, 1)
        if n >= self.total_de_linhas():
            self._trechos.append(nova)
            self._esquecer_cursor()
            return
        indice, deslocamento = self._localizar(n)
        trecho = self._trechos[indice]
        quantas = self._quantidade(trecho)
        partes: list[Trecho] = []
        if deslocamento > 0:
            partes.append(replace(trecho, quantidade=deslocamento))
        partes.append(nova)
        resto = quantas - deslocamento
        if trecho.aberto:
            partes.append(Trecho(trecho.tipo, trecho.inicio + deslocamento,
                                 ABERTO))
        elif resto > 0:
            partes.append(Trecho(trecho.tipo, trecho.inicio + deslocamento,
                                 resto))
        self._trechos[indice:indice + 1] = partes
        self._compactar_ao_redor(indice, len(partes), n - deslocamento)

    def _prim_remover(self, n: int) -> None:
        indice, deslocamento = self._localizar(n)
        partes = self._partir(indice, deslocamento)
        del partes[1 if deslocamento > 0 else 0]
        self._trechos[indice:indice + 1] = partes
        self._compactar_ao_redor(indice, len(partes), n - deslocamento)

    # -- publicas: registram para desfazer ---------------------------------

    def _registrar(self, operacao: Operacao) -> None:
        self._feitas.append(operacao)
        # Uma edicao nova invalida o que havia para refazer -- e' o
        # comportamento de qualquer editor, e manter a lista produziria um
        # "refazer" que costura dois futuros diferentes.
        self._desfeitas.clear()

    def substituir(self, n: int, texto: str) -> bool:
        """Troca o texto da linha `n`. False quando nada mudaria."""
        anterior = self.linha(n)
        if anterior == texto:
            return False
        self._prim_substituir(n, texto)
        self._registrar(Operacao("substituir", n, texto, anterior,
                                 f"editar linha {n + 1}"))
        return True

    def inserir(self, n: int, texto: str = "") -> None:
        """Insere uma linha ANTES da linha `n`. `n == total` acrescenta no fim."""
        self._prim_inserir(n, texto)
        self._registrar(Operacao("inserir", n, texto, "",
                                 f"inserir linha {n + 1}"))

    def remover(self, n: int) -> None:
        """Remove a linha `n`."""
        anterior = self.linha(n)
        self._prim_remover(n)
        self._registrar(Operacao("remover", n, "", anterior,
                                 f"remover linha {n + 1}"))

    def duplicar(self, n: int) -> None:
        texto = self.linha(n)
        self._prim_inserir(n + 1, texto)
        self._registrar(Operacao("inserir", n + 1, texto, "",
                                 f"duplicar linha {n + 1}"))

    # ==================================================================
    # Desfazer / refazer
    # ==================================================================

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._feitas)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._desfeitas)

    def _aplicar(self, operacao: Operacao) -> None:
        if operacao.tipo == "substituir":
            self._prim_substituir(operacao.linha, operacao.texto)
        elif operacao.tipo == "inserir":
            self._prim_inserir(operacao.linha, operacao.texto)
        else:
            self._prim_remover(operacao.linha)

    def _inverter(self, operacao: Operacao) -> None:
        if operacao.tipo == "substituir":
            self._prim_substituir(operacao.linha, operacao.anterior)
        elif operacao.tipo == "inserir":
            self._prim_remover(operacao.linha)
        else:
            self._prim_inserir(operacao.linha, operacao.anterior)

    def desfazer(self) -> str:
        """Desfaz a ultima operacao. Devolve o rotulo, ou "" se nao havia."""
        if not self._feitas:
            return ""
        operacao = self._feitas.pop()
        self._inverter(operacao)
        self._desfeitas.append(operacao)
        return operacao.rotulo

    def refazer(self) -> str:
        if not self._desfeitas:
            return ""
        operacao = self._desfeitas.pop()
        self._aplicar(operacao)
        self._feitas.append(operacao)
        return operacao.rotulo

    def confirmar_gravacao(self) -> None:
        """O disco passou a ser o que a tela mostra: zera tudo.

        Chamada DEPOIS de a `FonteDeArquivo` ser reaberta sobre o arquivo novo.
        Sem este passo, os trechos continuariam apontando para offsets do arquivo
        ANTIGO -- e a proxima gravacao remontaria o documento a partir do lugar
        errado, que e' o defeito mais destrutivo possivel aqui.
        """
        self._trechos = [Trecho(ORIGINAL, 0, ABERTO)]
        self._adicionadas.clear()
        self._feitas.clear()
        self._desfeitas.clear()
        self._esquecer_cursor()

    # ==================================================================
    # Diario, para a recuperacao (ver `sessao.py`)
    # ==================================================================

    def diario(self) -> list[dict]:
        """As edicoes como dados, para gravar poucos KB em vez de 240 MB.

        E' a lista de trechos, e nao a de operacoes: ela descreve o documento
        INTEIRO em O(edicoes) itens, e reaplica-la e' atribuicao direta -- nao
        depende de reexecutar operacoes na ordem certa sobre um arquivo que pode
        ter mudado no meio.
        """
        return [{"tipo": t.tipo, "inicio": t.inicio, "quantidade": t.quantidade}
                for t in self._trechos]

    def aplicar_diario(self, trechos: list[dict], adicionadas: list[str]) -> None:
        """Restaura um diario. Quem chama JA' conferiu a assinatura do arquivo."""
        self._adicionadas = list(adicionadas)
        self._trechos = [Trecho(str(t["tipo"]), int(t["inicio"]),
                                int(t["quantidade"])) for t in trechos]
        self._feitas = [Operacao("recuperado", lambda _a: None,
                                 lambda _a: None)]
        self._desfeitas.clear()

    @property
    def linhas_adicionadas(self) -> list[str]:
        return self._adicionadas

    # ==================================================================
    # Para o gravador
    # ==================================================================

    def blocos_para_gravar(self):
        """Gera (tipo, inicio, quantidade) na ordem do documento.

        O gravador usa isto para copiar os trechos ORIGINAIS byte a byte do mmap,
        sem decodificar, e codificar so' o que foi editado. Ver `gravacao.py`.
        """
        for trecho in self._trechos:
            quantas = self._quantidade(trecho)
            if quantas > 0:
                yield trecho.tipo, trecho.inicio, quantas
