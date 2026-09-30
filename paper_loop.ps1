# bnbot paper 前向观察循环：每 4h 跑一轮 paper，出错继续，日志滚动写 logs/paper-loop.log
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:HTTP_PROXY = "http://127.0.0.1:7890"
while ($true) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $s = python -m bnbot.sentiment --once --proxy http://127.0.0.1:7890 2>&1 | Out-String
    $out = python -m bnbot.live --sleeves --once 2>&1 | Out-String
    Add-Content -Path "logs\paper-loop.log" -Value "=== $ts ===`n$s$out" -Encoding UTF8
    Start-Sleep -Seconds (4 * 3600)
}
