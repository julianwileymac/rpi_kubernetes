#Requires -RunAsAdministrator
$entries = @"

# RPI Kubernetes Cluster Services
192.168.12.112 datahub.local grafana.local prometheus.local alertmanager.local jaeger.local vm.local loki.local mlflow.local ray.local dask.local minio.local s3.local milvus.local chromadb.local argo.local dagster.local jupyter.local control.local yatai.local ragflow.local
"@

$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$current = Get-Content $hostsPath -Raw

$marker = "# RPI Kubernetes Cluster Services"
if ($current -match [regex]::Escape($marker)) {
    $current = $current -replace "(?m)^$([regex]::Escape($marker))[\s\S]*?(?=\r?\n\r?\n|\z)", ""
    $current = $current.TrimEnd() + "`n" + $entries + "`n"
    Set-Content -Path $hostsPath -Value $current -NoNewline
    Write-Host "Hosts file updated. Replaced cluster service entries." -ForegroundColor Green
} else {
    Add-Content -Path $hostsPath -Value $entries
    Write-Host "Hosts file updated. Added cluster service entries." -ForegroundColor Green
}
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
