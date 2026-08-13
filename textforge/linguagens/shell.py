"""Provedores de shell: Batch/CMD, PowerShell e Bash.

Sao TRES linguagens diferentes, com comentario diferente (`REM`/`::`, `#`, `#`) e
vocabulario diferente. Um provedor so' para os tres daria realce errado em dois
deles.

Nenhum deles e' executado ao abrir -- requisito 35. O TextForge nao tem nenhum
caminho de codigo que rode o conteudo de um arquivo, e abrir um `.bat` e' apenas
exibi-lo.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce


# ---------------------------------------------------------------------------
# Batch / CMD
# ---------------------------------------------------------------------------

BATCH_COMANDOS = (
    "if else for in do goto call exit set setlocal endlocal echo cd chdir dir "
    "copy xcopy robocopy move del erase rename ren mkdir md rmdir rd type more "
    "find findstr sort pause cls title color start taskkill tasklist sc net "
    "reg attrib icacls where choice timeout ping shift verify pushd popd "
    "assoc ftype chcp").split()

BATCH_OPERADORES = ("equ neq lss leq gtr geq not exist defined errorlevel "
                    "nul").split()


class ProvedorBatch(ProvedorDeLinguagem):
    nome = "Batch"
    extensoes = (".bat", ".cmd")
    comentario_de_linha = "REM"
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache
        raiz = Contexto("raiz", (
            # Batch tem duas formas de comentario, e as duas sao insensiveis a
            # caixa. Flag com escopo porque as outras regras sao sensiveis.
            Regra(re.compile(r"(?i:^\s*(?:rem\b|::).*$)"), "comentario"),
            Regra(re.compile(r"(?i:^\s*@?echo\s+(?:on|off)\s*$)"),
                  "preprocessador"),
            # Rotulo de destino do goto.
            Regra(re.compile(r"^\s*:[\w.-]+\s*$"), "rotulo"),
            Regra(re.compile(r'"[^"\n]*"'), "texto_literal"),
            # Variavel: %VAR%, %1, !VAR! (expansao retardada).
            Regra(re.compile(r"%%?[\w~$*]+%?|![\w]+!"), "variavel"),
            Regra(re.compile(r"(?i:@)"), "operador"),
            r.regra_de_palavras(BATCH_OPERADORES, "palavra_chave_2",
                                sem_caixa=True),
            r.regra_de_palavras(BATCH_COMANDOS, "palavra_chave", sem_caixa=True),
            Regra(re.compile(r"\b\d+\b"), "numero"),
            Regra(re.compile(r"[|&<>()]+"), "operador"),
        ))
        self._cache = RegrasDeRealce(inicial="raiz", contextos={"raiz": raiz})
        return self._cache

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Os rotulos (:nome) -- sao os "blocos" de um .bat."""
        achados = []
        for numero, linha in enumerate(texto.split("\n")):
            c = re.match(r"^\s*:([\w.-]+)\s*$", linha)
            if c:
                achados.append(NoDeEstrutura(rotulo=c.group(1), tipo="rotulo",
                                             linha=numero, coluna=c.start(1)))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"(?im)^\s*@?echo\s+off", amostra):
            pontos += 60
        if re.search(r"(?im)^\s*rem\b", amostra):
            pontos += 25
        if re.search(r"%\w+%", amostra):
            pontos += 20
        if re.search(r"(?im)^\s*goto\s+\w+", amostra):
            pontos += 20
        return min(pontos, 100)


# ---------------------------------------------------------------------------
# PowerShell
# ---------------------------------------------------------------------------

PS_PALAVRAS = (
    "if elseif else switch foreach for while do until break continue return "
    "function filter workflow param begin process end try catch finally throw "
    "trap class enum using namespace module in default exit hidden static").split()

PS_COMANDOS = (
    "Get-ChildItem Get-Content Set-Content Add-Content Get-Item Set-Item "
    "New-Item Remove-Item Copy-Item Move-Item Rename-Item Test-Path Join-Path "
    "Split-Path Resolve-Path Select-Object Where-Object ForEach-Object "
    "Sort-Object Group-Object Measure-Object Format-Table Format-List Out-File "
    "Out-String Write-Host Write-Output Write-Error Write-Warning Write-Verbose "
    "Read-Host Get-Process Stop-Process Start-Process Get-Service Start-Service "
    "Stop-Service Invoke-WebRequest Invoke-RestMethod Invoke-Expression "
    "ConvertTo-Json ConvertFrom-Json Import-Csv Export-Csv Select-String "
    "New-Object Get-Date Start-Sleep Set-Location Get-Location Compress-Archive "
    "Expand-Archive Get-Command Get-Help Get-Member").split()

