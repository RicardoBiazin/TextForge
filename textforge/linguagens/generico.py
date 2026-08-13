"""`ProvedorGenerico`: uma linguagem declarada como DADOS, nao como codigo.

Cobre a maioria das linguagens de verdade -- as de chaves e as de comentario com
"#": palavras-chave, tipos, constantes, string com escape, numero, comentario de
linha e de bloco, chamada de funcao, operador. Com isso, acrescentar Lua, Go, Rust
ou Kotlin e' preencher listas.

Duas consequencias praticas:

  * um plugin nao precisa entender `Contexto` nem `Regra` para acrescentar uma
    linguagem;
  * `de_json()` aceita o mesmo dicionario vindo de um arquivo em
    %APPDATA%\\TextForge\\linguagens. E' a via de extensao que NAO executa codigo
    de terceiros -- coisa que a pasta de plugins, por definicao, faz.
"""

from __future__ import annotations

import re
from typing import Any

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

# Chaves aceitas por `de_json`. Uma chave desconhecida vira aviso, e nao excecao:
# um arquivo de linguagem escrito a mao com um erro de digitacao nao pode impedir o
# programa de abrir.
CHAVES = frozenset({
    "nome", "extensoes", "nomes_de_arquivo", "padroes_de_shebang", "prioridade",
    "palavras_chave", "palavras_chave_2", "tipos", "constantes", "embutidas",
    "comentario_de_linha", "comentario_de_bloco", "delimitadores_de_texto",
    "diferencia_maiusculas", "indentacao", "modo_de_dobra",
    "aumenta_indentacao", "diminui_indentacao", "prefixo_de_definicao",
})


