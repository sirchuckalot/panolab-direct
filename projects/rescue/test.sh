#!/usr/bin/env bash
# Verify source and run board SoC tests from declared PanoLab source dependencies.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
exec python3 shared/source_registry.py run --project projects/rescue/project.toml -- python3 projects/rescue/tests/test_rescue_soc.py
