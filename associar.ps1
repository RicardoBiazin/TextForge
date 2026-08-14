<#
.SYNOPSIS
    Registra o TextForge em "Abrir com" para as extensões que você escolher.

.DESCRIPTION
    Escreve APENAS em HKCU — nenhum privilégio de administrador é necessário, e
    nada fora do seu perfil é tocado.

    O ponto que importa: usa OpenWithProgids, que ACRESCENTA o TextForge à lista
    "Abrir com" da extensão SEM roubar o programa padrão. Abrir um .xml continua
    abrindo no que você já usava; o TextForge passa a ser uma opção.

    Registra SOMENTE as extensões passadas como argumento (requisito 33). Não há
    lista embutida de "extensões que um editor deveria pegar" — de propósito.

.PARAMETER Extensoes
    As extensões, com ou sem ponto: .log xml .csv

.PARAMETER Exe
    Caminho do TextForge.exe. Por padrão procura em dist\TextForge\ e em dist\.

.PARAMETER Remover
    Desfaz tudo o que este script criou.

.PARAMETER Simular
    Mostra o que seria feito, sem escrever nada no registro.

.EXAMPLE
    .\associar.ps1 .log .xml .csv
.EXAMPLE
    .\associar.ps1 -Remover
.EXAMPLE
    .\associar.ps1 .log -Simular

.NOTES
    ESTE ARQUIVO PRECISA ESTAR EM UTF-8 **COM BOM**. O PowerShell 5.1 lê arquivo
    sem BOM como ANSI, e todos os acentos das mensagens viram lixo.

    No Windows 11 o item do menu de contexto aparece em "Mostrar mais opções". O
    menu novo exige uma extensão de shell IExplorerCommand empacotada em MSIX, que
    não sai de um script — e prometer o contrário seria enganar quem lê.
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Extensoes,
    [string] $Exe = "",
    [switch] $Remover,
    [switch] $Simular
)

$ErrorActionPreference = "Stop"
$ProgID  = "TextForge.arquivo"
$AppExe  = "TextForge.exe"
$Raiz    = Split-Path -Parent $MyInvocation.MyCommand.Path

function Escrever($mensagem, $cor = "Gray") {
    Write-Host $mensagem -ForegroundColor $cor
}

function Definir-Chave($caminho, $nome, $valor) {
    if ($Simular) {
        Escrever "  [simulacao] $caminho :: $(if ($nome) { $nome } else { '(padrao)' }) = $valor"
        return
    }
    if (-not (Test-Path $caminho)) { New-Item -Path $caminho -Force | Out-Null }
    if ($nome) {
        New-ItemProperty -Path $caminho -Name $nome -Value $valor -PropertyType String -Force | Out-Null
    } else {
        Set-ItemProperty -Path $caminho -Name "(default)" -Value $valor -Force
    }
}

function Remover-Chave($caminho) {
    if (-not (Test-Path $caminho)) { return }
    if ($Simular) { Escrever "  [simulacao] remover $caminho"; return }
    Remove-Item -Path $caminho -Recurse -Force -ErrorAction SilentlyContinue
}

function Atualizar-Explorer {
    # Sem isto o Explorer só mostra a mudança depois de reiniciar. SHCNE_ASSOCCHANGED
    # = 0x08000000, SHCNF_IDLIST = 0.
    if ($Simular) { Escrever "  [simulacao] SHChangeNotify(ASSOCCHANGED)"; return }
    try {
        Add-Type -Namespace TF -Name Shell -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, System.IntPtr a, System.IntPtr b);
'@ -ErrorAction Stop
        [TF.Shell]::SHChangeNotify(0x08000000, 0, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
    } catch {
        Escrever "  (nao foi possivel notificar o Explorer: $($_.Exception.Message))" "DarkYellow"
    }
}

# ---------------------------------------------------------------------------
# Remover
# ---------------------------------------------------------------------------

if ($Remover) {
    Escrever "Removendo o registro do TextForge (somente HKCU)..." "Cyan"

    Remover-Chave "HKCU:\Software\Classes\$ProgID"
    Remover-Chave "HKCU:\Software\Classes\Applications\$AppExe"
    Remover-Chave "HKCU:\Software\Classes\*\shell\TextForge"

    # Tira o ProgID do OpenWithProgids de TODA extensão que o tenha. Varrer é
    # obrigatório: quem remove normalmente não lembra quais extensões registrou.
    $limpas = 0
    Get-ChildItem "HKCU:\Software\Classes" -ErrorAction SilentlyContinue |
        Where-Object { $_.PSChildName -like ".*" } |
        ForEach-Object {
            $alvo = "HKCU:\Software\Classes\$($_.PSChildName)\OpenWithProgids"
            if (Test-Path $alvo) {
                $prop = Get-ItemProperty -Path $alvo -ErrorAction SilentlyContinue
                if ($prop -and ($prop.PSObject.Properties.Name -contains $ProgID)) {
                    if ($Simular) {
                        Escrever "  [simulacao] tirar $ProgID de $($_.PSChildName)"
                    } else {
                        Remove-ItemProperty -Path $alvo -Name $ProgID -Force -ErrorAction SilentlyContinue
                    }
                    $limpas++
                }
            }
        }

    Atualizar-Explorer
    Escrever "Pronto. $limpas extensao(oes) desassociada(s)." "Green"
    Escrever "O programa padrao de cada extensao NAO foi alterado (nunca foi tocado)."
    exit 0
}

