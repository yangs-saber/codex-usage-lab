---
name: usage-lab
description: 查看本机 Codex 每轮、每次调用、对话和项目的 token 与估算 credits，按任务类型、模型、速度和推理强度比较使用情况，或打开用量实验室。
---

# 用量实验室

The user wants usage visible beside the *current chat*, not a generic browser dashboard. First get the current chat ID from `CODEX_THREAD_ID` in the local execution environment when it exists. Never substitute the most recently active chat. Start the local service with `python3 ../../plugin_api.py` relative to this skill directory if needed. Open `http://127.0.0.1:8770/?thread_id=<CODEX_THREAD_ID>` in this chat's Codex side panel with `mcp__codex_app__open_in_codex` (browser target). This focused panel shows current-chat totals and per-turn rows and refreshes every 10 seconds. If the Codex panel tool is unavailable, provide the exact focused URL; do not call the generic dashboard a chat-native meter.

Use this plugin's `open_usage_dashboard`, `query_usage`, and `annotate_usage_turn` MCP tools when actually loaded. The `open_usage_dashboard` tool advertises an MCP App thread entrypoint titled 实时用量, but installation alone does not prove the host loaded that entrypoint. If it is absent, use the focused side-panel route above and state the limitation clearly. Only say a native plugin tab is working after observing it in the Codex UI.

For a usage question, start with a bounded query (20–30 rows). `group_by` supports `thread`, `turn`, `call`, `project`, `model`, and `comparison`. Filter by thread ID, project ID, model, date, task label, or title search. Follow `nextOffset` only when needed. If indexing is still running, report that briefly and retry later rather than claiming zero usage.

Interpretation:
- Keep token counts and credits estimates separate. Input includes cached input; output includes reasoning. Never add either subset twice.
- Credits use a dated rate card, recorded speed, or an explicit Standard assumption when speed is absent. Unknown models or tiers are unpriced. Estimates are not account deductions or subscription-limit percentages.
- Retained local logs define coverage; older cumulative-only history, cloud work, and other devices may be absent. Read returned coverage before claiming completeness.
- A user turn may contain many model calls and several models. A call is not a whole task. Cross-model turns appear in multiple comparison groups.
- Compare like-labelled tasks with similar scope, effort, speed, and satisfactory outcomes. Small or self-selected samples do not establish causal model rankings. Show sample counts and unpriced coverage.
- Save task/outcome annotations only when the user provides them or asks to save a specific classification. Do not infer satisfaction from a task-complete event. Annotations are local, editable, and reversible.

Do not start automatic model-based monitoring or add commentary to every chat. The dashboard refreshes without model calls. Requesting analysis through this chat consumes normal model usage.
