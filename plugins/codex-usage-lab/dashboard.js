"use strict";
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const demo = params.get("demo") === "1",
  focusThread = params.get("thread_id");
let data = null,
  filtered = [],
  period = focusThread ? "all" : "week",
  view = "overview";
let selected = focusThread,
  activeTurn = null,
  callLimit = 100,
  busy = false;
const colors = [
  "var(--accent)",
  "var(--green)",
  "var(--blue)",
  "var(--orange)",
];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (n) =>
  new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(n ?? 0);
const compact = (n) =>
  n >= 1e8
    ? `${(n / 1e8).toFixed(2)}亿`
    : n >= 1e4
      ? `${(n / 1e4).toFixed(2)}万`
      : fmt(n);
const sum = (rows, key) => rows.reduce((n, r) => n + (Number(r[key]) || 0), 0);
function group(rows, key) {
  const groups = new Map();
  for (const row of rows) {
    const id = typeof key === "function" ? key(row) : row[key];
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(row);
  }
  return [...groups];
}
function credits(rows) {
  const known = rows.filter((r) => r.credits != null),
    missing = rows.length - known.length;
  if (rows.length && !known.length) return "未计价";
  return fmt(sum(known, "credits")) + (missing ? " + 未计价" : "");
}
function date(value, time = false) {
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "时间未记录"
    : d.toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
      });
}
const empty = (label) =>
  `<div class="empty">${label || "当前筛选下暂无记录。试试其他时间范围。"}</div>`;
function table(headers, rows) {
  return rows.length
    ? `<table><thead><tr>${headers.map((h, i) => `<th${i > 1 ? ' class="num"' : ""}>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`
    : empty();
}
function options(id, pairs, label) {
  const el = $(id),
    old = el.value;
  el.innerHTML =
    `<option value="all">${label}</option>` +
    pairs
      .map(
        ([value, text]) =>
          `<option value="${esc(value)}">${esc(text)}</option>`,
      )
      .join("");
  el.value = [...el.options].some((o) => o.value === old) ? old : "all";
}
async function load() {
  if (busy) return;
  busy = true;
  $("refresh").disabled = true;
  try {
    const response = await fetch(demo ? "/demo.json" : "/api/usage", {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const next = await response.json();
    if (next.error) throw Error(next.error);
    if (next.loading) {
      $("status").textContent = "首次索引中，稍后自动更新…";
      return;
    }
    data = next;
    data.annotations ||= {};
    data.turnTimes ||= {};
    options(
      "project",
      group(data.records, "projectId").map(([id, rs]) => [id, rs[0].project]),
      "所有项目",
    );
    options(
      "model",
      [...new Set(data.records.map((r) => r.model))].sort().map((m) => [m, m]),
      "所有模型",
    );
    $("error").hidden = true;
    render();
    $("status").textContent = demo
      ? "● 演示数据 · 不读取本机"
      : `● 已同步 ${new Date(data.updated).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent =
      `本地数据暂时无法更新：${e.message}。${data ? "当前保留上一次结果。" : "请确认用量实验室服务已启动。"}`;
    $("status").textContent = "连接中断 · 等待重试";
  } finally {
    busy = false;
    $("refresh").disabled = false;
  }
}
function render() {
  if (!data) return;
  const cutoff = new Date(`${data.today}T00:00:00+08:00`);
  cutoff.setUTCDate(cutoff.getUTCDate() - 6);
  const weekStart = new Date(cutoff.getTime() + 8 * 3600000)
    .toISOString()
    .slice(0, 10);
  filtered = data.records.filter(
    (r) =>
      (!focusThread || r.thread === focusThread) &&
      (period === "all" ||
        (r.date <= data.today &&
          r.date >= (period === "today" ? data.today : weekStart))) &&
      ($("project").value === "all" || r.projectId === $("project").value) &&
      ($("model").value === "all" || r.model === $("model").value) &&
      r.title
        .toLocaleLowerCase()
        .includes($("search").value.trim().toLocaleLowerCase()),
  );
  const rs = filtered,
    total = sum(rs, "total"),
    input = sum(rs, "input"),
    cached = sum(rs, "cached"),
    output = sum(rs, "output");
  const turns = group(rs, (r) => `${r.thread}:${r.turn}`),
    threads = group(rs, "thread");
  $("total").textContent = compact(total);
  $("total").title = `${fmt(total)} Token`;
  $("total-sub").textContent = `${fmt(rs.length)} 次模型调用`;
  $("credits").textContent = credits(rs);
  const missing = rs.filter((r) => r.credits == null).length,
    assumed = rs.filter((r) => !r.tierKnown).length;
  $("pricing-note").textContent = missing
    ? `${missing} 次调用未计价，非免费`
    : assumed
      ? `${assumed} 次按 Standard 估算 · 非账单`
      : "按记录速度折算 · 非实际扣费";
  $("cache").textContent = input
    ? `${((100 * cached) / input).toFixed(1)}%`
    : "—";
  $("cache-sub").textContent =
    `${compact(cached)} 缓存 / ${compact(input)} 输入`;
  $("chats").textContent = fmt(threads.length);
  $("chat-sub").textContent = `${fmt(turns.length)} 轮用户交互`;
  drawTrend(rs, weekStart);
  drawComposition(total, input, cached, output);
  const recent = threads.sort((a, b) =>
    latest(b[1]).localeCompare(latest(a[1])),
  );
  $("recent-table").innerHTML = threadTable(recent.slice(0, 5));
  $("all-table").innerHTML = threadTable(recent);
  $("thread-count").textContent = `${threads.length} 个对话`;
  ranks(
    "projects",
    group(rs, "projectId").map(([id, x]) => [x[0].project, sum(x, "total")]),
    total,
  );
  const models = group(rs, "model").sort(
    (a, b) => sum(b[1], "total") - sum(a[1], "total"),
  );
  ranks(
    "model-ranks",
    models.map(([id, x]) => [id, sum(x, "total")]),
    total,
  );
  $("model-table").innerHTML = table(
    [
      "模型",
      "调用 / 用户轮次",
      "输入（含缓存）",
      "缓存输入",
      "输出",
      "总 Token",
      "估算 Credits",
    ],
    models.map(
      ([name, x]) =>
        `<tr><td><span class="pill">${esc(name)}</span></td><td>${fmt(x.length)} / ${group(x, (r) => r.thread + ":" + r.turn).length}</td><td class="num">${fmt(sum(x, "input"))}</td><td class="num">${fmt(sum(x, "cached"))}</td><td class="num">${fmt(sum(x, "output"))}</td><td class="num">${fmt(sum(x, "total"))}</td><td class="num credits-cell">${credits(x)}</td></tr>`,
    ),
  );
  comparison();
  coverage();
  if (selected) detail(selected, false);
  if (activeTurn) calls(activeTurn, false);
}
const latest = (rows) =>
  rows.reduce((last, r) => (r.time > last ? r.time : last), "");
