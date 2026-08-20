"""Gravacao por PATCH. Este modulo nao importa openpyxl, e nao deve importar.

O que ele faz: abre o .xlsx original, reescreve os bytes SO' das abas que tem
celula editada, e copia todas as outras entradas do ZIP exatamente como vieram --
mesma ordem, mesmo metodo de compressao, mesma data. Graficos, imagens, tabelas
dinamicas, `vbaProject.bin`, formatacao condicional e validacao de dados
sobrevivem porque nunca sao tocados.

O que ele NAO faz, e por que:

  * **Nao regrava a pasta.** `openpyxl.save()` reconstroi o pacote a partir do que
    openpyxl entendeu, e descarta o resto. Ver o docstring de `__init__.py`.
  * **Nao mexe em estilo.** O atributo `s` da celula e' preservado literalmente:
    e' ele que carrega formato de data, moeda e cor. Sem isso, editar uma celula
    de data a transformaria num numero de serie exposto.
  * **Nao insere nem remove linha ou coluna no meio.** Isso deslocaria toda
    referencia, faixa mesclada e formula da pasta. Esta' declarado fora de escopo.

Duas consequencias de sobrescrever uma celula precisam de conserto, e as duas sao
feitas aqui:

  1. As formulas que dependiam dela ficaram com o valor em cache VELHO. Marcar
     `fullCalcOnLoad="1"` em `xl/workbook.xml` faz o Excel recalcular ao abrir.
  2. O `xl/calcChain.xml` e' um indice da ordem de calculo, e citar uma celula que
     deixou de ter formula faz o Excel acusar "conteudo ilegivel". Quando uma
     formula foi tocada, a parte inteira e' REMOVIDA -- o Excel a reconstroi
     sozinho, e essa e' a correcao consagrada.
"""

from __future__ import annotations

import io
import zipfile

from textforge import log_interno
from textforge.planilha import folha_xml, valores
from textforge.planilha.deteccao import PARTE_RELS, PARTE_WORKBOOK
from textforge.planilha.pasta import (Celula, Folha, Pasta, TIPO_BOOL,
                                      TIPO_DATA, TIPO_FORMULA, TIPO_NUMERO,
                                      TIPO_VAZIO)

log = log_interno.obter(__name__)

PARTE_TIPOS = "[Content_Types].xml"
PARTE_CALCCHAIN = "xl/calcChain.xml"

#: Atributos da celula copiados literalmente. `t` fica de fora porque e' o tipo,
#: que o valor novo redefine; `s` e' o mais importante da lista.
ATRIBUTOS_PRESERVADOS = ("s", "cm", "vm", "ph")


class ErroDeGravacao(Exception):
    """Nao da' para gravar esta pasta. A mensagem e' para o usuario."""


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


def montar(pasta: Pasta) -> bytes:
    """Os bytes da planilha com as edicoes aplicadas."""
    if not pasta.alterado:
        return pasta.bytes_originais
    if pasta.somente_leitura:
        raise ErroDeGravacao(pasta.aviso or "planilha em somente leitura")

    novas: dict[str, bytes] = {}
    formula_tocada = False

    with zipfile.ZipFile(io.BytesIO(pasta.bytes_originais)) as origem:
        nomes = set(origem.namelist())
        for folha in pasta.folhas:
            if not folha.sujas:
                continue
            if not folha.editavel:
                raise ErroDeGravacao(
                    f"aba {folha.nome!r}: {folha.motivo_somente_leitura}")
            if folha.parte not in nomes:
                raise ErroDeGravacao(
                    f"aba {folha.nome!r}: {folha.parte} nao esta' no pacote")
            corpo, tocou = _patchear_aba(origem.read(folha.parte), folha)
            novas[folha.parte] = corpo
            formula_tocada = formula_tocada or tocou

        if PARTE_WORKBOOK in nomes:
            novas[PARTE_WORKBOOK] = _forcar_recalculo(origem.read(PARTE_WORKBOOK))

        remover: set[str] = set()
        if formula_tocada and PARTE_CALCCHAIN in nomes:
            remover.add(PARTE_CALCCHAIN)
            if PARTE_TIPOS in nomes:
                novas[PARTE_TIPOS] = _sem_override(origem.read(PARTE_TIPOS),
                                                   "/" + PARTE_CALCCHAIN)
            if PARTE_RELS in nomes:
                novas[PARTE_RELS] = _sem_relacao(origem.read(PARTE_RELS),
                                                 "calcChain.xml")

        saida = _reescrever(origem, novas, remover)

    log.info("planilha gravada: %d parte(s) reescrita(s), %d removida(s)",
             len(novas), len(remover))
    return saida


