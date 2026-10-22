// MikeAdamsNC.com: the X-ray view and our own analytics events. No cookies.
(() => {
  const send = (kind, extra = {}) => {
    const body = JSON.stringify({ kind, path: location.pathname, ...extra });
    if (!navigator.sendBeacon?.("/e", new Blob([body], { type: "application/json" })))
      fetch("/e", { method: "POST", body, headers: { "Content-Type": "application/json" }, keepalive: true });
  };

  // X-ray: outline every part that explains itself (data-x="LABEL|what it is").
  const btn = document.querySelector(".lam");
  const draw = () => {
    document.querySelectorAll(".xr").forEach((e) => e.remove());
    if (!document.body.classList.contains("xray")) return;
    document.querySelectorAll("[data-x]").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (!r.width) return;
      const [t, d] = el.dataset.x.split("|");
      const box = document.createElement("div");
      box.className = "xr";
      Object.assign(box.style, { left: r.left + scrollX - 6 + "px", top: r.top + scrollY - 6 + "px", width: r.width + 12 + "px", height: r.height + 12 + "px" });
      const tag = document.createElement("i");
      tag.innerHTML = "<u></u>";
      tag.firstChild.textContent = t;
      tag.append(d || "");
      box.append(tag);
      document.body.append(box);
    });
  };
  const toggle = () => {
    const on = document.body.classList.toggle("xray");
    btn.setAttribute("aria-pressed", on);
    document.querySelector(".xside").setAttribute("aria-hidden", !on);
    draw();
    send(on ? "xray_open" : "xray_close");
  };
  btn?.addEventListener("click", toggle);
  addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() === "x" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !e.metaKey && !e.ctrlKey) toggle();
  });
  addEventListener("resize", draw);

  // Scroll depth (25/50/75/100), once each per page view.
  const marks = new Set();
  addEventListener("scroll", () => {
    const h = document.documentElement.scrollHeight - innerHeight;
    const pct = h <= 0 ? 100 : Math.round((scrollY / h) * 100);
    for (const m of [25, 50, 75, 100]) if (pct >= m && !marks.has(m)) { marks.add(m); send("scroll", { value: m }); }
  }, { passive: true });

  // Links out, buttons, and the first keystroke in the pitch form.
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a");
    if (!a) return;
    if (a.host && a.host !== location.host) send("outbound", { detail: a.host });
    else if (a.dataset.cta) send("cta", { detail: a.dataset.cta });
  });
  // Thumbs: tap once to vote, tap the same one again to take it back.
  document.querySelectorAll(".vote").forEach((box) => {
    const slug = box.dataset.slug;
    const saved = localStorage.getItem("vote:" + slug);
    if (saved && box.dataset.mine === "0") paint(box, +saved);
    box.addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const want = +b.dataset.v === +box.dataset.mine ? 0 : +b.dataset.v;
      try {
        const r = await fetch("/vote/" + slug, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: want }) });
        if (!r.ok) return;
        const t = await r.json();
        box.querySelector(".n-up").textContent = t.up;
        box.querySelector(".n-down").textContent = t.down;
        paint(box, t.mine);
        localStorage.setItem("vote:" + slug, t.mine);
      } catch (_) {}
    });
  });
  function paint(box, v) {
    box.dataset.mine = v;
    box.querySelectorAll("button").forEach((b) => { const on = +b.dataset.v === v; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  }

  const form = document.querySelector("form.form");
  form?.addEventListener("input", () => send("pitch_start"), { once: true });
})();
