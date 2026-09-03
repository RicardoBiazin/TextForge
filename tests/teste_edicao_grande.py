"""Edicao por linha em arquivo grande (etapa 14).

    .\\.venv\\Scripts\\python.exe tests\\teste_edicao_grande.py

Tres testes carregam esta suite, e vale saber quais antes de mexer em qualquer
coisa em `grande/edicao.py` ou `grande/gravacao.py`:

1. **Sem edicao, salvar devolve o arquivo BYTE A BYTE** -- inclusive CRLF, fim
   de linha misto e ausencia de quebra final. E' o requisito 38 no nivel do
   arquivo grande.
2. **A memoria nao acompanha o tamanho do arquivo.** Editar e' O(edicoes). A
   primeira versao guardava um instantaneo da lista de trechos por operacao e
   MEDIU 800 MB com 10 mil edicoes num arquivo de 59 MB; foi este teste que
   pegou.
3. **Editar com o indice INCOMPLETO** continua certo depois que a indexacao
   termina -- a invariante do trecho aberto, descrita no cabecalho de
   `grande/edicao.py`.

As fixtures aqui sao pequenas (poucos MB) de proposito: o arquivo de 200 MB
continua so' em `teste_indice_grande.py`, que ja' paga esse custo. O que se mede
aqui e' comportamento, e ele nao muda com o tamanho.
"""

from __future__ import annotations

import os
import re
import sys

from ajudantes import (checa, checa_igual, checa_levanta, memoria_privada_mb,
                       pasta_temporaria, preparar_qt, resumir, secao)

# ANTES de qualquer import do projeto que arraste Qt.
TEM_QT = preparar_qt()

from textforge import arquivos                                  # noqa: E402
from textforge.fonte import FonteDeArquivo                      # noqa: E402
from textforge.grande import gravacao                           # noqa: E402
from textforge.grande.edicao import FonteEditavel               # noqa: E402


# ===========================================================================
# Ajudantes
# ===========================================================================


def montar(pasta, nome: str, conteudo: bytes):
    """(caminho, FonteDeArquivo ja' indexada) para um conteudo literal."""
    alvo = pasta / nome
    alvo.write_bytes(conteudo)
    fonte = FonteDeArquivo(alvo)
    while not fonte.indexacao_completa:
        fonte.indexar()
    return alvo, fonte


def editavel(pasta, nome: str, conteudo: bytes):
    alvo, fonte = montar(pasta, nome, conteudo)
    return alvo, FonteEditavel(fonte)


def gerar(pasta, nome: str, linhas: int, molde: str = "registro {n:012d};valor\n"):
    alvo = pasta / nome
    with open(alvo, "wb", buffering=1024 * 1024) as f:
        for lote in range(0, linhas, 50_000):
            f.write(b"".join(molde.format(n=i).encode()
                             for i in range(lote, min(lote + 50_000, linhas))))
    return alvo


# ===========================================================================
# 1. Requisito 38: sem edicao, o arquivo sai identico
# ===========================================================================


CASOS = (
    ("lf", b"a\nb\nc\n"),
    ("sem quebra final", b"a\nb\nc"),
    ("crlf", b"a\r\nb\r\nc\r\n"),
    ("eol misto", b"a\r\nb\nc\r\n"),
    ("linha vazia no meio", b"a\n\nc\n"),
    ("uma linha so", b"linha unica"),
    ("so quebras", b"\n\n\n"),
)


def testar_ida_e_volta() -> None:
    secao("Sem edicao, o arquivo sai IDENTICO")

    with pasta_temporaria() as tmp:
        for rotulo, conteudo in CASOS:
            alvo, fonte = editavel(tmp, f"{rotulo}.txt".replace(" ", "_"),
                                   conteudo)
            checa(not fonte.alterado, f"{rotulo}: abrir nao suja nada")
            gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
            checa_igual(alvo.read_bytes(), conteudo,
                        f"*** {rotulo}: salvar sem editar devolve o arquivo "
                        f"byte a byte ***")

        # Ler tudo tambem nao pode sujar: pintar a tela chama `faixa()` o tempo
        # todo, e um `alterado` que ficasse True por leitura marcaria o
        # documento como modificado so' por ter sido olhado.
        alvo, fonte = editavel(tmp, "ler.txt", b"a\nb\nc\n")
        fonte.faixa(0, 99)
        checa(not fonte.alterado, "e percorrer todas as linhas tambem nao suja")