def _reescrever(origem: zipfile.ZipFile, novas: dict[str, bytes],
                remover: set[str]) -> bytes:
    """Monta o ZIP novo. Ordem, datas e metodo de compressao vem do original.

    Preservar a ORDEM importa: o Excel espera `[Content_Types].xml` primeiro, e
    escrever as entradas por ordem alfabetica ja' foi motivo de pacote recusado.
    """
    destino = io.BytesIO()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as novo:
        for info in origem.infolist():
            if info.filename in remover:
                continue
            dados = novas.get(info.filename)
            if dados is None:
                dados = origem.read(info.filename)
            entrada = zipfile.ZipInfo(info.filename, info.date_time)
            entrada.compress_type = info.compress_type
            entrada.external_attr = info.external_attr
            entrada.internal_attr = info.internal_attr
            entrada.create_system = info.create_system
            entrada.comment = info.comment
            novo.writestr(entrada, dados)
    return destino.getvalue()


# ---------------------------------------------------------------------------
# A aba
# ---------------------------------------------------------------------------


def _patchear_aba(dados: bytes, folha: Folha) -> tuple[bytes, bool]:
    """A aba com as celulas editadas trocadas. `True` se mexeu em formula."""
    inicio, fim, vazio = folha_xml.intervalo_de_sheetdata(dados)

    por_linha: dict[int, dict[int, Celula]] = {}
    for (linha, coluna) in folha.sujas:
        por_linha.setdefault(linha, {})[coluna] = folha.celula(linha, coluna)

    tocou = any(c.tipo == TIPO_FORMULA
                for colunas in por_linha.values() for c in colunas.values())

    if vazio:
        # `<sheetData/>`: nao ha' linha nenhuma para percorrer, entao o elemento
        # e' reaberto ja' com as linhas novas dentro.
        corpo = b"".join(_montar_linha(numero, por_linha[numero])
                         for numero in sorted(por_linha))
        novo = dados[:inicio] + b"<sheetData>" + corpo + b"</sheetData>" + \
            dados[fim:]
        return _ajustar_dimensao(novo, folha), tocou

    pedacos: list[bytes] = [dados[:inicio]]
    cursor = inicio
    pendentes = sorted(por_linha)
    feitas: set[int] = set()
    implicita = 0

    for elemento in folha_xml.percorrer(dados, b"row", inicio, fim):
        numero_bruto = elemento.atributos.get("r")
        numero = int(numero_bruto) if numero_bruto else implicita + 1
        implicita = numero

        pedacos.append(dados[cursor:elemento.inicio])
        # Linha nova cujo numero e' menor que esta entra ANTES: as linhas do
        # `<sheetData>` tem de ficar em ordem crescente, e o Excel acusa o
        # arquivo como ilegivel quando nao ficam.
        for anterior in pendentes:
            if anterior < numero and anterior not in feitas:
                pedacos.append(_montar_linha(anterior, por_linha[anterior]))
                feitas.add(anterior)

        if numero in por_linha:
            corpo, tocou_aqui = _patchear_linha(dados, elemento, numero,
                                                por_linha[numero])
            pedacos.append(corpo)
            tocou = tocou or tocou_aqui
            feitas.add(numero)
        else:
            pedacos.append(dados[elemento.inicio:elemento.fim])
        cursor = elemento.fim

    pedacos.append(dados[cursor:fim])
    for numero in pendentes:
        if numero not in feitas:
            pedacos.append(_montar_linha(numero, por_linha[numero]))
    pedacos.append(dados[fim:])

    return _ajustar_dimensao(b"".join(pedacos), folha), tocou


def _patchear_linha(dados: bytes, linha: folha_xml.Elemento, numero: int,
                    edicoes: dict[int, Celula]) -> tuple[bytes, bool]:
    """Uma `<row>` com as celulas editadas trocadas."""
    if linha.vazia:
        # `<row r="7"/>`: linha declarada sem nenhuma celula. Reabre com as
        # celulas novas dentro, preservando os atributos originais (altura,
        # estilo da linha).
        abertura = dados[linha.inicio:linha.fim_da_abertura - 2].rstrip()
        corpo = b"".join(_montar_celula(numero, coluna, {}, edicoes[coluna])
                         for coluna in sorted(edicoes))
        return abertura + b">" + corpo + b"</row>", False

    pedacos: list[bytes] = []
    cursor = linha.fim_da_abertura
    pendentes = sorted(edicoes)
    feitas: set[int] = set()
    colunas_presentes: list[int] = []
    implicita = 0
    tocou = False

    for celula in folha_xml.percorrer(dados, b"c", linha.fim_da_abertura,
                                      linha.inicio_do_fecho):
        posicao = valores.de_referencia(celula.atributos.get("r", ""))
        coluna = posicao[1] if posicao else implicita + 1
        implicita = coluna

        pedacos.append(dados[cursor:celula.inicio])
        for anterior in pendentes:
            if anterior < coluna and anterior not in feitas:
                pedacos.append(_montar_celula(numero, anterior, {},
                                              edicoes[anterior]))
                colunas_presentes.append(anterior)
                feitas.add(anterior)

        if coluna in edicoes:
            tinha_formula = folha_xml.proxima_tag(
                dados, b"<f", celula.fim_da_abertura, celula.inicio_do_fecho) >= 0
            tocou = tocou or tinha_formula
            pedacos.append(_montar_celula(numero, coluna, celula.atributos,
                                          edicoes[coluna]))
            feitas.add(coluna)
        else:
            pedacos.append(dados[celula.inicio:celula.fim])
        colunas_presentes.append(coluna)
        cursor = celula.fim

    pedacos.append(dados[cursor:linha.inicio_do_fecho])
    for coluna in pendentes:
        if coluna not in feitas:
            pedacos.append(_montar_celula(numero, coluna, {}, edicoes[coluna]))
            colunas_presentes.append(coluna)

    abertura = _ajustar_spans(dados[linha.inicio:linha.fim_da_abertura],
                              colunas_presentes)
    fecho = dados[linha.inicio_do_fecho:linha.fim]
    return abertura + b"".join(pedacos) + fecho, tocou


