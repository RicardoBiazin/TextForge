@echo off
chcp 65001 >nul
setlocal

rem ===========================================================================
rem  build.bat            gera dist\TextForge\TextForge.exe   (one-dir, padrao)
rem  build.bat umarquivo  gera dist\TextForge.exe             (one-file portatil)
rem
rem  SEMPRE o python do .venv, e nunca o `python` do PATH. O pyinstaller desta
rem  maquina esta' instalado no Python 3.14 global, que NAO tem PySide6 -- um
rem  build.bat chamando `python` puro falharia no meio, depois de dois minutos de
rem  analise, com um erro sobre PySide6 ausente que nao diz nada sobre a causa.
rem ===========================================================================

cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo ERRO: nao encontrei "%PY%"
    echo.
    echo Monte o ambiente primeiro:
    echo     py -3.13 -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo     .venv\Scripts\python.exe -m pip install pyinstaller==6.21.0
    echo.
    exit /b 1
)

"%PY%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo ERRO: pyinstaller nao esta' instalado NO VENV.
    echo     "%PY%" -m pip install pyinstaller==6.21.0
    exit /b 1
)

rem -- 1. A suite roda ANTES de empacotar --------------------------------------
rem Empacotar codigo quebrado so' adianta a descoberta do problema para depois de
rem o usuario instalar. A suite leva ~5 min por causa do teste de arquivo grande.
echo.
echo === [1/4] Rodando a suite de testes ===
"%PY%" -u tests\rodar_todos.py
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: a suite falhou. Corrija antes de empacotar.
    exit /b 1
)

rem -- 2. Empacotar ------------------------------------------------------------
echo.
if /i "%~1"=="umarquivo" (
    echo === [2/4] Empacotando ONE-FILE ===
    echo.
    echo     AVISO: o modo um-arquivo descompacta ~38 MB em %%TEMP%% a CADA
    echo     abertura. MEDIDO nesta maquina: 4 a 6 segundos de partida, contra
    echo     ~1 s do one-dir. Num editor aberto dezenas de vezes por dia isso
    echo     briga com o requisito 34. Use-o para pendrive; para uso diario,
    echo     prefira o one-dir.
    echo.
    set "TEXTFORGE_UM_ARQUIVO=1"
) else (
    echo === [2/4] Empacotando ONE-DIR ===
    set "TEXTFORGE_UM_ARQUIVO="
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

"%PY%" -m PyInstaller --noconfirm --clean TextForge.spec
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: o PyInstaller falhou.
    exit /b 1
)

rem -- 3. Fumaca do executavel -------------------------------------------------
rem `excludes` agressivos quebram o app SO' em tempo de execucao. Sem esta
rem checagem, "os excludes quebraram o app" viraria relatorio de bug do usuario em
rem vez de falha de build.
echo.
echo === [3/4] Autoverificacao do executavel gerado ===
set "EXE=dist\TextForge\TextForge.exe"
if /i "%~1"=="umarquivo" set "EXE=dist\TextForge.exe"

if not exist "%EXE%" (
    echo ERRO: "%EXE%" nao foi gerado.
    exit /b 1
)

"%EXE%" --autoverificacao
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: o executavel NAO passou na autoverificacao.
    echo Causa mais provavel: um modulo na lista `excludes` do TextForge.spec
    echo e' usado em tempo de execucao. Veja %%APPDATA%%\TextForge\erro.log
    exit /b 1
)

rem -- 4. ZIP, so' no one-dir -------------------------------------------------
rem O one-file ja' e' um arquivo autocontido: zipar um arquivo unico nao ajuda
rem ninguem. No one-dir o ZIP e' o unico jeito de entregar o programa sem alguem
rem copiar so' o .exe e descobrir que ele nao funciona.
if /i not "%~1"=="umarquivo" (
    echo.
    echo === [4/4] Gerando o ZIP e o manifesto de arquivos ===
    "%PY%" ferramentas\empacotar_zip.py
    if errorlevel 1 (
        echo AVISO: o ZIP nao foi gerado. O build em dist\TextForge continua valido.
    )
)

echo.
echo ============================================================
echo  BUILD OK
echo  Executavel: %EXE%
for %%F in ("%EXE%") do echo  Tamanho do .exe: %%~zF bytes
if /i not "%~1"=="umarquivo" (
    echo.
    echo  ATENCAO: o .exe do one-dir NAO funciona sozinho. Para distribuir,
    echo  use o ZIP acima ^(ou gere o portatil: build.bat umarquivo^).
)
echo.
echo  Para registrar em "Abrir com" (sem admin, so' HKCU):
echo      powershell -ExecutionPolicy Bypass -File associar.ps1 .log .xml .csv
echo  Para desfazer:
echo      powershell -ExecutionPolicy Bypass -File associar.ps1 -Remover
echo ============================================================
endlocal
