#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-$(uname -s)}" in
  Darwin|darwin|mac|macos)
    echo "[setup] macOS detected; Redis and Qdrant will be configured if available"
    exec "$ROOT/setup_macos.sh"
    ;;
  Linux|linux|ubuntu)
    echo "[setup] Linux detected; Redis and Qdrant will be configured if available"
    exec "$ROOT/setup_ubuntu.sh"
    ;;
  *)
    echo "usage: $0 [macos|ubuntu]" >&2
    exit 1
    ;;
esac
