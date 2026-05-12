#!/bin/sh
set -eu

data_dir="${FINSIGHT_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$data_dir"
    chown -R finsight:finsight "$data_dir"
    exec gosu finsight "$@"
fi

exec "$@"