def testar_preservacao_do_eol() -> None:
    secao("O que nao foi editado mantem o proprio fim de linha")

    with pasta_temporaria() as tmp:
        # A linha 1 e' editada; as linhas 0 e 2 continuam com o CRLF delas,
        # embora o EOL do documento seja LF. As partes intocadas sao COPIADAS
        # como bytes, e por isso nem precisam ser entendidas.
        alvo, fonte = editavel(tmp, "misto.txt", b"a\r\nb\nc\r\n")
        fonte.substituir(1, "B")
        gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
        checa_igual(alvo.read_bytes(), b"a\r\nB\nc\r\n",
                    "*** o CRLF das linhas intocadas sobrevive a uma edicao no "
                    "meio (elas sao copiadas como bytes) ***")

        alvo, fonte = editavel(tmp, "sem_final.txt", b"a\nb")
        fonte.inserir(2, "Z")
        gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
        checa_igual(alvo.read_bytes(), b"a\nb\nZ",
                    "acrescentar depois de um arquivo sem quebra final emenda "
                    "a quebra que faltava")

        alvo, fonte = editavel(tmp, "acento.txt", "acao\ncoracao\n".encode("cp1252"))
        fonte.substituir(0, "ação")
        gravacao.gravar(alvo, fonte, eol="\n", codec="cp1252")
        checa_igual(alvo.read_bytes(), "ação\ncoracao\n".encode("cp1252"),
                    "a linha editada e' gravada na codificacao do documento, e "
                    "nao em UTF-8")


# ===========================================================================
# 2. Operacoes
# ===========================================================================


def testar_operacoes() -> None:
    secao("Substituir, inserir, remover, duplicar")

    with pasta_temporaria() as tmp:
        base = b"".join(f"L{i}\n".encode() for i in range(10))
        alvo, fonte = editavel(tmp, "ops.txt", base)
        original = [f"L{i}" for i in range(10)] + [""]
        checa_igual(fonte.faixa(0, 99), original, "leitura antes de editar")

        checa(fonte.substituir(3, "TRES"), "substituir devolve True")
        checa(not fonte.substituir(3, "TRES"),
              "*** redigitar o MESMO texto nao marca alteracao (senao o "
              "documento ficaria sujo por um Enter sem edicao) ***")
        checa_igual(fonte.linha(3), "TRES", "e a linha mudou")

        fonte.inserir(0, "TOPO")
        checa_igual(fonte.linha(0), "TOPO", "inserir no comeco")
        checa_igual(fonte.linha(1), "L0", "e empurra o resto")

        fonte.remover(1)
        checa_igual(fonte.linha(1), "L1", "remover tira a linha certa")

        fonte.duplicar(0)
        checa_igual(fonte.faixa(0, 2), ["TOPO", "TOPO"], "duplicar")

        total = fonte.total_de_linhas()
        fonte.inserir(total, "FIM")
        checa_igual(fonte.linha(total), "FIM", "inserir no fim do documento")

        checa_levanta(IndexError, fonte.remover,
                      "operar numa linha inexistente levanta em vez de "
                      "corromper em silencio", 10_000)


def testar_desfazer() -> None:
    secao("Desfazer e refazer")

    with pasta_temporaria() as tmp:
        base = b"".join(f"L{i}\n".encode() for i in range(20))
        alvo, fonte = editavel(tmp, "undo.txt", base)
        original = fonte.faixa(0, 99)

        fonte.substituir(2, "X")
        fonte.inserir(5, "Y")
        fonte.remover(9)
        fonte.duplicar(1)
        depois = fonte.faixa(0, 99)
        checa(fonte.pode_desfazer, "ha' o que desfazer")

        for _ in range(4):
            fonte.desfazer()
        checa_igual(fonte.faixa(0, 99), original,
                    "*** desfazer tudo devolve o documento IDENTICO ao "
                    "original ***")
        checa(not fonte.alterado, "e o documento deixa de estar alterado")
        checa(not fonte.pode_desfazer, "a pilha esvaziou")

        for _ in range(4):
            fonte.refazer()
        checa_igual(fonte.faixa(0, 99), depois, "refazer tudo volta ao editado")

        # Uma edicao nova invalida o refazer: manter a lista produziria um
        # "refazer" que costura dois futuros diferentes.
        fonte.desfazer()
        fonte.substituir(0, "NOVO RUMO")
        checa(not fonte.pode_refazer,
              "*** editar depois de desfazer descarta o que havia para "
              "refazer ***")

        gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
        conferencia = FonteDeArquivo(alvo)
        while not conferencia.indexacao_completa:
            conferencia.indexar()
        checa_igual(conferencia.linha(0), "NOVO RUMO",
                    "e o disco recebe o resultado depois de desfazer/refazer")
        conferencia.fechar()


