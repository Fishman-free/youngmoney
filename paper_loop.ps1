# bnbot paper 前向观察循环：每 4h 跑一轮 paper，出错继续，日志滚动写 logs/paper-loop.log
#
# 每轮开跑前先探测数据源就绪（2026-10-05 实测事故：机器 23:31:27 开机、循环
# 23:32:14 起来，但代理 23:46:53 才起 —— 首轮所有行情请求被拒（WinError 10061），
# 全程读了 3 天前的缓存，把一个用陈旧价格标记出来的权益点写进了 STATE.md，
# 污染门禁的权益序列）。现在：探测不到就在日志里留一行 [skip] 并跳过本轮，
# 宁可少一个数据点，也不往审计序列里塞假点。
#
# 探测口径与数据层一致：主源（币安）或备用源（MEXC）任一连通即可开跑 ——
# 币安 451 地域风控期间数据层本来就靠 MEXC 回退，不该因此停摆。
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

# 子进程（python）按 UTF-8 输出，而 PS 5.1 默认按 OEM 代码页（CN 是 GBK）解码，
# 会把「长线」写成「闀跨嚎」。日志是审计面，必须可读——两端都钉死 UTF-8。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$Proxy = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = $Proxy
$env:HTTP_PROXY = $Proxy
$ProbeUrls = @(
    "https://fapi.binance.com/fapi/v1/ping",   # 主源
    "https://api.mexc.com/api/v3/ping"         # 备用源（币安 451 时的回退）
)
$ProxyWaitSeconds = 600      # 每轮最多等 10 分钟（代理冷启动）
$CycleHours = 4

function Test-ProxyReady {
    foreach ($url in $ProbeUrls) {
        try {
            $r = Invoke-WebRequest -Uri $url -Proxy $Proxy -TimeoutSec 8 -UseBasicParsing
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { }
    }
    return $false
}

function Wait-ProxyReady {
    param([int]$TimeoutSec = 600, [int]$PollSec = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $attempt = 0
    while ($true) {
        $attempt++
        if (Test-ProxyReady) { return @{ ok = $true; attempts = $attempt } }
        if ((Get-Date) -ge $deadline) { return @{ ok = $false; attempts = $attempt } }
        Start-Sleep -Seconds $PollSec
    }
}

while ($true) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $probe = Wait-ProxyReady -TimeoutSec $ProxyWaitSeconds -PollSec 15
    if (-not $probe.ok) {
        $msg = "[skip] 数据源不可达（代理 $Proxy，已探测 $($probe.attempts) 次 / " +
               "$([int]($ProxyWaitSeconds/60)) 分钟）：跳过本轮，避免用陈旧缓存写假数据；" +
               "$($CycleHours)h 后重试。检查 Clash/代理是否在跑。"
        Add-Content -Path "logs\paper-loop.log" -Value "=== $ts ===`n$msg" -Encoding UTF8
        Start-Sleep -Seconds ($CycleHours * 3600)
        continue
    }
    $s = python -m bnbot.sentiment --once --proxy $Proxy 2>&1 | Out-String
    $out = python -m bnbot.live --sleeves --once 2>&1 | Out-String
    Add-Content -Path "logs\paper-loop.log" -Value "=== $ts ===`n$s$out" -Encoding UTF8
    Start-Sleep -Seconds ($CycleHours * 3600)
}