def _montar_linha(numero: int, edicoes: dict[int, Celula]) -> bytes:
    """Uma `<row>` inteira, para uma linha que ainda nao existia no arquivo.

    Sem `spans`: o atributo e' opcional, e um valor calculado aqui teria de ser
    refeito na proxima edicao. A ausencia faz o Excel deduzir a faixa sozinho.
    """
    corpo = b"".join(_montar_celula(numero, coluna, {}, edicoes[coluna])
                     for coluna in sorted(edicoes))
    return f'<row r="{numero}">'.encode() + corpo + b"</row>"


def _ajustar_spans(abertura: bytes, colunas: list[int]) -> bytes:
    """Refaz o `spans="1:5"` da linha que ganhou coluna.

    `spans` e' so' uma dica de desempenho para o Excel, e e' opcional -- mas
    deixa-lo estreito demais faz a coluna nova nao aparecer ate' o arquivo ser
    reaberto. Linha que nao declarava `spans` continua sem.
    """
    inicio = abertura.find(b"spans=")
    if inicio < 0 or not colunas:
        return abertura
    aspa = abertura[inicio + 6:inicio + 7]
    if aspa not in (b'"', b"'"):
        return abertura
    fechamento = abertura.find(aspa, inicio + 7)
    if fechamento < 0:
        return abertura
    novo = f'spans={aspa.decode()}{min(colunas)}:{max(colunas)}{aspa.decode()}'
    return abertura[:inicio] + novo.encode() + abertura[fechamento + 1:]


# ---------------------------------------------------------------------------
# A celula
# ---------------------------------------------------------------------------


def _montar_celula(linha: int, coluna: int, originais: dict[str, str],
                   celula: Celula) -> bytes:
    """Uma `<c>` inteira, com os atributos originais menos o tipo."""
    referencia = valores.referencia(linha, coluna)

    if celula.tipo == TIPO_VAZIO or not celula.texto:
        # Celula esvaziada: some o valor, FICA o estilo. Remover o `s` junto
        # apagaria a formatacao da coluna inteira uma celula por vez.
        return b"<c " + _atributos(referencia, originais, None) + b"/>"

    if celula.tipo == TIPO_FORMULA:
        # O `<f>` guarda a formula SEM o "=" inicial, e o `<v>` do valor antigo
        # e' descartado: o `fullCalcOnLoad` manda o Excel calcular o novo.
        corpo = b"<f>" + _texto(celula.texto[1:]) + b"</f>"
        return (b"<c " + _atributos(referencia, originais, None) + b">" +
                corpo + b"</c>")

    if celula.tipo == TIPO_BOOL:
        marca = b"1" if celula.texto.strip().upper() in ("VERDADEIRO",
                                                         "TRUE") else b"0"
        return (b"<c " + _atributos(referencia, originais, "b") + b"><v>" +
                marca + b"</v></c>")

    if celula.tipo in (TIPO_NUMERO, TIPO_DATA):
        # A data vira o NUMERO DE SERIE e o `s` original continua: e' o formato
        # numerico do estilo que a faz aparecer como data. `ordenacao` ja' e' o
        # serial, calculado em `pasta.interpretar`.
        numero = celula.ordenacao if isinstance(celula.ordenacao, float) \
            else valores.ler_numero(celula.texto)
        if numero is None:
            raise ErroDeGravacao(f"{referencia}: {celula.texto!r} nao e' numero")
        return (b"<c " + _atributos(referencia, originais, None) + b"><v>" +
                valores.numero_como_texto(numero).encode() + b"</v></c>")

    # Texto: `inlineStr` para nao ter de mexer em `sharedStrings.xml` nem nos
    # contadores `count`/`uniqueCount` dele -- errar esses contadores faz o
    # Excel recusar o arquivo inteiro.
    preserva = b' xml:space="preserve"' if celula.texto != celula.texto.strip() \
        else b""
    return (b"<c " + _atributos(referencia, originais, "inlineStr") +
            b"><is><t" + preserva + b">" + _texto(celula.texto) +
            b"</t></is></c>")


