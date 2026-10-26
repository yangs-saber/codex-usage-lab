# 自动用量提示验证记录

2026-10-26，本机 Codex 0.164.0-alpha.11.1。

- 26 项 Python 测试通过：轮次与会话精确匹配、response ID 去重、缓存不重复计算、未知计价不当免费、配置合并与关闭、异常输入、现有 HTTP 和 MCP 功能。
- `tests/check_hook_runtime.py` 使用临时 CODEX_HOME 和本地假模型服务器。真实 Codex 生成逐次 Token 记录并自动执行 Stop Hook；脚本输出与记录一致，包含最后一次响应：1,010 Token、40% 缓存、估算 0.034 Credits。假模型不产生付费模型请求。
- 测试专用的临时进程使用 Hook 信任豁免来执行已审阅的测试代码，不写用户信任数据库。普通安装和用户级注册不使用豁免。
- 本机真实日志直接读取测试约 82ms；这是一次测量，不是性能保证。
- 实际用户配置已由 `hooks/list` 识别为 Stop、enabled=true、source=user、trustStatus=untrusted。需要人审阅并信任后才能执行。

## 已知限制

当前版本未发现插件包内的 Hook，但发现并执行了用户级 Hook，因此提供按用户要求启用的兼容注册。其他支持插件包 Hook 的版本不应重复注册。

自动执行成功与桌面渲染成功是两项不同的验收。本轮没有观测到桌面最终渲染。官方输出 `systemMessage` 是警告 / 事件流字段，桌面可能采用警告样式，也可能只在 Hook 明细显示，无法保证放在原生「用时」右侧。不能据此宣称已经实现原生小字条。

执行复现检查：

```sh
CODEX_TEST_BINARY=/path/to/codex python3 tests/check_hook_runtime.py
```

普通用户在插件中说“开启每轮自动用量提示”，由 Skill 配置兼容注册；用户无需运行这个开发测试。