# ===========================================================================
# 3. A invariante do trecho aberto
# ===========================================================================


def testar_indice_incompleto() -> None:
    secao("Editar com a indexacao ainda em curso")

    with pasta_temporaria() as tmp:
        alvo = gerar(tmp, "crescendo.txt", 50_000)
        fonte_bruta = FonteDeArquivo(alvo)
        fonte_bruta.indexar(8192)        # so' um pedacinho
        conhecidas = fonte_bruta.total_de_linhas()
        checa(conhecidas < 50_000,
              f"o indice comeca incompleto ({conhecidas} de 50.001 linhas)")

        fonte = FonteEditavel(fonte_bruta)
        fonte.substituir(10, "EDITADA CEDO")
        fonte.inserir(5, "INSERIDA CEDO")

        while not fonte_bruta.indexacao_completa:
            fonte_bruta.indexar(64 * 1024)

        checa_igual(fonte.total_de_linhas(), fonte_bruta.total_de_linhas() + 1,
                    "*** o total cresce com a indexacao mesmo depois de editar: "
                    "e' a invariante do trecho ABERTO ***")
        checa_igual(fonte.linha(5), "INSERIDA CEDO", "a insercao ficou no lugar")
        checa_igual(fonte.linha(11), "EDITADA CEDO", "e a edicao tambem")
        checa_igual(fonte.linha(49_999), "registro 000000049998;valor",
                    "e as linhas indexadas DEPOIS da edicao saem certas")

        abertos = [t for t in fonte._trechos if t.aberto]
        checa(len(abertos) == 1 and fonte._trechos[-1].aberto,
              "*** ha' exatamente UM trecho aberto, e ele e' o ultimo ***")

        gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
        conferencia = FonteDeArquivo(alvo)
        while not conferencia.indexacao_completa:
            conferencia.indexar()
        checa_igual(conferencia.total_de_linhas(), 50_002,
                    "e o arquivo gravado tem o numero de linhas esperado")
        checa_igual(conferencia.linha(5), "INSERIDA CEDO", "com o conteudo certo")
        conferencia.fechar()


# ===========================================================================
# 4. Memoria
# ===========================================================================


def testar_memoria() -> None:
    secao("A memoria acompanha as EDICOES, e nao o tamanho do arquivo")

    with pasta_temporaria() as tmp:
        alvo = gerar(tmp, "memoria.txt", 1_000_000)
        mb = alvo.stat().st_size / (1024 * 1024)
        fonte_bruta = FonteDeArquivo(alvo)
        while not fonte_bruta.indexacao_completa:
            fonte_bruta.indexar(8 * 1024 * 1024)

        base = memoria_privada_mb()
        fonte = FonteEditavel(fonte_bruta)
        for k in range(5_000):
            fonte.substituir(k * 11, f"EDITADA {k}")
        gasto = memoria_privada_mb() - base

        checa(gasto < 30,
              f"*** 5 mil edicoes num arquivo de {mb:.0f} MB custaram "
              f"{gasto:.1f} MB de RAM (teto 30) -- a versao que guardava um "
              f"instantaneo por operacao gastava 800 MB ***")

        antes_de_gravar = memoria_privada_mb()
        gravacao.gravar(alvo, fonte, eol="\n", codec="utf-8")
        pico = memoria_privada_mb() - antes_de_gravar
        checa(pico < 40,
              f"*** e gravar {mb:.0f} MB custou {pico:.1f} MB de pico (teto 40): "
              f"os trechos intocados vao do mmap para o disco sem virar str ***")

        conferencia = FonteDeArquivo(alvo)
        while not conferencia.indexacao_completa:
            conferencia.indexar(8 * 1024 * 1024)
        checa_igual(conferencia.linha(0), "EDITADA 0", "o disco recebeu a 1a")
        checa_igual(conferencia.linha(11), "EDITADA 1", "e a 2a")
        checa_igual(conferencia.linha(1), "registro 000000000001;valor",
                    "e o que nao foi editado continua igual")
        conferencia.fechar()


