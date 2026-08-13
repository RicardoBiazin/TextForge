"""Regras de realce: `Regra`, `Contexto` e `RegrasDeRealce`.

Ideia central: cada CONTEXTO compila UM regex, feito da alternancia de todas as
suas regras, e o pintor faz UMA passada de `finditer` por bloco. A alternativa
obvia -- iterar as ~15 regras da linguagem por bloco, cada uma varrendo a linha
inteira -- custa 15 varreduras por linha em vez de uma.

Como se descobre QUAL regra casou: cada regra entra na alternancia dentro de um
grupo de captura proprio, e guardamos o indice absoluto desse grupo. Num casamento,
o grupo nao-None diz a regra. Os grupos INTERNOS de cada regra continuam
funcionando (e' assim que `def (?P<nome>\\w+)` pinta o nome de forma diferente da
palavra-chave), com uma exigencia: dois grupos nomeados do MESMO contexto nao podem
ter o mesmo nome. `Contexto` valida isso na construcao e diz exatamente o que
corrigir -- e' melhor do que reescrever o fonte dos regexes para renomear grupos,
que e' fragil e ilegivel.

REGRA DE SEGURANCA (requisito 35, disponibilidade): nenhum padrao pode ter
quantificador aninhado -- `(a+)+`, `(x*)*`, `(\\w+)*`. Sao a receita do
backtracking catastrofico, e 5 MB numa linha de JS minificado congelariam a thread
da interface. `problemas_de_desempenho()` varre os padroes e o teste falha se
algum aparecer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Quantificador aplicado a um grupo que ja' contem quantificador. Nao pega todos
# os casos patologicos possiveis -- nenhuma heuristica pega --, mas pega os que
# aparecem em regra escrita a mao.
_ANINHADO = re.compile(r"\([^()]*[+*]\)[+*]")


@dataclass(frozen=True)
class Regra:
    """Um padrao e o papel com que ele e' pintado."""

    padrao: re.Pattern[str]
    papel: str
    # Nome do grupo -> papel. Para pintar parte do casamento de outra cor, como o
    # nome da funcao em "def nome".
    papeis_por_grupo: dict[str, str] = field(default_factory=dict)
    # Empilha um contexto ao casar (abrir uma string tripla, entrar em <?php).
    entrar_em: str | None = None
    # Desempilha UM nivel ao casar (fechar a string, ?>).
    sair: bool = False
    # Desempilha ATE' que este contexto seja o topo. Necessario quando a entrada
    # custou mais de um nivel: `<script src=x>` empilha `tag_de_script` e depois
    # `corpo_do_script`, entao `</script>` precisa voltar dois niveis de uma vez.
    # Um `sair` simples deixaria a pilha em `tag_de_script`, e o HTML seguinte
    # seria realcado como atributo de tag.
    voltar_para: str | None = None

    def __post_init__(self) -> None:
        if not self.papel:
            raise ValueError(f"regra sem papel: {self.padrao.pattern!r}")
        quantas = sum(1 for x in (self.entrar_em, self.sair or None,
                                  self.voltar_para) if x)
        if quantas > 1:
            raise ValueError(
                f"regra com mais de uma acao de pilha (entrar_em / sair / "
                f"voltar_para): {self.padrao.pattern!r}")


