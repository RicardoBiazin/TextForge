"""Documento: round-trip BYTE A BYTE, salvar atomico, alteracao externa.

    .venv\\Scripts\\python.exe tests\\teste_documento.py

Este e' o teste mais importante do projeto. A secao 1 abre e salva 14 arquivos de
caracteristicas diferentes e exige que os bytes gravados sejam IDENTICOS aos
lidos. Se qualquer um falhar, o TextForge esta' alterando arquivo do usuario sem
que ele peca -- o que o requisito 38 proibe e' exatamente isso.

A secao 2 e' o contraponto: mostra que `toPlainText()` CORROMPERIA o mesmo
arquivo. E' a razao de `Documento.texto()` usar `toRawText()`, e existe como teste
para ninguem "simplificar" isso depois.
"""

from __future__ import annotations

import codecs
import os
import sys

from ajudantes import (checa, checa_igual, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QTextCursor                           # noqa: E402

from textforge import arquivos, codificacao, configuracao      # noqa: E402
from textforge.arquivos import AlteradoNoDisco, Assinatura      # noqa: E402
from textforge.documento import Documento                       # noqa: E402

CFG = configuracao.padrao()

ACAO = "ação"
CORACAO = "coração"
NBSP = "\u00a0"
SEP_LINHA = "\u2028"

# (nome, bytes no disco). Cada um existe por um motivo escrito ao lado.
FIXTURES: list[tuple[str, bytes]] = [
    ("utf-8 sem BOM, LF",
     f"{CORACAO}\nsegunda linha\n".encode("utf-8")),
    ("utf-8 com BOM, CRLF",
     codecs.BOM_UTF8 + f"{CORACAO}\r\nsegunda\r\n".encode("utf-8")),
    ("cp1252, CRLF",
     f"{CORACAO}\r\n{ACAO}\r\n".encode("cp1252")),
    ("utf-16 LE com BOM",
     codecs.BOM_UTF16_LE + f"{CORACAO}\r\nfim\r\n".encode("utf-16-le")),
    ("utf-16 BE com BOM",
     codecs.BOM_UTF16_BE + f"{ACAO}\nfim\n".encode("utf-16-be")),
    # Fim de linha: cada um tem de sobreviver como estava.
    ("CRLF puro", b"a\r\nb\r\nc\r\n"),
    ("LF puro", b"a\nb\nc\n"),
    ("CR puro (Mac classico)", b"a\rb\rc\r"),
    # Misto: o TextForge mantem o dominante e NAO conserta o resto.
    ("EOL misto", b"a\r\nb\r\nc\r\nd\ne\n"),
    # Sem quebra final: acrescentar uma produziria um diff em todo arquivo salvo.
    ("sem nova linha final", b"a\r\nb\r\nsem quebra no fim"),
    # Espaco no fim: um .dat de largura fixa depende dele.
    ("espaco no fim das linhas", b"campo1   \r\ncampo2      \r\n"),
    (".dat de largura fixa",
     ("0001JOSE DA SILVA      000012345\r\n"
      "0002MARIA SOUZA        000067890\r\n").encode("cp1252")),
    # nbsp: e' o caractere que toPlainText() destrói.
    ("com nbsp (U+00A0)",
     f"antes{NBSP}depois\r\nlinha2\r\n".encode("utf-8")),
    ("vazio", b""),
]


def abrir(pasta, dados: bytes, nome: str = "alvo.txt") -> tuple[Documento, object]:
    caminho = pasta / nome
    caminho.write_bytes(dados)
    return Documento.abrir(caminho, CFG), caminho


# ---------------------------------------------------------------------------
secao("1 - round-trip BYTE A BYTE de 14 fixtures")

with pasta_temporaria() as pasta:
    for nome, dados in FIXTURES:
        doc, caminho = abrir(pasta, dados, f"{abs(hash(nome))}.txt")
        checa(not doc.modificado,
              f"[{nome}] recem-aberto NAO esta' marcado como modificado")
        gerado = doc.bytes_para_salvar()
        checa_igual(gerado, dados, f"[{nome}] os bytes gerados sao IDENTICOS")

        doc.salvar()
        checa_igual(caminho.read_bytes(), dados,
                    f"[{nome}] o arquivo no disco continua identico apos salvar")

# ---------------------------------------------------------------------------
secao("2 - por que toRawText() e nao toPlainText()")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, f"antes{NBSP}depois\n".encode("utf-8"))
    checa(NBSP in doc.texto(),
          "texto() preserva o nbsp (U+00A0), porque usa toRawText()")
    # O contraponto que justifica a escolha: com toPlainText o nbsp desaparece.
    pelo_toplaintext = doc.qt.toPlainText()
    checa(NBSP not in pelo_toplaintext,
          "toPlainText() TROCA o nbsp por espaco comum -- seria corrupcao")
    checa(doc.bytes_para_salvar() == f"antes{NBSP}depois\n".encode("utf-8"),
          "e por isso os bytes salvos preservam o nbsp")

