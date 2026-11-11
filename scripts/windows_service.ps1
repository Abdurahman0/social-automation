<#
  Keeps one part of Social Automation running on Windows (started at logon by the Task Scheduler task that
  install.ps1 creates). When the bot exits - for example with code 75 after the Setup page changed .env - it is
  started again after a short pause, like systemd's Restart=always on Linux and launchd's KeepAlive on macOS.
#>
param([ValidateSet('bot', 'web')][string]$Kind = 'bot')

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$py = Join-Path $Root '.venv\Scripts\python.exe'
$cmd = if ($Kind -eq 'bot') { 'run' } else { 'web' }
$env:PYTHONUNBUFFERED = '1'
# Task 11: Python in UTF-8 mode whatever the Windows locale (Korean cp949 crashed on 'c-cedilla'), and the log file
# below receives UTF-8 text, not the console code page.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:Path = (Join-Path $Root 'bin') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
Remove-Item Env:ANTHROPIC_API_KEY, Env:ANTHROPIC_AUTH_TOKEN, Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'logs') | Out-Null
$log = Join-Path $Root "logs\windows-$Kind.log"

while ($true) {
    & $py -X utf8 -m socialauto $cmd *>> $log
    $code = $LASTEXITCODE
    Start-Sleep -Seconds ($(if ($code -eq 75) { 1 } else { 5 }))
}
