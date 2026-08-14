"""Empacota `dist\\TextForge\\` num ZIP, com um manifesto do que ha' dentro.

    .venv\\Scripts\\python.exe ferramentas\\empacotar_zip.py

So' faz sentido para o modo ONE-DIR: no one-file o `.exe` ja' e' autocontido e
zipar um arquivo unico nao ajuda ninguem.

Por que o manifesto existe: "o que eu preciso copiar junto?" e' a primeira pergunta
de quem recebe a pasta, e a resposta -- 169 arquivos -- nao serve como resposta. O
manifesto agrupa por FUNCAO e diz o que quebra se cada grupo faltar, que e' a forma
util da mesma informacao.
"""

from __future__ import annotations

import pathlib
import sys
import zipfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# (prefixo do caminho relativo, rotulo, o que quebra sem isso). O primeiro que
# casar manda. A ordem vai do mais especifico para o mais geral.
GRUPOS: tuple[tuple[str, str, str], ...] = (
    ("TextForge.exe", "O programa",
     "e' o que voce executa. Sozinho ele NAO funciona"),
    ("_internal/textforge/recursos", "Recursos do TextForge",
     "temas e icone; sem eles a janela abre sem cor e sem icone"),
    ("_internal/PySide6/plugins/platforms", "Plugin de plataforma do Qt",
     "o qwindows.dll. Sem ele: 'no Qt platform plugin could be initialized'"),
    ("_internal/PySide6/plugins/styles", "Estilo do Qt",
     "sem ele a janela perde o visual nativo"),
    ("_internal/PySide6/plugins", "Outros plugins do Qt",
     "imagens (o icone .ico), TLS, rede"),
    ("_internal/PySide6/translations", "Traducoes do Qt",
     "os textos dos dialogos padrao do Qt"),
    ("_internal/PySide6", "Qt e PySide6",
     "a interface inteira. E' a maior parte do tamanho"),
    ("_internal/shiboken6", "Ponte Python<->C++",
     "sem ela o PySide6 nao carrega"),
    ("_internal/charset_normalizer", "Deteccao de codificacao",
     "sem ela, arquivo em cp1252 pode ser lido errado"),
    ("_internal/python313.dll", "Interpretador Python",
     "sem ele nada roda"),
    ("_internal/base_library.zip", "Biblioteca padrao do Python",
     "json, csv, mmap, codecs, hashlib..."),
    ("_internal", "Bibliotecas de apoio",
     "DLLs do sistema e do Python"),
)


def grupo_de(relativo: str) -> tuple[str, str]:
    alvo = relativo.replace("\\", "/")
    for prefixo, rotulo, porque in GRUPOS:
        if alvo == prefixo or alvo.startswith(prefixo + "/"):
            return rotulo, porque
    return "Outros", ""


def humano(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    if bytes_ >= 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_} B"


def montar_manifesto(pasta: pathlib.Path, versao: str) -> str:
    arquivos = sorted(p for p in pasta.rglob("*") if p.is_file())
    por_grupo: dict[str, list[pathlib.Path]] = {}
    porques: dict[str, str] = {}
    for arquivo in arquivos:
        relativo = str(arquivo.relative_to(pasta))
        rotulo, porque = grupo_de(relativo)
        por_grupo.setdefault(rotulo, []).append(arquivo)
        porques.setdefault(rotulo, porque)

    total = sum(a.stat().st_size for a in arquivos)
    linhas = [
        f"TextForge {versao} — arquivos do pacote (modo one-dir)",
        "=" * 74,
        "",
        f"{len(arquivos)} arquivos, {humano(total)} no total.",
        "",
        "IMPORTANTE: e' preciso copiar a PASTA INTEIRA. O TextForge.exe tem",
        f"{humano((pasta / 'TextForge.exe').stat().st_size)} e nao funciona sozinho"
        " -- todo o resto esta' em _internal\\.",
        "Se voce quer um arquivo unico, gere o portatil: build.bat umarquivo",
        "",
        "Nada aqui precisa ser instalado, e nada e' escrito fora da pasta do",
        "programa e de %APPDATA%\\TextForge. Nao precisa de administrador.",
        "",
        "-" * 74,
        "POR GRUPO",
        "-" * 74,
        "",
    ]
    # Do maior para o menor: e' a ordem que responde "por que sao 99 MB?".
    ordenados = sorted(por_grupo.items(),
                       key=lambda kv: -sum(a.stat().st_size for a in kv[1]))
    for rotulo, lista in ordenados:
        tamanho = sum(a.stat().st_size for a in lista)
        linhas.append(f"{rotulo}  —  {len(lista)} arquivo(s), {humano(tamanho)}")
        if porques.get(rotulo):
            linhas.append(f"    {porques[rotulo]}")
        # Os maiores de cada grupo, para o leitor ver onde o tamanho esta'.
        maiores = sorted(lista, key=lambda a: -a.stat().st_size)[:5]
        for arquivo in maiores:
            linhas.append(f"    {humano(arquivo.stat().st_size):>9}  "
                          f"{arquivo.relative_to(pasta)}")
        if len(lista) > 5:
            linhas.append(f"        (+{len(lista) - 5} arquivo(s) menores)")
        linhas.append("")

    linhas += ["-" * 74, "LISTA COMPLETA", "-" * 74, ""]
    for arquivo in arquivos:
        linhas.append(f"{humano(arquivo.stat().st_size):>9}  "
                      f"{arquivo.relative_to(pasta)}")
    return "\n".join(linhas) + "\n"


def main() -> int:
    from textforge import VERSAO

    pasta = RAIZ / "dist" / "TextForge"
    if not pasta.is_dir():
        print(f"ERRO: {pasta} nao existe. Rode `build.bat` primeiro.")
        return 1

    manifesto = montar_manifesto(pasta, VERSAO)
    caminho_manifesto = RAIZ / "dist" / f"TextForge-{VERSAO}-arquivos.txt"
    caminho_manifesto.write_text(manifesto, encoding="utf-8")

    destino = RAIZ / "dist" / f"TextForge-{VERSAO}-win64.zip"
    if destino.exists():
        destino.unlink()
    arquivos = sorted(p for p in pasta.rglob("*") if p.is_file())
    # ZIP_DEFLATED, e nao ZIP_STORED: sao ~99 MB de DLL, que comprimem bem. E o
    # ZIP fica com a pasta "TextForge/" na raiz de proposito -- extrair no
    # Explorer produz a pasta certa em vez de despejar 169 arquivos onde o
    # usuario estiver.
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zip_:
        for arquivo in arquivos:
            zip_.write(arquivo, f"TextForge/{arquivo.relative_to(pasta)}")
        zip_.writestr("TextForge/ARQUIVOS.txt", manifesto)
        for extra in ("README.md", "LICENSE", "associar.ps1"):
            if (RAIZ / extra).is_file():
                zip_.write(RAIZ / extra, f"TextForge/{extra}")

    bruto = sum(a.stat().st_size for a in arquivos)
    print(f"{destino}")
    print(f"  {humano(destino.stat().st_size)} zipado "
          f"(de {humano(bruto)} em {len(arquivos)} arquivos)")
    print(f"{caminho_manifesto}")
    print(f"  o manifesto tambem vai DENTRO do zip, como ARQUIVOS.txt")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    sys.exit(main())