# ===========================================================================
# 5. Nao sobrescrever alteracao externa
# ===========================================================================


def testar_alteracao_externa() -> None:
    secao("Alteracao externa em arquivo grande e' detectada")

    with pasta_temporaria() as tmp:
        grande = tmp / "vigiado.bin"
        tamanho = arquivos.LIMITE_PARA_HASH + 2 * 1024 * 1024
        grande.write_bytes(b"A" * tamanho)
        info = grande.stat()

        antes = arquivos.Assinatura.de_caminho(grande, amostrar=True)
        checa(antes.sha256 == "",
              "acima de 8 MB nao ha' sha256 (ler o arquivo inteiro custaria "
              "mais que a gravacao)")
        checa(bool(antes.amostra), "mas ha' a assinatura por amostra das pontas")

        # Outro programa reescreve o inicio PRESERVANDO tamanho e data.
        with open(grande, "r+b") as f:
            f.seek(0)
            f.write(b"REESCRITO POR OUTRO PROGRAMA")
        os.utime(grande, ns=(info.st_atime_ns, info.st_mtime_ns))

        sem_amostra = arquivos.Assinatura.de_caminho(grande)
        com_amostra = arquivos.Assinatura.de_caminho(grande, amostrar=True)
        checa(antes.compativel_com(sem_amostra),
              "so' tamanho + data NAO detecta (era o buraco: gravar por cima "
              "apagaria a alteracao alheia em silencio)")
        checa(not antes.compativel_com(com_amostra),
              "*** a amostra DETECTA, e a gravacao pode recusar (requisito 27) ***")
        checa("mesmo tamanho e data" in antes.descrever_diferenca(com_amostra),
              "e a mensagem diz exatamente o que aconteceu")

        # E o fim do arquivo tambem.
        outro = tmp / "fim.bin"
        outro.write_bytes(b"B" * tamanho)
        i2 = outro.stat()
        a2 = arquivos.Assinatura.de_caminho(outro, amostrar=True)
        with open(outro, "r+b") as f:
            f.seek(tamanho - 64)
            f.write(b"FIM TROCADO")
        os.utime(outro, ns=(i2.st_atime_ns, i2.st_mtime_ns))
        b2 = arquivos.Assinatura.de_caminho(outro, amostrar=True)
        checa(not a2.compativel_com(b2), "alteracao no FIM tambem e' detectada")
        checa(b2.compativel_com(arquivos.Assinatura.de_caminho(outro,
                                                               amostrar=True)),
              "e um arquivo intocado nao da' falso positivo")


def testar_espaco_em_disco() -> None:
    secao("Falta de espaco e' avisada ANTES de escrever")

    with pasta_temporaria() as tmp:
        alvo, fonte = editavel(tmp, "espaco.txt", b"a\nb\n")
        checa_levanta(
            gravacao.SemEspaco, gravacao.conferir_espaco,
            "*** conferir o espaco ANTES: descobrir que faltou disco depois de "
            "escrever 200 MB e' o pior momento possivel ***",
            alvo, 10 ** 15)
        gravacao.conferir_espaco(alvo, 1024)
        checa(True, "e um arquivo que cabe passa sem reclamar")


# ===========================================================================
# 6. Documento e visor
# ===========================================================================


