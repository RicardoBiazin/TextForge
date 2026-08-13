"""`Documento`: um arquivo aberto, com tudo o que e' preciso para devolve-lo ao
disco exatamente como veio.

O `QTextDocument` mora AQUI, e nao no widget. E' essa escolha que permite:

  * trocar de visualizador (texto <-> tabela CSV, texto <-> hexadecimal) sem
    perder a pilha de desfazer;
  * split view -- dois `EditorDeTexto` com `setDocument()` no mesmo documento;
  * comparar contra o BUFFER em memoria, e nao contra o disco.

REGRA CENTRAL (requisito 38): o que entrou tem de sair igual. Codificacao, BOM,
fim de linha, ausencia de nova linha final, espaco no fim das linhas e nbsp sao
todos preservados literalmente. A tabela em `salvar()` diz como cada um.

`texto()` usa `toRawText()`, NUNCA `toPlainText()`. O `toPlainText()` troca
U+00A0 (espaco inquebravel) por espaco comum e U+2028/U+2029 por "\\n". Num
editor de arquivos tecnicos isso e' corrupcao silenciosa de dados -- o usuario
salvaria um arquivo diferente do que abriu sem nada avisar.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextDocument
# QPlainTextDocumentLayout mora em QtWidgets (e' declarado junto do
# QPlainTextEdit), e nao em QtGui como os outros tipos de texto.
from PySide6.QtWidgets import QPlainTextDocumentLayout

from textforge import arquivos, codificacao, log_interno
from textforge.arquivos import AlteradoNoDisco, Assinatura
from textforge.codificacao import CRLF, LF, Perfil, PerfilDeLinha
from textforge.editor.indentacao import Indentacao
from textforge.editor import indentacao as imod

log = log_interno.obter(__name__)

# Modos de exibicao. Quem escolhe o widget da aba e' o gerenciador de abas; o
# documento so' diz qual e' o adequado ao conteudo.
MODO_TEXTO = "texto"
MODO_TABELA = "tabela"
MODO_HEX = "hex"
MODO_GRANDE = "grande"

_contador_sem_titulo = 0


def _proximo_sem_titulo() -> str:
    global _contador_sem_titulo
    _contador_sem_titulo += 1
    return f"Sem titulo {_contador_sem_titulo}"


class Documento(QObject):
    """Um arquivo aberto (ou um buffer novo, ainda sem arquivo)."""

    modificado_mudou = Signal(bool)
    metadados_mudaram = Signal()          # codificacao, EOL, linguagem, indentacao

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        super().__init__()
        cfg = cfg or {}
        self.caminho: pathlib.Path | None = None
        self.rotulo_sem_titulo: str = ""

        # -- como veio do disco. Tudo isto e' reproduzido ao salvar. ---------
        self.codec: str = str(cfg.get("codificacao_padrao", "utf-8"))
        self.bom: bytes = b""
        self.fim_de_linha: str = codificacao.EOL_POR_NOME.get(
            str(cfg.get("fim_de_linha_padrao", "crlf")), CRLF)
        self.fins_de_linha_mistos: bool = False
        self.termina_com_nova_linha: bool = True
        # Terminador que seguia CADA linha do arquivo original. Preenchido so'
        # quando o arquivo tem fins de linha mistos -- e' o que permite salvar um
        # arquivo misto exatamente como ele veio, em vez de normalizar tudo para
        # a quebra dominante e alterar linhas que o usuario nao tocou.
        self.eols_originais: list[str] = []
        # Fica True quando um arquivo misto foi editado de forma que a
        # correspondencia linha-a-linha se perdeu, e a normalizacao passa a ser
        # inevitavel. A interface avisa antes de gravar.
        self.eol_sera_normalizado: bool = False
        self.indentacao: Indentacao = Indentacao(
            usa_espacos=bool(cfg.get("usar_espacos", True)),
            largura=int(cfg.get("tabulacao", 4)))

        # -- estado ---------------------------------------------------------
        self.qt: QTextDocument = QTextDocument(self)
        # Instalar o layout de texto simples AGORA, e nao quando o primeiro
        # EditorDeTexto chamar setDocument(): um QTextDocument solto nasce com
        # QTextDocumentLayout (o de rich text), e a troca dispara um relayout
        # completo -- perceptivel num arquivo de 10 MB.
        self.qt.setDocumentLayout(QPlainTextDocumentLayout(self.qt))
        self.qt.setModified(False)

        self.modo: str = MODO_TEXTO
        self.somente_leitura: bool = False
        self.binario: bool = False
        self.assinatura: Assinatura | None = None
        self.perfil: Perfil | None = None     # como a deteccao decidiu
        self.provedor = None                  # ProvedorDeLinguagem
        # True quando o usuario escolheu a linguagem no menu: impede que uma
        # redetecao posterior desfaca a escolha dele.
        self.linguagem_manual: bool = False
        self.aviso: str = ""                  # texto para a barra de status

        self.qt.modificationChanged.connect(self.modificado_mudou)

    # ==================================================================
    # Identidade
    # ==================================================================

    @property
    def nome(self) -> str:
        """Nome curto, para a aba."""
        if self.caminho is not None:
            return self.caminho.name
        if not self.rotulo_sem_titulo:
            self.rotulo_sem_titulo = _proximo_sem_titulo()
        return self.rotulo_sem_titulo

    @property
    def titulo_da_aba(self) -> str:
        return ("*" if self.modificado else "") + self.nome

    @property
    def sem_arquivo(self) -> bool:
        return self.caminho is None

    @property
    def modificado(self) -> bool:
        return self.qt.isModified()

    def chave(self) -> str:
        """Identidade para "esta aba ja' tem este arquivo?".

        Usa `resolve()` e caixa baixa: no Windows o mesmo arquivo chega com caixa
        diferente do Explorer, pela forma curta 8.3, ou por um caminho relativo --
        e abrir a mesma coisa em duas abas produz duas versoes divergentes do
        arquivo, que e' um jeito garantido de perder trabalho.
        """
        if self.caminho is None:
            return f"<sem titulo>{id(self)}"
        try:
            return str(self.caminho.resolve()).lower()
        except OSError:
            return str(self.caminho).lower()

    # ==================================================================
    # Conteudo
    # ==================================================================

    def texto(self) -> str:
        """O conteudo, com \\n como separador.

        SEMPRE `toRawText()`. O `toPlainText()` troca U+00A0 por espaco comum e
        U+2028/U+2029 por "\\n" -- corrupcao silenciosa num arquivo tecnico. Como
        o `toRawText()` devolve U+2029 nas quebras de bloco, trocamos so' esse
        caractere de volta, o que preserva um U+2028 ou um nbsp que existisse no
        arquivo de verdade.
        """
        return self.qt.toRawText().replace(" ", LF)

    def definir_texto(self, texto: str, *, marcar_modificado: bool = False) -> None:
        """Substitui o conteudo. Por padrao, sem marcar como modificado."""
        self.qt.setPlainText(codificacao.para_lf(texto))
        if marcar_modificado:
            # setModified(True) EXPLICITO. O `setPlainText` do Qt zera a flag de
            # modificado, entao contar com ela para ficar True nao funciona -- e a
            # consequencia seria grave: conteudo RECUPERADO apos um encerramento
            # inesperado nao apareceria como nao salvo, e o usuario o perderia de
            # novo ao fechar. O mesmo vale para "aparar espaco no fim".
            self.qt.setModified(True)
        else:
            self.qt.setModified(False)
            # O carregamento nao e' uma acao do usuario: deixar o undo apontando
            # para "documento vazio" faria um Ctrl+Z apagar o arquivo inteiro.
            self.qt.clearUndoRedoStacks()

    def total_de_linhas(self) -> int:
        return self.qt.blockCount()

    def fonte(self):
        """A `FonteDeTexto` deste documento, para busca, diff e estrutura."""
        from textforge.fonte import FonteDeDocumento
        return FonteDeDocumento(self.qt)

    # ==================================================================
    # Abrir
    # ==================================================================

    @classmethod
    def novo(cls, cfg: dict[str, Any] | None = None) -> "Documento":
        doc = cls(cfg)
        doc.rotulo_sem_titulo = _proximo_sem_titulo()
        return doc

    @classmethod
    def abrir(cls, caminho: str | os.PathLike[str],
              cfg: dict[str, Any] | None = None,
              codec_forcado: str = "") -> "Documento":
        """Le' o arquivo e monta o documento.

        `codec_forcado` atende ao "Reabrir como" (requisito 7): o usuario viu que
        a deteccao errou e escolheu a codificacao na mao.
        """
        cfg = cfg or {}
        alvo = pathlib.Path(caminho)
        dados = arquivos.ler_bytes(alvo)

        doc = cls(cfg)
        doc.caminho = alvo
        doc.assinatura = Assinatura.de_caminho(alvo, dados)
        doc._aplicar_bytes(dados, cfg, codec_forcado)
        log.info("aberto %s (%d bytes, %s, %s, %s)", alvo, len(dados),
                 doc.perfil.rotulo if doc.perfil else "?",
                 codificacao.ROTULO_EOL.get(doc.fim_de_linha, "?"),
                 doc.perfil.como_decidiu if doc.perfil else "?")
        return doc

    def _aplicar_bytes(self, dados: bytes, cfg: dict[str, Any],
                       codec_forcado: str = "") -> None:
        preferida = str(cfg.get("codificacao_preferida_legado", "cp1252"))
        if codec_forcado:
            texto, trocas = codificacao._decodificar(dados, codec_forcado)
            perfil = Perfil(codec=codec_forcado, texto=texto,
                            confianca=100, substituicoes=trocas,
                            como_decidiu="escolhida pelo usuario")
        else:
            perfil = codificacao.detectar(dados, preferida)

        self.perfil = perfil
        self.binario = perfil.binario
        self.codec = perfil.codec
        self.bom = perfil.bom
        self.aviso = ""

        if perfil.binario:
            # Nao exibir bytes binarios como texto corrompido (requisito 7): o
            # documento fica vazio e o modo pede o visualizador hexadecimal.
            self.modo = MODO_HEX
            self.somente_leitura = True
            self.aviso = (f"Conteudo binario{' (' + perfil.assinatura + ')'
                                             if perfil.assinatura else ''}")
            return

        de_linha = codificacao.detectar_fim_de_linha(
            perfil.texto,
            codificacao.EOL_POR_NOME.get(
                str(cfg.get("fim_de_linha_padrao", "crlf")), CRLF))
        self.fim_de_linha = de_linha.fim_de_linha
        self.fins_de_linha_mistos = de_linha.misto
        self.termina_com_nova_linha = de_linha.termina_com_nova_linha
        self.eol_sera_normalizado = False
        # Guardar os terminadores linha a linha SO' quando o arquivo e' misto: num
        # arquivo normal a lista seria pura repeticao, e num de 1 milhao de linhas
        # custaria memoria por nada.
        self.eols_originais = (
            codificacao.separar_linhas_com_eol(perfil.texto)[1]
            if de_linha.misto else [])

        if cfg.get("detectar_indentacao", True):
            self.indentacao = imod.detectar(perfil.texto, self.indentacao)

        self.detectar_linguagem(perfil.texto)
        self.definir_texto(perfil.texto)

        if perfil.suspeito:
            # A leitura perdeu caracteres. Salvar assim gravaria U+FFFD no lugar
            # dos bytes originais -- destruicao de dados. Somente leitura ate' o
            # usuario escolher a codificacao certa em "Reabrir como".
            self.somente_leitura = True
            self.aviso = (f"{perfil.substituicoes} caractere(s) nao pudera(m) "
                          f"ser lido(s) como {perfil.rotulo}. Use "
                          f"Arquivo > Reabrir como para escolher a codificacao.")
            log.warning("%s: %d substituicoes ao decodificar como %s",
                        self.caminho, perfil.substituicoes, perfil.codec)

    # ==================================================================
    # Linguagem
    # ==================================================================

    def detectar_linguagem(self, texto: str = "") -> None:
        """Resolve o provedor pelo caminho e pelo conteudo (requisito 4).

        A amostra e' limitada aos primeiros 8 KB: e' o que basta para qualquer
        deteccao, e passar um arquivo de 20 MB pelas heuristicas de todos os
        provedores custaria mais que abrir o arquivo.
        """
        from textforge.linguagens import registro

        amostra = (texto or self.texto())[:8192]
        self.provedor = registro.por_caminho(self.caminho, amostra)
        self.linguagem_manual = False

    def definir_linguagem(self, provedor) -> None:
        """Troca a linguagem por escolha do usuario (menu Linguagem).

        `linguagem_manual` impede que uma redetecao posterior (ao salvar como, por
        exemplo) desfaca a escolha dele.
        """
        self.provedor = provedor
        self.linguagem_manual = True
        self.metadados_mudaram.emit()

    @property
    def nome_da_linguagem(self) -> str:
        return self.provedor.nome if self.provedor is not None else "Texto"

    def reabrir_como(self, codec: str) -> None:
        """Le' o MESMO arquivo com outra codificacao (requisito 7)."""
        if self.caminho is None:
            raise ValueError("documento sem arquivo nao pode ser reaberto")
        dados = arquivos.ler_bytes(self.caminho)
        self.assinatura = Assinatura.de_caminho(self.caminho, dados)
        self.somente_leitura = False
        self.modo = MODO_TEXTO
        self._aplicar_bytes(dados, {}, codec_forcado=codec)
        self.metadados_mudaram.emit()

    def recarregar(self) -> None:
        """Descarta as alteracoes e le' o arquivo de novo."""
        if self.caminho is None:
            return
        dados = arquivos.ler_bytes(self.caminho)
        self.assinatura = Assinatura.de_caminho(self.caminho, dados)
        self.somente_leitura = False
        self._aplicar_bytes(dados, {})
        self.metadados_mudaram.emit()

    # ==================================================================
    # Salvar
    # ==================================================================

    def bytes_para_salvar(self, *, substituir: bool = False) -> bytes:
        """Monta os bytes exatos que irao para o disco.

        A tabela de preservacao (requisito 38), toda aplicada aqui:

          codificacao  self.codec, do detector ou da escolha do usuario
          BOM          self.bom, os bytes literais -- nunca deduzidos do codec
          fim de linha self.fim_de_linha, re-expandido a partir do \\n interno
          EOL misto    mantem o DOMINANTE; nao "conserta" o resto
          nova linha   se o original nao terminava com quebra, o salvo tambem nao
          espaco final aparado SO' se a preferencia estiver ligada (vem desligada)
          nbsp/U+2028  preservados, porque `texto()` usa toRawText()
        """
        texto = self.texto()

        if not self.termina_com_nova_linha:
            # Acrescentar uma quebra que nao existia produz um diff de uma linha
            # em todo arquivo salvo -- e alguns arquivos de dados posicionais nao
            # aceitam a linha extra.
            texto = texto.rstrip("\r\n")
        elif not texto.endswith(LF):
            texto += LF

        texto = self._reexpandir_quebras(texto)
        return codificacao.codificar(texto, self.codec, self.bom,
                                     substituir=substituir)

    def _reexpandir_quebras(self, texto: str) -> str:
        """Devolve o \\n interno aos fins de linha que o arquivo tinha.

        Num arquivo de fim de linha uniforme e' so' trocar \\n pelo terminador.
        Num arquivo MISTO, cada linha recebe de volta o terminador que ela tinha:
        normalizar todas para a dominante reescreveria linhas que o usuario nao
        tocou, e o requisito 38 proibe alterar conteudo em silencio.

        Quando o numero de linhas mudou (o usuario inseriu ou removeu linhas), a
        correspondencia linha-a-linha se perde e a normalizacao passa a ser
        inevitavel. Nesse caso a normalizacao acontece, mas `eol_sera_normalizado`
        fica True para a interface poder avisar ANTES de gravar.
        """
        if not self.fins_de_linha_mistos or not self.eols_originais:
            return codificacao.de_lf(texto, self.fim_de_linha)

        linhas, _ = codificacao.separar_linhas_com_eol(texto)
        if len(linhas) != len(self.eols_originais):
            self.eol_sera_normalizado = True
            return codificacao.de_lf(texto, self.fim_de_linha)

        self.eol_sera_normalizado = False
        return codificacao.juntar_linhas_com_eol(linhas, self.eols_originais)

    def aparar_espaco_final(self) -> bool:
        """Apara espaco no fim das linhas. So' quando o usuario pede.

        DESLIGADO por padrao na configuracao: um `.dat` de largura fixa e um
        arquivo posicional dependem desse espaco, e apara-lo destroi os dados.
        """
        from textforge.editor import operacoes_linha as ops
        atual = self.texto()
        novo = LF.join(ops.aparar_fim(atual.split(LF)))
        if novo == atual:
            return False
        self.definir_texto(novo, marcar_modificado=True)
        return True

    def salvar(self, *, forcar: bool = False,
               substituir_incompativeis: bool = False) -> None:
        """Grava no arquivo, preservando tudo. Ver `bytes_para_salvar`.

        Levanta:
          ValueError            documento sem caminho (use `salvar_como`)
          AlteradoNoDisco       outro programa mexeu no arquivo (requisito 27)
          UnicodeEncodeError    o texto nao cabe na codificacao atual
        """
        if self.caminho is None:
            raise ValueError("documento sem caminho: use salvar_como()")
        if self.somente_leitura and not forcar:
            raise PermissionError(self.aviso or "documento em somente leitura")

        dados = self.bytes_para_salvar(substituir=substituir_incompativeis)
        self.assinatura = arquivos.gravar_conferindo(
            self.caminho, dados, self.assinatura, forcar=forcar)
        self.qt.setModified(False)
        log.info("salvo %s (%d bytes, %s, %s)", self.caminho, len(dados),
                 codificacao.ROTULOS.get(self.codec, self.codec),
                 codificacao.ROTULO_EOL.get(self.fim_de_linha, "?"))

    def salvar_como(self, caminho: str | os.PathLike[str], *,
                    substituir_incompativeis: bool = False) -> None:
        alvo = pathlib.Path(caminho)
        dados = self.bytes_para_salvar(substituir=substituir_incompativeis)
        arquivos.gravar_atomico(alvo, dados)
        self.caminho = alvo
        self.rotulo_sem_titulo = ""
        self.somente_leitura = False
        self.assinatura = Assinatura.de_caminho(alvo, dados)
        self.qt.setModified(False)
        self.metadados_mudaram.emit()
        log.info("salvo como %s (%d bytes)", alvo, len(dados))

    # ==================================================================
    # Metadados alteraveis pelo usuario
    # ==================================================================

    def definir_codificacao(self, codec: str, *, com_bom: bool | None = None,
                            substituir: bool = False) -> list[codificacao.Perda]:
        """Troca a codificacao de gravacao.

        Devolve a lista de perdas SEM aplicar nada quando a conversao seria
        destrutiva e `substituir` e' False. Quem chama mostra a tabela e decide --
        e' o que impede uma troca de codificacao de comer os acentos em silencio.
        """
        perdas = codificacao.conferir_conversao(self.texto(), codec)
        if perdas and not substituir:
            return perdas

        self.codec = codec
        if com_bom is not None:
            import codecs as _codecs
            if com_bom and codec.replace("-", "").lower().startswith("utf8"):
                self.bom = _codecs.BOM_UTF8
            elif not com_bom:
                self.bom = b""
        self.qt.setModified(True)
        self.metadados_mudaram.emit()
        return []

    def definir_fim_de_linha(self, fim_de_linha: str) -> None:
        if fim_de_linha == self.fim_de_linha and not self.fins_de_linha_mistos:
            return
        self.fim_de_linha = fim_de_linha
        # Depois de uma escolha explicita, o arquivo deixa de ser "misto": o
        # usuario decidiu, e o aviso na barra de status nao faz mais sentido.
        self.fins_de_linha_mistos = False
        self.qt.setModified(True)
        self.metadados_mudaram.emit()

    def definir_indentacao(self, indentacao: Indentacao) -> None:
        self.indentacao = indentacao
        self.metadados_mudaram.emit()

    # ==================================================================
    # Alteracao externa (requisito 27)
    # ==================================================================

    def mudou_no_disco(self) -> bool:
        if self.caminho is None or self.assinatura is None:
            return False
        return not self.assinatura.compativel_com(
            Assinatura.de_caminho(self.caminho))

    def descrever_mudanca_externa(self) -> str:
        if self.caminho is None or self.assinatura is None:
            return ""
        return self.assinatura.descrever_diferenca(
            Assinatura.de_caminho(self.caminho))

    # ==================================================================
    # Propriedades (requisito 25)
    # ==================================================================

    def propriedades(self) -> dict[str, Any]:
        """Dados para o dialogo Arquivo > Propriedades."""
        texto = self.texto()
        info: dict[str, Any] = {
            "nome": self.nome,
            "caminho": str(self.caminho) if self.caminho else "(nao salvo)",
            "extensao": self.caminho.suffix if self.caminho else "",
            "linhas": self.total_de_linhas(),
            "caracteres": len(texto),
            "caracteres_sem_espaco": len(
                "".join(texto.split())),
            "palavras": len(texto.split()),
            "codificacao": self.perfil.rotulo if self.perfil else
                           codificacao.ROTULOS.get(self.codec, self.codec),
            "como_detectou": self.perfil.como_decidiu if self.perfil else "",
            "fim_de_linha": codificacao.ROTULO_EOL.get(self.fim_de_linha, "?"),
            "fim_de_linha_misto": self.fins_de_linha_mistos,
            "indentacao": self.indentacao.rotulo(),
            "somente_leitura": self.somente_leitura,
            "modificado": self.modificado,
        }
        if self.caminho is not None:
            try:
                st = self.caminho.stat()
                info["tamanho"] = st.st_size
                info["criado_em"] = st.st_ctime
                info["alterado_em"] = st.st_mtime
            except OSError:
                info["tamanho"] = 0
        else:
            # Sem arquivo, o "tamanho" e' o que ele TERIA -- calculado dos bytes
            # que seriam gravados, para nao mentir por causa do encoding.
            info["tamanho"] = len(self.bytes_para_salvar(substituir=True))
        return info
