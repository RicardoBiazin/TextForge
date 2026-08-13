"""Formatador de JSON (requisito 6-JSON).

Formatar, compactar, validar e ordenar propriedades. `json.loads` NUNCA avalia
codigo -- e nao existe aqui nenhum fallback para `eval` nem para
`ast.literal_eval` em "JSON quase valido" (dict de Python, objeto JS, virgula
sobrando). Esse fallback e' a porta de entrada classica de execucao de codigo num
editor, e o requisito 35 o proibe.

DUAS ARMADILHAS DE FIDELIDADE que este modulo trata, e que quase toda
implementacao de "formatar JSON" tem:

  1. PRECISAO NUMERICA. `json.loads` devolve `float`, entao 1.10 volta como 1.1,
     1e400 vira `inf`, e um id de 20 digitos PERDE digitos. Num arquivo de
     integracao, alterar um identificador e' corromper dado. Resolvido com
     `parse_float`/`parse_int` guardando o texto original do numero e reemitindo-o
     verbatim.
  2. CHAVES DUPLICADAS. `{"a":1,"a":2}` colapsa em `{"a":2}` -- formatar APAGARIA
     dados. Um `object_pairs_hook` conta as duplicatas, e a operacao vira uma
     `Recusa`: o usuario decide, e nao descobre depois.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from textforge import seguranca
from textforge.formatadores.base import (ErroDeSintaxe, Recusa, Resultado, Saida,
                                         unidade_de_indentacao)


@dataclass(frozen=True)
class _Literal:
    """Um numero preservado como TEXTO, para nao perder precisao."""

    bruto: str

    def __repr__(self) -> str:      # usado pelo codificador
        return self.bruto


class _Codificador(json.JSONEncoder):
    """Emite `_Literal` verbatim.

    `default()` nao serve: ele exige um valor SERIALIZAVEL de volta, e devolver a
    string "1.10" produziria `"1.10"` com aspas. A saida passa por `iterencode`, e
    a substituicao acontece la'.
    """

    def iterencode(self, o, _one_shot: bool = False):
        for pedaco in super().iterencode(o, _one_shot):
            yield pedaco

    def default(self, o):
        if isinstance(o, _Literal):
            return o.bruto
        return super().default(o)


def _emitir(valor, indentacao: str | None, ordenar: bool) -> str:
    """Serializa tratando `_Literal` como numero cru.

    Feito a mao, e nao com `json.dumps`: o `dumps` poria aspas em qualquer coisa que
    o `default()` devolvesse, e o objetivo aqui e' justamente emitir o numero SEM
    aspas, exatamente como estava no arquivo.
    """
    pedacos: list[str] = []

    def escrever(v, nivel: int) -> None:
        recuo = ("\n" + indentacao * (nivel + 1)) if indentacao else ""
        fecha = ("\n" + indentacao * nivel) if indentacao else ""
        if isinstance(v, _Literal):
            pedacos.append(v.bruto)
        elif isinstance(v, dict):
            if not v:
                pedacos.append("{}")
                return
            itens = sorted(v.items(), key=lambda p: p[0]) if ordenar else v.items()
            pedacos.append("{")
            for i, (chave, sub) in enumerate(itens):
                if i:
                    pedacos.append(",")
                pedacos.append(recuo)
                pedacos.append(json.dumps(str(chave), ensure_ascii=False))
                pedacos.append(": " if indentacao else ":")
                escrever(sub, nivel + 1)
            pedacos.append(fecha)
            pedacos.append("}")
        elif isinstance(v, list):
            if not v:
                pedacos.append("[]")
                return
            pedacos.append("[")
            for i, sub in enumerate(v):
                if i:
                    pedacos.append(",")
                pedacos.append(recuo)
                escrever(sub, nivel + 1)
            pedacos.append(fecha)
            pedacos.append("]")
        elif isinstance(v, str):
            pedacos.append(json.dumps(v, ensure_ascii=False))
        elif v is True:
            pedacos.append("true")
        elif v is False:
            pedacos.append("false")
        elif v is None:
            pedacos.append("null")
        else:
            pedacos.append(json.dumps(v, ensure_ascii=False))

    escrever(valor, 0)
    return "".join(pedacos)


def _carregar(texto: str) -> tuple[object, list[str]]:
    """Le' o JSON preservando numeros e detectando chaves duplicadas."""
    duplicadas: list[str] = []

    def pares(itens):
        vistos: dict[str, object] = {}
        for chave, valor in itens:
            if chave in vistos:
                duplicadas.append(chave)
            vistos[chave] = valor
        return vistos

    dados = json.loads(
        texto,
        object_pairs_hook=pares,
        parse_float=_Literal,
        parse_int=_Literal,
        # NaN e Infinity NAO sao JSON valido. Recusar e' o correto: aceita-los
        # produziria um arquivo que outros programas nao conseguem ler.
        parse_constant=_constante_invalida)
    return dados, duplicadas