PS_CONSTANTES = ("$true $false $null $PSScriptRoot $PSVersionTable $_ $args "
                 "$Error $Host $Home $PWD $LASTEXITCODE $?").split()


class ProvedorPowerShell(ProvedorDeLinguagem):
    nome = "PowerShell"
    extensoes = (".ps1", ".psm1", ".psd1", ".ps1xml")
    comentario_de_linha = "#"
    comentario_de_bloco = ("<#", "#>")
    indentacao_padrao = Indentacao(usa_espacos=True, largura=4)
    aumenta_indentacao = re.compile(r"\{\s*$")
    diminui_indentacao = re.compile(r"^\s*\}")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache
        raiz = Contexto("raiz", (
            Regra(re.compile(r"<#"), "comentario", entrar_em="comentario"),
            Regra(re.compile(r"#.*$"), "comentario"),
            # Here-string: @" ... "@ e @' ... '@ (atravessam linhas).
            Regra(re.compile(r"@\""), "texto_literal", entrar_em="here_duplo"),
            Regra(re.compile(r"@'"), "texto_literal", entrar_em="here_simples"),
            Regra(re.compile(r'"(?:`.|[^"`])*"'), "texto_literal"),
            Regra(re.compile(r"'(?:[^']|'')*'"), "texto_literal"),
            # Tipo entre colchetes: [string], [System.IO.Path]
            Regra(re.compile(r"\[[\w.\[\]]+\]"), "tipo"),
            # Parametro: -Recurse, -Force
            Regra(re.compile(r"(?<=\s)-[A-Za-z]\w*"), "atributo"),
            Regra(re.compile(r"(?i:" + "|".join(
                re.escape(c) for c in PS_CONSTANTES) + ")"), "constante"),
            Regra(re.compile(r"\$\{?[\w:]+\}?"), "variavel"),
            r.regra_de_palavras(PS_COMANDOS, "embutida", sem_caixa=True),
            r.regra_de_palavras(PS_PALAVRAS, "palavra_chave", sem_caixa=True),
            # Verbo-Substantivo: qualquer cmdlet, inclusive os que nao listamos.
            Regra(re.compile(r"\b[A-Z][a-z]+-[A-Z]\w+\b"), "chamada"),
            Regra(re.compile(r.NUMERO), "numero"),
            Regra(re.compile(r"\|\||&&|\||[-+*/%=<>!]+"), "operador"),
            Regra(re.compile(r.PONTUACAO), "pontuacao"),
        ))
        comentario = Contexto("comentario", (
            Regra(re.compile(r"#>"), "comentario", sair=True),
        ), papel_padrao="comentario")
        # A here-string do PowerShell fecha com "@ NA COLUNA ZERO -- indentar o
        # fechamento e' erro de sintaxe. O padrao reflete isso.
        here_duplo = Contexto("here_duplo", (
            Regra(re.compile(r'^"@'), "texto_literal", sair=True),
            Regra(re.compile(r"\$\{?[\w:]+\}?"), "interpolacao"),
        ), papel_padrao="texto_literal")
        here_simples = Contexto("here_simples", (
            Regra(re.compile(r"^'@"), "texto_literal", sair=True),
        ), papel_padrao="texto_literal")

        self._cache = RegrasDeRealce(inicial="raiz", contextos={
            "raiz": raiz, "comentario": comentario,
            "here_duplo": here_duplo, "here_simples": here_simples})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="delimitadores")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(PS_PALAVRAS + PS_COMANDOS)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        achados = []
        padrao = re.compile(r"(?i:^\s*(?:function|filter|class)\s+([\w-]+))")
        for numero, linha in enumerate(texto.split("\n")):
            c = padrao.match(linha)
            if c:
                achados.append(NoDeEstrutura(rotulo=c.group(1), tipo="funcao",
                                             linha=numero, coluna=c.start(1)))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.search(r"\$\w+\s*=", amostra):
            pontos += 20
        if re.search(r"\b[A-Z][a-z]+-[A-Z]\w+\b", amostra):
            pontos += 50
        if re.search(r"(?im)^\s*param\s*\(", amostra):
            pontos += 30
        if re.search(r"\$PSScriptRoot|\$true|\$false|\$null", amostra):
            pontos += 25
        return min(pontos, 100)


