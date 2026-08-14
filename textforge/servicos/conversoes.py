"""Conversoes de texto: Base64, URL, HTML e JSON (requisito 24).

Todas tem a mesma forma: `str -> str`, levantando `ConversaoInvalida` com mensagem
para o usuario quando a entrada nao serve. Nenhuma delas toca em disco, em Qt ou em
estado global.

A DECISAO QUE ATRAVESSA O MODULO INTEIRO: **Base64 e URL trabalham sobre BYTES, e o
texto so' vira bytes depois de escolher uma codificacao.** `"ação"` em UTF-8 e' um
Base64; em cp1252 e' outro. O padrao e' UTF-8, porque e' o que praticamente todo
sistema que consome Base64 espera hoje -- mas o parametro existe, e a janela passa a
codificacao DO DOCUMENTO, para o resultado casar com o resto do arquivo que o
usuario esta' editando. Ignorar isso produziria um Base64 que decodifica errado no
sistema de destino, e o usuario levaria horas para descobrir por que.
"""

from __future__ import annotations

import base64
import binascii
import html as _html
import json
import re
import urllib.parse

# Aspa que NAO esta' escapada. Usado ao embrulhar um trecho solto como string JSON.
# Limite conhecido: numa sequencia `\\"` (barra escapada seguida de aspa solta) ele
# ve' a barra e nao escapa a aspa. E' raro o bastante para nao valer um analisador,
# e o desfecho e' uma mensagem de erro -- nao um texto corrompido em silencio.
_ASPA_SOLTA = re.compile(r'(?<!\\)"')


class ConversaoInvalida(ValueError):
    """A entrada nao pode ser convertida. A mensagem e' para o usuario ver."""


# ---------------------------------------------------------------------------
# Base64
# ---------------------------------------------------------------------------


def base64_codificar(texto: str, codec: str = "utf-8") -> str:
    try:
        bruto = texto.encode(codec)
    except UnicodeEncodeError as exc:
        raise ConversaoInvalida(
            f"o texto tem caracteres que nao existem em {codec} "
            f"(o primeiro e' {texto[exc.start:exc.start + 1]!r}). "
            f"Converta o arquivo para UTF-8 antes.") from exc
    return base64.b64encode(bruto).decode("ascii")