def _constante_invalida(nome: str):
    raise ValueError(
        f"{nome} nao e' JSON valido (apenas true, false e null sao aceitos)")


def validar(texto: str) -> ErroDeSintaxe | None:
    """None se valido. `JSONDecodeError` ja' entrega tudo pronto.

    `exc.pos` e' um offset em CARACTERES, e como o QTextDocument normaliza o fim de
    linha para um caractere so' e o `QTextCursor.position()` conta caracteres,
    `cursor.setPosition(exc.pos)` posiciona EXATO -- sem recalcular linha e coluna.
    """
    if not texto.strip():
        return ErroDeSintaxe(1, 1, "o documento esta' vazio", 0, "")
    try:
        _carregar(texto)
    except json.JSONDecodeError as exc:
        linhas = texto.split("\n")
        contexto = linhas[exc.lineno - 1] if exc.lineno - 1 < len(linhas) else ""
        return ErroDeSintaxe(exc.lineno, exc.colno, _traduzir(exc.msg),
                             exc.pos, contexto)
    except RecursionError:
        # Medido: um JSON com aninhamento muito profundo estoura a pilha do
        # decodificador. Virar mensagem, e nao traceback.
        return ErroDeSintaxe(
            1, 1, "o documento tem aninhamento profundo demais para ser "
                  "analisado", None, "")
    except ValueError as exc:
        # Cobre `NaN`/`Infinity` recusados e o limite de digitos de inteiro
        # ("Exceeds the limit (4300 digits)"), que o Python impoe.
        return ErroDeSintaxe(1, 1, str(exc), None, "")
    except MemoryError:
        return ErroDeSintaxe(1, 1, "o documento e' grande demais para analisar",
                             None, "")
    return None


MENSAGENS = {
    "Expecting value": "esperava um valor aqui",
    "Expecting ',' delimiter": "esperava uma virgula",
    "Expecting ':' delimiter": "esperava dois-pontos depois da chave",
    "Expecting property name enclosed in double quotes":
        "esperava um nome de propriedade entre aspas DUPLAS",
    "Unterminated string starting at": "string nao fechada, comecando em",
    "Extra data": "ha' conteudo depois do fim do JSON",
    "Invalid control character at": "caractere de controle invalido em",
    "Invalid \\escape": "sequencia de escape invalida",
}


def _traduzir(msg: str) -> str:
    for chave, traducao in MENSAGENS.items():
        if msg.startswith(chave):
            return f"{traducao} ({msg})"
    return msg


def _formatar(texto: str, opcoes: dict, *, indentar: bool,
              ordenar: bool = False) -> Saida:
    erro = validar(texto)
    if erro is not None:
        return erro
    try:
        seguranca.conferir_tamanho(texto)
    except seguranca.EntradaGrandeDemais as exc:
        return Recusa(str(exc), "Use um formatador de linha de comando para "
                               "arquivos desse tamanho.")

    dados, duplicadas = _carregar(texto)
    if duplicadas:
        distintas = sorted(set(duplicadas))
        return Recusa(
            f"Este JSON tem {len(duplicadas)} chave(s) duplicada(s): "
            f"{', '.join(repr(c) for c in distintas[:6])}"
            + (f" e mais {len(distintas) - 6}" if len(distintas) > 6 else "")
            + ".",
            "Formatar manteria apenas a ULTIMA de cada, apagando as outras. "
            "Remova as duplicatas antes de formatar.")

    unidade = unidade_de_indentacao(opcoes) if indentar else None
    novo = _emitir(dados, unidade, ordenar)
    avisos: list[str] = []
    if ordenar:
        avisos.append("As propriedades foram ordenadas alfabeticamente.")
    return Resultado(novo, avisos)


class FormatadorJson:
    nome = "JSON"

    def formatar(self, texto: str, opcoes: dict) -> Saida:
        return _formatar(texto, opcoes, indentar=True)

    def formatar_ordenando(self, texto: str, opcoes: dict) -> Saida:
        return _formatar(texto, opcoes, indentar=True, ordenar=True)

    def compactar(self, texto: str, opcoes: dict) -> Saida:
        return _formatar(texto, opcoes, indentar=False)

    def validar(self, texto: str) -> ErroDeSintaxe | None:
        return validar(texto)


FORMATADOR = FormatadorJson()
