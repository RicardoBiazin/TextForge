"""Sessao (requisito 17), trava e recuperacao apos crash (requisito 16).

    .venv\\Scripts\\python.exe tests\\teste_sessao.py

Duas verificacoes carregam o peso:

  * a recuperacao guarda BYTES JA CODIFICADOS, entao um arquivo cp1252 volta
    cp1252. Guardar o `str` faria o mecanismo de SEGURANCA introduzir a corrupcao
    que o requisito 38 proibe.
  * sessao morta e' detectada pelo TESTE DE RENAME da trava, nao por PID. Um PID
    pode ter sido reciclado por outro processo, e "o PID existe" nao significa "o
    TextForge esta' rodando".
"""

from __future__ import annotations

import codecs
import json
import sys

from ajudantes import (appdata_temporario, checa, checa_igual,
                       pasta_temporaria, preparar_qt, pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from textforge import codificacao, configuracao                 # noqa: E402
from textforge import sessao as smod                             # noqa: E402
from textforge.documento import Documento                        # noqa: E402

CFG = configuracao.padrao()
CORACAO = "coração"

# ---------------------------------------------------------------------------
secao("1 - round-trip da sessao")

with appdata_temporario():
    with pasta_temporaria() as pasta:
        a = pasta / "a.txt"
        b = pasta / "b com espaco.xml"
        a.write_bytes(b"um\r\n")
        b.write_bytes(b"<x/>\r\n")

        sessao = smod.Sessao(abas=[
            smod.EstadoDeAba(caminho=str(a), cursor=5, rolagem=2,
                             codec="cp1252", fim_de_linha="\r\n"),
            smod.EstadoDeAba(caminho=str(b), cursor=0, rolagem=0),
        ], ativa=1)
        alvo = smod.salvar_sessao(sessao)
        checa(alvo.is_file(), "salvar_sessao cria o arquivo")
        checa(not alvo.with_name(alvo.name + ".novo").exists(),
              "e nao deixa o temporario para tras")

        de_volta = smod.carregar_sessao()
        checa_igual(len(de_volta.abas), 2, "as duas abas voltam")
        checa_igual(de_volta.ativa, 1, "a aba ativa volta")
        checa_igual(de_volta.abas[0].caminho, str(a),
                    "o caminho volta intacto")
        checa_igual(de_volta.abas[0].cursor, 5, "a posicao do cursor volta")
        checa_igual(de_volta.abas[0].rolagem, 2, "a rolagem volta")
        checa_igual(de_volta.abas[1].caminho, str(b),
                    "caminho com espaco tambem volta intacto")

        # Todas as abas existem: nenhuma e' descartada.
        checa_igual(len(smod.abas_existentes(de_volta)), 2,
                    "abas_existentes mantem as duas")

        # Arquivo apagado desde a ultima sessao: a aba e' descartada em silencio.
        # Um dialogo de erro por arquivo ausente ao INICIAR o programa seria pior
        # do que simplesmente nao restaurar a aba.
        a.unlink()
        vivas = smod.abas_existentes(de_volta)
        checa_igual(len(vivas), 1, "aba de arquivo apagado e' descartada")
        checa_igual(vivas[0].caminho, str(b), "e a que existe permanece")

# ---------------------------------------------------------------------------
secao("2 - sessao ausente, ilegivel ou de versao futura")

with appdata_temporario():
    vazia = smod.carregar_sessao()
    checa_igual(vazia.abas, [], "sem arquivo de sessao, sessao vazia")

    caminho = configuracao.caminho_sessao()
    caminho.write_text("{isso nao e json", encoding="utf-8")
    checa_igual(smod.carregar_sessao().abas, [],
                "sessao corrompida devolve vazia, sem estourar")

    caminho.write_text('["lista", "em vez", "de objeto"]', encoding="utf-8")
    checa_igual(smod.carregar_sessao().abas, [],
                "sessao do tipo errado devolve vazia")

    # Uma sessao gravada por uma versao FUTURA nao pode impedir esta de abrir.
    caminho.write_text(json.dumps({
        "versao": "99.0", "ativa": 0,
        "abas": [{"caminho": "C:\\x.txt", "cursor": 1,
                  "campo_do_futuro": {"a": 1}}]}), encoding="utf-8")
    futura = smod.carregar_sessao()
    checa_igual(len(futura.abas), 1, "sessao de versao futura e' lida")
    checa_igual(futura.abas[0].cursor, 1, "os campos conhecidos sao aproveitados")

    # Aba sem caminho e' descartada: nao ha' o que restaurar.
    caminho.write_text(json.dumps({"abas": [{"cursor": 5}, {"caminho": ""}]}),
                       encoding="utf-8")
    checa_igual(smod.carregar_sessao().abas, [],
                "abas sem caminho sao descartadas")

# ---------------------------------------------------------------------------
secao("3 - trava: teste de rename, nao PID")

with appdata_temporario():
    trava = smod.Trava()
    checa(not trava.sessao_anterior_morreu(),
          "sem arquivo de trava, nenhuma sessao morreu")

    checa(trava.adquirir(), "adquirir cria a trava")
    checa(trava.caminho.is_file(), "e o arquivo existe")

    # Enquanto ESTA sessao mantem o arquivo aberto, outra instancia nao consegue
    # renomea-lo -- e e' assim que ela sabe que o TextForge esta' rodando.
    outra = smod.Trava()
    checa(not outra.sessao_anterior_morreu(),
          "com a trava ABERTA, a outra instancia nao a considera morta")

    trava.liberar()
    checa(not trava.caminho.is_file(), "liberar apaga a trava")

    # Simula um encerramento inesperado: a trava ficou no disco, sem ninguem
    # mantendo o arquivo aberto.
    trava.caminho.write_text(json.dumps({"pid": 999999, "versao": "0.1"}),
                             encoding="utf-8")
    checa(smod.Trava().sessao_anterior_morreu(),
          "trava orfa no disco = a sessao anterior morreu")
    checa(trava.caminho.is_file(),
          "e o teste de rename devolve o arquivo ao lugar")

    # Um PID inexistente nao e' o critério: o que decide e' conseguir renomear.
    trava.caminho.write_text(json.dumps({"pid": 4}), encoding="utf-8")
    checa(smod.Trava().sessao_anterior_morreu(),
          "o PID gravado e' irrelevante para a deteccao")
    trava.caminho.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
secao("4 - recuperacao preserva a CODIFICACAO")

with appdata_temporario():
    with pasta_temporaria() as pasta:
        # Um arquivo cp1252 com CRLF, modificado e nao salvo.
        alvo = pasta / "legado.txt"
        alvo.write_bytes(f"{CORACAO}\r\n".encode("cp1252"))
        doc = Documento.abrir(alvo, CFG)
        doc.qt.setModified(False)
        doc.definir_texto(f"{CORACAO} editado\r\n", marcar_modificado=True)
        checa(doc.modificado, "o documento esta' modificado")

        gravado = smod.gravar_copia(doc)
        checa(gravado is not None and gravado.is_file(),
              "gravar_copia cria a copia de recuperacao")

        recuperaveis = smod.listar_recuperaveis()
        checa_igual(len(recuperaveis), 1, "listar_recuperaveis acha a copia")
        r = recuperaveis[0]
        checa_igual(r.nome, "legado.txt", "o nome e' preservado")
        checa_igual(r.caminho_original, str(alvo), "e o caminho original")
        checa_igual(r.codec, "cp1252",
                    "o CODEC e' preservado (senao a recuperacao corromperia)")
        checa_igual(r.fim_de_linha, "\r\n", "o fim de linha e' preservado")
        checa(r.quando > 0, "e a hora da copia")
        checa(r.quando_texto, f"formatada para o dialogo: {r.quando_texto}")

        # O teste central: os bytes guardados sao os do arquivo cp1252, e nao
        # UTF-8. Guardar o `str` faria a recuperacao devolver o arquivo em UTF-8.
        checa_igual(r.bytes_do_conteudo, f"{CORACAO} editado\r\n".encode("cp1252"),
                    "os BYTES guardados estao em cp1252, como o original")
        checa(r.bytes_do_conteudo != f"{CORACAO} editado\r\n".encode("utf-8"),
              "e NAO em UTF-8 (que seria a corrupcao classica)")

        # Recuperar de verdade: os bytes voltam pela mesma cascata de deteccao.
        perfil = codificacao.detectar(r.bytes_do_conteudo, "cp1252")
        checa(CORACAO in perfil.texto,
              "recuperar devolve os acentos corretos")

        # Salvar de verdade apaga a copia: senao o proximo inicio ofereceria
        # recuperar algo que ja' esta' no disco.
        smod.esquecer_copia(doc)
        checa_igual(smod.listar_recuperaveis(), [],
                    "esquecer_copia remove a copia (chamado apos salvar)")

# ---------------------------------------------------------------------------
secao("5 - recuperacao de documento sem titulo, e com BOM")

with appdata_temporario():
    novo = Documento.novo(CFG)
    novo.definir_texto("rascunho que nunca foi salvo", marcar_modificado=True)
    checa(smod.gravar_copia(novo) is not None,
          "documento sem arquivo tambem gera copia")
    r = smod.listar_recuperaveis()[0]
    checa_igual(r.caminho_original, "",
                "e o caminho original fica vazio (era 'Sem titulo')")
    checa(r.nome.startswith("Sem titulo"), f"o rotulo e' preservado: {r.nome}")

    # Chamar de novo NAO deve criar uma segunda copia: o identificador e' estavel,
    # senao a pasta cresceria a cada intervalo de autosave.
    smod.gravar_copia(novo)
    smod.gravar_copia(novo)
    checa_igual(len(smod.listar_recuperaveis()), 1,
                "gravar varias vezes o mesmo documento nao acumula copias")

    smod.limpar_recuperacao()

    # BOM: tem de voltar exatamente igual.
    com_bom = Documento.novo(CFG)
    com_bom.codec = "utf-8"
    com_bom.bom = codecs.BOM_UTF8
    com_bom.definir_texto("com BOM", marcar_modificado=True)
    smod.gravar_copia(com_bom)
    r = smod.listar_recuperaveis()[0]
    checa_igual(r.bom, codecs.BOM_UTF8, "o BOM e' preservado na copia")
    checa(r.bytes_do_conteudo.startswith(codecs.BOM_UTF8),
          "e os bytes guardados comecam com ele")

    # Documento NAO modificado nao gera copia: nao ha' nada a recuperar.
    smod.limpar_recuperacao()
    limpo = Documento.novo(CFG)
    limpo.definir_texto("salvo e intacto")
    checa(smod.gravar_copia(limpo) is None,
          "documento nao modificado nao gera copia")
    checa_igual(smod.listar_recuperaveis(), [], "e a pasta continua vazia")

# ---------------------------------------------------------------------------
secao("6 - limpar recuperacao e pastas excluidas")

with appdata_temporario():
    for i in range(3):
        d = Documento.novo(CFG)
        d.definir_texto(f"rascunho {i}", marcar_modificado=True)
        smod.gravar_copia(d)
    checa_igual(len(smod.listar_recuperaveis()), 3, "tres copias")

    removidos = smod.limpar_recuperacao()
    checa(removidos >= 3, f"limpar_recuperacao removeu {removidos} arquivos")
    checa_igual(smod.listar_recuperaveis(), [], "e a pasta ficou vazia")

    # A pasta de recuperacao guarda TEXTO CLARO. Quem tem arquivo sensivel precisa
    # poder excluir a pasta dele da copia.
    import pathlib
    cfg = configuracao.padrao()
    cfg["recuperacao_pastas_excluidas"] = [r"C:\Sigiloso"]
    checa(not smod.pasta_permitida(pathlib.Path(r"C:\Sigiloso\dados.txt"), cfg),
          "arquivo em pasta excluida NAO recebe copia de recuperacao")
    checa(not smod.pasta_permitida(pathlib.Path(r"c:\sigiloso\sub\x.txt"), cfg),
          "a comparacao ignora a caixa e pega subpastas")
    checa(smod.pasta_permitida(pathlib.Path(r"C:\Outra\dados.txt"), cfg),
          "arquivo fora das pastas excluidas recebe copia")
    checa(smod.pasta_permitida(None, cfg),
          "documento sem arquivo sempre recebe copia")
    checa(smod.pasta_permitida(pathlib.Path(r"C:\Qualquer\x.txt"),
                               configuracao.padrao()),
          "sem lista de exclusao, tudo recebe copia")

# ---------------------------------------------------------------------------
secao("7 - manifesto ilegivel nao derruba a recuperacao")

with appdata_temporario():
    d = Documento.novo(CFG)
    d.definir_texto("bom", marcar_modificado=True)
    smod.gravar_copia(d)

    pasta = configuracao.pasta_de_recuperacao()
    (pasta / "quebrado.json").write_text("{nao e json", encoding="utf-8")
    (pasta / "quebrado.conteudo").write_bytes(b"orfao")
    # Manifesto sem o conteudo correspondente.
    (pasta / "sozinho.json").write_text(json.dumps({"nome": "x"}),
                                        encoding="utf-8")

    recuperaveis = smod.listar_recuperaveis()
    checa_igual(len(recuperaveis), 1,
                "manifesto ilegivel e manifesto sem conteudo sao ignorados")
    checa_igual(recuperaveis[0].nome, d.nome, "e o bom continua sendo listado")

sys.exit(resumir())
