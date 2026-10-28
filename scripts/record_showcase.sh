#!/bin/sh
set -eu
# Optional authoring tools: asciinema, installed guardrail-agent, then Pillow.
project=$(pwd)
python=${GUARDRAIL_PYTHON:-"$project/.venv/bin/python"}
recorder=${ASCIINEMA:-$(command -v asciinema)}
task=$(mktemp -d)
trap 'rm -rf "$task"' EXIT HUP INT TERM
mkdir -p "$task/home" "$task/xdg" "$task/asciinema" "$task/tmp"
env -i HOME="$task/home" XDG_CONFIG_HOME="$task/xdg" \
  ASCIINEMA_CONFIG_HOME="$task/asciinema" TMPDIR="$task/tmp" \
  PATH="$(dirname "$python"):/usr/bin:/bin:/usr/sbin:/sbin" TERM=xterm-256color \
  "$recorder" rec --overwrite --cols 120 --rows 44 \
  --title 'guardrail-agent: deterministic synthetic gates and receipt trust' \
  --command "\"$python\" scripts/showcase.py --out assets" assets/demo.cast