# ---------------------------------------------------------------------------
secao("3 - metadados detectados ao abrir")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, codecs.BOM_UTF8 + b"a\r\nb\r\n")
    checa_igual(doc.codec, "utf-8", "codec detectado")
    checa_igual(doc.bom, codecs.BOM_UTF8, "BOM guardado literalmente")
    checa_igual(doc.fim_de_linha, codificacao.CRLF, "CRLF detectado")
    checa(doc.termina_com_nova_linha, "termina com quebra")
    checa(doc.perfil is not None and doc.perfil.rotulo == "UTF-8 BOM",
          "o rotulo para a barra de status e' 'UTF-8 BOM'")

    doc, _ = abrir(pasta, b"a\r\nb\r\nc\r\nd\ne\n", "misto.txt")
    checa(doc.fins_de_linha_mistos, "arquivo misto e' sinalizado")
    checa_igual(doc.fim_de_linha, codificacao.CRLF, "mantendo o dominante")

    doc, _ = abrir(pasta, b"sem quebra", "sem.txt")
    checa(not doc.termina_com_nova_linha, "ausencia de quebra final e' registrada")

    # Indentacao detectada do arquivo, nao da preferencia global.
    py = b"def f():\n  if x:\n    return 1\n  return 0\n"
    doc, _ = abrir(pasta, py, "dois.py")
    checa_igual(doc.indentacao.largura, 2,
                "a indentacao vem do ARQUIVO (2), nao do config (4)")

# ---------------------------------------------------------------------------
secao("4 - binario nao e' exibido como texto corrompido (requisito 7)")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, b"%PDF-1.7\n" + bytes(range(256)) * 4, "arq.dat")
    checa(doc.binario, "conteudo binario e' reconhecido")
    checa_igual(doc.modo, "hex", "e o modo pedido e' o hexadecimal")
    checa(doc.somente_leitura, "documento binario entra em somente leitura")
    checa_igual(doc.texto(), "",
                "NAO traz texto nenhum (nada de caracteres corrompidos na tela)")
    checa("PDF" in doc.aviso, f"e o aviso nomeia o tipo: {doc.aviso!r}")

# ---------------------------------------------------------------------------
secao("5 - leitura suspeita bloqueia a edicao")

with pasta_temporaria() as pasta:
    # Bytes invalidos em UTF-8 que tambem nao formam nada plausivel: a leitura
    # produz U+FFFD, e salvar assim gravaria os U+FFFD no lugar dos bytes reais.
    doc, _ = abrir(pasta, b"inicio ok\x81\x8d\x90\x9d fim", "suspeito.txt",)
    if doc.perfil and doc.perfil.substituicoes:
        checa(doc.somente_leitura,
              "leitura com substituicoes poe o documento em somente leitura")
        checa("Reabrir como" in doc.aviso,
              "e o aviso diz o que fazer (Reabrir como)")
        try:
            doc.salvar()
            checa(False, "salvar deveria ser recusado em documento suspeito")
        except PermissionError:
            checa(True, "salvar e' RECUSADO (protege contra gravar U+FFFD)")
    else:
        checa(True, "esta amostra foi lida sem perda (nada a proteger)")

# ---------------------------------------------------------------------------
secao("6 - reabrir com outra codificacao (requisito 7)")

with pasta_temporaria() as pasta:
    # Um arquivo cp850 (DOS) que a cascata provavelmente le' como cp1252.
    dados = "Coração".encode("cp850")
    doc, _ = abrir(pasta, dados, "dos.txt")
    primeiro = doc.texto()
    doc.reabrir_como("cp850")
    checa_igual(doc.texto(), "Coração",
                "reabrir_como('cp850') le' o arquivo corretamente")
    checa_igual(doc.codec, "cp850", "e passa a usar esse codec ao salvar")
    checa_igual(doc.bytes_para_salvar(), dados,
                "salvar depois de reabrir preserva os bytes originais")
    checa(not doc.somente_leitura, "reabrir libera a edicao")
    del primeiro