function threadTable(groups) {
  return table(
    ["对话", "项目", "用户轮次", "总 Token", "估算 Credits"],
    groups.map(
      ([id, rows]) =>
        `<tr><td><div class="row-title"><span class="row-icon">▤</span><div><button class="row-name" data-thread="${esc(id)}" title="${esc(rows[0].title)}">${esc(rows[0].title)}</button><small>${date(latest(rows), true)} · ${rows.length} 次调用</small></div></div></td><td>${esc(rows[0].project)}</td><td class="num">${group(rows, "turn").length}</td><td class="num">${compact(sum(rows, "total"))}</td><td class="num credits-cell">${credits(rows)}</td></tr>`,
    ),
  );
}
function ranks(id, pairs, total) {
  $(id).innerHTML =
    pairs
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(
        ([label, value], i) =>
          `<div><div class="rank-top"><span>${esc(label)}</span><strong>${compact(value)} <span class="muted">· ${total ? ((100 * value) / total).toFixed(1) : 0}%</span></strong></div><div class="rank-track"><div class="rank-fill" style="width:${total ? (100 * value) / total : 0}%;background:${colors[i % colors.length]}"></div></div></div>`,
      )
      .join("") || empty("暂无记录");
}
function drawComposition(total, input, cached, output) {
  const values = [Math.max(0, input - cached), cached, output],
    labels = ["非缓存输入", "缓存输入", "输出（含推理）"];
  const a = total ? (values[0] / total) * 100 : 0,
    b = total ? ((values[0] + values[1]) / total) * 100 : 0;
  $("donut").style.background = total
    ? `conic-gradient(var(--accent) 0 ${a}%,var(--green) ${a}% ${b}%,var(--blue) ${b}% 100%)`
    : "var(--line)";
  $("donut-total").textContent = compact(total);
  $("composition").innerHTML = values
    .map(
      (n, i) =>
        `<div class="composition-row"><i class="mini-dot" style="background:${colors[i]}"></i>${labels[i]}<strong title="${fmt(n)}">${compact(n)}</strong><em>${total ? ((100 * n) / total).toFixed(1) : "0"}%</em></div>`,
    )
    .join("");
}
function drawTrend(rows, weekStart) {
  let start =
    period === "today"
      ? data.today
      : period === "week"
        ? weekStart
        : rows
            .map((r) => r.date)
            .filter(Boolean)
            .sort()[0];
  if (!start) {
    $("trend").innerHTML = empty("有记录后，这里会出现用量趋势。");
    return;
  }
  const end =
    period === "all"
      ? rows
          .map((r) => r.date)
          .filter(Boolean)
          .sort()
          .at(-1) || data.today
      : data.today;
  const days = Math.max(
      1,
      Math.round((new Date(end) - new Date(start)) / 86400000) + 1,
    ),
    bucketSize = Math.max(1, Math.ceil(days / 60));
  const buckets = Array.from(
    { length: Math.ceil(days / bucketSize) },
    (_, i) => ({
      day: new Date(new Date(start).getTime() + i * bucketSize * 86400000)
        .toISOString()
        .slice(0, 10),
      value: 0,
    }),
  );
  for (const r of rows) {
    const i = Math.floor(
      (new Date(r.date) - new Date(start)) / 86400000 / bucketSize,
    );
    if (buckets[i]) buckets[i].value += r.total;
  }
  const W = 660,
    H = 225,
    L = 48,
    R = 15,
    T = 12,
    B = 32,
    max = Math.max(1, ...buckets.map((b) => b.value)) * 1.15;
  const x = (i) =>
      buckets.length === 1
        ? (L + W - R) / 2
        : L + (i / (buckets.length - 1)) * (W - L - R),
    y = (n) => H - B - (n / max) * (H - T - B);
  const points = buckets.map((b, i) => `${x(i)},${y(b.value)}`).join(" "),
    firstX = x(0),
    lastX = x(buckets.length - 1);
  const grid = [0, 1, 2, 3]
    .map((i) => {
      const n = (max / 3) * i;
      return `<line class="gridline" x1="${L}" y1="${y(n)}" x2="${W - R}" y2="${y(n)}"/><text x="${L - 9}" y="${y(n) + 3}" text-anchor="end">${compact(n)}</text>`;
    })
    .join("");
  const stride = Math.max(1, Math.ceil(buckets.length / 7));
  const labels = buckets
    .map((b, i) =>
      i % stride === 0 || i === buckets.length - 1
        ? `<text x="${x(i)}" y="${H - 7}" text-anchor="middle">${b.day.slice(5).replace("-", "/")}</text>`
        : "",
    )
    .join("");
  $("trend").innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(bucketSize > 1 ? `每 ${bucketSize} 天汇总` : "每日")} Token 趋势"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".22"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>${grid}<polygon class="area" points="${firstX},${H - B} ${points} ${lastX},${H - B}"/><polyline class="chart-line" points="${points}"/>${buckets.map((b, i) => `<circle cx="${x(i)}" cy="${y(b.value)}" r="${buckets.length < 15 ? 3 : 2}" fill="var(--accent)"><title>${b.day}${bucketSize > 1 ? ` 起 ${bucketSize} 天` : ""}：${fmt(b.value)} Token</title></circle>`).join("")}${labels}</svg>`;
}
function detail(id, scroll = true) {
  if (selected !== id) {
    activeTurn = null;
    $("calls-panel").hidden = true;
  }
  selected = id;
  const rows = filtered.filter((r) => r.thread === id);
  if (!rows.length) {
    $("detail").hidden = true;
    $("calls-panel").hidden = true;
    activeTurn = null;
    return;
  }
  $("detail").hidden = false;
  $("detail-title").textContent = rows[0].title;
  $("turn-table").innerHTML = table(
    [
      "轮次开始 / 任务",
      "模型 / 调用",
      "输入（含缓存）",
      "缓存输入",
      "输出",
      "估算 Credits",
    ],
    group(rows, "turn")
      .sort((a, b) => latest(b[1]).localeCompare(latest(a[1])))
      .map(
        ([turn, rs]) =>
          `<tr><td><button class="row-name" data-turn="${esc(turn)}">${date(rs.map((r) => r.time).sort()[0], true)} ↗</button><small>${esc(data.annotations[id + ":" + turn]?.task || "未标注任务")}</small></td><td>${esc([...new Set(rs.map((r) => r.model))].join(" / "))}<small>${rs.length} 次调用</small></td><td class="num">${fmt(sum(rs, "input"))}</td><td class="num">${fmt(sum(rs, "cached"))}</td><td class="num">${fmt(sum(rs, "output"))}</td><td class="num credits-cell">${credits(rs)}</td></tr>`,
      ),
  );
  if (scroll)
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
}
function calls(turn, reset = true) {
  activeTurn = turn;
  if (reset) callLimit = 100;
  const rows = filtered
    .filter((r) => r.thread === selected && r.turn === turn)
    .sort((a, b) => a.time.localeCompare(b.time));
  if (!rows.length) {
    $("calls-panel").hidden = true;
    return;
  }
  const key = selected + ":" + turn,
    note = data.annotations[key] || {},
    timing = data.turnTimes[key] || {};
  if (reset) {
    $("task-label").value = note.task || "";
    $("outcome").value = note.outcome || "unrated";
    $("save-status").textContent = "";
  }
  $("duration").textContent =
    timing.start && timing.end
      ? `整轮 ${Math.max(0, Math.round((new Date(timing.end) - new Date(timing.start)) / 1000))} 秒 · 含工具与等待`
      : "起止时间不完整 · 不推算耗时";
  $("calls-panel").hidden = false;
  $("call-table").innerHTML = table(
    [
      "调用时间 / 模型",
      "速度 / 推理强度",
      "输入（含缓存）",
      "缓存输入",
      "输出",
      "估算 Credits",
    ],
    rows
      .slice(0, callLimit)
      .map(
        (r) =>
          `<tr><td>${date(r.time, true)}<small>${esc(r.model)}</small></td><td>${esc(r.tier)}<small>${esc(r.effort)}</small></td><td class="num">${fmt(r.input)}</td><td class="num">${fmt(r.cached)}</td><td class="num">${fmt(r.output)}</td><td class="num">${r.credits == null ? "未计价" : fmt(r.credits)}</td></tr>`,
      ),
  );
  $("more-calls").hidden = rows.length <= callLimit;
  if (reset)
    $("calls-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}
function comparison() {
  const groups = group(filtered, (r) =>
    JSON.stringify([
      data.annotations[r.thread + ":" + r.turn]?.task || "未标注",
      r.model,
      r.effort,
      r.tier,
    ]),
  );
  $("comparison-table").innerHTML = table(
    [
      "任务 / 模型",
      "推理强度 / 速度",
      "轮次",
      "平均 Token",
      "平均 / 中位 Credits",
      "满意 / 已评价",
    ],
    groups.map(([key, rows]) => {
      const [task, model, effort, tier] = JSON.parse(key),
        turns = group(rows, (r) => r.thread + ":" + r.turn);
      const costs = turns
        .filter(([, rs]) => rs.every((r) => r.credits != null))
        .map(([, rs]) => sum(rs, "credits"))
        .sort((a, b) => a - b);
      const notes = turns.map(([id]) => data.annotations[id] || {}),
        middle = costs.length
          ? (costs[Math.floor((costs.length - 1) / 2)] +
              costs[Math.floor(costs.length / 2)]) /
            2
          : null;
      return `<tr><td>${esc(task)}<small>${esc(model)}</small></td><td>${esc(effort)}<small>${esc(tier)}</small></td><td class="num">${turns.length}</td><td class="num">${compact(sum(rows, "total") / turns.length)}</td><td class="num">${costs.length ? `${fmt(costs.reduce((a, b) => a + b, 0) / costs.length)} / ${fmt(middle)}` : "未计价"}<small>完整计价 ${costs.length} / ${turns.length} 轮</small></td><td class="num">${notes.filter((n) => n.outcome === "success").length} / ${notes.filter((n) => n.outcome && n.outcome !== "unrated").length}</td></tr>`;
    }),
  );
}
function coverage() {
  const c = data.coverage || {};
  $("coverage").textContent =
    `数据覆盖 ${fmt(c.coveredThreads)} / ${fmt(c.threads)} 个对话 · 查看计算口径`;
  $("coverage-detail").textContent =
    `扫描 ${fmt(c.files)} 个日志，${fmt(c.errors)} 个读取失败，${fmt(c.gaps?.length)} 个对话存在累计与逐次记录差额。${demo ? "此处为虚构演示。" : "差额可能包含分叉继承，不能视为新增消耗。"}`;
  $("rate-note").textContent =
    `费率日期 ${data.rateDate || "未记录"} · Credits 为估算，非账单或套餐额度`;
}
function setView(next) {
  if (!["overview", "threads", "models", "comparison"].includes(next)) return;
  view = next;
  const names = {
    overview: "用量总览",
    threads: "对话明细",
    models: "模型分析",
    comparison: "任务对比",
  };
  document.querySelectorAll(".view").forEach((el) => {
    el.hidden = el.id !== "view-" + view;
  });
  document
    .querySelectorAll(".nav,.mobile-nav button")
    .forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  $("breadcrumb").textContent = names[view];
  $("page-title").innerHTML =
    `${view === "overview" ? "看清每一次消耗" : names[view]}<span class="title-dot">.</span>`;
}
document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]"),
    thread = event.target.closest("[data-thread]"),
    turn = event.target.closest("[data-turn]"),
    time = event.target.closest("[data-period]");
  if (nav) setView(nav.dataset.view);
  if (thread) detail(thread.dataset.thread);
  if (turn) calls(turn.dataset.turn);
  if (time) {
    period = time.dataset.period;
    document
      .querySelectorAll("[data-period]")
      .forEach((b) =>
        b.classList.toggle("active", b.dataset.period === period),
      );
    render();
  }
});
["project", "model", "search"].forEach((id) =>
  $(id).addEventListener("input", render),
);
$("refresh").onclick = load;
$("theme").onclick = () => {
  document.body.classList.toggle("light");
  try {
    localStorage.setItem(
      "usage-lab-theme",
      document.body.classList.contains("light") ? "light" : "dark",
    );
  } catch {}
};
try {
  if (localStorage.getItem("usage-lab-theme") === "light")
    document.body.classList.add("light");
} catch {}
$("close-detail").onclick = () => {
  selected = null;
  activeTurn = null;
  $("detail").hidden = true;
  $("calls-panel").hidden = true;
};
$("close-calls").onclick = () => {
  activeTurn = null;
  $("calls-panel").hidden = true;
};
$("more-calls").onclick = () => {
  callLimit += 100;
  calls(activeTurn, false);
};
$("note-form").onsubmit = async (event) => {
  event.preventDefault();
  if (!selected || !activeTurn || !data) return;
  const note = {
    thread_id: selected,
    turn_id: activeTurn,
    task: $("task-label").value.trim(),
    outcome: $("outcome").value,
  };
  if (demo) {
    data.annotations[selected + ":" + activeTurn] = note;
    $("save-status").textContent = "仅修改演示内存，未写入本机";
    render();
    return;
  }
  try {
    const response = await fetch("/api/annotate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": data.csrf,
      },
      body: JSON.stringify(note),
      signal: AbortSignal.timeout(10000),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "保存失败");
    $("save-status").textContent = "已保存到本机";
    await load();
  } catch (e) {
    $("save-status").textContent = e.message;
  }
};
$("export").onclick = () => {
  const fields = [
    "time",
    "title",
    "project",
    "thread",
    "turn",
    "model",
    "tier",
    "effort",
    "task",
    "outcome",
    "input",
    "cached",
    "output",
    "reasoning",
    "total",
    "credits",
  ];
  const cell = (value) =>
    '"' +
    String(value ?? "")
      .replace(/^[\s]*[=+@-]/, "'$&")
      .replace(/"/g, '""') +
    '"';
  const csv =
    "\ufeff" +
    [
      fields,
      ...filtered.map((r) =>
        fields.map((k) =>
          ["task", "outcome"].includes(k)
            ? data.annotations[r.thread + ":" + r.turn]?.[k]
            : r[k],
        ),
      ),
    ]
      .map((row) => row.map(cell).join(","))
      .join("\r\n");
  const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = demo ? "codex-usage-demo.csv" : "codex-usage.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
if (focusThread) {
  document.body.classList.add("focus");
  $("subtitle").textContent = "当前对话的逐轮用量 · 每 10 秒自动更新";
}
$("demo-banner").hidden = !demo;
setView("overview");
document
  .querySelectorAll("[data-period]")
  .forEach((b) => b.classList.toggle("active", b.dataset.period === period));
load();
if (!demo) {
  setInterval(() => {
    if (document.visibilityState !== "hidden") load();
  }, 10000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") load();
  });
}
