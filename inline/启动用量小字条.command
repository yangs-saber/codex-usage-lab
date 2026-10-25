#!/bin/zsh
set -eu
TASK_DIR="${0:A:h}"
TASK_NODE='/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node'
if [[ ! -x "$TASK_NODE" ]]; then TASK_NODE="$(command -v node)"; fi
if ! curl --silent --fail --max-time 2 http://127.0.0.1:9335/json/version >/dev/null; then
  if pgrep -f '^/Applications/ChatGPT.app/Contents/MacOS/' >/dev/null; then
    print '请先用 Command+Q 退出 Codex，再双击这个文件。不会强制关闭你的应用。'
    read -r '?按回车退出：'
    exit 1
  fi
  print '本实现会临时启用仅限 127.0.0.1 的调试端口，以便在「用时」旁加小字。'
  print '本机其他进程也可能连接这个端口。正常退出并普通启动 Codex 即可关闭它。'
  read -r 'TASK_ANSWER?是否这样启动？输入 y 继续：'
  [[ "$TASK_ANSWER" == y ]] || exit 0
  open -a /Applications/ChatGPT.app --args --remote-debugging-address=127.0.0.1 --remote-debugging-port=9335
  for TASK_ATTEMPT in {1..30}; do
    curl --silent --fail --max-time 1 http://127.0.0.1:9335/json/version >/dev/null && break
    sleep 1
  done
fi
if ! curl --silent --fail --max-time 2 http://127.0.0.1:8770/health >/dev/null; then
  TASK_PLUGIN=("$HOME"/.codex/plugins/cache/ekko-local-tools/codex-usage-lab/*/plugin_api.py(N))
  if (( ${#TASK_PLUGIN} == 0 )); then print '未找到已安装的用量实验室插件。'; exit 1; fi
  python3 "${TASK_PLUGIN[-1]}"
fi
exec "$TASK_NODE" "$TASK_DIR/bridge.mjs"
