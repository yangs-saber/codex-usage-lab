import { App } from "@modelcontextprotocol/ext-apps";
const app = new App(
  { name: "Codex 实时用量", version: "0.5.0" },
  {},
  { autoResize: true },
);
const $ = (id) => document.getElementById(id),
  fmt = (n) => new Intl.NumberFormat("zh-CN").format(n || 0),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
let selected = "",
  busy = false,
  ready = false,
  lastData = null,
  collapsed = false,
  threads = [],
  explicit = false;
function remember() {
  try {
    window.openai?.setWidgetState?.({ threadId: selected, collapsed });
  } catch {}
}
function credits(s) {
  return s.credits == null
    ? "未知"
    : s.credits.toFixed(3) + (s.unpricedCalls ? " + 未计价" : "");
}
async function call(name, args = {}) {
  const r = await app.callServerTool({ name, arguments: args });
  if (r.isError) throw Error(r.content?.[0]?.text || "查询失败");
  return r.structuredContent;
}
function choices(rows) {
  threads = rows;
  $("thread").innerHTML =
    '<option value="">选择要跟踪的对话…</option>' +
    rows
      .map(
        (r) => `<option value="${esc(r.thread_id)}">${esc(r.title)}</option>`,
      )
      .join("");
  if (selected && !rows.some((r) => r.thread_id === selected))
    $("thread").add(new Option("已绑定对话 " + selected.slice(0, 8), selected));
  $("thread").value = selected;
}
function paint(d) {
  lastData = d;
  const s = d.summary;
  $("total").textContent = fmt(s.tokens);
  $("credits").textContent = credits(s);
  $("title").textContent = d.rows[0]?.title || "已选对话暂无逐次记录";
  const latest = d.rows[0];
  $("lastTokens").textContent = latest ? fmt(latest.tokens) : "—";
  $("lastCredits").textContent = latest ? credits(latest) : "—";
  $("cache").textContent = s.input
    ? ((100 * s.cached) / s.input).toFixed(1) + "%"
    : "—";
  $("status").textContent =
    "● " +
    new Date(d.updated).toLocaleTimeString("zh-CN", {
      timeZone: "Asia/Shanghai",
    }) +
    " 更新";
  $("compact").textContent =
    `${fmt(s.tokens)} tokens · ≈ ${credits(s)} credits`;
  $("rows").innerHTML = d.rows
    .map(
      (r) =>
        `<tr><td><span>${esc((r.timing?.message || "用户消息摘录不可用").replace(/\s+/g," ").slice(0,72))}</span><small>${esc(new Date(r.first).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }))}</small><small>${esc(r.models.join(" / "))} · ${r.calls} 次调用</small></td><td>${fmt(r.tokens)}</td><td>${credits(r)}</td></tr>`,
    )
    .join("");
  $("info").textContent =
    `最近 ${d.rows.length} / ${d.totalRows} 轮 · ${s.calls} 次调用 · 缓存命中 ${$("cache").textContent}`;
  $("note").textContent =
    `Credits 是估算，不是扣费。${s.assumedSpeedCalls} 次调用缺少速度，按 Standard 折算；${s.unpricedCalls} 次未计价。仅含保留的本机逐次记录。`;
  $("values").hidden = false;
}
async function refresh() {
  if (!ready || busy) return;
  busy = true;
  try {
    if (!selected) {
      const d = await call("query_usage", { group_by: "thread", limit: 100 });
      if (d.loading) {
        $("status").textContent = "正在索引…";
        return;
      }
      choices(d.rows);
      $("status").textContent = "选择一次，随后自动刷新";
      return;
    }
    const d = await call("query_usage", {
      group_by: "turn",
      thread_id: selected,
      limit: 30,
    });
    if (d.loading) {
      $("status").textContent = "正在索引…";
      return;
    }
    paint(d);
    $("error").textContent = "";
  } catch (e) {
    $("error").textContent = "刷新失败：" + e.message;
    $("status").textContent = "未更新，请重试";
  } finally {
    busy = false;
  }
}
function toggle() {
  collapsed = !collapsed;
  $("body").hidden = collapsed;
  $("collapse").textContent = collapsed ? "展开" : "收起";
  remember();
}
$("thread").onchange = () => {
  selected = $("thread").value;
  explicit = true;
  remember();
  $("values").hidden = true;
  refresh();
};
$("refresh").onclick = refresh;
$("collapse").onclick = toggle;
app.ontoolresult = (params) => {
  const d = params.structuredContent;
  if (d?.thread_id && !explicit) {
    selected = d.thread_id;
    explicit = true;
  }
  if (d?.threads) choices(d.threads);
  refresh();
};
(async () => {
  try {
    const saved = window.openai?.widgetState;
    if (saved?.threadId) {
      selected = saved.threadId;
      explicit = true;
    }
    if (saved?.collapsed) toggle();
    await app.connect();
    ready = true;
    await refresh();
    setInterval(() => {
      if (document.visibilityState !== "hidden") refresh();
    }, 10000);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "hidden") refresh();
    });
  } catch (e) {
    $("error").textContent = "未连接到 Codex 插件界面：" + e.message;
  }
})();