def testar_documento() -> None:
    secao("Documento: habilitar, editar, salvar")

    from textforge.documento import MODO_GRANDE, Documento

    with pasta_temporaria() as tmp:
        alvo = gerar(tmp, "doc.txt", 200_000)
        antes = alvo.read_bytes()
        cfg = {"limite_texto_mb": 1}

        doc = Documento.abrir(alvo, cfg)
        checa_igual(doc.modo, MODO_GRANDE, "abre em modo de arquivo grande")
        checa(doc.somente_leitura,
              "*** e abre SOMENTE LEITURA: a edicao e' um ato do usuario, nao "
              "o estado inicial ***")
        checa(not doc.edicao_grande_ligada, "a edicao comeca desligada")
        checa_levanta(PermissionError, doc.bytes_para_salvar,
                      "*** bytes_para_salvar() RECUSA um arquivo grande: sem "
                      "isso ele leria o QTextDocument vazio e gravaria um "
                      "arquivo de zero byte ***")
        checa_levanta(PermissionError, doc.salvar_como,
                      "e 'Salvar como' sem habilitar a edicao tambem recusa "
                      "(era um defeito latente: gravava arquivo vazio)",
                      str(tmp / "copia.txt"))

        checa(doc.habilitar_edicao_grande(), "habilitar edicao funciona")
        checa(not doc.somente_leitura, "e o documento deixa de ser so' leitura")
        checa(doc.edicao_grande_ligada, "a fonte agora e' editavel")

        while not doc.fonte_grande.indexacao_completa:
            doc.fonte_grande.indexar(8 * 1024 * 1024)

        doc.fonte_grande.substituir(7, "SETE EDITADA")
        checa(doc.fonte_grande.alterado, "a edicao ficou registrada")
        doc.salvar()
        checa(not doc.modificado, "depois de salvar, nao ha' pendencia")
        checa(not doc.fonte_grande.alterado,
              "*** e os trechos sao zerados: sem isso eles apontariam para "
              "offsets do arquivo ANTIGO na proxima gravacao ***")

        depois = alvo.read_bytes()
        checa(depois != antes, "o arquivo mudou no disco")

        # Ctrl+S sem ter editado nada NAO pode reescrever o arquivo. Foi um
        # teste com o executavel de verdade que pegou isto: salvar logo depois
        # de habilitar a edicao regravava 40 MB e registrava "0 edicoes".
        marca = alvo.stat().st_mtime_ns
        doc.salvar()
        checa_igual(alvo.stat().st_mtime_ns, marca,
                    "*** salvar sem edicao pendente nao toca no arquivo: "
                    "reescrever 240 MB a toa mexeria ate' na data, e o backup "
                    "acharia que o arquivo mudou ***")
        checa(b"SETE EDITADA" in depois, "com o texto novo")
        checa_igual(len(depois.split(b"\n")), len(antes.split(b"\n")),
                    "e o numero de linhas nao mudou")

        # Salvar de novo, depois de outra edicao, nao pode reverter a primeira.
        while not doc.fonte_grande.indexacao_completa:
            doc.fonte_grande.indexar(8 * 1024 * 1024)
        doc.fonte_grande.substituir(9, "NOVE EDITADA")
        doc.salvar()
        final = alvo.read_bytes()
        checa(b"SETE EDITADA" in final and b"NOVE EDITADA" in final,
              "*** a segunda gravacao preserva a primeira edicao ***")
        doc.fechar()


