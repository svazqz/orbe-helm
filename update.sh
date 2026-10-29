#!/bin/sh
# Apply this checkout's application, dependency, source, and database updates.
# Version-specific upgrade steps belong in the shared installer/migration path.
set -eu
update_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$update_root/setup.sh" --update "$@"
