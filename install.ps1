<#
  Social Automation - one-command installer for Windows.

    powershell -ExecutionPolicy Bypass -File install.ps1              install or update (safe to run again after git pull)
    powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall   remove the background tasks (files and .env stay)
    ... -NoService   install everything but do not register background tasks
    ... -NoOpen      do not open the browser at the end

  One line, no git login and no GitHub account needed (the repo is public). In PowerShell:
    irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex
  It installs Git if missing, clones over public HTTPS into %USERPROFILE%\social-automation and continues.

  Messages are in Uzbek, then English. Nothing here prints a token or a password.
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$NoService,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'
$RepoUrl = if ($env:SA_REPO_URL) { $env:SA_REPO_URL } else { 'https://github.com/Abdurahman0/social-automation.git' }   # SA_REPO_URL: a mirror (tests)

# --- bootstrap: started as `irm ... | iex` (no file on disk yet) -> get the code anonymously, then run the real
# installer from it. `return`, never `exit`, here: exit would close the user's PowerShell window.
$SelfPath = $MyInvocation.MyCommand.Path
if (-not $SelfPath -or -not (Test-Path (Join-Path (Split-Path -Parent $SelfPath) 'socialauto/__init__.py'))) {
    $home0 = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
    $dir = if ($env:SA_DIR) { $env:SA_DIR } else { Join-Path $home0 'social-automation' }
    Write-Host ""; Write-Host "==> Social Automation: kod yuklanmoqda / downloading the code -> $dir" -ForegroundColor White
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "  ... winget install Git.Git"
            winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
            if (Test-Path "$env:ProgramFiles\Git\cmd") { $env:Path += ";$env:ProgramFiles\Git\cmd" }
        }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "  [X] Git o'rnatilmadi / Git could not be installed: https://git-scm.com/download/win , keyin shu buyruqni qayta ishga tushiring / then run this command again." -ForegroundColor Red
            return
        }
    }
    # Never a login prompt: no credential helper (no Git Credential Manager window), no terminal prompt.
    $env:GIT_TERMINAL_PROMPT = '0'
    if (Test-Path (Join-Path $dir '.git')) { git -c credential.helper= -C $dir pull --ff-only --quiet }
    else { git -c credential.helper= clone --quiet $RepoUrl $dir }
    if ($LASTEXITCODE -ne 0) { Write-Host "  [X] Kodni yuklab bo'lmadi / could not download the code. Internetni tekshiring / check the internet." -ForegroundColor Red; return }
    # The owner's repo is read-only for everyone else: this copy gets no push address at all.
    git -C $dir remote set-url --push origin 'no-push:the-code-repo-is-read-only'
    if ($env:SA_BOOTSTRAP_DRYRUN) { Write-Host "  [OK] cloned anonymously; next: install.ps1 from $dir"; return }
    $rest = @(); if ($Uninstall) { $rest += '-Uninstall' }; if ($NoService) { $rest += '-NoService' }; if ($NoOpen) { $rest += '-NoOpen' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dir 'install.ps1') @rest
    return
}
$Root = Split-Path -Parent $SelfPath
Set-Location $Root
$Port = 8090
$Tasks = @('SocialAutomation-Bot', 'SocialAutomation-Web')