# ---------------------------------------------------------------------------
# Bash / sh
# ---------------------------------------------------------------------------

SH_PALAVRAS = (
    "if then elif else fi case esac for while until do done function return "
    "break continue in select time coproc local export readonly declare typeset "
    "unset shift eval exec trap source alias unalias set unsetopt").split()

SH_EMBUTIDAS = (
    "echo printf read cd pwd ls cp mv rm mkdir rmdir touch cat head tail grep "
    "sed awk cut sort uniq wc tr find xargs chmod chown ln df du ps kill sleep "
    "test true false exit env which type command getopts basename dirname "
    "mktemp tee curl wget tar gzip gunzip zip unzip ssh scp rsync git").split()


class ProvedorShell(ProvedorDeLinguagem):
    nome = "Shell"
    extensoes = (".sh", ".bash", ".zsh", ".ksh", ".ash", ".bashrc", ".profile",
                 ".zshrc")
    nomes_de_arquivo = (".bashrc", ".bash_profile", ".zshrc", ".profile",
                        "Makefile.am", "configure")
    padroes_de_shebang = ("sh", "bash", "zsh", "ksh", "dash")
    comentario_de_linha = "#"
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    aumenta_indentacao = re.compile(r"\b(?:then|do|in)\s*$|\{\s*$")
    diminui_indentacao = re.compile(r"^\s*(?:fi|done|esac|else|elif|\})\b")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache
        raiz = Contexto("raiz", (
            # O shebang e' a primeira linha, e nao um comentario comum.
            Regra(re.compile(r"^#!.*$"), "preprocessador"),
            Regra(re.compile(r"#.*$"), "comentario"),
            Regra(re.compile(r'"(?:\\.|[^"\\])*"'), "texto_literal"),
            # Aspas SIMPLES no shell nao aceitam escape: '\' e' uma barra literal.
            Regra(re.compile(r"'[^']*'"), "texto_literal"),
            # Variavel: $nome, ${nome}, $1, $@, $?
            Regra(re.compile(r"\$\{[^}\n]*\}|\$[\w@?*#!$-]+"), "variavel"),
            # Substituicao de comando: $(...) e `...`
            Regra(re.compile(r"\$\([^)\n]*\)|`[^`\n]*`"), "interpolacao"),
            # Definicao de funcao: nome() {  ou  function nome
            Regra(re.compile(r"^\s*(?:function\s+)?(?P<sh_nome>[\w-]+)\s*\(\s*\)"),
                  "palavra_chave", papeis_por_grupo={"sh_nome": "definicao"}),
            Regra(re.compile(r"(?<=\s)--?[\w-]+"), "atributo"),
            r.regra_de_palavras(SH_PALAVRAS, "palavra_chave"),
            r.regra_de_palavras(SH_EMBUTIDAS, "embutida"),
            Regra(re.compile(r"\b\d+\b"), "numero"),
            Regra(re.compile(r"\|\||&&|[|&;<>]+|[-+*/%=!]+"), "operador"),
            Regra(re.compile(r"[(){}\[\]]"), "pontuacao"),
        ))
        self._cache = RegrasDeRealce(inicial="raiz", contextos={"raiz": raiz})
        return self._cache

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset(SH_PALAVRAS + SH_EMBUTIDAS)

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        achados = []
        padrao = re.compile(r"^\s*(?:function\s+)?([\w-]+)\s*\(\s*\)")
        for numero, linha in enumerate(texto.split("\n")):
            c = padrao.match(linha)
            if c:
                achados.append(NoDeEstrutura(rotulo=c.group(1), tipo="funcao",
                                             linha=numero, coluna=c.start(1)))
        return achados

    def detectar_por_conteudo(self, amostra: str) -> int:
        pontos = 0
        if re.match(r"^#!.*\b(?:ba|z|k|d)?a?sh\b", amostra):
            pontos += 70
        if re.search(r"(?m)^\s*(?:if|for|while)\b.*(?:then|do)\s*$", amostra):
            pontos += 25
        if re.search(r"(?m)^\s*(?:fi|done|esac)\s*$", amostra):
            pontos += 25
        if re.search(r"\$\{?\w+\}?", amostra):
            pontos += 10
        return min(pontos, 100)


PROVEDORES = (ProvedorBatch(), ProvedorPowerShell(), ProvedorShell())
