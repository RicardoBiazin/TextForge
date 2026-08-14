"""Hashes de texto e de arquivo (etapa 12, requisito 25).

    .\\.venv\\Scripts\\python.exe tests\\teste_hash.py

Os digests sao conferidos contra VALORES CONHECIDOS publicados (RFC 1321 para o MD5,
FIPS 180 para os SHA), e nao contra o proprio `hashlib`. Comparar a saida do modulo
com `hashlib.sha256(...)` provaria apenas que o modulo chama o hashlib -- o que ja'
se ve' lendo o codigo. O valor externo prova que o resultado e' o hash de verdade.

A verificacao que mais importa na pratica: **o hash do TEXTO e o do ARQUIVO nao sao
iguais, e nao deveriam ser.** O arquivo tem BOM e CRLF; o texto em memoria tem "\\n"
e nao tem BOM. Quem compara com um `.sha256` publicado ou com o `certutil` do
Windows quer o do ARQUIVO.
"""

from __future__ import annotations

import hashlib
import sys

from ajudantes import (checa, checa_igual, checa_levanta, pasta_temporaria,
                       resumir, secao)

from textforge.servicos import hashes as h

# Valores publicados. "abc" e a string vazia sao os vetores de teste classicos.
CONHECIDOS = {
    ("MD5", ""): "d41d8cd98f00b204e9800998ecf8427e",
    ("MD5", "abc"): "900150983cd24fb0d6963f7d28e17f72",
    ("SHA-1", ""): "da39a3ee5e6b4b0d3255bfef95601890afd80709",
    ("SHA-1", "abc"): "a9993e364706816aba3e25717850c26c9cd0d89d",
    ("SHA-256", ""):
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ("SHA-256", "abc"):
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    ("SHA-512", "abc"):
        "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
        "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
}


def testar_valores_conhecidos() -> None:
    secao("Digests contra valores PUBLICADOS")

    for (algoritmo, entrada), esperado in CONHECIDOS.items():
        checa_igual(h.de_texto(entrada, algoritmo), esperado,
                    f"{algoritmo} de {entrada!r} bate com o valor publicado")

    checa_igual(len(h.de_texto("x", "MD5")), 32, "MD5 tem 32 caracteres hex")
    checa_igual(len(h.de_texto("x", "SHA-1")), 40, "SHA-1 tem 40")
    checa_igual(len(h.de_texto("x", "SHA-256")), 64, "SHA-256 tem 64")
    checa_igual(len(h.de_texto("x", "SHA-512")), 128, "SHA-512 tem 128")
    checa(h.de_texto("x", "SHA-256").islower(), "o digest sai em minusculas")

    checa_levanta(ValueError, h.de_texto, "algoritmo desconhecido levanta",
                  "abc", "SHA-3")


def testar_codificacao() -> None:
    secao("*** A codificacao muda o hash ***")

    em_utf8 = h.de_texto("ação", "SHA-256", "utf-8")
    em_cp1252 = h.de_texto("ação", "SHA-256", "cp1252")
    checa(em_utf8 != em_cp1252,
          "'ação' em UTF-8 e em cp1252 tem SHA-256 diferentes (sao bytes "
          "diferentes)")
    checa_igual(em_utf8, hashlib.sha256("ação".encode("utf-8")).hexdigest(),
                "e o de UTF-8 e' o dos bytes UTF-8, como esperado")

    checa_levanta(UnicodeEncodeError, h.de_texto,
                  "caractere ausente na codificacao LEVANTA em vez de virar '?'",
                  "preço → 10", "SHA-256", "cp1252")
    checa(True, "  (substituir por '?' daria o hash de um texto DIFERENTE do "
                "que esta' na tela — um numero com cara de correto)")