function Step($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor White }
function Ok($t)   { Write-Host "  [OK] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!] $t" -ForegroundColor Yellow }
function Fail($t, $hint) {
    Write-Host ""; Write-Host "  [X] $t" -ForegroundColor Red
    if ($hint) { Write-Host "      $hint" }
    exit 1
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Has($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Winget-Install($id) {
    if (-not (Has 'winget')) { return $false }
    Write-Host "  ... winget install $id"
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Refresh-Path
    return $true
}

if ($Uninstall) {
    Step "Fon vazifalari o'chirilmoqda / removing the background tasks"
    foreach ($t in $Tasks) {
        Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$Root*socialauto*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Ok "Vazifalar o'chirildi / tasks removed"
    Write-Host "  Loyiha papkasi, .env va ma'lumotlar joyida qoldi. / The project folder, .env and data are kept."
    exit 0
}

try {
    # ------------------------------------------------------------------------------------------- 1. tools
    Step "1/8 Kerakli dasturlar tekshirilmoqda / checking required programs"
    $Py = $null
    $venvPy = Join-Path $Root '.venv\Scripts\python.exe'
    function Py-Ok($exe, $pre) {
        try { & $exe @pre -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
    }
    if ((Test-Path $venvPy) -and (Py-Ok $venvPy @())) { $Py = @($venvPy) }
    if (-not $Py) {
        foreach ($v in @('-3.13', '-3.12', '-3.11')) { if ((Has 'py') -and (Py-Ok 'py' @($v))) { $Py = @('py', $v); break } }
    }
    if (-not $Py -and (Has 'python') -and (Py-Ok 'python' @())) { $Py = @('python') }
    if (-not $Py -and (Winget-Install 'Python.Python.3.12')) {
        if ((Has 'py') -and (Py-Ok 'py' @('-3.12'))) { $Py = @('py', '-3.12') }
    }
    if (-not $Py) { Fail "Python 3.11+ topilmadi / Python 3.11 or newer not found." "winget install Python.Python.3.12  (yoki/or https://www.python.org/downloads/), keyin terminalni qayta oching / then reopen the terminal." }
    $pyExe = $Py[0]; $pyArgs = @($Py | Select-Object -Skip 1)
    Ok ("Python: " + (& $pyExe @pyArgs --version))

    if (-not (Has 'ffmpeg')) { [void](Winget-Install 'Gyan.FFmpeg') }
    if (-not (Has 'ffmpeg')) { Fail "ffmpeg topilmadi / ffmpeg not found." "winget install Gyan.FFmpeg  , keyin terminalni qayta oching / then reopen the terminal." }
    Ok "ffmpeg"

    function Node-Ok { if (-not ((Has 'node') -and (Has 'npm'))) { return $false }; return ([int](node -p "process.versions.node.split('.')[0]") -ge 18) }
    if (-not (Node-Ok)) { [void](Winget-Install 'OpenJS.NodeJS.LTS') }
    if (-not (Node-Ok)) { Fail "Node.js 18+ topilmadi / Node.js 18 or newer not found." "winget install OpenJS.NodeJS.LTS  (yoki/or https://nodejs.org), keyin terminalni qayta oching / then reopen the terminal." }
    Ok ("Node.js: " + (node --version))

    # ------------------------------------------------------------------------------------------- 2. Python env
    Step "2/8 Python muhiti / Python environment (.venv)"
    if (-not (Test-Path $venvPy)) {
        & $pyExe @pyArgs -m venv .venv
        if ($LASTEXITCODE -ne 0) { Fail "venv yaratib bo'lmadi / could not create the virtual environment." "Python'ni qayta o'rnating / reinstall Python." }
    }
    & $venvPy -m pip install -q --disable-pip-version-check --upgrade pip
    & $venvPy -m pip install -q --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Fail "Python paketlarini o'rnatib bo'lmadi / could not install the Python packages." "Internetni tekshirib qayta ishga tushiring / check the internet and run install.ps1 again." }
    Ok "Python paketlari o'rnatildi / Python packages installed"

    # ------------------------------------------------------------------------------------------- 3. Remotion
    Step "3/8 Video chizuvchi (Remotion) / video renderer (Remotion)"
    Push-Location (Join-Path $Root 'remotion')
    try {
        npm install --no-audit --no-fund --loglevel=error | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "npm paketlarini o'rnatib bo'lmadi / npm install failed." "Internetni tekshirib qayta ishga tushiring / run install.ps1 again." }
        npx --no-install remotion browser ensure | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "Remotion brauzerini yuklab bo'lmadi / could not download Remotion's browser." "Qayta ishga tushiring / run install.ps1 again." }
    } finally { Pop-Location }
    Ok "Remotion tayyor / Remotion ready"

    # ------------------------------------------------------------------------------------------- 4. model
    Step "4/8 O'zbekcha nutq modeli (~800 MB) / Uzbek speech model (~800 MB)"
    & $venvPy -m socialauto download-model
    if ($LASTEXITCODE -ne 0) { Fail "Model yuklanmadi / the model was not downloaded." "Qayta ishga tushiring / run install.ps1 again." }

    # ------------------------------------------------------------------------------------------- 5. cloudflared
    Step "5/8 cloudflared (ixtiyoriy / optional)"
    $cf = Join-Path $Root 'bin\cloudflared.exe'
    if ((Test-Path $cf) -or (Has 'cloudflared')) { Ok "cloudflared bor / already installed" }
    else {
        try {
            New-Item -ItemType Directory -Force -Path (Join-Path $Root 'bin') | Out-Null
            Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile "$cf.part"
            Move-Item -Force "$cf.part" $cf
            Ok "cloudflared o'rnatildi / installed"
        } catch { Remove-Item -Force -ErrorAction SilentlyContinue "$cf.part"; Warn "cloudflared yuklanmadi - shart emas / not downloaded - optional, skipped" }
    }

    # ------------------------------------------------------------------------------------------- 6. .env
    Step "6/8 Sozlamalar fayli / settings file (.env)"
    $envFile = Join-Path $Root '.env'
    if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $Root '.env.example') $envFile; Ok ".env yaratildi / created (kalitlar saytdagi Sozlash sahifasida / keys go on the Setup page)" }
    else { Ok ".env bor, tegilmadi / exists, left as is" }
    foreach ($d in @('secrets', 'data', 'logs')) { New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null }
    # Only the current user may read them (law 7): inherited permissions removed, full control for this user only.
    icacls $envFile /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
    icacls (Join-Path $Root 'secrets') /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null

    # ------------------------------------------------------------------------------------------- 7. Claude
    Step "7/8 Claude Code (har kim o'z akkaunti bilan / each user's own account)"
    if (Has 'claude') {
        $st = (claude auth status --json 2>$null | Out-String)
        if ($st -match '"loggedIn"\s*:\s*true') { Ok "Claude Code o'rnatilgan va kirilgan / installed and logged in" }
        else { Warn "Claude Code'ga kirilmagan / not logged in: terminalda 'claude' yozing va o'z akkauntingiz bilan kiring / type 'claude' and log in." }
    } else {
        Warn "Claude Code o'rnatilmagan / not installed: npm install -g @anthropic-ai/claude-code , keyin 'claude' yozib kiring / then type 'claude' and log in."
    }

    # ------------------------------------------------------------------------------------------- 8. tasks
    Step "8/8 Fon vazifalari / background tasks (Task Scheduler)"
    if ($NoService) {
        Warn "-NoService: vazifalar ro'yxatdan o'tkazilmadi / tasks not registered. Qo'lda / by hand: .venv\Scripts\python.exe -m socialauto web  va/and  run"
    } else {
        $wrapper = Join-Path $Root 'scripts\windows_service.ps1'
        foreach ($kind in @('bot', 'web')) {
            $name = if ($kind -eq 'bot') { $Tasks[0] } else { $Tasks[1] }
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            $action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $Root `
                -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$wrapper`" -Kind $kind"
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
                -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false
            $desc = "Social Automation ($kind). Approved reels go into the Buffer queue."
            # Start when the computer turns on, even before anyone logs in (S4U: no password stored). Windows allows
            # this from an administrator PowerShell; otherwise the task starts when this user logs in.
            $startup = $false
            try {
                $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
                $triggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME))
                Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
                    -Description $desc -Force -ErrorAction Stop | Out-Null
                $startup = $true
            } catch {
                $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
                Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
                    -Description $desc -Force | Out-Null
            }
            Start-ScheduledTask -TaskName $name
        }
        if ($startup) { Ok "Vazifalar ishga tushdi: kompyuter yonganda o'zi ishlaydi / tasks start when the computer turns on" }
        else {
            Ok "Vazifalar ishga tushdi: Windows'ga kirganingizda o'zi ishlaydi / tasks start at logon"
            Warn "Kirishdan oldin ishlashi uchun install.ps1 ni administrator PowerShell'da bir marta ishga tushiring / run once as administrator to start before logon."
        }
    }

    $url = "http://localhost:$Port/setup"
    if (-not $NoService) {
        for ($i = 0; $i -lt 30; $i++) {
            try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/session" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 }
        }
    }
    Write-Host ""
    Write-Host "Tayyor! / Done! Sozlash sahifasi / Setup page: $url" -ForegroundColor Green
    Write-Host "  Sinov rejimi yoqiq (dry_run): Buffer'ga hech narsa yuborilmaydi. O'chirish: .venv\Scripts\python -m socialauto dry-run off"
    Write-Host "  Dry-run is on: nothing is sent to Buffer. Turn it off: .venv\Scripts\python -m socialauto dry-run off"
    if (-not $NoOpen -and -not $NoService) { Start-Process $url }
} catch {
    Fail "Kutilmagan xato / unexpected error: $($_.Exception.Message)" "O'rnatuvchini qayta ishga tushiring / run install.ps1 again."
}
