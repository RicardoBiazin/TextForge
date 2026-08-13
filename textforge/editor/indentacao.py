"""Indentacao: deteccao por arquivo, conversao e auto-indent.

Regra do projeto: a indentacao e' detectada POR ARQUIVO e vence a preferencia
global. Abrir um `.py` alheio indentado com 2 espacos e comecar a digitar com 4
porque "a minha configuracao e' 4" e' a forma mais rapida de sujar um diff com
alteracoes que ninguem pediu -- justamente o que o requisito 38 proibe.

Este modulo nao importa Qt: e' logica pura sobre texto, e por isso o
`teste_editor.py` consegue exercitar a deteccao sem subir uma janela.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Larguras aceitas na deteccao. 3 esta' na lista porque aparece em codigo legado
# de verdade, ainda que raro; 5, 6 e 7 sao quase sempre desalinhamento acidental,
# e aceita-los faria uma linha torta redefinir o arquivo inteiro.
LARGURAS_PLAUSIVEIS = (2, 3, 4, 8)

# Quantas linhas olhar. Um arquivo de 500 mil linhas nao fica mais bem detectado
# do que pelas primeiras milhares, e a deteccao roda ao abrir cada arquivo.
LINHAS_PARA_DETECTAR = 5000

_SO_ESPACO = re.compile(r"^[ \t]*")


@dataclass(frozen=True)
class Indentacao:
    usa_espacos: bool = True
    largura: int = 4

    def unidade(self) -> str:
        """O que uma tecla Tab insere."""
        return " " * self.largura if self.usa_espacos else "\t"

    def rotulo(self) -> str:
        """Como aparece na barra de status."""
        return f"{'Espacos' if self.usa_espacos else 'TAB'}: {self.largura}"

    def largura_visual(self, prefixo: str) -> int:
        """Quantas colunas o prefixo ocupa na tela, expandindo os TAB.

        Um TAB nao vale `largura` colunas: vale ate' a proxima parada de
        tabulacao. Num arquivo com TAB e espacos misturados, contar caractere a
        caractere daria a coluna errada na barra de status.
        """
        colunas = 0
        for ch in prefixo:
            if ch == "\t":
                colunas += self.largura - (colunas % self.largura)
            else:
                colunas += 1
        return colunas


def prefixo_de_indentacao(linha: str) -> str:
    """O espaco em branco no inicio da linha, literalmente."""
    return _SO_ESPACO.match(linha).group(0)


def detectar(texto: str, padrao: Indentacao | None = None) -> Indentacao:
    """Descobre a indentacao usada no texto.

    Estrategia:
      1. conta quantas linhas indentadas comecam com TAB e quantas com espaco;
      2. se TAB ganha, e' TAB -- a largura vem do padrao, porque um arquivo com
         TAB nao revela quantas colunas o autor via;
      3. se espaco ganha, olha os AUMENTOS de indentacao entre linhas
         consecutivas e escolhe o mais frequente entre 2, 3, 4 e 8.

    Olhar os aumentos, e nao os valores absolutos, e' o que faz a deteccao
    funcionar em codigo real: num arquivo indentado com 2, ha' muitas linhas com
    4 e 8 espacos (niveis 2 e 4), e o valor absoluto mais comum poderia ser 4.
    """
    base = padrao or Indentacao()
    linhas = texto.split("\n", LINHAS_PARA_DETECTAR)[:LINHAS_PARA_DETECTAR]

    com_tab = 0
    com_espaco = 0
    larguras: list[int] = []          # indentacao em espacos, por linha
    for linha in linhas:
        if not linha.strip():
            continue                  # linha em branco nao indica nada
        prefixo = prefixo_de_indentacao(linha)
        if not prefixo:
            larguras.append(0)
            continue
        if prefixo[0] == "\t":
            com_tab += 1
            larguras.append(-1)       # marca "nao e' espaco", ver abaixo
        else:
            com_espaco += 1
            larguras.append(len(prefixo))

    if com_tab == 0 and com_espaco == 0:
        return base
    if com_tab > com_espaco:
        return Indentacao(usa_espacos=False, largura=base.largura)

    # Aumentos entre linhas consecutivas, ignorando as marcadas com TAB.
    aumentos: dict[int, int] = {}
    anterior = 0
    for atual in larguras:
        if atual < 0:
            continue
        diferenca = atual - anterior
        if diferenca > 0:
            aumentos[diferenca] = aumentos.get(diferenca, 0) + 1
        anterior = atual

    candidatos = {w: n for w, n in aumentos.items() if w in LARGURAS_PLAUSIVEIS}
    if not candidatos:
        # Sem nenhum aumento plausivel: pode ser um arquivo de uma linha, ou um
        # .txt qualquer. Nao inventar -- fica o padrao do usuario.
        return Indentacao(usa_espacos=True, largura=base.largura)

    # Desempate pela MENOR largura: num arquivo indentado com 2, os saltos de 4
    # (dois niveis de uma vez) sao comuns, e escolher 4 estragaria a indentacao
    # de tudo o que fosse digitado depois.
    melhor = max(candidatos.items(), key=lambda par: (par[1], -par[0]))[0]
    return Indentacao(usa_espacos=True, largura=melhor)


# ---------------------------------------------------------------------------
# Conversoes (requisito 3)
# ---------------------------------------------------------------------------


def tab_para_espacos(texto: str, largura: int) -> str:
    """Expande TAB respeitando as paradas de tabulacao.

    `str.expandtabs()` faz exatamente isso e trata cada linha em separado. A
    diferenca para um `replace("\\t", " " * n)` ingenuo aparece em qualquer
    arquivo onde o TAB nao esteja no inicio da linha: o replace desalinha tudo.
    """
    return texto.expandtabs(largura)


def espacos_para_tab(texto: str, largura: int) -> str:
    """Converte espacos em TAB APENAS na indentacao.

    So' no inicio da linha, de proposito: espaco dentro de uma string, de um
    comentario ou de um arquivo de largura fixa e' conteudo, e trocar por TAB
    seria alterar dados.
    """
    if largura <= 0:
        return texto
    saida = []
    for linha in texto.split("\n"):
        prefixo = prefixo_de_indentacao(linha)
        resto = linha[len(prefixo):]
        if not prefixo:
            saida.append(linha)
            continue
        colunas = Indentacao(True, largura).largura_visual(prefixo)
        saida.append("\t" * (colunas // largura)
                     + " " * (colunas % largura) + resto)
    return "\n".join(saida)


# ---------------------------------------------------------------------------
# Indentar e desindentar blocos
# ---------------------------------------------------------------------------


def indentar(linhas: list[str], indentacao: Indentacao) -> list[str]:
    """Acrescenta um nivel. Linha vazia continua vazia.

    Indentar uma linha em branco criaria espaco no fim da linha -- ruido no diff
    e exatamente o que muitos revisores de codigo reclamam.
    """
    unidade = indentacao.unidade()
    return [linha if not linha.strip() else unidade + linha for linha in linhas]


def desindentar(linhas: list[str], indentacao: Indentacao) -> list[str]:
    """Remove um nivel, aceitando TAB e espacos misturados."""
    saida = []
    for linha in linhas:
        if linha.startswith("\t"):
            saida.append(linha[1:])
            continue
        # Remove ate' `largura` espacos, mas nunca mais do que existem.
        quantos = 0
        while quantos < indentacao.largura and quantos < len(linha) \
                and linha[quantos] == " ":
            quantos += 1
        saida.append(linha[quantos:])
    return saida


# ---------------------------------------------------------------------------
# Auto-indent
# ---------------------------------------------------------------------------


def proxima_indentacao(linha_anterior: str, indentacao: Indentacao,
                       aumenta: re.Pattern[str] | None = None,
                       diminui: re.Pattern[str] | None = None) -> str:
    """Prefixo que a linha nova deve receber ao apertar Enter.

    Por padrao, repete a indentacao da linha anterior. Se o provedor da
    linguagem declarar um padrao `aumenta` (o `:` do Python, o `{` do C), soma
    um nivel.

    `diminui` NAO e' usado aqui: ele vale para reindentar a linha ATUAL quando o
    usuario digita `}` ou `else`, que e' um comportamento diferente e mora no
    widget. Fica no parametro para a assinatura ser a mesma nos dois usos.
    """
    prefixo = prefixo_de_indentacao(linha_anterior)
    if aumenta is not None and aumenta.search(linha_anterior):
        prefixo += indentacao.unidade()
    return prefixo
