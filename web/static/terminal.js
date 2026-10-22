// The Terminal version: the whole site as a command line. Reads /api/site.json.
(() => {
  const out = document.getElementById("tout"), form = document.getElementById("tin"), cmd = document.getElementById("cmd");
  let data = null;
  const hist = [];
  let hi = 0;
  const beacon = (detail) => navigator.sendBeacon?.("/e", new Blob([JSON.stringify({ kind: "terminal_command", path: "/", detail })], { type: "application/json" }));

  const line = (html, cls = "") => { const d = document.createElement("div"); d.className = "tl " + cls; d.innerHTML = html; out.append(d); out.scrollTop = out.scrollHeight; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = (href, text) => `<a href="${esc(href)}">${esc(text)}</a>`;
  const narrow = matchMedia("(max-width:820px)").matches;
  const pad = (s, n) => (narrow ? esc(s) + " " : esc(s).padEnd(n, " "));

  const COMMANDS = {
    help: () => {
      line("Commands:");
      [["about", "who's behind this"], ["projects", "things I keep running"], ["project <name>", "one project, e.g. project archer"],
       ["lab [hot|new|top]", "experiments, flops included"], ["exp <number>", "one experiment, e.g. exp 6"],
       ["vote <number> up|down", "thumbs up or down"], ["pitch", "pitch me an idea"], ["socials", "where else I am"],
       ["versions", "other ways to see this site"], ["classic", "back to the normal site"], ["clear", "clear the screen"]]
        .forEach(([c, d]) => line(`  <b>${pad(c, 24)}</b><span class="dim">${esc(d)}</span>`));
    },
    about: () => { line(esc(data.site.about)); line(`<span class="dim">${esc(data.site.headline)}</span>`); },
    projects: () => data.projects.forEach((p) => line(`  <b>${pad(p.slug, 16)}</b>${esc(p.line)} <span class="t-ok">[${esc(p.status)}]</span>`)),
    project: (name) => {
      const p = data.projects.find((x) => x.slug === name || x.name.toLowerCase() === (name || "").toLowerCase());
      if (!p) return line(`project: try one of ${data.projects.map((x) => x.slug).join(", ")}`, "t-err");
      line(`<b>${esc(p.name)}</b> <span class="t-ok">[${esc(p.status)}]</span>`); line(esc(p.body));
      line(`<span class="dim">built with: ${esc(p.built_with.join(", "))}</span>`);
      line(p.link ? link(p.link, p.link) + "  " + link(`/projects/${p.slug}`, "page") : link(`/projects/${p.slug}`, "open the page"));
    },
    lab: (how = "hot") => {
      let ex = [...data.experiments];
      if (how === "new") ex.sort((a, b) => String(b.added).localeCompare(String(a.added)));
      if (how === "top") ex.sort((a, b) => (b.up - b.down) - (a.up - a.down));
      ex.forEach((e) => line(`  <b>${e.number.replace("EXP ", "")}</b>  ${pad(e.title, 40)} <span class="${e.verdict === "flop" ? "t-err" : "t-ok"}">${esc(e.verdict_label.toLowerCase())}</span> <span class="dim">▲${e.up - e.down}</span>`));
      line(`<span class="dim">exp &lt;number&gt; to read one · vote &lt;number&gt; up</span>`);
    },
    exp: (n) => {
      const e = data.experiments.find((x) => parseInt(x.number.replace("EXP ", ""), 10) === parseInt(n, 10));
      if (!e) return line("exp: give a number, e.g. exp 2", "t-err");
      line(`<b>${esc(e.number)} · ${esc(e.title)}</b>`);
      line(`<span class="dim">question:</span> ${esc(e.question)}`);
      line(`<span class="dim">used:</span>     ${esc(e.used.join(", "))}`);
      line(`<span class="dim">result:</span>   ${esc(e.result)}`);
      line(`<span class="dim">verdict:</span>  <span class="${e.verdict === "flop" ? "t-err" : "t-ok"}">${esc(e.verdict_label)}</span>. ${esc(e.verdict_line)}`);
      line(link(`/lab/${e.slug}`, "open the page (comments live there)"));
    },
    vote: async (n, dir) => {
      const e = data.experiments.find((x) => parseInt(x.number.replace("EXP ", ""), 10) === parseInt(n, 10));
      const value = dir === "up" ? 1 : dir === "down" ? -1 : null;
      if (!e || value === null) return line("vote: e.g. vote 2 up", "t-err");
      const r = await fetch(`/vote/${e.slug}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) });
      if (!r.ok) return line("vote: that didn't go through", "t-err");
      const t = await r.json(); e.up = t.up; e.down = t.down;
      localStorage.setItem("vote:" + e.slug, t.mine);
      line(`<span class="t-ok">counted.</span> ${esc(e.title)} ▲${t.up} ▼${t.down}`);
    },
    pitch: () => { line("opening the pitch chat…"); setTimeout(() => (location.href = "/pitch"), 500); },
    socials: () => data.site.socials.forEach((s) => line(`  ${pad(s.name, 12)}${link(s.url, s.url.replace("https://", ""))}`)),
    versions: () => data.versions.forEach((v) => line(`  <b>${pad(v.slug, 12)}</b>${esc(v.line)} ${link(`/?v=${v.slug}`, "→")}`)),
    classic: () => { location.href = "/?v=classic"; },
    exit: () => COMMANDS.classic(),
    clear: () => { out.innerHTML = ""; },
    sudo: () => line("nice try.", "t-err"),
    ls: () => { line("projects/  lab/  pitch  about  socials"); },
  };

  const run = async (raw) => {
    const text = raw.trim();
    if (!text) return;
    line(`<span class="ps">mike@adamsnc ~ $</span> ${esc(text)}`);
    hist.push(text); hi = hist.length;
    const [c, ...args] = text.split(/\s+/);
    const fn = COMMANDS[c.toLowerCase()];
    beacon(c.toLowerCase().slice(0, 20));
    if (!fn) return line(`${esc(c)}: command not found. Try <b>help</b>.`, "t-err");
    try { await fn(...args); } catch (_) { line("something broke. Try again.", "t-err"); }
  };

  form.addEventListener("submit", (e) => { e.preventDefault(); run(cmd.value); cmd.value = ""; });
  cmd.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp" && hi > 0) { cmd.value = hist[--hi]; e.preventDefault(); }
    if (e.key === "ArrowDown") { cmd.value = hi < hist.length - 1 ? hist[++hi] : ""; hi = Math.min(hi, hist.length); e.preventDefault(); }
    if (e.key === "Tab") {
      e.preventDefault();
      const hit = Object.keys(COMMANDS).filter((k) => k.startsWith(cmd.value.toLowerCase()));
      if (hit.length === 1) cmd.value = hit[0] + " ";
      else if (hit.length > 1) line(hit.join("  "), "dim");
    }
  });
  document.getElementById("tkeys").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) run(b.dataset.c); });
  document.getElementById("term").addEventListener("click", (e) => { if (!e.target.closest("a") && !matchMedia("(max-width:820px)").matches) cmd.focus(); });

  fetch("/api/site.json").then((r) => r.json()).then((d) => {
    data = d;
    line(`<b>MikeAdamsNC</b> <span class="dim">· the terminal version · ${d.experiments.length} experiments, ${d.projects.length} projects</span>`);
    line(esc(d.site.headline));
    line(`Type <b>help</b> to start, or tap a shortcut below.`, "dim");
    if (!matchMedia("(max-width:820px)").matches) cmd.focus();
  }).catch(() => line("couldn't load the site. Try Classic: " + link("/?v=classic", "/?v=classic"), "t-err"));
})();