def testar_arquivo() -> None:
    secao("Hash de arquivo, em blocos")

    with pasta_temporaria("textforge-hash-") as pasta:
        alvo = pasta / "dados.bin"
        alvo.write_bytes(b"abc")
        checa_igual(h.de_arquivo(alvo, "SHA-256"), CONHECIDOS[("SHA-256", "abc")],
                    "arquivo com 'abc' da' o mesmo digest publicado")

        vazio = pasta / "vazio.bin"
        vazio.write_bytes(b"")
        checa_igual(h.de_arquivo(vazio, "MD5"), CONHECIDOS[("MD5", "")],
                    "arquivo vazio da' o digest da string vazia")

        # Maior que um bloco, para exercitar o laco de leitura.
        grande = pasta / "grande.bin"
        conteudo = bytes(range(256)) * (5 * 1024)          # ~1,25 MB
        grande.write_bytes(conteudo)
        checa(len(conteudo) > h.BLOCO,
              f"o arquivo tem {len(conteudo)} bytes, mais que o bloco de {h.BLOCO}")
        checa_igual(h.de_arquivo(grande, "SHA-256"),
                    hashlib.sha256(conteudo).hexdigest(),
                    "*** lido em blocos, o digest continua o do arquivo inteiro ***")

        secao("Progresso e cancelamento")
        chamadas: list[tuple[int, int]] = []
        h.de_arquivo(grande, "SHA-256",
                     progresso=lambda lidos, total: chamadas.append((lidos, total)))
        checa(len(chamadas) >= 2, f"o progresso foi reportado ({len(chamadas)}x)")
        checa_igual(chamadas[-1][0], len(conteudo),
                    "e a ultima chamada reporta o arquivo inteiro lido")
        checa_igual(chamadas[-1][1], len(conteudo), "com o total certo")

        parcial = h.de_arquivo(grande, "SHA-256", cancelar=lambda: True)
        checa_igual(parcial, "",
                    "*** cancelado, devolve string VAZIA — nunca um digest "
                    "parcial que pareceria valido ***")

        secao("Texto x arquivo: sao DIFERENTES, e por bons motivos")
        com_bom = pasta / "com_bom.txt"
        # UTF-8 com BOM e CRLF: o arquivo tipico do Bloco de Notas.
        com_bom.write_bytes(b"\xef\xbb\xbf" + "ação\r\n".encode("utf-8"))
        do_arquivo = h.de_arquivo(com_bom, "SHA-256")
        do_texto = h.de_texto("ação\n", "SHA-256", "utf-8")
        checa(do_arquivo != do_texto,
              "o hash do ARQUIVO (com BOM e CRLF) difere do do TEXTO (sem BOM, LF)")
        checa_igual(do_arquivo,
                    hashlib.sha256(com_bom.read_bytes()).hexdigest(),
                    "e o do arquivo e' o dos bytes do disco — o que o certutil da'")


def testar_formatacao() -> None:
    secao("Formatacao para conferencia visual")

    valor = CONHECIDOS[("SHA-256", "abc")]
    checa_igual(h.formatar(valor), valor, "sem agrupar, devolve como esta'")
    agrupado = h.formatar(valor, agrupado=True)
    checa_igual(agrupado.replace(" ", ""), valor,
                "agrupado, so' insere espacos — nenhum caractere se perde")
    checa_igual(len(agrupado.split(" ")), 8,
                "um SHA-256 vira 8 grupos de 8 caracteres")
    checa_igual(h.formatar("ABCDEF"), "abcdef", "normaliza para minusculas")


def testar_registro() -> None:
    secao("Registro de comandos")

    from textforge.interface import acoes

    ids = set(acoes.REGISTRO.ids())
    faltando = [i for i in h.POR_COMANDO if i not in ids]
    checa_igual(faltando, [], "todo id em POR_COMANDO existe no registro")
    declarados = [i for i in ids if i.startswith("hash.")]
    checa_igual([i for i in declarados if i not in h.POR_COMANDO], [],
                "e todo comando 'hash.*' declarado tem algoritmo")
    desconhecidos = [n for n in h.POR_COMANDO.values() if n not in h.ALGORITMOS]
    checa_igual(desconhecidos, [], "e todos os algoritmos citados existem")


def main() -> int:
    testar_valores_conhecidos()
    testar_codificacao()
    testar_arquivo()
    testar_formatacao()
    testar_registro()
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