class ProvedorGenerico(ProvedorDeLinguagem):
    def __init__(
        self, *,
        nome: str,
        extensoes: tuple[str, ...] = (),
        nomes_de_arquivo: tuple[str, ...] = (),
        padroes_de_shebang: tuple[str, ...] = (),
        prioridade: int = 0,
        palavras_chave: tuple[str, ...] = (),
        palavras_chave_2: tuple[str, ...] = (),      # segunda familia (import, as)
        tipos: tuple[str, ...] = (),
        constantes: tuple[str, ...] = (),
        embutidas: tuple[str, ...] = (),
        comentario_de_linha: str | None = None,
        comentario_de_bloco: tuple[str, str] | None = None,
        delimitadores_de_texto: tuple[str, ...] = ('"', "'"),
        diferencia_maiusculas: bool = True,
        indentacao: Indentacao | None = None,
        modo_de_dobra: str = "indentacao",
        aumenta_indentacao: str | None = None,
        diminui_indentacao: str | None = None,
        # Palavras que introduzem uma definicao ("def", "class", "function"): o
        # NOME que vem depois delas e' pintado com o papel "definicao".
        prefixo_de_definicao: tuple[str, ...] = (),
    ) -> None:
        self.nome = nome
        self.extensoes = tuple(e.lower() for e in extensoes)
        self.nomes_de_arquivo = tuple(nomes_de_arquivo)
        self.padroes_de_shebang = tuple(padroes_de_shebang)
        self.prioridade = prioridade
        self.comentario_de_linha = comentario_de_linha
        self.comentario_de_bloco = (tuple(comentario_de_bloco)
                                    if comentario_de_bloco else None)
        self.indentacao_padrao = indentacao or Indentacao()
        self.diferencia_maiusculas = diferencia_maiusculas

        self._palavras_chave = tuple(palavras_chave)
        self._palavras_chave_2 = tuple(palavras_chave_2)
        self._tipos = tuple(tipos)
        self._constantes = tuple(constantes)
        self._embutidas = tuple(embutidas)
        self._delimitadores = tuple(delimitadores_de_texto)
        self._modo_de_dobra = modo_de_dobra
        self._prefixo_de_definicao = tuple(prefixo_de_definicao)

        self.aumenta_indentacao = (re.compile(aumenta_indentacao)
                                   if aumenta_indentacao else None)
        self.diminui_indentacao = (re.compile(diminui_indentacao)
                                  if diminui_indentacao else None)

        # Os regexes sao compilados UMA vez por processo, na primeira chamada de
        # `regras()`. Compilar a cada bloco pintado seria o gargalo do realce.
        self._cache: RegrasDeRealce | None = None

    # ==================================================================
    # Realce
    # ==================================================================

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is None:
            self._cache = self._montar()
        return self._cache

    def _montar(self) -> RegrasDeRealce:
        bandeiras = 0 if self.diferencia_maiusculas else re.IGNORECASE
        lista: list[Regra] = []
        contextos: dict[str, Contexto] = {}

        # A ORDEM importa: o regex combinado e' uma alternancia, e o Python para no
        # primeiro ramo que casa. Comentario e string vem ANTES de palavra-chave,
        # senao "# if x" teria o "if" pintado como palavra-chave dentro do
        # comentario.

        # 1. Comentario de bloco -- vira contexto, porque atravessa linhas.
        if self.comentario_de_bloco:
            abre, fecha = self.comentario_de_bloco
            lista.append(Regra(re.compile(re.escape(abre), bandeiras),
                               "comentario", entrar_em="comentario_de_bloco"))
            contextos["comentario_de_bloco"] = Contexto(
                "comentario_de_bloco",
                (Regra(re.compile(re.escape(fecha), bandeiras), "comentario",
                       sair=True),),
                papel_padrao="comentario")

        # 2. Comentario de linha.
        if self.comentario_de_linha:
            lista.append(Regra(
                re.compile(re.escape(self.comentario_de_linha) + r".*$",
                           bandeiras), "comentario"))

        # 3. Strings de uma linha.
        for delimitador in self._delimitadores:
            lista.append(Regra(
                re.compile(r.texto_com_escape(delimitador), bandeiras),
                "texto_literal"))

        # 4. Definicoes: "def nome", "function nome", "class Nome".
        if self._prefixo_de_definicao:
            alternativa = r.alternativa_de_palavras(self._prefixo_de_definicao)
            lista.append(Regra(
                re.compile(rf"{alternativa}\s+(?P<def_nome>[A-Za-z_]\w*)",
                           bandeiras),
                "palavra_chave", papeis_por_grupo={"def_nome": "definicao"}))

        # 5. Numeros antes das palavras: "0x1F" nao deve ser quebrado.
        lista.append(Regra(re.compile(r.NUMERO, bandeiras), "numero"))

        # 6. Familias de palavras, das mais especificas para as mais gerais.
        for palavras, papel in ((self._constantes, "constante"),
                                (self._tipos, "tipo"),
                                (self._palavras_chave_2, "palavra_chave_2"),
                                (self._palavras_chave, "palavra_chave"),
                                (self._embutidas, "embutida")):
            if palavras:
                lista.append(r.regra_de_palavras(
                    palavras, papel, sem_caixa=not self.diferencia_maiusculas))

        # 7. Chamada de funcao, operador e pontuacao -- os mais genericos por
        #    ultimo, senao engoliriam os casos acima.
        lista.append(Regra(re.compile(r.CHAMADA, bandeiras), "chamada"))
        lista.append(Regra(re.compile(r.OPERADOR, bandeiras), "operador"))
        lista.append(Regra(re.compile(r.PONTUACAO, bandeiras), "pontuacao"))

        contextos["raiz"] = Contexto("raiz", tuple(lista))
        return RegrasDeRealce(inicial="raiz", contextos=contextos)

    # ==================================================================
    # Restante do contrato
    # ==================================================================

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo=self._modo_de_dobra)

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(self._palavras_chave + self._palavras_chave_2
                         + self._tipos + self._constantes + self._embutidas)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Definicoes achadas por regex. Serve a qualquer linguagem declarativa.

        E' proposital que seja por regex e nao por parser: um provedor generico
        nao tem gramatica. O provedor de Python sobrepoe isto usando `ast`.
        """
        if not self._prefixo_de_definicao:
            return []
        alternativa = r.alternativa_de_palavras(self._prefixo_de_definicao)
        padrao = re.compile(rf"^\s*(?:{alternativa[2:-2]})\s+([A-Za-z_]\w*)",
                            0 if self.diferencia_maiusculas else re.IGNORECASE)
        achados: list[NoDeEstrutura] = []
        for numero, linha in enumerate(texto.split("\n")):
            casamento = padrao.match(linha)
            if casamento:
                achados.append(NoDeEstrutura(
                    rotulo=casamento.group(1), tipo="funcao", linha=numero,
                    coluna=casamento.start(1)))
        return achados

    # ==================================================================
    # Construcao a partir de JSON
    # ==================================================================

    @classmethod
    def de_json(cls, dados: dict[str, Any]) -> tuple["ProvedorGenerico | None",
                                                     list[str]]:
        """Monta um provedor a partir de um dicionario. (provedor, avisos).

        Devolve avisos em vez de levantar: um arquivo de linguagem do usuario com
        erro de digitacao tem de gerar um item no painel Problemas, nao impedir o
        programa de abrir.
        """
        avisos: list[str] = []
        if not isinstance(dados, dict):
            return None, ["o arquivo de linguagem nao contem um objeto JSON"]
        nome = dados.get("nome")
        if not nome or not isinstance(nome, str):
            return None, ["o arquivo de linguagem nao declara 'nome'"]

        for chave in dados:
            if chave not in CHAVES:
                avisos.append(f"{nome}: chave desconhecida ignorada: {chave!r}")

        def tupla(chave: str) -> tuple[str, ...]:
            valor = dados.get(chave) or ()
            if isinstance(valor, str):
                # Aceita "if while for" e ["if","while","for"]: e' o erro mais
                # comum de quem escreve o JSON a mao.
                return tuple(valor.split())
            if isinstance(valor, (list, tuple)):
                return tuple(str(v) for v in valor)
            avisos.append(f"{nome}: {chave!r} deveria ser uma lista")
            return ()

        bloco = dados.get("comentario_de_bloco")
        if bloco is not None and not (isinstance(bloco, (list, tuple))
                                     and len(bloco) == 2):
            avisos.append(f"{nome}: 'comentario_de_bloco' precisa de 2 itens")
            bloco = None

        indentacao = None
        bruta = dados.get("indentacao")
        if isinstance(bruta, dict):
            indentacao = Indentacao(
                usa_espacos=bool(bruta.get("usa_espacos", True)),
                largura=int(bruta.get("largura", 4) or 4))

        for chave in ("aumenta_indentacao", "diminui_indentacao"):
            valor = dados.get(chave)
            if valor:
                try:
                    re.compile(str(valor))
                except re.error as exc:
                    avisos.append(f"{nome}: {chave!r} nao e' um regex valido "
                                  f"({exc}); ignorado")
                    dados = {**dados, chave: None}

        try:
            provedor = cls(
                nome=nome,
                extensoes=tupla("extensoes"),
                nomes_de_arquivo=tupla("nomes_de_arquivo"),
                padroes_de_shebang=tupla("padroes_de_shebang"),
                prioridade=int(dados.get("prioridade", 10) or 10),
                palavras_chave=tupla("palavras_chave"),
                palavras_chave_2=tupla("palavras_chave_2"),
                tipos=tupla("tipos"),
                constantes=tupla("constantes"),
                embutidas=tupla("embutidas"),
                comentario_de_linha=dados.get("comentario_de_linha"),
                comentario_de_bloco=tuple(bloco) if bloco else None,
                delimitadores_de_texto=tupla("delimitadores_de_texto")
                or ('"', "'"),
                diferencia_maiusculas=bool(
                    dados.get("diferencia_maiusculas", True)),
                indentacao=indentacao,
                modo_de_dobra=str(dados.get("modo_de_dobra", "indentacao")),
                aumenta_indentacao=dados.get("aumenta_indentacao"),
                diminui_indentacao=dados.get("diminui_indentacao"),
                prefixo_de_definicao=tupla("prefixo_de_definicao"),
            )
        except (TypeError, ValueError, re.error) as exc:
            return None, avisos + [f"{nome}: nao foi possivel montar ({exc})"]
        return provedor, avisos