def _atributos(referencia: str, originais: dict[str, str],
               tipo: str | None) -> bytes:
    partes = [f'r="{referencia}"']
    for nome in ATRIBUTOS_PRESERVADOS:
        if nome in originais:
            partes.append(f'{nome}="{_atributo(originais[nome])}"')
    if tipo:
        partes.append(f't="{tipo}"')
    return " ".join(partes).encode("utf-8")


def _texto(valor: str) -> bytes:
    return folha_xml.escapar(valor).encode("utf-8")


def _atributo(valor: str) -> str:
    return folha_xml.escapar(valor).replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Partes vizinhas
# ---------------------------------------------------------------------------


def _ajustar_dimensao(dados: bytes, folha: Folha) -> bytes:
    """Estica o `<dimension ref="A1:D10"/>` quando a aba cresceu.

    Um `dimension` estreito demais faz o Excel ignorar as celulas de fora ao
    desenhar a aba -- o dado esta' no arquivo e nao aparece na tela, que e' o
    pior dos dois mundos.
    """
    inicio = folha_xml.proxima_tag(dados, b"<dimension", 0, len(dados))
    if inicio < 0:
        return dados
    fim = folha_xml.fim_da_tag(dados, inicio)
    atual = folha_xml.atributos(dados, inicio, fim).get("ref", "")
    if not atual:
        return dados

    canto = atual.split(":")[-1]
    posicao = valores.de_referencia(canto)
    linhas = max(folha.linhas, posicao[0] if posicao else 1)
    colunas = max(folha.colunas, posicao[1] if posicao else 1)
    novo = f'<dimension ref="A1:{valores.referencia(linhas, colunas)}"/>'
    return dados[:inicio] + novo.encode("utf-8") + dados[fim:]


def _forcar_recalculo(workbook: bytes) -> bytes:
    """Marca `fullCalcOnLoad="1"` para o Excel recalcular ao abrir.

    Sem isto, uma formula que dependia da celula editada continua exibindo o
    numero antigo -- guardado em `<v>` -- ate' alguem forcar F9. Um total errado
    numa planilha e' exatamente o tipo de erro que passa despercebido.
    """
    inicio = folha_xml.proxima_tag(workbook, b"<calcPr", 0, len(workbook))
    if inicio >= 0:
        fim = folha_xml.fim_da_tag(workbook, inicio)
        atributos = folha_xml.atributos(workbook, inicio, fim)
        atributos["fullCalcOnLoad"] = "1"
        texto = " ".join(f'{n}="{_atributo(v)}"' for n, v in atributos.items())
        return workbook[:inicio] + f"<calcPr {texto}/>".encode() + workbook[fim:]

    # Sem `<calcPr>`: ele tem de entrar na posicao que o esquema exige, logo
    # depois do ultimo destes. Inserir antes de `</workbook>` seria mais simples
    # e produziria um arquivo fora de ordem, que o Excel recusa.
    novo = b'<calcPr calcId="0" fullCalcOnLoad="1"/>'
    for marca in (b"</definedNames>", b"</externalReferences>",
                  b"</functionGroups>", b"</sheets>"):
        posicao = workbook.find(marca)
        if posicao >= 0:
            corte = posicao + len(marca)
            return workbook[:corte] + novo + workbook[corte:]
    return workbook


def _sem_override(tipos: bytes, parte: str) -> bytes:
    """Tira um `<Override PartName="..."/>` do `[Content_Types].xml`."""
    alvo = f'PartName="{parte}"'.encode()
    posicao = tipos.find(alvo)
    if posicao < 0:
        return tipos
    inicio = tipos.rfind(b"<Override", 0, posicao)
    if inicio < 0:
        return tipos
    return tipos[:inicio] + tipos[folha_xml.fim_da_tag(tipos, inicio):]


def _sem_relacao(rels: bytes, sufixo_do_alvo: str) -> bytes:
    """Tira do `.rels` a relacao que aponta para uma parte removida."""
    fim_total = len(rels)
    for relacao in folha_xml.percorrer(rels, b"Relationship", 0, fim_total):
        if relacao.atributos.get("Target", "").endswith(sufixo_do_alvo):
            return rels[:relacao.inicio] + rels[relacao.fim:]
    return rels
