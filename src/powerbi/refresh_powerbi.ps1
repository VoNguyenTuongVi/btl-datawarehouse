<#
Tự Refresh mô hình đang mở trong Power BI Desktop (nạp lại dữ liệu từ PostgreSQL).

Power BI Desktop chạy một Analysis Services cục bộ trên một cổng ngẫu nhiên.
Script tìm cổng đó, rồi gửi lệnh TMSL refresh qua Invoke-ASCmd.

Cần module SqlServer (cài một lần):
    Install-Module SqlServer -Scope CurrentUser

Cách dùng:
    powershell -ExecutionPolicy Bypass -File src\powerbi\refresh_powerbi.ps1
#>
param(
    [long]$LaunchedAfter = 0,      # chỉ nhận phiên Power BI mở sau mốc này (Unix time)
    [int]$TimeoutSec = 180,
    [string]$RefreshType = "full"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Module -ListAvailable -Name SqlServer)) {
    Write-Host "[X] Chưa có module SqlServer. Chạy: Install-Module SqlServer -Scope CurrentUser" -ForegroundColor Red
    Write-Host "    Tạm thời có thể bấm Refresh trong Power BI Desktop."
    exit 1
}
Import-Module SqlServer -DisableNameChecking

# Bản cài từ trang Microsoft và bản Microsoft Store lưu workspace ở hai chỗ khác nhau
$candidates = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"),
    (Join-Path $env:USERPROFILE  "Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces")
)

$since = [DateTimeOffset]::FromUnixTimeSeconds($LaunchedAfter).LocalDateTime
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$port = $null

Write-Host "-> Chờ Power BI Desktop khởi động..."
while (-not $port -and (Get-Date) -lt $deadline) {
    # Thư mục workspace chỉ xuất hiện sau khi Power BI khởi động, nên kiểm tra lại mỗi vòng
    $roots = @($candidates | Where-Object { Test-Path $_ })
    if ($roots.Count -eq 0) { Start-Sleep -Seconds 3; continue }
    $file = Get-ChildItem -Path $roots -Recurse -Filter "msmdsrv.port.txt" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $since } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($file) {
        # File cổng được ghi bằng UTF-16
        $port = (Get-Content $file.FullName -Encoding Unicode -Raw).Trim()
    } else {
        Start-Sleep -Seconds 3
    }
}
if (-not $port) {
    Write-Host "[X] Không tìm thấy Power BI Desktop sau $TimeoutSec giây. Hãy bấm Refresh thủ công." -ForegroundColor Red
    exit 1
}
$server = "localhost:$port"

# Chờ mô hình nạp xong định nghĩa rồi mới lấy tên database
$db = $null
while (-not $db -and (Get-Date) -lt $deadline) {
    try {
        $xml = [xml](Invoke-ASCmd -Server $server -Query 'SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS')
        $db = ($xml.GetElementsByTagName("CATALOG_NAME") | Select-Object -First 1).'#text'
    } catch { }
    if (-not $db) { Start-Sleep -Seconds 3 }
}
if (-not $db) {
    Write-Host "[X] Không đọc được mô hình trên $server. Hãy bấm Refresh thủ công." -ForegroundColor Red
    exit 1
}

Write-Host "-> Refresh '$db' trên $server ..."
$tmsl = @{ refresh = @{ type = $RefreshType; objects = @(@{ database = $db }) } } | ConvertTo-Json -Depth 5
$result = Invoke-ASCmd -Server $server -Query $tmsl

if ($result -match "<Error") {
    Write-Host "[X] Refresh lỗi:" -ForegroundColor Red
    Write-Host $result
    Write-Host "    Nếu lỗi về thông tin đăng nhập: mở Power BI, bấm Refresh một lần và nhập tài khoản PostgreSQL."
    exit 1
}
Write-Host "-> Đã nạp xong dữ liệu. Trong Power BI Desktop, bấm vào một visual bất kỳ để thấy số mới." -ForegroundColor Green