def base64_decodificar(texto: str, codec: str = "utf-8") -> str:
    """Decodifica Base64, aceitando o alfabeto padrao E o urlsafe.

    Duas tolerancias deliberadas, porque as duas aparecem em arquivo real:

      * ESPACO EM BRANCO. Base64 colado de um e-mail ou de um XML vem quebrado em
        linhas de 76 colunas; recusar isso seria recusar o caso mais comum.
      * PADDING FALTANDO. Muitos geradores omitem o "=" do fim. `b64decode` com
        `validate=False` ainda assim levanta se o comprimento nao for multiplo de
        4, entao o padding e' recomposto aqui.

    O que NAO e' tolerado: caractere fora do alfabeto. Ai a entrada realmente nao
    e' Base64, e "decodificar" produziria lixo silencioso.
    """
    limpo = "".join(texto.split())
    if not limpo:
        raise ConversaoInvalida("nao ha' nada para decodificar")
    # O alfabeto urlsafe troca "+/" por "-_". Normalizar aqui faz os dois
    # funcionarem sem o usuario precisar saber qual gerou o texto.
    limpo = limpo.replace("-", "+").replace("_", "/")
    limpo += "=" * (-len(limpo) % 4)
    try:
        bruto = base64.b64decode(limpo, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConversaoInvalida(
            f"isto nao e' Base64 valido ({exc}). Confira se a selecao pegou o "
            f"texto inteiro e nada em volta.") from exc
    try:
        return bruto.decode(codec)
    except UnicodeDecodeError as exc:
        raise ConversaoInvalida(
            f"o Base64 e' valido, mas os bytes nao formam texto em {codec}. "
            f"Pode ser um arquivo binario codificado (uma imagem, por exemplo) "
            f"-- {exc.reason}.") from exc


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------


def url_codificar(texto: str, codec: str = "utf-8") -> str:
    """Percent-encode de um COMPONENTE de URL (`safe=""`).

    Nada e' preservado, nem "/" nem ":" nem "?". E' o que se quer ao montar o valor
    de um parametro: `?busca=` + url_codificar("a/b?c") tem de virar `a%2Fb%3Fc`,
    senao a barra e a interrogacao mudariam o significado da URL inteira.

    Para escapar uma URL JA montada sem quebra-la, o usuario nao quer esta funcao --
    quer nao escapar nada.
    """
    return urllib.parse.quote(texto, safe="", encoding=codec, errors="strict")


def url_decodificar(texto: str, codec: str = "utf-8") -> str:
    """Decodifica percent-encoding.

    `+` NAO vira espaco: isso e' regra de `application/x-www-form-urlencoded`, e nao
    de URL. Num caminho ou num fragmento, `+` e' um `+` literal, e trocar por espaco
    corromperia o dado. Quem tem um corpo de formulario troca o `+` antes.
    """
    try:
        return urllib.parse.unquote(texto, encoding=codec, errors="strict")
    except UnicodeDecodeError as exc:
        raise ConversaoInvalida(
            f"as sequencias %XX nao formam texto valido em {codec} "
            f"({exc.reason}). O texto pode estar em outra codificacao.") from exc


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def html_codificar(texto: str, _codec: str = "utf-8") -> str:
    """Escapa `& < > " '`.

    Com `quote=True`: as aspas TEM de ser escapadas, porque o uso mais comum e'
    colar o texto dentro de um atributo (`value="..."`), e uma aspa solta ali fecha
    o atributo e abre um buraco de injecao.
    """
    return _html.escape(texto, quote=True)


def html_decodificar(texto: str, _codec: str = "utf-8") -> str:
    """Resolve entidades nomeadas e numericas. Nao levanta: o que nao e' entidade
    fica como esta', que e' o comportamento do navegador."""
    return _html.unescape(texto)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def json_escapar(texto: str, _codec: str = "utf-8") -> str:
    """Escapa o texto como conteudo de string JSON, SEM as aspas em volta.

    Sem as aspas de proposito: o gesto e' "peguei este texto e quero cola-lo dentro
    de uma string que ja' existe no arquivo". Devolver `"..."` obrigaria o usuario a
    apagar duas aspas toda vez.

    `ensure_ascii=False` preserva os acentos como caracteres. JSON e' UTF-8 por
    especificacao (RFC 8259), entao `\\u00e7` seria correto mas ilegivel; quem
    precisa da forma ASCII tem o formatador de JSON.
    """
    return json.dumps(texto, ensure_ascii=False)[1:-1]


def json_desescapar(texto: str, _codec: str = "utf-8") -> str:
    """O inverso: resolve `\\n`, `\\uXXXX`, `\\"` e afins.

    Aceita o texto COM ou SEM as aspas em volta -- o usuario pode ter selecionado a
    string inteira do arquivo, incluindo as aspas, e recusar isso seria pedante.
    """
    bruto = texto.strip()

    # A selecao ja' e' um valor JSON COMPLETO? So' vale a pena tentar quando ela
    # comeca como um -- senao "123" seria lido como o numero 123 e recusado como
    # "nao e' uma string", o que nao ajudaria ninguem que so' queria desescapar
    # um texto que por acaso e' numerico.
    if bruto[:1] in ('"', "{", "["):
        try:
            valor = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise ConversaoInvalida(
                f"nao e' uma string JSON valida: {exc.msg} (posicao {exc.pos}). "
                f"Uma barra invertida solta e' a causa mais comum -- em JSON ela "
                f"precisa ser escrita como \\\\.") from exc
        if not isinstance(valor, str):
            raise ConversaoInvalida(
                "a selecao e' um valor JSON, mas nao uma string (e' um "
                f"{type(valor).__name__}). Para reindentar um objeto ou uma "
                "lista, use Formatar > Formatar documento.")
        return valor

    # Nao e': trata como CONTEUDO de string e embrulha. As aspas ainda NAO
    # escapadas precisam ser escapadas antes, senao montariamos um JSON invalido
    # aqui dentro e o erro apontaria para uma posicao que o usuario nao ve.
    montado = '"' + _ASPA_SOLTA.sub(r'\\"', texto) + '"'
    try:
        valor = json.loads(montado)
    except json.JSONDecodeError as exc:
        raise ConversaoInvalida(
            f"nao e' uma string JSON valida: {exc.msg}. Uma barra invertida "
            f"solta e' a causa mais comum -- em JSON ela precisa ser escrita "
            f"como \\\\.") from exc
    return valor


# ---------------------------------------------------------------------------
# Registro, para o menu e a paleta ligarem por id
# ---------------------------------------------------------------------------

POR_COMANDO = {
    "conv.base64_codificar": base64_codificar,
    "conv.base64_decodificar": base64_decodificar,
    "conv.url_codificar": url_codificar,
    "conv.url_decodificar": url_decodificar,
    "conv.html_codificar": html_codificar,
    "conv.html_decodificar": html_decodificar,
    "conv.json_escapar": json_escapar,
    "conv.json_desescapar": json_desescapar,
}
