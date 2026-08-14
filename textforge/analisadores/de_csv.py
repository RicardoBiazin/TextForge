"""Deteccao de dialeto e divisao em registros de um CSV (requisito 6-CSV).

Duas coisas que costumam ser tratadas como triviais e nao sao:

1. O DELIMITADOR. O `csv.Sniffer` sozinho e' fragil: erra em arquivo de uma linha,
   erra quando ha' ponto e virgula DENTRO de aspas, e levanta `csv.Error` em vez de
   devolver palpite. A heuristica propria pontua pela CONSISTENCIA -- a fracao de
   linhas com a MESMA contagem do candidato --, e nao pela frequencia. A diferenca
   aparece num CSV brasileiro com ";" separando 8 colunas e virgulas decimais
   dentro dos valores: por frequencia a virgula ganharia; por consistencia, nao.

2. O REGISTRO NAO E' A LINHA. Um campo entre aspas pode conter quebra de linha, e e'
   comum em CSV exportado de planilha (endereco, observacao). Dividir por "\\n" e'
   o erro classico: ele parte o registro ao meio e a tabela inteira sai deslocada a
   partir dali. `dividir_registros` varre respeitando as aspas.

Tudo aqui trabalha sobre texto ja' decodificado, com "\\n" como quebra -- e' o que o
`Documento` entrega.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from textforge import log_interno

log = log_interno.obter(__name__)

# Na ordem de utilidade nesta maquina: ";" primeiro porque e' o separador do CSV
# brasileiro (o Excel em pt-BR usa ";" porque a virgula e' o decimal).
CANDIDATOS = (";", ",", "\t", "|", ":")

# Quantas linhas olhar para decidir. Mais que isto nao melhora a deteccao e custa.
LINHAS_DE_AMOSTRA = 50

# Fracao minima de linhas que precisam concordar na contagem do delimitador.
CONCORDANCIA_MINIMA = 0.8


@dataclass(frozen=True)
class Dialeto:
    delimitador: str = ";"
    aspas: str = '"'
    tem_cabecalho: bool = True
    colunas: int = 0
    confianca: int = 0
    como_decidiu: str = ""

    @property
    def rotulo_do_delimitador(self) -> str:
        return {";": "ponto e virgula", ",": "virgula", "\t": "TAB",
                "|": "barra vertical", ":": "dois-pontos"}.get(
                    self.delimitador, repr(self.delimitador))

    def descrever(self) -> str:
        cabecalho = "com cabecalho" if self.tem_cabecalho else "sem cabecalho"
        return (f"{self.rotulo_do_delimitador} · {self.colunas} coluna(s) · "
                f"{cabecalho}")


# ---------------------------------------------------------------------------
# Divisao em registros (respeitando aspas)
# ---------------------------------------------------------------------------


def dividir_registros(texto: str, dialeto: Dialeto) -> list[str]:
    """Divide em REGISTROS, e nao em linhas.

    Um campo entre aspas pode conter "\\n"; dividir por linha partiria o registro e
    deslocaria a tabela inteira dali para a frente.

    A juncao com "\\n" reconstroi o texto EXATAMENTE: cada registro carrega as
    proprias quebras internas, e a quebra entre registros e' o separador. E' o que
    garante o round-trip byte a byte quando nada foi editado.
    """
    aspas = dialeto.aspas
    registros: list[str] = []
    atual: list[str] = []
    dentro = False
    i = 0
    n = len(texto)

    while i < n:
        ch = texto[i]
        if dentro:
            if ch == aspas:
                # Aspa DOBRADA e' o escape do CSV: "" continua dentro do campo.
                if i + 1 < n and texto[i + 1] == aspas:
                    atual.append(ch)
                    atual.append(aspas)
                    i += 2
                    continue
                dentro = False
            atual.append(ch)
        elif ch == aspas:
            dentro = True
            atual.append(ch)
        elif ch == "\n":
            registros.append("".join(atual))
            atual.clear()
        else:
            atual.append(ch)
        i += 1

    registros.append("".join(atual))
    return registros


def campos_de(registro: str, dialeto: Dialeto) -> list[str]:
    """Os campos de UM registro."""
    if not registro:
        return [""]
    leitor = csv.reader(io.StringIO(registro), delimiter=dialeto.delimitador,
                        quotechar=dialeto.aspas)
    try:
        return next(leitor, [])
    except csv.Error:
        # Registro malformado (aspas desbalanceadas). Devolver o texto cru numa
        # coluna e' melhor que perder a linha -- o usuario ve o problema e corrige.
        return [registro]


def montar_registro(campos: list[str], dialeto: Dialeto) -> str:
    """Campos -> texto de um registro, com o quoting minimo necessario."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=dialeto.delimitador,
                          quotechar=dialeto.aspas, quoting=csv.QUOTE_MINIMAL,
                          lineterminator="")
    escritor.writerow(campos)
    return saida.getvalue()


