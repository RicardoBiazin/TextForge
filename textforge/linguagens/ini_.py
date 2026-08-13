"""Provedor de INI / CFG / CONF / ENV / TOML simples.

E' o formato mais simples e um dos mais usados no dia a dia deste usuario. Duas
particularidades que o realce trata:

  * `.env` usa "#" e nao aceita `;`; INI classico aceita os dois. Reconhecer os
    dois cobre tudo sem prejuizo -- um `;` no meio de um valor de `.env` seria raro,
    e o pior caso e' um comentario pintado onde havia texto.
  * `chave = valor` NAO tem o valor pintado como string, mesmo sem aspas: num
    arquivo de configuracao o valor e' o dado mais importante da linha, e deixa-lo
    da cor do texto comum e' o que o torna legivel.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce


class ProvedorIni(ProvedorDeLinguagem):
    nome = "INI"
    extensoes = (".ini", ".cfg", ".conf", ".env", ".properties", ".toml",
                 ".editorconfig", ".gitconfig", ".inf", ".reg", ".desktop",
                 ".service", ".spec")
    nomes_de_arquivo = (".env", ".env.local", ".env.production", ".gitconfig",
                        ".editorconfig", ".npmrc", ".condarc", "setup.cfg",
                        "tox.ini", "pytest.ini", "my.cnf", "php.ini")
    comentario_de_linha = "#"
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        raiz = Contexto("raiz", (
            # Comentario primeiro: "# [secao]" nao e' uma secao.
            Regra(re.compile(r"[#;].*$"), "comentario"),
            # A secao pega a linha inteira, o que a destaca de verdade.
            Regra(re.compile(r"^\s*\[[^\]\n]*\]"), "secao"),
            # A chave e' o que vem antes do "=" ou do ":", no inicio da linha.
            Regra(re.compile(r"^\s*(?P<ini_chave>[^=:#;\[\s][^=:#;\n]*?)(?=\s*[=:])"),
                  "chave", papeis_por_grupo={"ini_chave": "chave"}),
            Regra(re.compile(r"[=:]"), "operador"),
            Regra(re.compile(r.texto_com_escape('"')), "texto_literal"),
            Regra(re.compile(r.texto_com_escape("'")), "texto_literal"),
            # Flag com escopo: ver o comentario equivalente em xml_.py.
            Regra(re.compile(r"(?i:\b(?:true|false|yes|no|on|off|none|null)\b)"),
                  "constante"),
            # Interpolacao de variavel de ambiente: ${VAR}, %VAR%, $VAR.
            Regra(re.compile(r"\$\{[^}\n]*\}|%[A-Za-z_]\w*%|\$[A-Za-z_]\w*"),
                  "interpolacao"),
            Regra(re.compile(r.NUMERO), "numero"),
        ))
        self._cache = RegrasDeRealce(inicial="raiz",
                                     contextos={"raiz": raiz})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        # Uma secao vai ate' a proxima: nao e' indentacao nem delimitador. Fica em
        # "marcadores", e a regiao e' a secao inteira.
        return RegraDeDobra(modo="marcadores",
                            marcador_abre=re.compile(r"^\s*\["))

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset({"true", "false", "yes", "no", "on", "off", "none"})

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Secoes, com as chaves de cada uma como filhas (requisito 11)."""
        raizes: list[NoDeEstrutura] = []
        atual: NoDeEstrutura | None = None
        secao = re.compile(r"^\s*\[([^\]]*)\]")
        chave = re.compile(r"^\s*([^=:#;\[\s][^=:#;]*?)\s*[=:]")

        for numero, linha in enumerate(texto.split("\n")):
            sem_comentario = re.sub(r"[#;].*$", "", linha)
            c = secao.match(sem_comentario)
            if c:
                atual = NoDeEstrutura(rotulo=c.group(1).strip() or "(sem nome)",
                                      tipo="secao", linha=numero,
                                      coluna=c.start(1))
                raizes.append(atual)
                continue
            c = chave.match(sem_comentario)
            if c:
                no = NoDeEstrutura(rotulo=c.group(1).strip(), tipo="chave",
                                   linha=numero, coluna=c.start(1),
                                   detalhe=sem_comentario.split("=", 1)[-1]
                                   .strip()[:50])
                if atual is not None:
                    atual.filhos.append(no)
                else:
                    # Chave antes de qualquer secao: e' o caso normal de um .env.
                    raizes.append(no)
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        linhas = [l for l in amostra.split("\n")[:60] if l.strip()
                  and not l.lstrip().startswith(("#", ";"))]
        if not linhas:
            return 0
        secoes = sum(1 for l in linhas if re.match(r"^\s*\[[^\]]+\]\s*$", l))
        atribuicoes = sum(1 for l in linhas
                          if re.match(r"^\s*[\w.\-]+\s*=", l))
        pontos = 0
        if secoes:
            pontos += 40
        if atribuicoes:
            # Proporcao de linhas que sao "chave = valor": num .env e' quase 100%.
            pontos += int(45 * atribuicoes / len(linhas))
        # Chave de abertura solta sugere JSON ou codigo, nao INI.
        if any(l.strip().endswith(("{", "}", "();", ");")) for l in linhas):
            pontos -= 35
        return max(0, min(pontos, 100))


PROVEDORES = (ProvedorIni(),)
