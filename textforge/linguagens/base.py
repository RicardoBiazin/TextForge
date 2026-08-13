"""`ProvedorDeLinguagem`: tudo o que o nucleo precisa saber sobre uma linguagem.

Esta assinatura e' o contrato do requisito 36, e e' o arquivo mais estavel do
projeto: mexer nela quebra todo provedor e todo plugin. Por isso ela e' pequena, e
tudo alem do realce tem implementacao padrao INERTE -- um provedor minimo declara
nome, extensoes e regras, e ganha comentar/descomentar, dobra por indentacao e
autocomplete de palavras do proprio arquivo sem escrever mais nada.

O nucleo nunca importa um provedor concreto: ele pergunta ao `registro`. E' o que
permite um plugin acrescentar uma linguagem sem tocar em nenhum arquivo do nucleo.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field

from textforge.editor.indentacao import Indentacao
from textforge.realce.regras import RegrasDeRealce


@dataclass
class NoDeEstrutura:
    """Item do painel Estrutura (requisito 11). Arvore rasa ou profunda."""

    rotulo: str
    tipo: str                      # "classe" | "funcao" | "secao" | "tag" | "chave"
    linha: int                     # BASE ZERO, como o resto do nucleo
    coluna: int = 0
    detalhe: str = ""              # assinatura, atributos
    filhos: list["NoDeEstrutura"] = field(default_factory=list)


@dataclass(frozen=True)
class RegraDeDobra:
    """Como a linguagem forma regioes dobraveis (requisito 12).

    "indentacao"     Python, YAML: a regiao vai ate' a linha com indentacao menor.
    "delimitadores"  C, JSON, CSS: a regiao vai da abertura ao fechamento.
    """

    modo: str = "indentacao"
    marcador_abre: re.Pattern[str] | None = None      # #region
    marcador_fecha: re.Pattern[str] | None = None     # #endregion


class ProvedorDeLinguagem(abc.ABC):
    # -- identidade --------------------------------------------------------
    nome: str = ""
    # Sempre com o ponto e em minusculas: (".py", ".pyw").
    extensoes: tuple[str, ...] = ()
    # Nomes de arquivo INTEIROS, para os que nao tem extensao: ("Makefile",
    # ".gitignore", "Dockerfile").
    nomes_de_arquivo: tuple[str, ...] = ()
    # Trechos procurados na primeira linha, para arquivo sem extensao.
    padroes_de_shebang: tuple[str, ...] = ()
    # Maior ganha o empate. Provedor de plugin usa >0 para sobrepor um embutido.
    prioridade: int = 0

    # -- edicao ------------------------------------------------------------
    comentario_de_linha: str | None = None            # "#", "//"
    comentario_de_bloco: tuple[str, str] | None = None  # ("/*", "*/")
    indentacao_padrao: Indentacao = Indentacao()
    pares_para_fechar: tuple[tuple[str, str], ...] = (
        ("(", ")"), ("[", "]"), ("{", "}"), ('"', '"'), ("'", "'"))
    # Linha que termina abrindo um bloco: o ":" do Python, o "{" do C.
    aumenta_indentacao: re.Pattern[str] | None = None
    # Linha que fecha um bloco e deve recuar: "}", "else:", "end".
    diminui_indentacao: re.Pattern[str] | None = None

    # -- realce (o unico obrigatorio) --------------------------------------
    @abc.abstractmethod
    def regras(self, tema) -> RegrasDeRealce:
        """Contextos e regras. Cita PAPEIS do tema, nunca cores literais."""

    # -- opcionais, com padrao inerte --------------------------------------
    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="indentacao")

    def formatador(self):
        """`Formatador` da etapa 8, ou None se a linguagem nao tem."""
        return None

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        return []

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset()

    def detectar_por_conteudo(self, amostra: str) -> int:
        """Confianca 0..100 de que a amostra e' desta linguagem.

        Consultado APENAS quando extensao, nome de arquivo e shebang nao
        decidiram. Recebe os primeiros KB ja' decodificados -- nenhum provedor
        toca em disco, o que mantem os testes puros e permite classificar um buffer
        sem titulo.
        """
        return 0

    def visualizador_preferido(self) -> str:
        """"texto" | "tabela" | "hex".

        E' assim que o CSV pede o modo tabela sem que o gerenciador de abas
        precise conhecer CSV.
        """
        return "texto"

    # -- ajudantes ---------------------------------------------------------

    def comenta_linha(self) -> bool:
        return bool(self.comentario_de_linha)

    def comenta_bloco(self) -> bool:
        return bool(self.comentario_de_bloco)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.nome!r} {self.extensoes}>"
