"""`Pintor`: o `QSyntaxHighlighter` do TextForge.

Um so' pintor para todas as linguagens. Ele nao sabe nada sobre Python ou XML --
apenas percorre os contextos que o `ProvedorDeLinguagem` declarou.

Por que `QSyntaxHighlighter` basta, sem nenhuma otimizacao propria: o Qt o chama
bloco a bloco, apenas nos blocos que o layout precisa, e reaproveita
`previousBlockState()`. Depois de uma edicao, ele reprocessa dali para baixo e
PARA sozinho quando `setCurrentBlockState()` reproduz o valor que o bloco ja'
tinha. E' exatamente o comportamento desejado, e vem de graca -- desde que o
estado seja comparavel, que e' o que o internamento de pilha garante.

Limites de disponibilidade (requisito 34): o realce roda na thread da interface,
entao um bloco absurdamente longo ou um arquivo grande demais nao podem ser
processados a qualquer custo. Ha' dois tetos, ambos configuraveis, e os dois
avisam em vez de simplesmente nao funcionar.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QSyntaxHighlighter, QTextDocument

from textforge import log_interno
from textforge.realce.dados_do_bloco import DadosDoBloco, Par, Token
from textforge.realce.pilha import Internador

log = log_interno.obter(__name__)

# Delimitadores rastreados para o pareamento (requisito 14).
ABRE = "([{"
FECHA = ")]}"
PARES = {"(": ")", "[": "]", "{": "}"}

# Papeis em que um delimitador NAO conta como par: dentro de string ou comentario,
# um "(" solto e' texto, e casa-lo com um ")" de codigo seria pior que nao casar.
PAPEIS_SEM_PAR = frozenset({"texto_literal", "comentario", "comentario_doc",
                            "escape", "regex", "citacao", "codigo"})

_SO_ESPACO = re.compile(r"^[ \t]*")


class Pintor(QSyntaxHighlighter):
    def __init__(self, documento: QTextDocument, provedor, tema,
                 cfg: dict | None = None) -> None:
        super().__init__(documento)
        self.tema = tema
        self.cfg = cfg or {}
        self.internador = Internador()
        self.provedor = None
        self.regras = None
        self.largura_da_indentacao = int(self.cfg.get("tabulacao", 4)) or 4
        self._avisou_do_limite = False
        self.definir_provedor(provedor)

    # ==================================================================
    # Configuracao
    # ==================================================================

    def definir_provedor(self, provedor) -> None:
        """Troca a linguagem. Repinta o documento inteiro (O(n), so' aqui)."""
        self.provedor = provedor
        self.regras = provedor.regras(self.tema) if provedor is not None else None
        self.internador = Internador()
        if self.document() is not None:
            self.rehighlight()

    def definir_tema(self, tema) -> None:
        self.tema = tema
        # As regras citam PAPEIS, e o papel e' resolvido em cor na hora de pintar.
        # Ainda assim reconstruimos: um provedor pode ter cacheado formatos.
        if self.provedor is not None:
            self.regras = self.provedor.regras(tema)
        self.rehighlight()

    def definir_configuracao(self, cfg: dict) -> None:
        self.cfg = cfg
        self.largura_da_indentacao = int(cfg.get("tabulacao", 4)) or 4

    @property
    def limite_por_linha(self) -> int:
        return int(self.cfg.get("limite_realce_por_linha", 10_000))

    @property
    def limite_do_arquivo(self) -> int:
        return int(self.cfg.get("limite_realce_mb", 8)) * 1024 * 1024

    def realce_desligado_por_tamanho(self) -> bool:
        doc = self.document()
        return doc is not None and doc.characterCount() > self.limite_do_arquivo

    # ==================================================================
    # O laco principal
    # ==================================================================

    def highlightBlock(self, texto: str) -> None:            # noqa: N802 - Qt
        dados = DadosDoBloco()
        dados.vazio = not texto.strip()
        self._medir_indentacao(texto, dados)

        if self.regras is None or self.realce_desligado_por_tamanho():
            if not self._avisou_do_limite and self.realce_desligado_por_tamanho():
                self._avisou_do_limite = True
                log.info("realce desligado: o documento passou de %d MB",
                         self.limite_do_arquivo // (1024 * 1024))
            self.setCurrentBlockUserData(dados)
            return

        if len(texto) > self.limite_por_linha:
            # Uma unica linha gigante (JS ou JSON minificado) tornaria o regex o
            # gargalo da rolagem. O bloco fica sem realce, mas o resto do arquivo
            # continua realcado -- e' melhor que desligar tudo.
            self.setCurrentBlockState(self.previousBlockState())
            self.setCurrentBlockUserData(dados)
            return

        pilha = self.internador.pilha_de(self.previousBlockState())
        if not pilha:
            pilha = (self.regras.inicial,)

        pilha = self._pintar(texto, pilha, dados)

        dados.pilha_ao_terminar = pilha
        self.setCurrentBlockState(self.internador.id_de(pilha))
        self._marcar_dobra(texto, dados)
        # setCurrentBlockUserData por ultimo: o Qt assume a posse do objeto, e
        # mexer nele depois disso e' uso apos transferencia de propriedade.
        self.setCurrentBlockUserData(dados)

    def _pintar(self, texto: str, pilha: tuple[str, ...],
                dados: DadosDoBloco) -> tuple[str, ...]:
        posicao = 0
        limite = len(texto)
        voltas = 0
        maximo_de_voltas = limite * 2 + 16      # rede contra regra patologica

        while posicao <= limite:
            voltas += 1
            if voltas > maximo_de_voltas:
                log.warning("realce interrompido no bloco: laco longo demais "
                            "(contexto %s)", pilha[-1] if pilha else "?")
                break

            contexto = self.regras.contextos.get(pilha[-1])
            if contexto is None or contexto.combinado is None:
                if contexto is not None and contexto.papel_padrao:
                    self._aplicar(posicao, limite - posicao,
                                  contexto.papel_padrao, dados)
                return pilha

            casamento = contexto.combinado.search(texto, posicao)
            if casamento is None:
                # Nada mais casa: o resto do bloco leva o papel do contexto (o
                # interior de uma string ou de um comentario de bloco).
                if contexto.papel_padrao and posicao < limite:
                    self._aplicar(posicao, limite - posicao,
                                  contexto.papel_padrao, dados)
                return pilha

            # O que ficou ANTES do casamento tambem leva o papel do contexto.
            if contexto.papel_padrao and casamento.start() > posicao:
                self._aplicar(posicao, casamento.start() - posicao,
                              contexto.papel_padrao, dados)

            regra = contexto.regra_de(casamento)
            if regra is None:
                posicao = max(casamento.end(), posicao + 1)
                continue

            inicio, fim = casamento.start(), casamento.end()
            self._aplicar(inicio, fim - inicio, regra.papel, dados)
            for nome_do_grupo, papel in regra.papeis_por_grupo.items():
                try:
                    g_inicio = casamento.start(nome_do_grupo)
                except IndexError:
                    # Grupo declarado no papel mas ausente do padrao. E' erro de
                    # declaracao do provedor, e nao pode derrubar o desenho da
                    # tela; o teste generico dos provedores pega isso.
                    log.warning("grupo %r nao existe no padrao %r",
                                nome_do_grupo, regra.padrao.pattern)
                    continue
                if g_inicio >= 0:
                    self._aplicar(g_inicio,
                                  casamento.end(nome_do_grupo) - g_inicio,
                                  papel, dados)

            self._registrar_pares(texto, inicio, fim, regra.papel, dados)

            if regra.entrar_em:
                pilha = pilha + (regra.entrar_em,)
            elif regra.voltar_para:
                # Desempilha ate' o destino ficar no topo. Se ele nao estiver na
                # pilha (documento malformado), volta ao inicial em vez de zerar:
                # uma pilha vazia faria o proximo bloco recomecar do zero e
                # perder o contexto do arquivo.
                if regra.voltar_para in pilha:
                    pilha = pilha[:pilha.index(regra.voltar_para) + 1]
                else:
                    pilha = pilha[:1]
            elif regra.sair and len(pilha) > 1:
                pilha = pilha[:-1]

            # `max(..., inicio + 1)` e' a rede contra regra que casa VAZIO: sem
            # isso, um padrao como `x*` faria o laco nunca avancar.
            posicao = max(fim, inicio + 1)

        return pilha

    def _aplicar(self, inicio: int, tamanho: int, papel: str,
                 dados: DadosDoBloco) -> None:
        if tamanho <= 0:
            return
        self.setFormat(inicio, tamanho, self.tema.formato(papel))
        dados.tokens.append(Token(inicio, tamanho, papel))

    def _registrar_pares(self, texto: str, inicio: int, fim: int, papel: str,
                         dados: DadosDoBloco) -> None:
        """Guarda ( [ { ) ] } para o pareamento, ignorando string e comentario."""
        if papel in PAPEIS_SEM_PAR:
            return
        for i in range(inicio, min(fim, len(texto))):
            ch = texto[i]
            if ch in ABRE:
                dados.pares.append(Par(i, ch, True))
            elif ch in FECHA:
                dados.pares.append(Par(i, ch, False))

    # ==================================================================
    # Dobra e indentacao
    # ==================================================================

    def _medir_indentacao(self, texto: str, dados: DadosDoBloco) -> None:
        prefixo = _SO_ESPACO.match(texto).group(0)
        colunas = 0
        largura = self.largura_da_indentacao
        for ch in prefixo:
            colunas += largura - (colunas % largura) if ch == "\t" else 1
        dados.nivel_de_dobra = colunas // largura

    def _marcar_dobra(self, texto: str, dados: DadosDoBloco) -> None:
        """Este bloco abre uma regiao dobravel?

        A pergunta e' respondida pelo PROVEDOR: `dobras()` diz se a linguagem
        dobra por indentacao (Python, YAML) ou por delimitador (C, JSON, CSS).
        """
        if self.provedor is None:
            return
        regra = self.provedor.dobras()
        if regra.modo == "delimitadores":
            # Saldo positivo de aberturas nao fechadas neste bloco.
            saldo = 0
            for par in dados.pares:
                saldo += 1 if par.abre else -1
            dados.abre_dobra = saldo > 0
            return
        if regra.marcador_abre is not None and regra.marcador_abre.search(texto):
            dados.abre_dobra = True
            return
        aumenta = getattr(self.provedor, "aumenta_indentacao", None)
        if aumenta is not None and aumenta.search(texto):
            dados.abre_dobra = True

    # ==================================================================
    # Consulta (usada pelo autocomplete e pelo pareamento)
    # ==================================================================

    def dados_do_bloco(self, numero: int) -> DadosDoBloco | None:
        bloco = self.document().findBlockByNumber(numero)
        if not bloco.isValid():
            return None
        dados = bloco.userData()
        return dados if isinstance(dados, DadosDoBloco) else None

    def papel_em(self, numero: int, coluna: int) -> str:
        dados = self.dados_do_bloco(numero)
        return dados.papel_em(coluna) if dados is not None else ""

    def dentro_de_texto_ou_comentario(self, numero: int, coluna: int) -> bool:
        """Serve ao autocomplete: nao sugerir palavra-chave dentro de string."""
        return self.papel_em(numero, coluna) in PAPEIS_SEM_PAR