# ---------------------------------------------------------------------------
secao("7 - gravacao atomica")

with pasta_temporaria() as pasta:
    alvo = pasta / "atomico.txt"
    arquivos.gravar_atomico(alvo, b"conteudo novo")
    checa_igual(alvo.read_bytes(), b"conteudo novo", "gravar_atomico escreve")
    checa(not (pasta / ("atomico.txt" + arquivos.SUFIXO_TEMPORARIO)).exists(),
          "e NAO deixa o temporario .tfnew para tras")

    # Sobrescrever preserva o conteudo novo e nao deixa lixo.
    arquivos.gravar_atomico(alvo, b"segunda versao")
    checa_igual(alvo.read_bytes(), b"segunda versao", "sobrescreve corretamente")
    restos = list(pasta.glob("*" + arquivos.SUFIXO_TEMPORARIO))
    checa_igual(restos, [], "nenhum temporario sobrou depois de sobrescrever")

    # Morte entre o write e a troca: o ORIGINAL tem de continuar intacto. E' a
    # razao de existir a gravacao em duas etapas.
    original = pasta / "sobrevive.txt"
    original.write_bytes(b"conteudo ORIGINAL")
    real = arquivos._trocar

    def falhar(*_a, **_k):
        raise OSError("falha simulada entre o write e a troca")

    arquivos._trocar = falhar
    try:
        try:
            arquivos.gravar_atomico(original, b"conteudo NOVO")
        except OSError:
            pass
    finally:
        arquivos._trocar = real
    checa_igual(original.read_bytes(), b"conteudo ORIGINAL",
                "falha na troca deixa o arquivo ORIGINAL intacto")
    checa_igual(list(pasta.glob("*" + arquivos.SUFIXO_TEMPORARIO)), [],
                "e o temporario e' limpo mesmo em caso de erro")

# ---------------------------------------------------------------------------
secao("7b - troca sobre arquivo somente-leitura e arquivo travado")

# Regressao: um .csv marcado como somente-leitura era editavel na tela mas o
# salvamento morria com "[WinError 5] Acesso negado: x.csv.tfnew -> x.csv".
# Nem ReplaceFileW nem os.replace substituem destino somente-leitura.
if os.name == "nt":
    import ctypes

    RO = arquivos.FILE_ATTRIBUTE_READONLY
    _k = ctypes.windll.kernel32
    _k.GetFileAttributesW.restype = ctypes.c_uint32

    def _somente_leitura(caminho):
        return bool(_k.GetFileAttributesW(str(caminho)) & RO)

    with pasta_temporaria() as pasta:
        alvo = pasta / "conta.csv"
        alvo.write_bytes(b"antes")
        _k.SetFileAttributesW(str(alvo), RO)
        try:
            arquivos.gravar_atomico(alvo, b"depois")
            checa_igual(alvo.read_bytes(), b"depois",
                        "grava sobre arquivo marcado como somente-leitura")
            checa(_somente_leitura(alvo),
                  "e DEVOLVE o atributo somente-leitura depois de trocar")
            checa_igual(list(pasta.glob("*" + arquivos.SUFIXO_TEMPORARIO)), [],
                        "sem temporario para tras no caminho somente-leitura")
        finally:
            _k.SetFileAttributesW(str(alvo), 0x80)

    # Arquivo aberto por outro processo sem permitir escrita: nao da' para
    # salvar, mas o erro tem de dizer O QUE fazer, e o original fica intacto.
    with pasta_temporaria() as pasta:
        travado = pasta / "travado.csv"
        travado.write_bytes(b"ORIGINAL")
        GENERIC_READ, SHARE_READ, OPEN_EXISTING = 0x80000000, 0x1, 3
        h = _k.CreateFileW(str(travado), GENERIC_READ, SHARE_READ, None,
                           OPEN_EXISTING, 0, None)
        try:
            erro = None
            try:
                arquivos.gravar_atomico(travado, b"NOVO")
            except OSError as exc:
                erro = exc
            checa(isinstance(erro, arquivos.FalhaNaTroca),
                  "arquivo travado levanta FalhaNaTroca, nao OSError cru")
            checa("aberto em outro programa" in str(erro),
                  "e a mensagem diz que outro programa esta' segurando")
            checa("WinError" not in str(erro),
                  "sem despejar o WinError cru na cara do usuario")
            checa(getattr(erro, "causa", None) is not None,
                  "guardando o erro original em .causa para o log")
            checa_igual(travado.read_bytes(), b"ORIGINAL",
                        "e o arquivo original continua intacto")
            checa_igual(list(pasta.glob("*" + arquivos.SUFIXO_TEMPORARIO)), [],
                        "sem temporario para tras quando a troca falha")
        finally:
            _k.CloseHandle(h)

