#!/bin/sh
# Install OrbeHelm without changing global Python or agent configuration.
set -eu
setup_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${ORBEHELM_PYTHON:-}" ]; then
    setup_python=$ORBEHELM_PYTHON
else
    setup_python=
    for candidate in python3 python3.13 python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
            setup_python=$candidate
            break
        fi
    done
fi
if [ -z "$setup_python" ] || ! "$setup_python" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    echo 'OrbeHelm requires Python 3.11 or later. Install it, or set ORBEHELM_PYTHON to its executable.' >&2
    exit 1
fi
exec "$setup_python" "$setup_root/src/orbehelm/installer.py" "$@"
