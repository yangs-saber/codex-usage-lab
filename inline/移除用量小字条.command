#!/bin/zsh
set -eu
TASK_DIR="${0:A:h}"
TASK_NODE='/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node'
if [[ ! -x "$TASK_NODE" ]]; then TASK_NODE="$(command -v node)"; fi
exec "$TASK_NODE" "$TASK_DIR/bridge.mjs" --restore
