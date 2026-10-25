import fs from "node:fs/promises";
const origin = "http://127.0.0.1:9335";
const usageOrigin = "http://127.0.0.1:8770";
const script = await fs.readFile(
  new URL("./usage-strip.js", import.meta.url),
  "utf8",
);
const sessions = new Map();
const restore = process.argv.includes("--restore");
let stopped = false;
process.on("SIGINT", () => {
  stopped = true;
});
process.on("SIGTERM", () => {
  stopped = true;
});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function json(url, options = {}) {
  const r = await fetch(url, { ...options, signal: AbortSignal.timeout(5000) });
  if (!r.ok) throw new Error(`${new URL(url).pathname}: HTTP ${r.status}`);
  return r.json();
}
class Session {
  constructor(socket) {
    this.socket = socket;
    this.pending = new Map();
    this.counter = 0;
    socket.addEventListener("message", (event) => {
      const data = JSON.parse(event.data);
      const pending = this.pending.get(data.id);
      if (!pending) return;
      clearTimeout(pending.timer);
      this.pending.delete(data.id);
      data.error
        ? pending.reject(new Error(data.error.message))
        : pending.resolve(data.result);
    });
    socket.addEventListener("close", () => {
      for (const p of this.pending.values()) {
        clearTimeout(p.timer);
        p.reject(new Error("页面已关闭"));
      }
      this.pending.clear();
    });
  }
  async evaluate(expression) {
    const id = ++this.counter;
    const result = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("页面响应超时"));
      }, 5000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(
        JSON.stringify({
          id,
          method: "Runtime.evaluate",
          params: { expression, returnByValue: true },
        }),
      );
    });
    if (result.exceptionDetails) throw new Error("页面脚本执行失败");
    return result.result?.value;
  }
  close() {
    this.socket.close();
  }
}
async function connect(target) {
  const url = new URL(target.webSocketDebuggerUrl);
  if (!["127.0.0.1", "localhost"].includes(url.hostname) || url.port !== "9335")
    throw new Error("拒绝非本机调试连接");
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error("连接超时"));
    }, 5000);
    socket.addEventListener(
      "open",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
    socket.addEventListener(
      "error",
      () => {
        clearTimeout(timer);
        reject(new Error("连接失败"));
      },
      { once: true },
    );
  });
  return new Session(socket);
}
async function queryTurns(thread) {
  const rows = [];
  let offset = 0;
  for (let pages = 0; pages < 20; pages++) {
    const data = await json(`${usageOrigin}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        group_by: "turn",
        thread_id: thread,
        limit: 100,
        offset,
      }),
    });
    if (data.loading) return null;
    rows.push(...(data.rows ?? []));
    if (data.nextOffset == null) return rows;
    offset = data.nextOffset;
  }
  return rows;
}
async function tick() {
  const targets = (await json(`${origin}/json/list`)).filter((t) => {
    try {
      const u = new URL(t.url);
      return t.type === "page" && u.protocol === "app:" && u.hostname === "-";
    } catch {
      return false;
    }
  });
  for (const [id, session] of sessions) {
    if (!targets.some((t) => t.id === id)) {
      session.close();
      sessions.delete(id);
    }
  }
  const cache = new Map();
  for (const target of targets) {
    try {
      let session = sessions.get(target.id);
      if (!session) {
        session = await connect(target);
        sessions.set(target.id, session);
      }
      if (restore) {
        await session.evaluate("window.__codexUsageStripV1?.remove()");
        continue;
      }
      await session.evaluate(script);
      const ids = await session.evaluate(
        "window.__codexUsageStripV1.visibleTurns()",
      );
      const rows = [];
      let loading = false;
      for (const thread of new Set((ids ?? []).map((id) => id.thread))) {
        if (!cache.has(thread)) cache.set(thread, await queryTurns(thread));
        if (cache.get(thread) == null) loading = true;
        else rows.push(...cache.get(thread));
      }
      if (!loading) {
        const result = await session.evaluate(
          `window.__codexUsageStripV1.update(${JSON.stringify(rows)})`,
        );
        if (result?.matched && !session.reported) {
          console.log(`已在 ${result.matched} 条「用时」旁显示本轮用量。`);
          session.reported = true;
        }
      }
    } catch (error) {
      sessions.get(target.id)?.close();
      sessions.delete(target.id);
      console.error(error.message);
    }
  }
  return targets.length;
}
console.log(
  restore
    ? "正在移除用量小字条…"
    : "用量小字条：等待 Codex 页面；每 10 秒读取本机记录。按 Control+C 停止。",
);
try {
  do {
    await tick();
    if (!restore && !stopped) await sleep(10000);
  } while (!restore && !stopped);
} catch (error) {
  console.error(`尚未启用：${error.message}。请使用附带的启动文件。`);
  process.exitCode = 1;
} finally {
  for (const session of sessions.values()) {
    if (!restore)
      await session
        .evaluate("window.__codexUsageStripV1?.remove()")
        .catch(() => {});
    session.close();
  }
}