# ---------------------------------------------------------------------------
# Localizar o executavel
# ---------------------------------------------------------------------------

if (-not $Exe) {
    $candidatos = @(
        (Join-Path $Raiz "dist\TextForge\$AppExe"),
        (Join-Path $Raiz "dist\$AppExe"),
        (Join-Path $Raiz $AppExe)
    )
    $Exe = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $Exe -or -not (Test-Path $Exe)) {
    Escrever "ERRO: nao encontrei o TextForge.exe." "Red"
    Escrever ""
    Escrever "Gere o executavel primeiro:"
    Escrever "    .\build.bat"
    Escrever "ou informe o caminho:"
    Escrever "    .\associar.ps1 .log -Exe C:\caminho\TextForge.exe"
    exit 1
}
$Exe = (Resolve-Path $Exe).Path

if (-not $Extensoes -or $Extensoes.Count -eq 0) {
    Escrever "Nenhuma extensao informada." "Yellow"
    Escrever ""
    Escrever "Uso:  .\associar.ps1 .log .xml .csv"
    Escrever ""
    Escrever "De proposito nao ha' lista embutida: o requisito e' registrar SOMENTE"
    Escrever "o que voce pedir. Sugestoes comuns para um editor tecnico:"
    Escrever "    .txt .log .dat .csv .ini .cfg .conf .env .json .xml .yaml .yml"
    Escrever "    .md .py .php .js .ts .html .css .sql .bat .cmd .ps1 .sh"
    exit 1
}

# ---------------------------------------------------------------------------
# Registrar
# ---------------------------------------------------------------------------

Escrever "TextForge: $Exe" "Cyan"
if ($Simular) { Escrever "MODO SIMULACAO: nada sera' escrito no registro." "Yellow" }
Escrever ""

$comando = "`"$Exe`" `"%1`""

# 1. O ProgID: o "tipo de arquivo" do TextForge.
Escrever "1. ProgID $ProgID"
Definir-Chave "HKCU:\Software\Classes\$ProgID" $null "Arquivo de texto (TextForge)"
Definir-Chave "HKCU:\Software\Classes\$ProgID\DefaultIcon" $null "`"$Exe`",0"
Definir-Chave "HKCU:\Software\Classes\$ProgID\shell\open\command" $null $comando

# 2. O registro do aplicativo, que faz o nome aparecer bonito no "Abrir com".
Escrever "2. Applications\$AppExe"
Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe" "FriendlyAppName" "TextForge"
Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe\shell\open\command" $null $comando
# SupportedTypes vazio nao restringe: e' o que faz o TextForge aparecer tambem no
# "Abrir com > Escolher outro aplicativo" de QUALQUER extensao.
Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe\SupportedTypes" ".*" ""

# 3. As extensoes pedidas -- via OpenWithProgids, que ACRESCENTA sem roubar.
Escrever "3. Extensoes"
foreach ($bruta in $Extensoes) {
    $ext = $bruta.Trim()
    if (-not $ext) { continue }
    if (-not $ext.StartsWith(".")) { $ext = ".$ext" }
    $ext = $ext.ToLower()

    if ($ext -notmatch '^\.[a-z0-9_\-\.]{1,20}$') {
        Escrever "   ignorada (nao parece uma extensao): $bruta" "DarkYellow"
        continue
    }

    Definir-Chave "HKCU:\Software\Classes\$ext\OpenWithProgids" $ProgID ""
    Escrever "   $ext  ->  adicionado a lista 'Abrir com'" "Green"
}

# 4. Menu de contexto de qualquer arquivo.
Escrever "4. Menu de contexto ('Abrir com o TextForge')"
Definir-Chave "HKCU:\Software\Classes\*\shell\TextForge" $null "Abrir com o &TextForge"
Definir-Chave "HKCU:\Software\Classes\*\shell\TextForge" "Icon" "`"$Exe`",0"
Definir-Chave "HKCU:\Software\Classes\*\shell\TextForge\command" $null $comando

Atualizar-Explorer

Escrever ""
Escrever "Pronto." "Green"
Escrever "O programa PADRAO de cada extensao NAO foi alterado: o TextForge foi"
Escrever "ACRESCENTADO a lista 'Abrir com'. Para torna-lo padrao de uma extensao,"
Escrever "use Botao direito > Abrir com > Escolher outro aplicativo > Sempre."
Escrever ""
Escrever "No Windows 11, o item do menu de contexto fica em 'Mostrar mais opcoes'."
Escrever "O menu novo exige uma extensao de shell empacotada em MSIX, que nao sai"
Escrever "de um script."
Escrever ""
Escrever "Para desfazer:  .\associar.ps1 -Remover"
