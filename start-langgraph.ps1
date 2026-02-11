$env:UV_HTTP_TIMEOUT="300"
$uvPath = "C:\Users\HP\.local\bin\uv.exe"
if (-not (Test-Path $uvPath)) {
    Write-Error "uv not found at $uvPath"
    exit 1
}
& $uvPath run langgraph dev --allow-blocking
