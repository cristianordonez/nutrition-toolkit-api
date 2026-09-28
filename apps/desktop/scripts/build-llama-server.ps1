# Build the llama-server that ships inside the Windows x64 app.
#
# Produces src-tauri\binaries\llama-server-x86_64-pc-windows-msvc.exe, the
# name Tauri's `bundle.externalBin` expects (see
# src-tauri\tauri.local-ai.conf.json). Static, with the static MSVC runtime,
# so no DLLs or VC++ redistributable are needed. CPU build (AVX2); GPU builds
# (Vulkan/CUDA) are not packaged yet. Requires Visual Studio 2022 build
# tools, git and cmake.
#
#   $env:LLAMA_CPP_TAG = "b11146"; .\apps\desktop\scripts\build-llama-server.ps1
$ErrorActionPreference = "Stop"

$Tag = if ($env:LLAMA_CPP_TAG) { $env:LLAMA_CPP_TAG } else { "b11146" }
$Triple = "x86_64-pc-windows-msvc"
$Desktop = Resolve-Path (Join-Path $PSScriptRoot "..")
$Out = Join-Path $Desktop "src-tauri\binaries\llama-server-$Triple.exe"
$Work = Join-Path ([IO.Path]::GetTempPath()) ("llama-" + [Guid]::NewGuid())

try {
    git clone --depth 1 --branch $Tag https://github.com/ggml-org/llama.cpp "$Work\llama.cpp"
    cmake -S "$Work\llama.cpp" -B "$Work\build" -A x64 `
        -DBUILD_SHARED_LIBS=OFF `
        -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded `
        -DGGML_NATIVE=OFF `
        -DGGML_AVX2=ON `
        -DLLAMA_CURL=OFF `
        -DLLAMA_OPENSSL=OFF `
        -DLLAMA_BUILD_TESTS=OFF `
        -DLLAMA_BUILD_EXAMPLES=OFF `
        -DLLAMA_BUILD_SERVER=ON
    cmake --build "$Work\build" --config Release --target llama-server -j
    New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
    Copy-Item "$Work\build\bin\Release\llama-server.exe" $Out -Force
    & $Out --version
    Write-Host "Built $Out from llama.cpp $Tag"
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