# ---------------------------------------------------------------------------
# Deteccao de dialeto
# ---------------------------------------------------------------------------


def _contar_fora_de_aspas(linha: str, delimitador: str, aspas: str) -> int:
    total = 0
    dentro = False
    i = 0
    while i < len(linha):
        ch = linha[i]
        if ch == aspas:
            if dentro and i + 1 < len(linha) and linha[i + 1] == aspas:
                i += 2
                continue
            dentro = not dentro
        elif ch == delimitador and not dentro:
            total += 1
        i += 1
    return total


def _pontuar(linhas: list[str], delimitador: str, aspas: str) -> tuple[int, int]:
    """(pontuacao 0..100, contagem modal) para um candidato a delimitador.

    A pontuacao e' a fracao de linhas com a MESMA contagem, e nao a frequencia do
    caractere. E' o que distingue um separador real de um caractere que aparece
    muito: num CSV com ";" e valores decimais, a virgula aparece mais, mas com
    contagem irregular.
    """
    contagens = [_contar_fora_de_aspas(l, delimitador, aspas) for l in linhas]
    validas = [c for c in contagens if c > 0]
    if not validas:
        return 0, 0

    frequencia: dict[int, int] = {}
    for c in validas:
        frequencia[c] = frequencia.get(c, 0) + 1
    modal, quantas = max(frequencia.items(), key=lambda p: (p[1], p[0]))

    # Exige presenca na maioria das linhas: um delimitador que so' aparece em duas
    # de trinta linhas nao e' o separador do arquivo.
    if len(validas) / len(linhas) < CONCORDANCIA_MINIMA:
        return 0, modal
    consistencia = quantas / len(validas)
    return int(consistencia * 100), modal


def _linhas_de_amostra(texto: str) -> list[str]:
    linhas = []
    for linha in texto.split("\n"):
        if linha.strip():
            linhas.append(linha)
        if len(linhas) >= LINHAS_DE_AMOSTRA:
            break
    return linhas


def _tem_cabecalho(registros: list[list[str]]) -> bool:
    """A primeira linha e' cabecalho?

    Duas evidencias: a primeira linha nao tem nenhum campo NUMERICO, e alguma linha
    seguinte tem numero na MESMA coluna. E' a regra que funciona em arquivo de
    dados de verdade, onde o cabecalho e' texto e os dados tem numero.
    """
    if len(registros) < 2:
        return False
    primeira = registros[0]
    if not primeira or any(e_numero(c) for c in primeira):
        return False
    for coluna in range(len(primeira)):
        for registro in registros[1:6]:
            if coluna < len(registro) and e_numero(registro[coluna]):
                return True
    # Nenhum numero em lugar nenhum: se a primeira linha tem campos mais curtos e
    # sem repeticao, ainda e' provavel que seja cabecalho.
    return all(c.strip() and len(c) < 40 for c in primeira)


_NUMERO = re.compile(r"^\s*[-+]?[\d.,]+\s*$")


def e_numero(campo: str) -> bool:
    """O campo e' numerico? Usado no cabecalho e no alinhamento da grade."""
    return bool(campo.strip()) and bool(_NUMERO.match(campo)) and any(
        c.isdigit() for c in campo)


