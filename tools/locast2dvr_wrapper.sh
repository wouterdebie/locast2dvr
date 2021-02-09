#!/bin/bash
while getopts :c: flag
do
    case "${flag}" in
        c) config=${OPTARG};;
        :  ) echo "Missing option argument for -$OPTARG" >&2; exit 1;;
    esac
  done

if [ -x $config ]; then
  echo "No config specified"
  exit 1
fi
SELF_PATH=$(cd -P -- "$(dirname -- "$0")" && pwd -P)
# resolve symlinks
while [ -h "$SELF_PATH" ]; do
    DIR=$(dirname -- "$SELF_PATH")
    SYM=$(readlink "$SELF_PATH")
    SELF_PATH=$(cd "$DIR" && cd "$(dirname -- "$SYM")" && pwd)/$(basename -- "$SYM")
done

cd ${SELF_PATH}

if ! test -d venv; then
    export PATH=/usr/local/bin:$PATH
    python3 -m venv locast2dvr-venv
    . locast2dvr-venv/bin/activate
	  pip install locast2dvr
fi
. locast2dvr-venv/bin/activate
exec locast2dvr --config ${config}
