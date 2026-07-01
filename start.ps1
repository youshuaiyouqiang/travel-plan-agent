<#
.SYNOPSIS
    Claw 项目一键启动脚本（Windows PowerShell 版）
.DESCRIPTION
    启动后端 FastAPI（uvicorn，http://localhost:8000）和前端 Vite Dev Server（http://localhost:5173）。
    首次运行会自动安装 Python 依赖和前端 node_modules。
    按 Ctrl+C 退出时会自动清理两个子进程。
#>
[CmdletBinding()]
param(
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step($msg) { Write-Host "`n[*] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[X] $msg" -ForegroundColor Red }

# ---------- 0. 清理占用端口的进程 ----------
function Clear-Port($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return $false }
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Warn "已清理占用端口 $port 的进程: $($proc.Name) (PID=$($c.OwningProcess))"
        }
    }
    Start-Sleep -Milliseconds 300
    return $true
}

Write-Step "清理占用端口（后端 $BackendPort / 前端 $FrontendPort）"
$cleared = $false
if (Clear-Port $BackendPort) { $cleared = $true }
if (Clear-Port $FrontendPort) { $cleared = $true }
if (-not $cleared) { Write-Ok "端口 $BackendPort / $FrontendPort 空闲" }

# ---------- 1. 环境检查 ----------
Write-Step "环境检查"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $Python = "py" } else { Write-Err "未找到 python / py，请先安装 Python 3.10+"; exit 1 }
} else {
    $Python = "python"
}
Write-Ok "Python: $Python (& $Python --version)"

$node = Get-Command npm -ErrorAction SilentlyContinue
if (-not $node) { Write-Err "未找到 npm，请先安装 Node.js 18+"; exit 1 }
Write-Ok "npm: $(npm --version)"

if (-not (Test-Path ".env")) {
    Write-Warn "未找到 .env，从 .env.example 复制（请随后填入 API Key）"
    Copy-Item ".env.example" ".env"
}

# ---------- 2. 依赖安装 ----------
if (-not $SkipInstall) {
    Write-Step "检查 Python 依赖"
    & $Python -c "import fastapi, uvicorn, openai" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "安装 Python 依赖（requirements.txt）"
        & $Python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Write-Err "Python 依赖安装失败"; exit 1 }
    }
    Write-Ok "Python 依赖就绪"

    Write-Step "检查前端依赖"
    if (-not (Test-Path "frontend/node_modules")) {
        Write-Warn "安装前端依赖（首次较慢）"
        Push-Location frontend
        npm install
        if ($LASTEXITCODE -ne 0) { Write-Err "前端依赖安装失败"; exit 1 }
        Pop-Location
    }
    Write-Ok "前端依赖就绪"
} else {
    Write-Warn "跳过依赖安装 (-SkipInstall)"
}

# ---------- 3. 启动服务 ----------
Write-Step "启动后端 FastAPI (http://${BackendHost}:${BackendPort})"
$backend = Start-Process -PassThru -NoNewWindow -FilePath $Python `
    -ArgumentList "-m","uvicorn","api.server:app","--host",$BackendHost,"--port",$BackendPort,"--reload"
Write-Ok "后端 PID=$($backend.Id)"

Write-Step "启动前端 Vite (http://localhost:${FrontendPort})"
$env:PORT = $FrontendPort
# Windows 上 npm 是 npm.cmd（批处理），用 cmd /c 启动；清理时按进程名 kill node 以连带退出 vite
$frontend = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" `
    -ArgumentList "/c","npm","run","dev" -WorkingDirectory (Join-Path $Root "frontend")
Write-Ok "前端 PID=$($frontend.Id)"

# ---------- 4. 退出清理 ----------
Write-Ok "两个服务已启动。按 Ctrl+C 退出并自动清理。"
Write-Host "    后端: http://${BackendHost}:${BackendPort}"
Write-Host "    前端: http://localhost:${FrontendPort}"
Write-Host "    API 文档: http://${BackendHost}:${BackendPort}/docs"

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Write-Step "清理子进程"
    # kill 后端 uvicorn
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    # kill 前端 cmd 父进程
    if ($frontend -and -not $frontend.HasExited) {
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    }
    # cmd /c npm run dev 会拉起 node（vite），父进程 kill 后 node 仍可能残留，按命令行特征清理
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*vite*" -or $_.CommandLine -like "*npm*dev*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Ok "已退出"
}
