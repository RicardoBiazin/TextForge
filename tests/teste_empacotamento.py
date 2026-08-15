"""Conferencias ESTATICAS do empacotamento (etapa 12).

    .\\.venv\\Scripts\\python.exe tests\\teste_empacotamento.py

Nenhum build e' feito aqui -- empacotar leva minutos e exige o pyinstaller. O que
esta suite pega sao os erros que so' apareceriam NA MAQUINA DO USUARIO:

  * um tema novo em `recursos/` que nao entrou no `datas` -> "as cores sumiram";
  * uma linguagem nova em `linguagens/` que ninguem registrou -> "o realce nao
    funciona nesse arquivo";
  * `PySide6.QtNetwork` na lista de excludes -> a instancia unica e o "Abrir com"
    morrem, e SO' no .exe;
  * `versao.txt` desatualizado -> o usuario relata a versao errada nas
    propriedades do arquivo, e o bug fica impossivel de reproduzir;
  * `associar.ps1` salvo sem BOM -> o PowerShell 5.1 le' como ANSI e destroi todos
    os acentos das mensagens.

Sem Qt: e' leitura de arquivo e de fonte.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

from ajudantes import RAIZ, checa, checa_igual, resumir, secao

PACOTE = RAIZ / "textforge"
SPEC = RAIZ / "TextForge.spec"


def ler(caminho: pathlib.Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace")


def _lista_do_spec(fonte: str, nome: str) -> list[str]:
    """Le' uma lista literal do .spec pela ARVORE, e nao por busca de texto.

    O .spec e' Python valido, entao `ast` da' a lista de verdade. Procurar o nome
    de um modulo no texto acusaria os COMENTARIOS -- e o comentario que explica
    por que QtNetwork nao pode ser excluido seria lido como a exclusao dele.
    """
    arvore = ast.parse(fonte)
    for no in ast.walk(arvore):
        # Lista OU tupla: no .spec `excludes` e' lista e `DLLS_DESNECESSARIAS` e'
        # tupla, e o teste nao deve depender de qual foi escolhida.
        if (isinstance(no, ast.Assign) and no.targets
                and isinstance(no.targets[0], ast.Name)
                and no.targets[0].id == nome
                and isinstance(no.value, (ast.List, ast.Tuple))):
            return [e.value for e in no.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


# ===========================================================================


def testar_arquivos_do_projeto() -> None:
    secao("Arquivos que o build precisa")

    for nome in ("TextForge.spec", "build.bat", "versao.txt",
                 "textforge.manifest", "associar.ps1", "requirements.txt",
                 "LICENSE", "README.md", "app.py"):
        checa((RAIZ / nome).is_file(), f"{nome} existe")

    checa((RAIZ / "CLAUDE.md").is_file(),
          "CLAUDE.md existe (as convencoes do projeto para quem editar depois)")


def testar_recursos_no_spec() -> None:
    secao("Todo recurso entra no pacote")

    spec = ler(SPEC)
    pasta = PACOTE / "recursos"
    checa(pasta.is_dir(), "a pasta textforge/recursos existe")

    arquivos = [p for p in pasta.rglob("*") if p.is_file()]
    checa(len(arquivos) >= 2, f"ha' {len(arquivos)} arquivo(s) em recursos/")

    # A regra do spec e' incluir a PASTA inteira. Conferir isso e' melhor que
    # listar arquivo por arquivo: um tema novo entra sem ninguem tocar no spec.
    checa('"recursos"' in spec or "'recursos'" in spec
          or 'recursos"' in spec,
          "o .spec inclui a pasta recursos/ inteira em `datas`")
    checa("textforge/recursos" in spec,
          "e a leva para o destino textforge/recursos dentro do pacote")

    temas = list((pasta / "temas").glob("*.json"))
    checa(len(temas) >= 2,
          f"ha' pelo menos dois temas ({', '.join(t.stem for t in temas)})")


def testar_linguagens_registradas() -> None:
    secao("*** Toda linguagem do pacote esta' registrada ***")

    pasta = PACOTE / "linguagens"
    # Um modulo conta como "de linguagem" quando define PROVEDORES -- e nao por
    # uma lista de excecoes escrita a mao. `base.py`, `registro.py` e
    # `generico.py` sao infraestrutura: nao registram nada e nao precisam entrar
    # no __init__ nem no hiddenimports.
    modulos = sorted(p.stem for p in pasta.glob("*.py")
                     if p.stem != "__init__"
                     and re.search(r"^PROVEDORES\s*=", ler(p), re.MULTILINE))
    checa(len(modulos) >= 10, f"ha' {len(modulos)} modulos que definem PROVEDORES")

    fonte = ler(pasta / "__init__.py")
    faltando = [m for m in modulos if not re.search(rf"\b{re.escape(m)}\b", fonte)]
    checa_igual(faltando, [],
                "todo modulo de linguagem e' citado no __init__ "
                "(criar lua.py e esquecer de registrar falha AQUI)")

    # E o `hiddenimports` do spec tem de conhecer todos: eles sao importados
    # dentro de funcao, e o PyInstaller nao os enxerga sozinho.
    spec = ler(SPEC)
    fora_do_spec = [m for m in modulos
                    if f"textforge.linguagens.{m}" not in spec]
    checa_igual(fora_do_spec, [],
                "e todo modulo esta' no `hiddenimports` do .spec "
                "(importacao tardia e' invisivel para a analise estatica)")


def testar_excludes() -> None:
    secao("Excludes: o que NAO pode entrar na lista")

    spec = ler(SPEC)
    excluidos = _lista_do_spec(spec, "excludes")
    checa(len(excluidos) > 10, f"o .spec exclui {len(excluidos)} modulos")

    # A lista e' lida da ARVORE, e nao procurada no texto: o proprio .spec
    # EXPLICA em comentario por que QtNetwork nao pode ser excluido, e uma busca
    # textual acusaria esse comentario como se fosse a exclusao.
    checa("PySide6.QtNetwork" not in excluidos,
          "*** PySide6.QtNetwork NAO esta' nos excludes "
          "(e' onde vivem QLocalServer/QLocalSocket: instancia unica e Abrir com) ***")
    checa("QtNetwork" in spec,
          "e o motivo esta' escrito no proprio .spec, como comentario")
    checa("PySide6.QtTest" in excluidos,
          "QtTest esta' excluido de proposito (os testes rodam do FONTE)")

    for proibido in ("QtWebEngineCore", "QtQuick", "QtCharts", "QtMultimedia",
                     "tkinter", "numpy", "pandas", "PyQt5", "PyQt6"):
        checa(any(proibido in e for e in excluidos),
              f"{proibido} esta' excluido do pacote")

    secao("Opcoes que nao podem mudar sem intencao")
    checa("uac_admin=False" in spec,
          "*** uac_admin=False: elevado, o arrastar-e-soltar do Explorer PARA "
          "de funcionar ***")
    checa("console=False" in spec, "console=False (e' programa de janela)")
    checa("disable_windowed_traceback=False" in spec,
          "disable_windowed_traceback=False: sem isso um erro fica invisivel")
    checa("optimize=1" in spec,
          "optimize=1, e nao 2 (o 2 apagaria os docstrings)")
    for dll in ("Qt6Core.dll", "python313.dll", "qwindows.dll"):
        checa(dll in spec, f"{dll} esta' fora do UPX (custo de partida e antivirus)")

    secao("DLLs descartadas do pacote")

    descartadas = _lista_do_spec(spec, "DLLS_DESNECESSARIAS")
    checa(len(descartadas) >= 4,
          f"o .spec descarta {len(descartadas)} DLL(s) que vinham por dependencia")
    for esperada in ("libcrypto-3.dll", "libssl-3.dll", "opengl32sw.dll"):
        checa(esperada in descartadas, f"{esperada} esta' na lista")
    # A remocao e' feita sobre `a.binaries`, e nao por `excludes`: aquele age sobre
    # MODULOS Python, e estas sao bibliotecas nativas.
    checa("a.binaries = [" in spec,
          "e sao filtradas de `a.binaries` (excludes nao pega DLL nativa)")
    checa("qschannelbackend" in spec,
          "*** o .spec registra que o Qt continua com TLS pelo Schannel do "
          "Windows -- e' o que torna seguro tirar o OpenSSL ***")
    checa("QT_OPENGL=software" in spec,
          "*** e registra a MEDICAO que justifica tirar o opengl32sw ***")
    checa("nao foi possivel testar" in spec.lower()
          or "NAO FOI POSSIVEL TESTAR" in spec,
          "e declara o que NAO foi possivel testar (RDP, driver quebrado)")


def testar_versao() -> None:
    secao("*** versao.txt bate com __version__ ***")

    from textforge import VERSAO

    texto = ler(RAIZ / "versao.txt")
    partes = VERSAO.split(".")
    checa(len(partes) == 3, f"a versao do pacote e' {VERSAO}")

    esperado_tupla = f"({partes[0]}, {partes[1]}, {partes[2]}, 0)"
    checa(f"filevers={esperado_tupla}" in texto,
          f"filevers e' {esperado_tupla}")
    checa(f"prodvers={esperado_tupla}" in texto,
          f"prodvers e' {esperado_tupla}")
    checa(f"'FileVersion', '{VERSAO}'" in texto,
          f"a string FileVersion e' '{VERSAO}'")
    checa(f"'ProductVersion', '{VERSAO}'" in texto,
          f"a string ProductVersion e' '{VERSAO}'")

    manifesto = ler(RAIZ / "textforge.manifest")
    checa(f'version="{VERSAO}.0"' in manifesto,
          f"e o manifesto declara {VERSAO}.0")


def testar_manifesto() -> None:
    secao("Manifesto do Windows")

    texto = ler(RAIZ / "textforge.manifest")
    checa('level="asInvoker"' in texto,
          "*** asInvoker, nunca requireAdministrator (mataria o drag-and-drop) ***")
    checa("longPathAware" in texto and ">true<" in texto,
          "longPathAware: caminho de rede passa de 260 caracteres facil")
    checa("PerMonitorV2" in texto,
          "DPI por monitor: sem isso a fonte borra ao trocar de tela")

    # Tem de ser XML bem formado -- o compilador de recurso nao perdoa.
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(texto)
        checa(True, "o manifesto e' XML bem formado")
    except ET.ParseError as exc:
        checa(False, f"o manifesto e' XML bem formado ({exc})")


def testar_build_bat() -> None:
    secao("build.bat")

    texto = ler(RAIZ / "build.bat")
    checa("chcp 65001" in texto,
          "chcp 65001: sem isso os acentos das mensagens saem como lixo")
    checa(".venv\\Scripts\\python.exe" in texto,
          "*** usa o python do .venv, e nunca o `python` do PATH "
          "(o pyinstaller global esta' no 3.14, que nao tem PySide6) ***")
    checa("rodar_todos.py" in texto,
          "roda a suite ANTES de empacotar")
    checa("--autoverificacao" in texto,
          "*** e roda a fumaca do .exe DEPOIS "
          "(excludes agressivos quebram so' em tempo de execucao) ***")
    checa("TEXTFORGE_UM_ARQUIVO" in texto, "serve os dois modos de empacotamento")
    checa("associar.ps1" in texto, "e diz como registrar no 'Abrir com'")
    checa("empacotar_zip.py" in texto,
          "gera o ZIP do one-dir (o .exe sozinho nao funciona nesse modo)")
    checa("NAO funciona sozinho" in texto,
          "*** e AVISA disso no fim do build, onde alguem vai ler ***")

    zipador = RAIZ / "ferramentas" / "empacotar_zip.py"
    checa(zipador.is_file(), "ferramentas/empacotar_zip.py existe")
    fonte_zip = ler(zipador)
    checa("ZIP_DEFLATED" in fonte_zip,
          "o ZIP e' comprimido (sao ~99 MB de DLL, que comprimem bem)")
    checa('"TextForge/' in fonte_zip,
          "e tem a pasta TextForge/ na raiz — extrair no Explorer nao despeja "
          "169 arquivos onde o usuario estiver")
    checa("ARQUIVOS.txt" in fonte_zip,
          "o manifesto vai DENTRO do zip, onde quem recebe vai procurar")


def testar_associar_ps1() -> None:
    secao("associar.ps1")

    caminho = RAIZ / "associar.ps1"
    bruto = caminho.read_bytes()
    checa(bruto.startswith(b"\xef\xbb\xbf"),
          "*** salvo em UTF-8 COM BOM: o PowerShell 5.1 le' sem BOM como ANSI "
          "e destroi os acentos ***")

    texto = bruto.decode("utf-8-sig")
    checa("OpenWithProgids" in texto,
          "*** usa OpenWithProgids: ACRESCENTA ao 'Abrir com' sem roubar o padrao ***")
    checa("HKLM" not in texto,
          "*** nao escreve em HKLM: nenhum privilegio de administrador ***")
    checa(texto.count("HKCU:") >= 5, "escreve so' em HKCU")
    checa("-Remover" in texto or "Remover" in texto, "tem modo de remocao")
    checa("Simular" in texto, "e modo de simulacao")
    checa("SHChangeNotify" in texto,
          "notifica o Explorer para a mudanca aparecer sem reiniciar")
    checa("ValueFromRemainingArguments" in texto,
          "registra SOMENTE as extensoes passadas (requisito 33)")
    checa("Mostrar mais op" in texto,
          "e avisa que no Windows 11 o item fica em 'Mostrar mais opcoes'")


def testar_imports_proibidos() -> None:
    secao("*** Nenhum modulo importa Qt que nao empacotamos ***")

    proibidos = ("QtWebEngineCore", "QtWebEngineWidgets", "QtQuick", "QtQml",
                 "QtCharts", "QtMultimedia", "Qt3DCore", "QtSql",
                 "QtDataVisualization", "PyQt5", "PyQt6")
    culpados: list[str] = []
    for arquivo in PACOTE.rglob("*.py"):
        fonte = ler(arquivo)
        try:
            arvore = ast.parse(fonte)
        except SyntaxError as exc:
            checa(False, f"{arquivo.name} nao compila: {exc}")
            continue
        # A ARVORE, e nao o texto: um comentario CITANDO QtWebEngine para explicar
        # por que ele e' excluido nao pode reprovar o teste.
        for no in ast.walk(arvore):
            nomes: list[str] = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or ""]
                nomes += [f"{no.module}.{a.name}" for a in no.names]
            for nome in nomes:
                for proibido in proibidos:
                    if proibido in nome:
                        culpados.append(
                            f"{arquivo.relative_to(RAIZ)}: {nome}")
    checa_igual(sorted(set(culpados)), [],
                f"nenhum dos {len(proibidos)} modulos proibidos e' importado")


def testar_requirements() -> None:
    secao("requirements.txt")

    texto = ler(RAIZ / "requirements.txt")
    checa("PySide6-Essentials" in texto,
          "*** pede PySide6-Essentials, e NAO o metapacote PySide6 "
          "(que arrasta 169 MB de Addons que nao usamos) ***")
    linhas = [l.strip() for l in texto.splitlines()
              if l.strip() and not l.strip().startswith("#")]
    # TETO em toda dependencia. Aqui as faixas sao `>=x,<y` em vez do `==` que o
    # plano previa: fixar a versao exata obrigaria a mexer no arquivo a cada
    # correcao de seguranca do PySide6. O que de fato protege o build e' o TETO --
    # e' ele que impede um major novo entrar sozinho e quebrar o empacotamento.
    sem_teto = [l for l in linhas if "<" not in l and "==" not in l]
    checa_igual(sem_teto, [],
                f"todas as {len(linhas)} dependencias tem TETO de versao "
                "(um major novo nao entra sozinho)")
    checa(all(">=" in l or "==" in l for l in linhas),
          "e todas tem piso tambem")
    checa(not any(l.startswith("PySide6==") or l.startswith("PySide6>=")
                  for l in linhas),
          "e o metapacote PySide6 nao aparece por engano")

    extras = RAIZ / "requirements-extras.txt"
    checa(extras.is_file(), "requirements-extras.txt existe")
    texto_extras = ler(extras)
    for opcional in ("lxml", "black"):
        checa(opcional in texto_extras,
              f"{opcional} esta' declarado como OPCIONAL, e nao obrigatorio")
        checa(opcional not in texto,
              f"e {opcional} NAO esta' no requirements.txt (o app roda sem ele)")


def testar_autoverificacao() -> None:
    secao("A flag --autoverificacao")

    fonte = ler(RAIZ / "app.py")
    checa("--autoverificacao" in ler(RAIZ / "textforge" / "cli.py"),
          "a flag esta' declarada no cli.py")
    checa("_autoverificar" in fonte, "e o app.py a implementa")
    checa("QtNetwork" in fonte,
          "*** e a autoverificacao confere QtNetwork: e' o exclude que mataria "
          "o 'Abrir com' sem nenhum sintoma no build ***")
    checa("offscreen" in fonte,
          "roda em modo offscreen (nao pisca janela durante o build)")
    checa("charset_normalizer" in fonte,
          "e confere o charset-normalizer, que e' import tardio")


def main() -> int:
    testar_arquivos_do_projeto()
    testar_recursos_no_spec()
    testar_linguagens_registradas()
    testar_excludes()
    testar_versao()
    testar_manifesto()
    testar_build_bat()
    testar_associar_ps1()
    testar_imports_proibidos()
    testar_requirements()
    testar_autoverificacao()
    return resumir()


if __name__ == "__main__":
    sys.exit(main())