class Contexto:
    """Um estado do realcador, com as regras validas nele.

    `papel_padrao` pinta o que NAO casa com nenhuma regra. E' o que faz o interior
    de uma string ou de um comentario de bloco ficar todo colorido, e nao apenas
    os delimitadores.
    """

    def __init__(self, nome: str, regras: tuple[Regra, ...],
                 papel_padrao: str | None = None) -> None:
        if not nome:
            raise ValueError("contexto sem nome")
        self.nome = nome
        self.regras = tuple(regras)
        self.papel_padrao = papel_padrao
        self._indices: tuple[int, ...] = ()
        self.combinado = self._combinar()

    def _combinar(self) -> re.Pattern[str] | None:
        if not self.regras:
            return None

        vistos: dict[str, int] = {}
        partes: list[str] = []
        indices: list[int] = []
        proximo = 1                      # o grupo 0 e' o casamento inteiro
        bandeiras = 0

        for i, regra in enumerate(self.regras):
            padrao = regra.padrao
            # As bandeiras vao para o regex COMBINADO. Misturar regras com e sem
            # IGNORECASE no mesmo contexto e' erro de declaracao, e silenciar isso
            # daria realce que funciona em metade das palavras.
            if i == 0:
                bandeiras = padrao.flags
            elif padrao.flags != bandeiras:
                raise ValueError(
                    f"contexto {self.nome!r}: a regra {padrao.pattern!r} usa "
                    f"bandeiras diferentes das anteriores.\n"
                    f"As regras de um contexto entram todas no MESMO regex "
                    f"combinado, e um regex tem um conjunto de bandeiras so'.\n"
                    f"Para uma regra insensivel a caixa dentro de um contexto "
                    f"sensivel, use a flag com ESCOPO: r'(?i:minha|regra)'.")

            for nome_do_grupo in padrao.groupindex:
                if nome_do_grupo in vistos:
                    raise ValueError(
                        f"contexto {self.nome!r}: o grupo (?P<{nome_do_grupo}>) "
                        f"aparece em duas regras. Cada grupo nomeado tem de ser "
                        f"unico no contexto -- renomeie um deles.")
                vistos[nome_do_grupo] = i

            indices.append(proximo)
            partes.append(f"({padrao.pattern})")
            proximo += 1 + padrao.groups

        self._indices = tuple(indices)
        return re.compile("|".join(partes), bandeiras)

    def regra_de(self, casamento: re.Match[str]) -> Regra | None:
        """Qual regra produziu este casamento."""
        for i, indice in enumerate(self._indices):
            if casamento.group(indice) is not None:
                return self.regras[i]
        return None

    def __repr__(self) -> str:
        return f"Contexto({self.nome!r}, {len(self.regras)} regras)"


@dataclass(frozen=True)
class RegrasDeRealce:
    """O conjunto de contextos de uma linguagem, e por qual deles se comeca."""

    inicial: str
    contextos: dict[str, Contexto]

    def __post_init__(self) -> None:
        if self.inicial not in self.contextos:
            raise ValueError(
                f"o contexto inicial {self.inicial!r} nao esta' declarado")
        # Todo destino de `entrar_em` tem de existir: um nome errado faria o
        # realcador entrar num contexto inexistente e estourar dentro do
        # highlightBlock, ou seja, no meio do desenho da tela.
        for contexto in self.contextos.values():
            for regra in contexto.regras:
                for destino, campo in ((regra.entrar_em, "entra em"),
                                       (regra.voltar_para, "volta para")):
                    if destino and destino not in self.contextos:
                        raise ValueError(
                            f"contexto {contexto.nome!r}: a regra "
                            f"{regra.padrao.pattern!r} {campo} "
                            f"{destino!r}, que nao esta' declarado")

    def papeis_usados(self) -> set[str]:
        """Todos os papeis citados. O teste confere que o tema declara todos."""
        papeis: set[str] = set()
        for contexto in self.contextos.values():
            if contexto.papel_padrao:
                papeis.add(contexto.papel_padrao)
            for regra in contexto.regras:
                papeis.add(regra.papel)
                papeis.update(regra.papeis_por_grupo.values())
        return papeis

    def problemas_de_desempenho(self) -> list[str]:
        """Padroes com quantificador aninhado. Vazio e' o unico aceitavel.

        `(a+)+` sobre 5 MB numa linha nao termina em tempo humano, e como o realce
        roda na thread da interface, o programa simplesmente congela. Um JS ou JSON
        minificado numa linha unica e' entrada comum num editor de arquivos
        tecnicos, entao isto nao e' hipotese remota.
        """
        problemas: list[str] = []
        for contexto in self.contextos.values():
            for regra in contexto.regras:
                if _ANINHADO.search(regra.padrao.pattern):
                    problemas.append(
                        f"{contexto.nome}: {regra.padrao.pattern!r}")
        return problemas