def testar_visor() -> None:
    secao("Visor: o campo sobreposto")

    from textforge.documento import Documento
    from textforge.interface import tema as tmod
    from textforge.interface.abas import Aba
    from textforge.linguagens import carregar_embutidos

    carregar_embutidos()
    with pasta_temporaria() as tmp:
        alvo = gerar(tmp, "visor.txt", 100_000)
        cfg = {"limite_texto_mb": 1, "fonte": "Consolas", "fonte_tamanho": 11,
               "tabulacao": 4}
        doc = Documento.abrir(alvo, cfg)
        aba = Aba(doc, cfg, tmod.resolver("escuro"))
        painel = aba.view("grande")

        checa(painel is not None, "a aba registra a view 'grande'")
        checa(not painel.editavel,
              "*** o painel se declara NAO editavel enquanto a edicao nao for "
              "habilitada ***")
        checa("somente leitura" in painel.aviso.text(),
              "e a infobar diz isso")
        checa(painel.botao_editar.text() == "Habilitar edicao",
              "com o botao que liga a edicao")
        checa(not painel.visor.editar_linha(),
              "F2 nao abre campo nenhum antes de habilitar")

        painel.edicao_pedida.emit()
        checa(painel.editavel, "depois do clique, o painel e' editavel")
        checa("edicao por linha ativa" in painel.aviso.text(),
              "e a infobar passa a explicar como editar")
        checa("F2" in painel.aviso.text(), "dizendo a tecla")

        while not doc.fonte_grande.indexacao_completa:
            doc.fonte_grande.indexar(8 * 1024 * 1024)

        visor = painel.visor
        visor.ir_para_linha(4)
        checa(visor.editar_linha(), "F2 abre o campo")
        checa(visor.editando, "e o visor sabe que esta' editando")
        checa_igual(visor._campo.text(), doc.fonte_grande.linha(4),
                    "o campo vem preenchido com a linha")

        visor._campo.setText("QUATRO ALTERADA")
        checa(visor.confirmar_edicao(), "Enter confirma")
        checa(not visor.editando, "e fecha o campo")
        checa_igual(doc.fonte_grande.linha(4), "QUATRO ALTERADA", "a linha mudou")
        checa(doc.modificado,
              "*** e o DOCUMENTO fica modificado: sem isso o titulo nao ganha "
              "o '*' e fechar a aba nao perguntaria nada ***")

        # Esc descarta.
        visor.ir_para_linha(6)
        antes = doc.fonte_grande.linha(6)
        visor.editar_linha()
        visor._campo.setText("NAO DEVE ENTRAR")
        visor.cancelar_edicao()
        checa_igual(doc.fonte_grande.linha(6), antes,
                    "Esc fecha o campo SEM aplicar")

        total = doc.fonte_grande.total_de_linhas()
        visor.ir_para_linha(10)
        visor.duplicar_linha()
        checa_igual(doc.fonte_grande.total_de_linhas(), total + 1, "duplicar")
        visor.remover_linha()
        checa_igual(doc.fonte_grande.total_de_linhas(), total, "remover")
        visor.desfazer()
        checa_igual(doc.fonte_grande.total_de_linhas(), total + 1, "desfazer")
        visor.refazer()
        checa_igual(doc.fonte_grande.total_de_linhas(), total, "refazer")

        aba.encerrar()


def testar_diario() -> None:
    secao("Diario de recuperacao: KB, e nao 240 MB")

    from textforge import sessao as sessao_mod
    from textforge.documento import Documento
    from ajudantes import appdata_temporario

    with appdata_temporario(), pasta_temporaria() as tmp:
        alvo = gerar(tmp, "diario.txt", 300_000)
        doc = Documento.abrir(alvo, {"limite_texto_mb": 1})
        doc.habilitar_edicao_grande()
        while not doc.fonte_grande.indexacao_completa:
            doc.fonte_grande.indexar(8 * 1024 * 1024)
        for k in range(50):
            doc.fonte_grande.substituir(k * 3, f"EDITADA {k}")
        doc.qt.setModified(True)

        caminho = sessao_mod.gravar_copia(doc)
        checa(caminho is not None and caminho.suffix == ".diario",
              "um arquivo grande gera DIARIO, e nao copia de conteudo")
        tamanho = caminho.stat().st_size
        checa(tamanho < 64 * 1024,
              f"*** o diario tem {tamanho} bytes, e nao os {alvo.stat().st_size} "
              f"do arquivo -- copiar tudo a cada autosave seria pior que nao "
              f"ter recuperacao ***")

        lido = sessao_mod.ler_diario(alvo)
        checa(lido is not None, "e o diario e' relido")
        checa(len(lido["adicionadas"]) == 50, "com as 50 linhas digitadas")
        checa(sessao_mod.diario_ainda_vale(lido, alvo),
              "e vale enquanto o arquivo do disco for o mesmo")

        # O arquivo muda no disco: reaplicar apontaria para as linhas erradas.
        with open(alvo, "ab") as f:
            f.write(b"linha nova de outro programa\n")
        checa(not sessao_mod.diario_ainda_vale(lido, alvo),
              "*** e deixa de valer quando o arquivo muda: reaplicar trechos "
              "sobre outro arquivo escreveria no lugar errado ***")
        doc.fechar()


# ===========================================================================


def main() -> int:
    testar_ida_e_volta()
    testar_preservacao_do_eol()
    testar_operacoes()
    testar_desfazer()
    testar_indice_incompleto()
    testar_memoria()
    testar_alteracao_externa()
    testar_espaco_em_disco()
    if TEM_QT:
        testar_documento()
        testar_visor()
        testar_diario()
    else:
        print("\n[PySide6 ausente: Documento, visor e diario foram pulados]")
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
