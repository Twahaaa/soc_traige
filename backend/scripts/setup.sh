#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-$(uname -s)}" in
  Darwin|darwin|mac|macos)
    exec "$ROOT/setup_macos.sh"
    ;;
  Linux|linux|ubuntu)
    exec "$ROOT/setup_ubuntu.sh"
    ;;
  *)
    echo "usage: $0 [macos|ubuntu]" >&2
    exit 1
    ;;
esac
