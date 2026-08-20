"""`Pasta`, `Folha` e `Celula`: a planilha aberta em memoria.

A divisao espelha a de `visualizadores/tabela_csv.py`, e pelo mesmo motivo:

    bytes_originais   o arquivo .xlsx inteiro, VERBATIM, como veio do disco
    celulas           os valores ja' lidos, para a grade desenhar
    sujas             so' as celulas que o usuario editou

Sem nenhuma edicao, `bytes_para_salvar()` devolve `bytes_originais` -- o mesmo
arquivo, byte a byte. Com edicao, o gravador patcheia so' as abas atingidas.

Guardar o arquivo inteiro em memoria e' de proposito. Um .xlsx e' comprimido e
raramente passa de poucos MB; e sem os bytes originais nao ha' como garantir que o
que nao foi editado sai igual -- que e' a unica coisa que este pacote promete.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

# Tipo da celula. Nao e' o `data_type` do OOXML: e' o que a GRADE precisa saber
# para alinhar, ordenar e decidir como reescrever a celula ao salvar.
TIPO_VAZIO = "vazio"
TIPO_TEXTO = "texto"
TIPO_NUMERO = "numero"
TIPO_DATA = "data"
TIPO_BOOL = "bool"
TIPO_FORMULA = "formula"
TIPO_ERRO = "erro"

#: Tipos que o gravador sabe reescrever. Uma celula de erro (`#REF!`) fica
#: visivel mas nao editavel: nao ha' texto que o usuario possa digitar que
#: signifique "um erro do Excel", e aceitar a edicao a transformaria em texto.
TIPOS_EDITAVEIS = frozenset({TIPO_VAZIO, TIPO_TEXTO, TIPO_NUMERO, TIPO_DATA,
                             TIPO_BOOL, TIPO_FORMULA})


@dataclass(slots=True)
class Celula:
    """O que a grade mostra de uma celula.

    `ordenacao` existe pelo mesmo motivo que `PAPEL_DE_ORDENACAO` no CSV: ordenar
    pelo texto exibido poria "10" antes de "9" em toda coluna numerica.
    """

    texto: str = ""
    tipo: str = TIPO_VAZIO
    ordenacao: float | str = ""
    #: Valor em cache de uma formula, para a dica de contexto. A grade mostra a
    #: FORMULA -- e' o arquivo que o editor abriu, nao a interpretacao dele --, e
    #: o numero que o Excel calculou fica aqui.
    cache: str = ""
    #: True para celula que o gravador nao sabe reescrever sem estragar o resto
    #: da aba: hoje, so' a formula COMPARTILHADA (`<f t="shared" si="0">`), cujo
    #: texto e' a origem de todas as outras celulas do mesmo `si`. Sobrescrever a
    #: origem apagaria a formula das demais.
    travada: bool = False

    @property
    def editavel(self) -> bool:
        return self.tipo in TIPOS_EDITAVEIS and not self.travada


@dataclass
class Folha:
    """Uma aba da planilha.

    `parte` e' o caminho DENTRO do ZIP ("xl/worksheets/sheet1.xml"). E' por ele
    que o gravador acha os bytes a patchear, e por isso ele e' resolvido pelo
    `xl/workbook.xml` + `xl/_rels/workbook.xml.rels`, e nao deduzido do indice da
    aba: a numeracao dos arquivos `sheetN.xml` NAO acompanha a ordem das abas
    numa pasta cujas abas foram reordenadas ou removidas.
    """

    nome: str
    parte: str
    linhas: int = 0
    colunas: int = 0
    oculta: bool = False
    celulas: dict[tuple[int, int], Celula] = field(default_factory=dict)
    #: (linha, coluna) base 1 -> texto digitado pelo usuario, ainda nao gravado.
    sujas: dict[tuple[int, int], str] = field(default_factory=dict)
    #: Vazio quando a aba pode ser editada; senao, o motivo mostrado ao usuario.
    motivo_somente_leitura: str = ""

    @property
    def editavel(self) -> bool:
        return not self.motivo_somente_leitura

    def celula(self, linha: int, coluna: int) -> Celula:
        """A celula em base 1. Uma celula que nao existe no arquivo e' VAZIA.

        Devolver uma celula vazia nova, e nao guarda-la no dicionario, mantem
        esparsa a planilha esparsa: uma aba com `dimension="A1:Z100000"` e cem
        celulas preenchidas ocupa cem celulas de memoria, e nao 2,6 milhoes.
        """
        return self.celulas.get((linha, coluna)) or Celula()


class Pasta:
    """A planilha aberta: os bytes originais, as abas e o que foi editado."""

    def __init__(self, caminho: pathlib.Path, dados: bytes) -> None:
        self.caminho = caminho
        self.bytes_originais = dados
        self.folhas: list[Folha] = []
        #: Sistema de data de 1904 (Excel para Mac antigo). Muda a origem do
        #: numero de serie das datas, e por isso o gravador se recusa a escrever
        #: data numa pasta assim em vez de gravar quatro anos errado.
        self.data1904 = False
        self.somente_leitura = False
        self.aviso = ""
        #: Rotulos do conteudo rico que o TextForge nao edita mas PRESERVA:
        #: "grafico", "macro", "tabela dinamica". Vai para a barra de status --
        #: e' o que da' ao usuario confianca para salvar.
        self.preservadas: list[str] = []

    # ==================================================================
    # Edicao
    # ==================================================================

    @property
    def alterado(self) -> bool:
        return any(folha.sujas for folha in self.folhas)

    def definir(self, folha: Folha, linha: int, coluna: int, texto: str) -> bool:
        """Registra uma edicao e atualiza o que a grade mostra.

        Devolve False quando nada mudou -- e' o que impede um duplo-clique
        seguido de Enter, sem digitar nada, de marcar o documento como modificado.
        """
        atual = folha.celula(linha, coluna)
        if atual.texto == texto:
            return False

        folha.sujas[(linha, coluna)] = texto
        nova = interpretar(texto, atual)
        folha.celulas[(linha, coluna)] = nova
        folha.linhas = max(folha.linhas, linha)
        folha.colunas = max(folha.colunas, coluna)
        return True

    def confirmar_gravacao(self, dados: bytes | None = None) -> None:
        """Os bytes do disco passaram a ser o que a grade mostra.

        Sem esta promocao, salvar e editar de novo faria o gravador partir dos
        bytes ANTIGOS e reverter em silencio a primeira gravacao -- o mesmo
        defeito que `ModeloCsv.confirmar_gravacao` evita no CSV.

        `dados` sao os bytes que acabaram de ir para o disco. Recebe-los evita
        montar o pacote uma segunda vez, e -- o que importa mais -- garante que
        a memoria fique com EXATAMENTE o que foi gravado.
        """
        if dados is None:
            from textforge.planilha import gravador
            dados = gravador.montar(self)
        self.bytes_originais = dados
        for folha in self.folhas:
            folha.sujas.clear()

    # ==================================================================
    # Gravacao
    # ==================================================================

    def bytes_para_salvar(self) -> bytes:
        """Os bytes exatos que vao para o disco.

        SEM edicao, o arquivo original inteiro -- nem sequer recomprimido.
        """
        if not self.alterado:
            return self.bytes_originais
        from textforge.planilha import gravador
        return gravador.montar(self)


def interpretar(texto: str, anterior: Celula) -> Celula:
    """Que tipo de celula o usuario acabou de digitar.

    O tipo ANTERIOR pesa: um "15/03/2024" digitado numa celula que ja' era data
    continua data (e mantem o formato do Excel), enquanto o mesmo texto numa
    celula de texto continua texto. E' o comportamento do Excel, e e' o que evita
    que editar uma coluna de datas transforme cada celula num numero de serie
    exposto.
    """
    from textforge.planilha import valores

    if texto.startswith("="):
        return Celula(texto=texto, tipo=TIPO_FORMULA, ordenacao=texto.lower())
    if not texto:
        return Celula()

    if anterior.tipo == TIPO_DATA:
        data = valores.ler_data(texto)
        if data is not None:
            try:
                serial = valores.serial_de_data(data, False)
            except ValueError:
                # Data que o numero de serie do Excel nao representa direito
                # (anterior a 01/03/1900). Vira texto: a celula fica visivelmente
                # diferente das vizinhas, o que e' melhor que um dia errado.
                serial = None
            if serial is not None:
                return Celula(texto=valores.data_como_texto(data),
                              tipo=TIPO_DATA, ordenacao=serial)

    numero = valores.ler_numero(texto)
    if numero is not None:
        return Celula(texto=texto, tipo=TIPO_NUMERO, ordenacao=numero)

    if texto.strip().upper() in ("VERDADEIRO", "FALSO", "TRUE", "FALSE"):
        return Celula(texto=texto, tipo=TIPO_BOOL, ordenacao=texto.lower())

    # Uma data digitada numa celula que NAO era data vira texto, de proposito. O
    # que faz um numero de serie aparecer como "15/03/2024" e' o formato numerico
    # do estilo, e este editor nao mexe em estilo (ver `gravador.py`): gravar o
    # serial numa celula de formato Geral mostraria "45366" ao usuario.
    return Celula(texto=texto, tipo=TIPO_TEXTO, ordenacao=texto.lower())
