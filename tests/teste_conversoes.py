"""Conversoes de texto: Base64, URL, HTML e JSON (etapa 12, requisito 24).

    .\\.venv\\Scripts\\python.exe tests\\teste_conversoes.py

A verificacao que carrega o peso: **a codificacao importa**. Base64 e URL trabalham
sobre BYTES, e `"acao"` em cp1252 produz um resultado DIFERENTE do de UTF-8. Um
editor que sempre usasse UTF-8 geraria um Base64 que decodifica errado no sistema de
destino, e o usuario levaria horas para descobrir por que.

Sem Qt: sao funcoes puras.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, checa_levanta, resumir, secao

from textforge.servicos import conversoes as c
from textforge.servicos.conversoes import ConversaoInvalida

# Texto de trabalho: acentos que existem nos dois codecs, e um que so' existe em
# UTF-8 (o travessao), para o teste de perda.
ACENTOS = "transação concluída às 3h"


def testar_base64() -> None:
    secao("Base64")

    checa_igual(c.base64_codificar("abc"), "YWJj", "ASCII: o caso simples")
    checa_igual(c.base64_decodificar("YWJj"), "abc", "e a volta")
    checa_igual(c.base64_decodificar(c.base64_codificar(ACENTOS)), ACENTOS,
                "ida e volta com acentos preserva o texto")

    secao("*** A CODIFICACAO IMPORTA ***")
    em_utf8 = c.base64_codificar("ação", "utf-8")
    em_cp1252 = c.base64_codificar("ação", "cp1252")
    checa(em_utf8 != em_cp1252,
          f"'ação' em UTF-8 ({em_utf8}) e em cp1252 ({em_cp1252}) sao Base64 "
          f"DIFERENTES")
    checa_igual(c.base64_decodificar(em_cp1252, "cp1252"), "ação",
                "decodificando com o MESMO codec, o texto volta certo")
    checa(c.base64_decodificar(em_utf8, "cp1252") != "ação",
          "e com o codec ERRADO, volta diferente — por isso o parametro existe")

    # A seta U+2192 nao existe em cp1252. (O travessao "—" existe: cp1252 tem
    # 0x97, e usa-lo aqui daria um falso negativo.)
    checa_levanta(ConversaoInvalida, c.base64_codificar,
                  "caractere que nao existe em cp1252 avisa em vez de estourar",
                  "preço → 10", "cp1252")

    secao("Tolerancias deliberadas")
    with_quebras = "YWJj\nZGVm\n"
    checa_igual(c.base64_decodificar(with_quebras), "abcdef",
                "Base64 quebrado em linhas (como vem de e-mail e XML) e' aceito")
    checa_igual(c.base64_decodificar("  YWJj  "), "abc",
                "espaco em volta tambem")
    checa_igual(c.base64_decodificar("YWJjZA"), "abcd",
                "padding '=' faltando e' recomposto")
    # Alfabeto urlsafe: "+/" viram "-_".
    bruto = bytes([251, 255, 190])
    import base64 as b64
    padrao = b64.b64encode(bruto).decode()
    urlsafe = b64.urlsafe_b64encode(bruto).decode()
    checa(padrao != urlsafe, f"o alfabeto urlsafe e' mesmo diferente "
                             f"({padrao} vs {urlsafe})")
    checa_igual(c.base64_decodificar(urlsafe, "latin-1"),
                c.base64_decodificar(padrao, "latin-1"),
                "os dois alfabetos decodificam para o mesmo texto")

    secao("O que NAO e' tolerado")
    checa_levanta(ConversaoInvalida, c.base64_decodificar,
                  "caractere fora do alfabeto e' recusado (nao produz lixo)",
                  "isto nao e' base64!!!")
    checa_levanta(ConversaoInvalida, c.base64_decodificar,
                  "entrada vazia avisa", "   ")
    # Base64 valido cujos bytes nao sao texto: uma imagem, por exemplo.
    png = b64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00").decode()
    checa_levanta(ConversaoInvalida, c.base64_decodificar,
                  "Base64 de conteudo BINARIO explica o que aconteceu", png)
    try:
        c.base64_decodificar(png)
    except ConversaoInvalida as exc:
        checa("binario" in str(exc),
              f"e a mensagem cita 'binario': {str(exc)[:70]}...")


def testar_url() -> None:
    secao("URL")

    checa_igual(c.url_codificar("a b"), "a%20b", "espaco vira %20")
    checa_igual(c.url_codificar("ação"), "a%C3%A7%C3%A3o", "acentos em UTF-8")
    checa_igual(c.url_codificar("ação", "cp1252"), "a%E7%E3o",
                "e em cp1252 sao outros bytes")
    checa_igual(c.url_decodificar("a%C3%A7%C3%A3o"), "ação", "a volta")
    checa_igual(c.url_decodificar(c.url_codificar(ACENTOS)), ACENTOS,
                "ida e volta preserva")

    secao("safe='' — o comportamento que se quer num COMPONENTE")
    checa_igual(c.url_codificar("a/b?c=1&d"), "a%2Fb%3Fc%3D1%26d",
                "barra, interrogacao, igual e & sao TODOS escapados")
    checa("/" not in c.url_codificar("http://x/y"),
          "nem a barra de um URL colado e' preservada — e' um COMPONENTE")

    secao("'+' NAO vira espaco")
    checa_igual(c.url_decodificar("a+b"), "a+b",
                "'+' e' regra de formulario, nao de URL: trocar corromperia o dado")
    checa_igual(c.url_decodificar("a%2Bb"), "a+b",
                "o '+' de verdade vem escapado como %2B")

    checa_levanta(ConversaoInvalida, c.url_decodificar,
                  "%XX que nao forma texto no codec avisa",
                  "%E7%E3", "utf-8")


def testar_html() -> None:
    secao("HTML")

    checa_igual(c.html_codificar("<b>a & b</b>"), "&lt;b&gt;a &amp; b&lt;/b&gt;",
                "tags e & sao escapados")
    checa_igual(c.html_codificar('x="1"'), "x=&quot;1&quot;",
                "*** as ASPAS tambem: colar num atributo com aspa solta o abre ***")
    checa_igual(c.html_codificar("o'brien"), "o&#x27;brien",
                "e a apostrofe")
    checa_igual(c.html_decodificar("&lt;b&gt;&amp;&lt;/b&gt;"), "<b>&</b>",
                "a volta")
    checa_igual(c.html_decodificar("&ccedil;&atilde;o"), "ção",
                "entidades NOMEADAS")
    checa_igual(c.html_decodificar("&#231;&#x00e3;o"), "ção",
                "entidades numericas, decimais e hexadecimais")
    checa_igual(c.html_decodificar("100% & 50%"), "100% & 50%",
                "o que nao e' entidade fica como esta' (como no navegador)")
    checa_igual(c.html_decodificar(c.html_codificar(ACENTOS)), ACENTOS,
                "ida e volta preserva")
    checa_igual(c.html_codificar("ação"), "ação",
                "acentos NAO viram entidade: o arquivo ja' tem codificacao")


def testar_json() -> None:
    secao("JSON")

    checa_igual(c.json_escapar('a"b'), 'a\\"b', "aspas sao escapadas")
    checa_igual(c.json_escapar("a\nb"), "a\\nb", "quebra de linha vira \\n")
    checa_igual(c.json_escapar("a\\b"), "a\\\\b", "barra invertida e' dobrada")
    checa_igual(c.json_escapar("a\tb"), "a\\tb", "TAB vira \\t")
    checa_igual(c.json_escapar("ação"), "ação",
                "*** acentos NAO viram \\u00e7: JSON e' UTF-8 por especificacao ***")
    checa('"' not in c.json_escapar("abc"),
          "o resultado vem SEM as aspas em volta (para colar dentro de uma string)")

    checa_igual(c.json_desescapar("a\\nb"), "a\nb", "\\n vira quebra de verdade")
    checa_igual(c.json_desescapar('"a\\nb"'), "a\nb",
                "aceita tambem COM as aspas em volta")
    checa_igual(c.json_desescapar("\\u00e7\\u00e3o"), "ção",
                "\\uXXXX vira o caractere")
    checa_igual(c.json_desescapar(c.json_escapar(ACENTOS)), ACENTOS,
                "ida e volta preserva")
    checa_igual(c.json_desescapar('a"b'), 'a"b',
                "aspas nao escapadas no meio nao quebram o desescape")

    checa_levanta(ConversaoInvalida, c.json_desescapar,
                  "barra invertida solta avisa com mensagem util", "a\\qb")
    try:
        c.json_desescapar("a\\qb")
    except ConversaoInvalida as exc:
        checa("barra invertida" in str(exc),
              f"e a mensagem diz o que fazer: {str(exc)[:60]}...")
    checa_levanta(ConversaoInvalida, c.json_desescapar,
                  "um OBJETO json nao e' uma string: manda usar o formatador",
                  '{"a": 1}')
    checa_levanta(ConversaoInvalida, c.json_desescapar,
                  "e uma LISTA tambem", '[1, 2]')
    checa_igual(c.json_desescapar("123"), "123",
                "mas '123' NAO e' recusado como 'nao e uma string': e' texto")


def testar_registro() -> None:
    secao("Registro de comandos")

    from textforge.interface import acoes

    ids = set(acoes.REGISTRO.ids())
    faltando = [i for i in c.POR_COMANDO if i not in ids]
    checa_igual(faltando, [],
                "todo id em POR_COMANDO existe no registro de comandos")
    declarados = [i for i in ids if i.startswith("conv.")]
    sem_funcao = [i for i in declarados if i not in c.POR_COMANDO]
    checa_igual(sem_funcao, [],
                "e todo comando 'conv.*' declarado tem funcao")

    # A assinatura tem de ser uniforme: a janela chama todas do mesmo jeito.
    erros = []
    for id_, funcao in c.POR_COMANDO.items():
        try:
            funcao("abc", "utf-8")
        except ConversaoInvalida:
            pass
        except TypeError as exc:
            erros.append(f"{id_}: {exc}")
    checa_igual(erros, [],
                "todas aceitam (texto, codec) — a janela chama todas igual")


def main() -> int:
    testar_base64()
    testar_url()
    testar_html()
    testar_json()
    testar_registro()
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