# ---------------------------------------------------------------------------
secao("8 - assinatura e alteracao externa (requisito 27)")

with pasta_temporaria() as pasta:
    alvo = pasta / "vigiado.txt"
    alvo.write_bytes(b"versao 1")
    a1 = Assinatura.de_caminho(alvo)
    checa(a1.existe, "assinatura de arquivo existente")
    checa(a1.sha256, "arquivo pequeno tem sha256 calculado")
    checa(a1.compativel_com(Assinatura.de_caminho(alvo)),
          "assinatura e' compativel consigo mesma")

    alvo.write_bytes(b"versao 2 alterada por outro programa")
    a2 = Assinatura.de_caminho(alvo)
    checa(not a1.compativel_com(a2), "alteracao externa e' detectada")
    checa("tamanho" in a1.descrever_diferenca(a2),
          f"e descrita em portugues: {a1.descrever_diferenca(a2)!r}")

    # O caso que so' o hash pega: mesmo tamanho e mesmo mtime, conteudo diferente.
    import os as _os
    alvo.write_bytes(b"versao 1")
    _os.utime(alvo, ns=(a1.mtime_ns, a1.mtime_ns))
    igual = Assinatura.de_caminho(alvo)
    checa(a1.compativel_com(igual),
          "conteudo identico com mtime restaurado e' compativel")
    alvo.write_bytes(b"versao X")            # mesmo tamanho!
    _os.utime(alvo, ns=(a1.mtime_ns, a1.mtime_ns))
    disfarcado = Assinatura.de_caminho(alvo)
    checa(not a1.compativel_com(disfarcado),
          "conteudo diferente com MESMO tamanho e mtime e' pego pelo sha256")

    ausente = Assinatura.de_caminho(pasta / "nao-existe.txt")
    checa(not ausente.existe, "assinatura de arquivo ausente")
    checa("apagado" in a1.descrever_diferenca(ausente),
          "e a descricao diz que o arquivo foi apagado")

with pasta_temporaria() as pasta:
    doc, caminho = abrir(pasta, b"conteudo\r\n", "externo.txt")
    checa(not doc.mudou_no_disco(), "recem-aberto, nada mudou no disco")

    caminho.write_bytes(b"mexido por outro programa\r\n")
    checa(doc.mudou_no_disco(), "alteracao externa e' notada pelo documento")

    doc.qt.setPlainText("minha versao")
    try:
        doc.salvar()
        checa(False, "salvar deveria ter sido recusado")
    except AlteradoNoDisco as exc:
        checa(True, "salvar levanta AlteradoNoDisco (NAO sobrescreve em silencio)")
        checa(exc.esperada is not None and exc.encontrada is not None,
              "e a excecao carrega as duas assinaturas, para o dialogo explicar")

    # Com forcar=True (o usuario escolheu "manter o meu"), grava.
    doc.salvar(forcar=True)
    checa(b"minha versao" in caminho.read_bytes(),
          "com forcar=True, a gravacao acontece")
    checa(not doc.mudou_no_disco(),
          "e a assinatura e' atualizada (nao avisa de novo no proximo salvamento)")

    doc.recarregar()
    checa("minha versao" in doc.texto(), "recarregar le' o arquivo do disco")
    checa(not doc.modificado, "e o documento deixa de estar modificado")

