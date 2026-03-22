#Requires -RunAsAdministrator
$entries = @"

# RPI Kubernetes Cluster Services
192.168.12.112 datahub.local grafana.local prometheus.local alertmanager.local jaeger.local vm.local loki.local mlflow.local ray.local dask.local minio.local s3.local milvus.local chromadb.local argo.local jupyter.local control.local
"@

$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$current = Get-Content $hostsPath -Raw
if ($current -notmatch "datahub\.local") {
    Add-Content -Path $hostsPath -Value $entries
    Write-Host "Hosts file updated. Added cluster service entries." -ForegroundColor Green
} else {
    Write-Host "Hosts file already contains cluster entries." -ForegroundColor Yellow
}
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
