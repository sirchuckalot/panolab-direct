#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

litex_root=${LITEX_ROOT:-/opt/panolab/litex}
upstream="$litex_root/upstream"
export PYTHONPATH="$upstream/migen:$upstream/litex:$upstream/litex-boards:$upstream/liteeth:$upstream/litespi"
export PYTHONDONTWRITEBYTECODE=1
"$litex_root/venv/bin/python" -u - <<'PY' 2>&1 | tee timing_fix_tests.log
from pathlib import Path
import runpy
import sys
import litex
import migen

for name, module, checkout in (
    ("Migen", migen, sys.path[1]),
    ("LiteX", litex, sys.path[2]),
):
    source = Path(module.__file__).resolve()
    if not source.is_relative_to(Path(checkout).resolve()):
        raise SystemExit(f"{name} imported outside the pinned checkout: {source}")
    print(f"{name}: {source}")

runpy.run_path("test_timing_fix.py", run_name="__main__")
PY
