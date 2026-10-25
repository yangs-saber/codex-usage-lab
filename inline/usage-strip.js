// Local renderer customization. Inject only into Codex's app://- main page.
(() => {
  const key = "__codexUsageStripV1";
  if (window[key]) return;
  const rows = new Map();
  const badges = new Set();
  const isId = (value) =>
    typeof value === "string" && /^[a-zA-Z0-9_-]{8,100}$/.test(value);
  function identity(button) {
    const fiberKey = Object.keys(button).find((k) =>
      k.startsWith("__reactFiber$"),
    );
    let fiber = fiberKey && button[fiberKey];
    for (let depth = 0; fiber && depth < 100; depth++, fiber = fiber.return) {
      const props = fiber.memoizedProps;
      if (!props || typeof props !== "object") continue;
      const thread = props.conversationId ?? props.threadId;
      const turn = props.turnId ?? props.mcpTurn?.turnId;
      if (isId(thread) && isId(turn)) return { thread, turn };
    }
    return null; // Never substitute a recent chat or infer a turn from row order.
  }
  function buttons() {
    return [...document.querySelectorAll("button[aria-expanded]")].filter((b) =>
      /^(?:用时\s*|耗时\s*|工作了\s*|Worked for\s+)/i.test(
        b.textContent.trim(),
      ),
    );
  }
  const number = (value) =>
    new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value);
  function text(row) {
    const tokens =
      row.tokens >= 10000
        ? `${number(row.tokens / 10000)}万`
        : number(row.tokens);
    const credits =
      row.credits == null
        ? "未定价"
        : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(
            row.credits,
          );
    return `本轮 ${tokens} Token · 估算 ${credits}${row.credits == null ? "" : " Credits"}${row.unpricedCalls && row.credits != null ? "（部分未定价）" : ""}`;
  }
  function render() {
    const active = new Set();
    for (const button of buttons()) {
      const id = identity(button);
      if (!id) continue;
      const row = rows.get(`${id.thread}:${id.turn}`);
      if (!row) continue;
      const parent = button.parentElement;
      if (!parent) continue;
      let badge = [...parent.children].find(
        (e) => e.dataset?.usageLabStrip === "true",
      );
      if (!badge) {
        badge = document.createElement("span");
        badge.dataset.usageLabStrip = "true";
        badge.style.cssText =
          "display:inline-block;margin-inline-start:12px;font-size:12px;line-height:1.4;opacity:.72;font-variant-numeric:tabular-nums;vertical-align:baseline;white-space:normal;overflow-wrap:anywhere;";
        parent.append(badge);
        badges.add(badge);
      }
      const label = text(row);
      const title = `输入 ${number(row.input)}（含缓存 ${number(row.cached)}）；输出 ${number(row.output)}；${row.calls} 次调用。Credits 为本地估算，非账单。${row.assumedSpeedCalls ? "部分调用按 Standard 速度估算。" : ""}`;
      if (badge.textContent !== label) badge.textContent = label;
      if (badge.title !== title) badge.title = title;
      active.add(badge);
    }
    for (const badge of badges) {
      if (!active.has(badge)) {
        badge.remove();
        badges.delete(badge);
      }
    }
  }
  let pending = false;
  const observer = new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      render();
    });
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  window[key] = {
    visibleTurns: () => buttons().map(identity).filter(Boolean),
    update(data) {
      rows.clear();
      for (const row of data) {
        if (isId(row.thread_id) && isId(row.turn_id))
          rows.set(`${row.thread_id}:${row.turn_id}`, row);
      }
      render();
      return { matched: badges.size };
    },
    remove() {
      observer.disconnect();
      badges.forEach((badge) => badge.remove());
      delete window[key];
    },
  };
})();