def com_prefixo(contextos: dict[str, Contexto],
                prefixo: str) -> dict[str, Contexto]:
    """Renomeia um conjunto de contextos com um prefixo, reescrevendo os saltos.

    E' o mecanismo que faz PHP dentro de HTML, JS em <script> e CSS em <style>
    funcionarem SEM duplicar regra: `html.py` pede os contextos do PHP com o
    prefixo "php", e uma correcao no provedor de PHP vale para os dois.

    Reescrever `entrar_em` e' obrigatorio: uma regra do PHP que entra em
    "comentario" precisa passar a entrar em "php:comentario", senao ela cairia no
    contexto de comentario do HTML.

    `sair` NAO precisa de reescrita: ele desempilha, e a pilha ja' sabe de onde
    veio.
    """
    saida: dict[str, Contexto] = {}
    for nome, contexto in contextos.items():
        regras = tuple(
            Regra(padrao=regra.padrao, papel=regra.papel,
                  papeis_por_grupo=dict(regra.papeis_por_grupo),
                  entrar_em=(f"{prefixo}:{regra.entrar_em}"
                             if regra.entrar_em else None),
                  sair=regra.sair,
                  # `voltar_para` tambem e' renomeado: o destino faz parte do
                  # conjunto que esta' sendo prefixado.
                  voltar_para=(f"{prefixo}:{regra.voltar_para}"
                               if regra.voltar_para else None))
            for regra in contexto.regras)
        novo = f"{prefixo}:{nome}"
        saida[novo] = Contexto(novo, regras, contexto.papel_padrao)
    return saida


# ---------------------------------------------------------------------------
# Ajudantes de declaracao
# ---------------------------------------------------------------------------


def alternativa_de_palavras(palavras, *, limite: bool = True) -> str:
    """Fonte de regex que casa qualquer uma das palavras.

    Ordena da mais longa para a mais curta: numa alternancia, o regex do Python
    para no PRIMEIRO ramo que casa, entao "in" antes de "int" faria "int" nunca
    ser reconhecido inteiro.
    """
    escapadas = sorted((re.escape(p) for p in palavras), key=len, reverse=True)
    corpo = "|".join(escapadas)
    return rf"\b(?:{corpo})\b" if limite else f"(?:{corpo})"


def regra_de_palavras(palavras, papel: str, *,
                      sem_caixa: bool = False) -> Regra:
    """Regra que casa uma lista de palavras.

    `sem_caixa` usa a flag com ESCOPO -- `(?i:...)` -- e nao `re.IGNORECASE` no
    padrao inteiro. A diferenca importa: as regras de um contexto entram todas no
    mesmo regex combinado, que tem UM conjunto de bandeiras, entao uma regra com
    `re.IGNORECASE` no meio de regras sensiveis a caixa e' recusada na construcao.
    Com escopo, a regra e' componivel em qualquer contexto.
    """
    fonte = alternativa_de_palavras(palavras)
    return Regra(re.compile(f"(?i:{fonte})" if sem_caixa else fonte), papel)


# Padroes reaproveitados por varias linguagens. Ficam aqui para uma correcao valer
# para todas -- e para nao haver cinco versoes ligeiramente diferentes de
# "string com escape".
def texto_com_escape(delimitador: str, escape: str = "\\\\") -> str:
    """String de uma linha, com escapes. Sem quantificador aninhado.

    O padrao e' `"(?:\\\\.|[^"\\\\])*"`: alternancia de "escape seguido de
    qualquer coisa" ou "caractere que nao e' o delimitador nem a barra". Nao usa
    `.*?` porque um `.` preguicoso atravessaria o escape do proprio delimitador.
    """
    d = re.escape(delimitador)
    return rf"{d}(?:{escape}.|[^{d}{escape}])*{d}"


NUMERO = (r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
          r"|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b")
IDENTIFICADOR = r"\b[A-Za-z_][A-Za-z0-9_]*\b"
CHAMADA = r"\b[A-Za-z_][A-Za-z0-9_]*(?=\s*\()"
OPERADOR = r"[-+*/%=<>!&|^~?:]+"
PONTUACAO = r"[(){}\[\];,.]"
