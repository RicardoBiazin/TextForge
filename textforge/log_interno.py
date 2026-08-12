"""Log de diagnostico em %APPDATA%\\TextForge\\textforge.log.

Requisito 42: "criar logs internos para diagnostico" e "nao deixar excecoes
silenciosas". Este modulo e o `relatorio_de_erro` sao as duas metades disso --
aqui fica o rastro do que aconteceu, ali o que estourou.

REGRA DE PRIVACIDADE, valida para os dois: registramos CAMINHO, TAMANHO,
ENCODING e CONTAGEM. Nunca bytes nem trechos do documento. Um log com pedaco de
arquivo dentro, enviado por e-mail pelo usuario para relatar um bug, e' um
vazamento de dados que o programa causou.
"""

from __future__ import annotations

import logging
import logging.handlers

from textforge import APP, VERSAO
from textforge import configuracao

_pronto = False

FORMATO = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"


def preparar(nivel: int = logging.INFO) -> logging.Logger:
    """Liga o log em arquivo com rotacao. Chamar uma vez, no inicio do app."""
    global _pronto
    raiz = logging.getLogger("textforge")
    if _pronto:
        return raiz

    raiz.setLevel(nivel)
    raiz.propagate = False
    try:
        arquivo = logging.handlers.RotatingFileHandler(
            configuracao.caminho_log(), maxBytes=1_000_000, backupCount=3,
            encoding="utf-8")
        arquivo.setFormatter(logging.Formatter(FORMATO))
        raiz.addHandler(arquivo)
    except OSError:
        # Sem permissao de escrita em %APPDATA%: o programa continua, sem log.
        # Nao ha' a quem reportar isto ainda -- a janela nem existe.
        pass

    # No modo janela (console=False) nao existe stderr util, mas rodando do
    # fonte ele ajuda muito. O handler de console e' barato e nao atrapalha.
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMATO))
    raiz.addHandler(console)

    _pronto = True
    raiz.info("--- %s %s iniciando ---", APP, VERSAO)
    return raiz


def obter(nome: str) -> logging.Logger:
    """Logger de um modulo: obter(__name__)."""
    return logging.getLogger(nome if nome.startswith("textforge")
                             else "textforge." + nome)
