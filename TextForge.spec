# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller. VERSIONADA de proposito.

Nos outros projetos desta maquina o `*.spec` esta' no .gitignore, porque e' gerado
por um `empacotar.py`. Aqui ele e' versionado -- junto com `versao.txt`,
`textforge.manifest` e o icone -- para o build ser reproduzivel numa maquina que nao
tenha Pillow instalado para regerar o icone. Esta nota tambem esta' no .gitignore,
para ninguem "corrigir" a diferenca depois.

Dois modos, escolhidos pela variavel de ambiente TEXTFORGE_UM_ARQUIVO:

  vazia  ONE-DIR (padrao)  a PASTA dist\TextForge inteira, 99 MB em 169 arquivos.
                           O TextForge.exe tem 2,7 MB e NAO funciona sozinho -- o
                           resto esta' em _internal\. Parte em ~1 s.
  "1"    ONE-FILE          UM arquivo de 38 MB que funciona sozinho, mas
                           descompacta em %TEMP% a CADA abertura: ~4 a 6 s de
                           partida. Bom para pendrive, ruim para um editor aberto
                           dezenas de vezes por dia.

Os numeros acima foram MEDIDOS nesta maquina, e nao estimados. O one-file tambem
aparece como DOIS processos no Gerenciador de Tarefas (o bootloader que descompacta
e o programa de verdade) -- e' normal do PyInstaller, e nao um segundo TextForge.
"""

import os
import pathlib

RAIZ = pathlib.Path(os.getcwd())
UM_ARQUIVO = os.environ.get("TEXTFORGE_UM_ARQUIVO") == "1"

# Tudo em `recursos/` entra. O `teste_empacotamento.py` confere que nenhum arquivo
# de la' ficou de fora -- um tema esquecido so' apareceria como "cores erradas" na
# maquina do usuario, nunca aqui.
datas = [(str(RAIZ / "textforge" / "recursos"), "textforge/recursos")]
for extra in ("LICENSE", "README.md"):
    if (RAIZ / extra).is_file():
        datas.append((str(RAIZ / extra), "."))

hiddenimports = [
    # Importados tardiamente, dentro de funcao, e por isso invisiveis para a
    # analise estatica do PyInstaller.
    "charset_normalizer",
    "textforge.linguagens.c_like", "textforge.linguagens.csv_",
    "textforge.linguagens.css", "textforge.linguagens.html",
    "textforge.linguagens.ini_", "textforge.linguagens.javascript",
    "textforge.linguagens.json_", "textforge.linguagens.markdown",
    "textforge.linguagens.php", "textforge.linguagens.python_",
    "textforge.linguagens.shell", "textforge.linguagens.sql",
    "textforge.linguagens.texto", "textforge.linguagens.xml_",
    "textforge.linguagens.yaml_",
]

excludes = [
    # Modulos Qt que o projeto nao usa. Vem do PySide6-Essentials; o metapacote
    # PySide6 traria muito mais (QtWebEngine, Qt3D, Charts, Multimedia) e por isso
    # o requirements.txt pede o -Essentials.
    #
    # ATENCAO: `PySide6.QtNetwork` NAO entra nesta lista, por mais que pareca um
    # recurso de rede dispensavel. E' onde vivem QLocalServer e QLocalSocket, ou
    # seja, a instancia unica e o "Abrir com" do Explorer. Excluir mata os dois.
    #
    # `PySide6.QtTest` e' excluido de PROPOSITO: os testes rodam do FONTE, e nunca
    # do .exe. Isso esta' escrito aqui para ninguem "consertar" o build depois de
    # um teste falhar.
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSql",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvgWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    # Bibliotecas que nao usamos e que outro pacote poderia arrastar.
    "tkinter", "unittest", "pydoc_data", "numpy", "pandas", "PIL",
    "matplotlib", "scipy", "pytest", "setuptools", "pip", "wheel",
    "PyQt5", "PyQt6",
]

# UPX NAO nas DLLs grandes do Qt e do Python: comprimir custa tempo de PARTIDA
# toda vez que o programa abre, e e' a maior fonte de falso positivo de antivirus
# em executavel Python.
upx_exclude = [
    "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll",
    "Qt6Svg.dll", "Qt6Pdf.dll", "python313.dll", "python3.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll",
    "qwindows.dll",
]

a = Analysis(
    ["app.py"],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,          # remove asserts; NAO usa 2, que apagaria os docstrings
)
pyz = PYZ(a.pure)

_icone = RAIZ / "textforge" / "recursos" / "icone.ico"
icone = str(_icone) if _icone.is_file() else None
versao = str(RAIZ / "versao.txt") if (RAIZ / "versao.txt").is_file() else None
manifesto = (str(RAIZ / "textforge.manifest")
             if (RAIZ / "textforge.manifest").is_file() else None)

comum = dict(
    name="TextForge",
    # console=False: e' um programa de janela. A consequencia -- que um erro nao
    # tratado fica TOTALMENTE invisivel -- e' coberta pelo excepthook global do
    # relatorio_de_erro.py, que grava %APPDATA%\TextForge\erro.log.
    console=False,
    disable_windowed_traceback=False,
    # uac_admin=False, e nao e' negociavel: um editor nunca pede administrador, e
    # ELEVADO o arrastar-e-soltar do Explorer PARA DE FUNCIONAR (regra de
    # integridade obrigatoria do Windows), o que mataria o requisito 19.
    uac_admin=False,
    icon=icone,
    version=versao,
    manifest=manifesto,
    upx=True,
    upx_exclude=upx_exclude,
)

if UM_ARQUIVO:
    splash = None
    if (RAIZ / "splash.png").is_file():
        # No modo um-arquivo a partida leva segundos descompactando em %TEMP%.
        # Sem splash, o usuario clica de novo achando que nao abriu.
        splash = Splash(str(RAIZ / "splash.png"), binaries=a.binaries,
                        datas=a.datas, text_pos=None, always_on_top=False)
    partes = [pyz, a.scripts, a.binaries, a.datas]
    if splash is not None:
        partes = [pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas]
    exe = EXE(*partes, [], strip=False, runtime_tmpdir=None, **comum)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, strip=False, **comum)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
                   upx_exclude=upx_exclude, name="TextForge")
