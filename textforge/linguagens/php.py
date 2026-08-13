"""Provedor de PHP.

Um arquivo `.php` e' HTML com blocos de PHP dentro -- e' assim que a linguagem
funciona de verdade: fora de `<?php` tudo e' texto enviado ao navegador. Por isso o
contexto INICIAL aqui e' a raiz do HTML, e nao do PHP, mesmo que o arquivo comece
com `<?php` (nesse caso o `<?php` e' a primeira coisa que casa, e a pilha entra no
contexto do PHP imediatamente).

A barra de status mostra "PHP" porque o PROVEDOR e' PHP, ainda que os contextos
comecem no HTML.

Este modulo importa `html.py`, e nao o contrario: e' o que evita a dependencia
circular. O `contextos_html()` aceita regras extra justamente para receber o
`<?php` daqui.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens import html as html_mod
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce

PALAVRAS_CHAVE = (
    "abstract and array as break callable case catch class clone const continue "
    "declare default do echo else elseif empty enddeclare endfor endforeach endif "
    "endswitch endwhile enum extends final finally fn for foreach function global "
    "goto if implements include include_once instanceof insteadof interface isset "
    "list match namespace new or print private protected public readonly require "
    "require_once return static switch throw trait try unset use var while xor "
    "yield").split()

CONSTANTES = ("true false null TRUE FALSE NULL PHP_EOL PHP_INT_MAX PHP_VERSION "
              "__LINE__ __FILE__ __DIR__ __FUNCTION__ __CLASS__ __METHOD__ "
              "__NAMESPACE__").split()

TIPOS = ("int float string bool array object mixed void never iterable self "
         "parent static callable null false true").split()

EMBUTIDAS = (
    "count strlen str_replace substr strpos sprintf printf implode explode "
    "array_map array_filter array_keys array_values array_merge in_array "
    "json_encode json_decode var_dump print_r isset unset die exit "
    "file_get_contents file_put_contents fopen fclose fgets preg_match "
    "preg_replace preg_split date time mktime number_format htmlspecialchars "
    "trim ltrim rtrim strtolower strtoupper ucfirst is_array is_null is_string "
    "is_numeric intval floatval strval").split()


def contextos_php() -> dict[str, Contexto]:
    """Contextos do CODIGO PHP (sem o HTML em volta)."""
    raiz = Contexto("raiz", (
        # O fechamento vem primeiro: "?>" tem de vencer qualquer regra de codigo.
        Regra(re.compile(r"\?>"), "preprocessador", sair=True),
        Regra(re.compile(r"/\*"), "comentario", entrar_em="comentario"),
        Regra(re.compile(r"//.*$"), "comentario"),
        Regra(re.compile(r"#(?!\[).*$"), "comentario"),   # "#" mas nao "#[Attr]"
        Regra(re.compile(r"#\[[^\]\n]*\]"), "decorador"),  # atributo do PHP 8
        # Heredoc e nowdoc: <<<SQL ... SQL;  Atravessam linhas.
        Regra(re.compile(r"<<<'?\"?(?P<php_here>[A-Za-z_]\w*)'?\"?"),
              "texto_literal", papeis_por_grupo={"php_here": "tipo"},
              entrar_em="heredoc"),
        # String com aspas duplas: aceita interpolacao de variavel.
        Regra(re.compile(r.texto_com_escape('"')), "texto_literal"),
        Regra(re.compile(r.texto_com_escape("'")), "texto_literal"),
        Regra(re.compile(r"\b(?:function|class|interface|trait|enum)\s+"
                         r"(?P<php_nome>\w+)"),
              "palavra_chave", papeis_por_grupo={"php_nome": "definicao"}),
        # A variavel do PHP e' $nome: sempre visivel, sempre no mesmo papel.
        Regra(re.compile(r"\$this\b"), "pseudo_variavel"),
        Regra(re.compile(r"\$[A-Za-z_]\w*"), "variavel"),
        Regra(re.compile(r"->\s*\w+"), "chamada"),
        Regra(re.compile(r"::\s*\w+"), "chamada"),
        Regra(re.compile(r.NUMERO), "numero"),
        r.regra_de_palavras(CONSTANTES, "constante"),
        r.regra_de_palavras(TIPOS, "tipo"),
        r.regra_de_palavras(PALAVRAS_CHAVE, "palavra_chave"),
        r.regra_de_palavras(EMBUTIDAS, "embutida"),
        Regra(re.compile(r.CHAMADA), "chamada"),
        Regra(re.compile(r"=>|->|::"), "operador"),
        Regra(re.compile(r.OPERADOR), "operador"),
        Regra(re.compile(r.PONTUACAO), "pontuacao"),
    ))
    comentario = Contexto("comentario", (
        Regra(re.compile(r"\*/"), "comentario", sair=True),
    ), papel_padrao="comentario")
    # O heredoc termina numa linha que so' tem o rotulo. Nao ha' como validar QUAL
    # rotulo dentro de um regex por bloco (o pintor nao guarda o texto do
    # casamento), entao aceitamos qualquer identificador sozinho na linha.
    # Consequencia pratica: dois heredocs de rotulos diferentes aninhados seriam
    # fechados pelo primeiro rotulo -- construcao que praticamente nao existe.
    heredoc = Contexto("heredoc", (
        Regra(re.compile(r"^\s*[A-Za-z_]\w*\s*;?\s*$"), "texto_literal",
              sair=True),
        Regra(re.compile(r"\$[A-Za-z_]\w*|\{\$[^}\n]*\}"), "interpolacao"),
    ), papel_padrao="texto_literal")
    return {"raiz": raiz, "comentario": comentario, "heredoc": heredoc}


class ProvedorPhp(ProvedorDeLinguagem):
    nome = "PHP"
    extensoes = (".php", ".php3", ".php4", ".php5", ".php7", ".php8", ".phtml",
                 ".phps", ".inc")
    padroes_de_shebang = ("php",)
    comentario_de_linha = "//"
    comentario_de_bloco = ("/*", "*/")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)
    aumenta_indentacao = re.compile(r"[{(\[]\s*$|:\s*$")
    diminui_indentacao = re.compile(r"^\s*[})\]]|^\s*(?:else|elseif|endif)\b")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        # As regras que abrem PHP entram no INICIO da raiz do HTML: "<?php" tem de
        # ser testado antes da regra de tag, senao casaria como uma tag "?php".
        do_php = r.com_prefixo(contextos_php(), "php")
        abre_php = (
            Regra(re.compile(r"<\?php\b|<\?=|<\?(?!xml)"), "preprocessador",
                  entrar_em="php:raiz"),
        )
        contextos = html_mod.contextos_html(extras=abre_php)
        contextos.update(do_php)

        # O contexto inicial e' o do HTML: fora de <?php, um .php e' texto enviado
        # ao navegador. E' assim que a linguagem funciona.
        self._cache = RegrasDeRealce(inicial="raiz", contextos=contextos)
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(PALAVRAS_CHAVE + CONSTANTES + TIPOS + EMBUTIDAS)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Classes, interfaces, traits, funcoes e metodos (requisito 11-PHP).

        Ignora o que esta' dentro de <script> e <style>: num arquivo .php ha'
        JavaScript, e `function formatar(...)` do JS apareceria como METODO da
        ultima classe PHP -- que e' errado de duas formas ao mesmo tempo.
        """
        raizes: list[NoDeEstrutura] = []
        atual: NoDeEstrutura | None = None
        fora_do_php = re.compile(r"(?i:<(script|style)\b)")
        fim_do_bloco = re.compile(r"(?i:</(script|style)\s*>)")
        dentro_de_outra_linguagem = False
        tipo_de_classe = re.compile(
            r"^\s*(?:abstract\s+|final\s+)*(?P<tipo>class|interface|trait|enum)"
            r"\s+(?P<nome>\w+)")
        funcao = re.compile(
            r"^(?P<recuo>\s*)(?:(?:public|protected|private|static|abstract|final"
            r"|readonly)\s+)*function\s+&?\s*(?P<nome>\w+)")

        for numero, linha in enumerate(texto.split("\n")):
            if dentro_de_outra_linguagem:
                if fim_do_bloco.search(linha):
                    dentro_de_outra_linguagem = False
                continue
            if fora_do_php.search(linha) and not fim_do_bloco.search(linha):
                dentro_de_outra_linguagem = True
                continue

            c = tipo_de_classe.match(linha)
            if c:
                atual = NoDeEstrutura(rotulo=c.group("nome"),
                                      tipo="classe", linha=numero,
                                      coluna=c.start("nome"),
                                      detalhe=c.group("tipo"))
                raizes.append(atual)
                continue
            c = funcao.match(linha)
            if c:
                dentro = bool(c.group("recuo")) and atual is not None
                no = NoDeEstrutura(rotulo=c.group("nome"),
                                   tipo="metodo" if dentro else "funcao",
                                   linha=numero, coluna=c.start("nome"))
                if dentro:
                    atual.filhos.append(no)
                else:
                    raizes.append(no)
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        if "<?php" in amostra[:500] or amostra.lstrip().startswith("<?php"):
            return 95
        pontos = 0
        if re.search(r"<\?(?:php|=)", amostra):
            pontos += 60
        if re.search(r"\$\w+\s*=", amostra):
            pontos += 20
        if re.search(r"->\w+\(|::\w+\(", amostra):
            pontos += 15
        if re.search(r"\becho\b|\bfunction\s+\w+\s*\(", amostra):
            pontos += 15
        return min(pontos, 100)


PROVEDORES = (ProvedorPhp(),)
