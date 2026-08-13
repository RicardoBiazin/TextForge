"""Provedor de YAML.

O nome termina em "_" para nao sombrear o pacote `yaml` (o PyYAML), que esta'
instalado nesta maquina.

A particularidade do YAML e' que a CHAVE nao tem delimitador: ela e' o que vem antes
do ":" no inicio da linha. E o valor nao tem aspas na maioria dos casos, entao
pinta-lo como string seria mentira -- fica com o papel de texto comum, o que e'
justamente o que torna um docker-compose.yml legivel.
"""

from __future__ import annotations

import re

from textforge.editor.indentacao import Indentacao
from textforge.linguagens.base import (NoDeEstrutura, ProvedorDeLinguagem,
                                       RegraDeDobra)
from textforge.realce import regras as r
from textforge.realce.regras import Contexto, Regra, RegrasDeRealce


class ProvedorYaml(ProvedorDeLinguagem):
    nome = "YAML"
    extensoes = (".yaml", ".yml")
    nomes_de_arquivo = ("docker-compose.yml", "docker-compose.yaml",
                        ".gitlab-ci.yml", ".travis.yml", "action.yml",
                        "pubspec.yaml", "_config.yml")
    comentario_de_linha = "#"
    comentario_de_bloco = None
    indentacao_padrao = Indentacao(usa_espacos=True, largura=2)
    # YAML NAO aceita TAB na indentacao -- e' erro de sintaxe. A indentacao padrao
    # com espacos nao e' preferencia, e' exigencia do formato.
    aumenta_indentacao = re.compile(r":\s*$|^\s*-\s*$")

    def __init__(self) -> None:
        self._cache: RegrasDeRealce | None = None

    def regras(self, tema) -> RegrasDeRealce:
        if self._cache is not None:
            return self._cache

        raiz = Contexto("raiz", (
            Regra(re.compile(r"#.*$"), "comentario"),
            # Separador de documento e fim de documento.
            Regra(re.compile(r"^---\s*$|^\.\.\.\s*$"), "preprocessador"),
            # Diretiva: %YAML 1.2
            Regra(re.compile(r"^%\S+.*$"), "preprocessador"),
            # A CHAVE: do inicio da linha (ou depois de "- ") ate' o ":".
            Regra(re.compile(r"^(?P<yl_recuo>\s*(?:-\s+)?)"
                             r"(?P<yl_chave>[^\s:#][^:#\n]*?)(?=\s*:(?:\s|$))"),
                  "chave", papeis_por_grupo={"yl_chave": "chave"}),
            # Marcador de item de lista.
            Regra(re.compile(r"^\s*-(?=\s|$)"), "lista"),
            # Ancora e referencia: &nome e *nome.
            Regra(re.compile(r"[&*][\w-]+"), "variavel"),
            # Tag de tipo: !!str, !Ref
            Regra(re.compile(r"!!?[\w:/.-]+"), "tipo"),
            # Bloco literal e dobrado: | e >
            Regra(re.compile(r"[|>][-+]?\d*\s*$"), "operador"),
            Regra(re.compile(r.texto_com_escape('"')), "texto_literal"),
            Regra(re.compile(r"'(?:[^']|'')*'"), "texto_literal"),
            # Interpolacao das ferramentas: ${VAR}, {{ var }}, $(cmd)
            Regra(re.compile(r"\$\{[^}\n]*\}|\{\{[^}\n]*\}\}|\$\([^)\n]*\)"),
                  "interpolacao"),
            Regra(re.compile(r"(?i:\b(?:true|false|yes|no|on|off|null|~)\b)"),
                  "constante"),
            Regra(re.compile(r"\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b"),
                  "numero"),
            Regra(re.compile(r"[:,\[\]{}]"), "pontuacao"),
        ))
        self._cache = RegrasDeRealce(inicial="raiz", contextos={"raiz": raiz})
        return self._cache

    def dobras(self) -> RegraDeDobra:
        return RegraDeDobra(modo="indentacao")

    def palavras_de_autocomplete(self) -> frozenset[str]:
        return frozenset({"true", "false", "yes", "no", "on", "off", "null"})

    def estrutura(self, texto: str) -> list[NoDeEstrutura]:
        """Chaves aninhadas pela INDENTACAO -- e' a estrutura do YAML."""
        raizes: list[NoDeEstrutura] = []
        pilha: list[tuple[int, NoDeEstrutura]] = []
        padrao = re.compile(r"^(?P<recuo>\s*)(?:-\s+)?"
                            r"(?P<chave>[^\s:#][^:#\n]*?)\s*:(?:\s|$)")

        for numero, linha in enumerate(texto.split("\n")):
            if not linha.strip() or linha.lstrip().startswith("#"):
                continue
            c = padrao.match(linha)
            if not c:
                continue
            recuo = len(c.group("recuo").expandtabs(2))
            no = NoDeEstrutura(rotulo=c.group("chave").strip(), tipo="chave",
                               linha=numero, coluna=c.start("chave"),
                               detalhe=linha.split(":", 1)[-1].strip()[:40])
            while pilha and pilha[-1][0] >= recuo:
                pilha.pop()
            if pilha:
                pilha[-1][1].filhos.append(no)
            else:
                raizes.append(no)
            pilha.append((recuo, no))
        return raizes

    def detectar_por_conteudo(self, amostra: str) -> int:
        linhas = [l for l in amostra.split("\n")[:60]
                  if l.strip() and not l.lstrip().startswith("#")]
        if not linhas:
            return 0
        pontos = 0
        if amostra.lstrip().startswith("---"):
            pontos += 40
        # "chave:" no inicio da linha, seguido de espaco ou fim -- a marca do YAML.
        com_chave = sum(1 for l in linhas
                        if re.match(r"^\s*[^\s:#][^:#]*:(?:\s|$)", l))
        if com_chave:
            pontos += int(50 * com_chave / len(linhas))
        if any(re.match(r"^\s*-\s+\S", l) for l in linhas):
            pontos += 20
        # Chave e chave de abertura sugerem JSON.
        if any("{" in l or "}" in l for l in linhas[:5]):
            pontos -= 25
        return max(0, min(pontos, 100))


PROVEDORES = (ProvedorYaml(),)