# ---------------------------------------------------------------------------
secao("9 - troca de codificacao avisa antes de destruir")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, f"{CORACAO}\r\n".encode("utf-8"), "conv.txt")

    perdas = doc.definir_codificacao("ascii")
    checa(len(perdas) > 0,
          "converter para ASCII devolve a lista de perdas SEM aplicar")
    checa_igual(doc.codec, "utf-8", "e a codificacao do documento NAO mudou")
    checa(perdas[0].nome_unicode, "cada perda traz o nome Unicode")

    perdas = doc.definir_codificacao("cp1252")
    checa_igual(perdas, [], "converter para cp1252 nao perde nada")
    checa_igual(doc.codec, "cp1252", "e a codificacao muda")
    checa(doc.modificado, "a troca marca o documento como modificado")
    checa_igual(doc.bytes_para_salvar(), f"{CORACAO}\r\n".encode("cp1252"),
                "e os bytes saem na codificacao nova")

    # Com substituir=True o usuario aceitou a perda.
    doc2, _ = abrir(pasta, f"{ACAO}\n".encode("utf-8"), "conv2.txt")
    checa_igual(doc2.definir_codificacao("ascii", substituir=True), [],
                "com substituir=True a conversao e' aplicada")
    checa(b"?" in doc2.bytes_para_salvar(substituir=True),
          "e os caracteres perdidos viram '?'")

# ---------------------------------------------------------------------------
secao("10 - troca de fim de linha")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, b"a\r\nb\r\n", "eol.txt")
    doc.definir_fim_de_linha(codificacao.LF)
    checa_igual(doc.bytes_para_salvar(), b"a\nb\n",
                "trocar para LF reescreve as quebras")
    checa(doc.modificado, "e marca como modificado")

    doc, _ = abrir(pasta, b"a\nb\n", "eol2.txt")
    doc.definir_fim_de_linha(codificacao.CRLF)
    checa_igual(doc.bytes_para_salvar(), b"a\r\nb\r\n", "e de LF para CRLF")

    # Depois de uma escolha explicita, o arquivo deixa de ser "misto".
    doc, _ = abrir(pasta, b"a\r\nb\nc\r\n", "eol3.txt")
    checa(doc.fins_de_linha_mistos, "o arquivo comeca misto")
    doc.definir_fim_de_linha(codificacao.LF)
    checa(not doc.fins_de_linha_mistos,
          "apos a escolha do usuario, deixa de ser misto")
    checa_igual(doc.bytes_para_salvar(), b"a\nb\nc\n",
                "e TODAS as quebras passam a ser LF")

# ---------------------------------------------------------------------------
secao("10b - EOL misto e' PRESERVADO linha a linha")

# Regressao: a primeira versao normalizava tudo para a quebra dominante, e o
# arquivo b"a\r\nb\r\nc\r\nd\ne\n" era gravado como b"...d\r\ne\r\n". Isso
# reescreve DUAS linhas que o usuario nao tocou -- o requisito 38 proibe.
MISTO = b"a\r\nb\r\nc\r\nd\ne\n"

with pasta_temporaria() as pasta:
    doc, caminho = abrir(pasta, MISTO, "misto1.txt")
    checa(doc.fins_de_linha_mistos, "o arquivo e' reconhecido como misto")
    checa_igual(doc.fim_de_linha, codificacao.CRLF,
                "e a barra de status mostra o dominante (CRLF)")
    checa_igual(len(doc.eols_originais), 6,
                "os terminadores de cada linha foram guardados")
    checa_igual(doc.bytes_para_salvar(), MISTO,
                "salvar SEM editar devolve os bytes IDENTICOS")
    checa(not doc.eol_sera_normalizado, "e nada foi normalizado")

    # Edicao DENTRO de uma linha: a correspondencia linha-a-linha se mantem, e
    # cada linha conserva o terminador que tinha.
    doc, _ = abrir(pasta, MISTO, "misto2.txt")
    # QTextCursor(documento) -- `textCursor()` e' do widget, nao do documento.
    cursor = QTextCursor(doc.qt)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                        QTextCursor.MoveMode.KeepAnchor)
    cursor.insertText("PRIMEIRA")
    checa_igual(doc.bytes_para_salvar(), b"PRIMEIRA\r\nb\r\nc\r\nd\ne\n",
                "editar DENTRO de uma linha preserva os EOLs mistos")
    checa(not doc.eol_sera_normalizado, "e nao normaliza nada")

    # Edicao que MUDA o numero de linhas: a correspondencia se perde, e a
    # normalizacao passa a ser inevitavel -- mas fica sinalizada, para a
    # interface poder avisar antes de gravar.
    doc, _ = abrir(pasta, MISTO, "misto3.txt")
    cursor = QTextCursor(doc.qt)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.insertText("nova\n")
    gerado = doc.bytes_para_salvar()
    checa(doc.eol_sera_normalizado,
          "inserir uma linha marca que o EOL sera' normalizado")
    checa(b"\n" in gerado and gerado.count(b"\r\n") >= 4,
          "e a normalizacao usa a quebra dominante")