def chave_de_ordenacao(campo: str, dialeto: Dialeto) -> float | str:
    """Valor para ORDENAR a coluna. `float` quando o campo e' numero.

    Sem isto a grade ordena como texto e "10" vem antes de "9" -- defeito que
    aparece no primeiro clique num cabecalho de coluna numerica.

    O separador decimal e' deduzido, e nao adivinhado:

      * os DOIS separadores presentes -> o ULTIMO e' o decimal. "1.234,56" e
        "1,234.56" ficam certos sem precisar saber a regiao.
      * so' um presente -> o delimitador do arquivo decide. Num CSV separado por
        ";" a virgula e' decimal (e' justamente por isso que o Excel em pt-BR usa
        ";"); num separado por "," a virgula nunca poderia estar solta dentro de um
        numero, entao o ponto e' que e' o decimal.
    """
    texto = campo.strip()
    if not e_numero(texto):
        return campo
    tem_ponto, tem_virgula = "." in texto, "," in texto
    if tem_ponto and tem_virgula:
        decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
    elif tem_virgula:
        decimal = "," if dialeto.delimitador == ";" else "."
    else:
        decimal = "."
    milhar = "," if decimal == "." else "."
    try:
        return float(texto.replace(milhar, "").replace(decimal, "."))
    except ValueError:
        # "1.2.3" e afins: e' texto com cara de numero. Ordenar como texto e'
        # melhor que descartar a linha.
        return campo


def detectar(texto: str, aspas: str = '"') -> Dialeto:
    """Descobre o dialeto. Nunca levanta -- sempre devolve um palpite usavel."""
    linhas = _linhas_de_amostra(texto)
    if not linhas:
        return Dialeto(colunas=0, confianca=0, como_decidiu="arquivo vazio")

    melhor = ";"
    melhor_nota = 0
    melhor_contagem = 0
    for candidato in CANDIDATOS:
        nota, contagem = _pontuar(linhas, candidato, aspas)
        # Desempate pela MAIOR contagem: num arquivo com ";" separando 8 colunas e
        # ":" aparecendo uma vez por linha num horario, os dois sao consistentes,
        # mas o de 8 e' o separador.
        if nota > melhor_nota or (nota == melhor_nota and nota > 0
                                  and contagem > melhor_contagem):
            melhor, melhor_nota, melhor_contagem = candidato, nota, contagem

    como = "consistencia entre as linhas"
    if melhor_nota == 0:
        # Nenhum candidato convence: pode ser um arquivo de uma coluna so'.
        return Dialeto(delimitador=";", aspas=aspas, tem_cabecalho=False,
                       colunas=1, confianca=20,
                       como_decidiu="nenhum delimitador encontrado")

    # O `Sniffer` roda em paralelo: quando ele CONCORDA, a confianca vai a 100.
    try:
        amostra = "\n".join(linhas[:20])
        farejado = csv.Sniffer().sniff(amostra, delimiters="".join(CANDIDATOS))
        if farejado.delimiter == melhor:
            melhor_nota = 100
            como = "consistencia + csv.Sniffer concordam"
    except (csv.Error, TypeError, ValueError):
        # O Sniffer levanta em arquivo de uma linha e em varios casos legitimos.
        # Nao e' erro: a heuristica propria ja' decidiu.
        pass

    dialeto = Dialeto(delimitador=melhor, aspas=aspas, tem_cabecalho=False,
                      colunas=melhor_contagem + 1, confianca=melhor_nota,
                      como_decidiu=como)

    registros = [campos_de(r, dialeto)
                 for r in dividir_registros("\n".join(linhas[:10]), dialeto)]
    registros = [r for r in registros if r and any(c.strip() for c in r)]
    cabecalho = _tem_cabecalho(registros)

    colunas = max((len(r) for r in registros), default=melhor_contagem + 1)
    return Dialeto(delimitador=melhor, aspas=aspas, tem_cabecalho=cabecalho,
                   colunas=colunas, confianca=melhor_nota, como_decidiu=como)


def parece_csv(texto: str) -> bool:
    """Vale a pena oferecer o modo tabela para este conteudo?"""
    dialeto = detectar(texto)
    return dialeto.confianca >= 70 and dialeto.colunas >= 2
