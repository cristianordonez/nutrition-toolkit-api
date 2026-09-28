#!/usr/bin/env bash
# Build the llama-server that ships inside the macOS arm64 app.
#
# Produces src-tauri/binaries/llama-server-aarch64-apple-darwin, the name
# Tauri's `bundle.externalBin` expects (see src-tauri/tauri.local-ai.conf.json).
# The build is static with the Metal shaders embedded, so the one file is the
# whole runtime; the script refuses a result that still links non-system
# libraries. Requires Xcode command line tools, git and cmake.
#
#   LLAMA_CPP_TAG=b11146 apps/desktop/scripts/build-llama-server.sh
set -euo pipefail

LLAMA_CPP_TAG="${LLAMA_CPP_TAG:-b11146}"
TRIPLE="aarch64-apple-darwin"
DESKTOP="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$DESKTOP/src-tauri/binaries/llama-server-$TRIPLE"

if [[ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]]; then
  echo "This script builds the macOS arm64 runtime only." >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --depth 1 --branch "$LLAMA_CPP_TAG" \
  https://github.com/ggml-org/llama.cpp "$WORK/llama.cpp"

# Options a given llama.cpp release does not know are ignored by cmake; the
# self-containment check below is what guarantees the result.
cmake -S "$WORK/llama.cpp" -B "$WORK/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF \
  -DGGML_METAL=ON \
  -DGGML_METAL_EMBED_LIBRARY=ON \
  -DLLAMA_CURL=OFF \
  -DLLAMA_OPENSSL=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=ON
cmake --build "$WORK/build" --config Release --target llama-server -j

mkdir -p "$(dirname "$OUT")"
install -m 0755 "$WORK/build/bin/llama-server" "$OUT"

if otool -L "$OUT" | tail -n +2 | grep -vE '^[[:space:]]*(/usr/lib/|/System/Library/)'; then
  echo "llama-server still links the libraries above; it would not run elsewhere." >&2
  rm -f "$OUT"
  exit 1
fi
"$OUT" --version
echo "Built $OUT from llama.cpp $LLAMA_CPP_TAG"