# ---------------------------------------------------------------------------
secao("11 - identidade da aba e nome")

with pasta_temporaria() as pasta:
    alvo = pasta / "Config.XML"
    alvo.write_bytes(b"<a/>")
    doc = Documento.abrir(alvo, CFG)
    checa_igual(doc.nome, "Config.XML", "o nome curto e' o do arquivo")
    checa_igual(doc.titulo_da_aba, "Config.XML", "sem asterisco quando salvo")
    doc.qt.setPlainText("mexido")
    checa_igual(doc.titulo_da_aba, "*Config.XML",
                "com asterisco quando modificado (requisito 2)")

    # No Windows o mesmo arquivo chega com caixa diferente. Duas abas do mesmo
    # arquivo produzem duas versoes divergentes -- e uma delas se perde.
    outro = Documento.abrir(pasta / "config.xml", CFG)
    checa_igual(doc.chave(), outro.chave(),
                "a chave ignora a CAIXA do caminho (Config.XML == config.xml)")

    novo = Documento.novo(CFG)
    checa(novo.sem_arquivo, "documento novo nao tem arquivo")
    checa(novo.nome.startswith("Sem titulo"), f"e ganha um rotulo: {novo.nome}")
    outro_novo = Documento.novo(CFG)
    checa(novo.nome != outro_novo.nome, "dois novos tem rotulos diferentes")
    checa(novo.chave() != outro_novo.chave(),
          "e chaves diferentes (nao colidem entre si)")

    try:
        novo.salvar()
        checa(False, "salvar sem caminho deveria levantar")
    except ValueError:
        checa(True, "salvar() sem caminho levanta ValueError (use salvar_como)")

    destino = pasta / "novo.txt"
    novo.qt.setPlainText("conteudo")
    novo.salvar_como(destino)
    checa(destino.is_file(), "salvar_como cria o arquivo")
    checa_igual(novo.nome, "novo.txt", "e o documento passa a se chamar assim")
    checa(not novo.modificado, "e deixa de estar modificado")

# ---------------------------------------------------------------------------
secao("12 - propriedades (requisito 25)")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, f"{CORACAO}\r\nsegunda\r\n".encode("utf-8"),
                   "props.txt")
    p = doc.propriedades()
    for chave in ("nome", "caminho", "extensao", "tamanho", "linhas",
                  "caracteres", "codificacao", "fim_de_linha", "criado_em",
                  "alterado_em"):
        checa(chave in p, f"propriedades traz '{chave}' (requisito 25)")
    checa_igual(p["extensao"], ".txt", "a extensao e' extraida")
    checa_igual(p["fim_de_linha"], "CRLF", "o fim de linha aparece legivel")
    checa_igual(p["codificacao"], "UTF-8", "a codificacao aparece legivel")
    checa_igual(p["linhas"], 3, "3 linhas (2 com texto + a vazia final)")
    checa(p["tamanho"] > 0, "o tamanho vem do disco")
    checa(p["como_detectou"], "e diz COMO a codificacao foi decidida")

    novo = Documento.novo(CFG)
    novo.qt.setPlainText("abc")
    p = novo.propriedades()
    checa_igual(p["caminho"], "(nao salvo)", "documento novo diz que nao foi salvo")
    checa(p["tamanho"] > 0, "e o tamanho e' o que ELE TERIA se fosse salvo")

# ---------------------------------------------------------------------------
secao("13 - aparar espaco no fim e' opt-in")

with pasta_temporaria() as pasta:
    doc, _ = abrir(pasta, b"campo   \r\noutro  \r\n", "espacos.txt")
    checa_igual(doc.bytes_para_salvar(), b"campo   \r\noutro  \r\n",
                "por padrao, o espaco no fim das linhas e' PRESERVADO")
    checa(doc.aparar_espaco_final(), "aparar_espaco_final relata que mudou algo")
    checa_igual(doc.bytes_para_salvar(), b"campo\r\noutro\r\n",
                "e depois de pedido, o espaco sai")
    checa(not doc.aparar_espaco_final(),
          "chamar de novo nao muda nada e devolve False")

sys.exit(resumir())
