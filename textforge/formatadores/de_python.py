"""Formatador de Python (requisito 6-Python).

Usa o `black`, que e' o formatador padrao de mercado. E' dependencia OPCIONAL
(requirements-extras.txt): sem ele, "Formatar documento" num `.py` avisa como
instalar em vez de aplicar uma indentacao caseira -- reindentar Python a mao e' o
caminho mais curto para quebrar o codigo, porque a indentacao E' a sintaxe.

O `black` e' chamado como BIBLIOTECA (`black.format_str`), nunca como processo.
Rodar `subprocess` sobre o arquivo do usuario seria executar um programa externo
sobre o conteudo aberto, o que este editor nao faz (requisito 35).

`validar` usa `ast.parse`, que NAO executa nada -- e' a diferenca entre `ast.parse`
(analise, permitido) e `eval`/`exec`/`compile` (execucao, proibido).
"""

from __future__ import annotations

from textforge import log_interno
from textforge.formatadores.base import ErroDeSintaxe, Recusa, Resultado, Saida

log = log_interno.obter(__name__)

# Comprimento de linha. 88 e' o padrao do black; o TextForge nao inventa outro,
# porque um arquivo formatado aqui e' reformatado pelo black do projeto depois, e
# duas larguras diferentes produzem um vai-e-vem eterno no diff.
COMPRIMENTO_PADRAO = 88


def _disponivel() -> bool:
    try:
        import black  # noqa: F401
    except ImportError:
        return False
    return True


def validar(texto: str) -> ErroDeSintaxe | None:
    """Erro de sintaxe com linha, coluna e motivo. Usa `ast.parse`."""
    import ast

    if not texto.strip():
        return None
    try:
        ast.parse(texto)
    except SyntaxError as exc:
        linhas = texto.split("\n")
        numero = exc.lineno or 1
        contexto = (exc.text or (linhas[numero - 1]
                                 if numero - 1 < len(linhas) else "")).rstrip()
        return ErroDeSintaxe(numero, exc.offset or 1, exc.msg or "erro de sintaxe",
                             None, contexto)
    except (ValueError, RecursionError, MemoryError) as exc:
        # `ValueError` cobre o caso de bytes nulos no fonte; os outros dois, arquivo
        # gerado com aninhamento absurdo. Virar mensagem, nao traceback.
        return ErroDeSintaxe(1, 1, f"nao foi possivel analisar: {exc}", None, "")
    return None


def formatar(texto: str, opcoes: dict) -> Saida:
    if not texto.strip():
        return Resultado(texto)

    erro = validar(texto)
    if erro is not None:
        return erro

    if not _disponivel():
        return Recusa(
            "Formatar Python depende do pacote 'black', que nao esta' instalado.",
            "Instale com: pip install black   (ou "
            "pip install -r requirements-extras.txt)")

    import black

    largura = int(opcoes.get("comprimento_de_linha") or COMPRIMENTO_PADRAO)
    modo = black.Mode(line_length=largura,
                      # O black normaliza a string para aspas duplas. E' o padrao
                      # dele, e desligar produziria arquivo que o black do projeto
                      # reformataria na primeira execucao.
                      string_normalization=True)
    try:
        novo = black.format_str(texto, mode=modo)
    except black.NothingChanged:
        return Resultado(texto, ["O arquivo ja' estava formatado."])
    except Exception as exc:            # noqa: BLE001 - biblioteca de terceiros
        log.warning("black falhou: %s", exc)
        return Recusa(f"O black nao conseguiu formatar este arquivo ({exc}).",
                      "O arquivo nao foi alterado.")

    avisos = []
    if largura != COMPRIMENTO_PADRAO:
        avisos.append(f"Formatado com linhas de {largura} colunas.")
    return Resultado(novo, avisos)


def compactar(texto: str, opcoes: dict) -> Saida:
    """Python NAO tem forma compactada.

    A indentacao E' a sintaxe: remover quebras de linha nao produz um programa
    equivalente, produz um programa quebrado. Recusar e' a unica resposta honesta.
    """
    return Recusa(
        "Python nao pode ser compactado: a indentacao e as quebras de linha fazem "
        "parte da sintaxe da linguagem.",
        "Use 'Formatar documento' para organizar o codigo.")


class FormatadorPython:
    nome = "Python"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return formatar(texto, opcoes)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return compactar(texto, opcoes)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorPython()
