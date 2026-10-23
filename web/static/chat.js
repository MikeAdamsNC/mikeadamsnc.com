// The pitch chat. The conversation lives here in the page until the visitor sends it.
// Free-text answers go to the AI (its reply streams in as it's written); the questions with fixed
// answers are buttons, and after a tap this page asks the next one itself, with no AI wait.
// Beside the chat, the idea is drawn as an app listing that fills in every couple of answers.
(() => {
  const $ = (id) => document.getElementById(id);
  const msgs = $("msgs"), form = $("composer"), say = $("say"), go = $("go");
  const summary = $("summary"), list = $("sumlist"), slot = $("cardslot"), opts = $("cardopts");
  const CHIPS = JSON.parse($("chipdata").textContent);
  const FIXED = ["kind", "purpose", "payment"];
  const STEPS = ["what", "kind", "purpose", "payment", "features"];
  const LABELS = { what: "What it is", kind: "Type", purpose: "For", payment: "Who pays", features: "Ideas", marketing: "Getting the word out", name: "Name", email: "Email" };
  const KIND = { App: "App", Website: "Website" }, PURPOSE = { "Personal use": "for personal use", Business: "for a business", "Something to sell": "to sell" };
  const history = [], pitch = {};
  let busy = false, ready = false, card = null, drawing = false, finalWanted = false, drawnAt = -1, answers = 0;

  const beacon = (kind, detail) => {
    try { navigator.sendBeacon?.("/e", new Blob([JSON.stringify({ kind, path: "/pitch", detail })], { type: "application/json" })); } catch (_) {}
  };
  const scroll = (el) => el.scrollIntoView({ block: "nearest", behavior: "smooth" });

  // ---------- bubbles ----------
  const botRow = (text = "") => {
    const row = document.createElement("div");
    row.className = "prow fb";
    row.innerHTML = '<div class="av" aria-hidden="true">λ</div><div class="pbub"></div>';
    row.lastChild.textContent = text;
    msgs.append(row); scroll(row);
    return row;
  };
  const youRow = (text) => {
    const row = document.createElement("div");
    row.className = "prow fy";
    row.innerHTML = '<div class="pbub"></div>';
    row.firstChild.textContent = text;
    msgs.append(row);
    const tags = tagsFor(text);
    if (tags.length) {
      const t = document.createElement("div");
      t.className = "ptags";
      for (const x of tags) { const i = document.createElement("i"); i.textContent = x; t.append(i); }
      msgs.append(t);
    }
    scroll(row);
  };
  // Instant tags from the visitor's own words (our code, no AI), so the page reacts at once.
  const TAGS = [[/\bapp\b|iphone|android/i, "app"], [/web ?site|\bsite\b|web page/i, "website"], [/business|customers?|clients?|shop|store/i, "business"],
    [/\bsell|money|earn|subscription/i, "to sell"], [/\bbook|schedul|appointment|reserv/i, "booking"], [/\bpay|payment|invoice|checkout/i, "payments"],
    [/nearby|near me|map|location|gps/i, "location"], [/alert|notif|remind|ping|text me/i, "alerts"], [/\bkids?\b|family|son|daughter|parents?/i, "family"],
    [/game|points|badges?/i, "game"], [/\bai\b|chatbot|smart/i, "AI"], [/track|log|history|stats/i, "tracking"]];
  const tagsFor = (text) => TAGS.filter(([re]) => re.test(text)).map(([, t]) => t).slice(0, 3);

  // ---------- buttons for the fixed questions ----------
  const showChips = (field) => {
    const c = CHIPS[field];
    const why = document.createElement("div");
    why.className = "pwhy"; why.textContent = `asks ${c.why} · tap one, or type your own`;
    const row = document.createElement("div");
    row.className = "qchips";
    for (const [label, value] of c.options) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label;
      if (value === "Not sure") b.className = "other";
      b.addEventListener("click", () => { if (busy) return; clearChips(); beacon("cta", `chip_${field}`); answer(label, { field, value }); });
      row.append(b);
    }
    msgs.append(why, row); scroll(row);
  };
  const clearChips = () => msgs.querySelectorAll(".qchips, .starters").forEach((r) => { r.querySelectorAll("button").forEach((b) => (b.disabled = true)); r.classList.add("used"); });
  const nextFixed = () => (pitch.what && pitch.type !== "site idea" ? FIXED.find((f) => !pitch[f]) : null);

  // ---------- progress ----------
  const progress = () => {
    const n = STEPS.filter((k) => pitch[k]).length;
    $("wave").style.strokeDashoffset = 100 - (ready ? 100 : n * 20);
    $("step").innerHTML = ready ? "<b>ready to send</b>" : `<b>${n} of 5</b>${n >= 4 ? " · almost a pitch" : ""}`;
    const label = [KIND[pitch.kind] || "Idea", PURPOSE[pitch.purpose]].filter(Boolean).join(" · ");
    if (!card) { $("ghostkind").textContent = pitch.kind || pitch.purpose ? label : "Your idea"; $("minilabel").textContent = label; }
  };

  // ---------- one answer from the visitor ----------
  const answer = (text, chip) => {
    $("starters")?.remove();
    $("startwhy")?.remove();
    youRow(text);
    history.push({ role: "user", text });
    answers++;
    if (chip) {
      pitch[chip.field] = chip.value;
      progress(); draw();
      const next = nextFixed();
      if (next) { const q = CHIPS[next].ask; botRow(q); history.push({ role: "bot", text: q }); showChips(next); return; }
    }
    aiTurn();
  };

  // ---------- an AI turn, streamed ----------
  const STAGES = [[0, "Reading your idea…"], [5, "Thinking of a good question…"], [15, "The AI is slow right now. Still working…"]];
  const aiTurn = async () => {
    busy = true; go.disabled = true;
    const row = botRow(), bub = row.lastChild;
    bub.className = "pbub status";
    bub.innerHTML = '<span class="dots"><i></i><i></i><i></i></span><span class="st"></span><em></em>';
    const t0 = Date.now();
    let slowBox = null, started = false, text = "";
    const tick = () => {
      if (started) return;
      const s = Math.floor((Date.now() - t0) / 1000);
      bub.querySelector(".st").textContent = STAGES.filter(([at]) => s >= at).pop()[1];
      bub.querySelector("em").textContent = s >= 15 ? `${s}s` : "";
      if (s >= 30 && !slowBox) slowBox = slow();
    };
    tick();
    const timer = setInterval(tick, 500);
    const begin = () => { if (started) return; started = true; clearInterval(timer); slowBox?.remove(); bub.className = "pbub"; bub.textContent = ""; };
    try {
      const r = await fetch("/pitch/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }) });
      if (!r.ok || !r.body) throw new Error(r.status);
      const reader = r.body.getReader(), dec = new TextDecoder();
      let buf = "", done = null;
      while (!done) {
        const { value, done: end } = await reader.read();
        if (end) break;
        buf += dec.decode(value, { stream: true });
        let k;
        while ((k = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, k); buf = buf.slice(k + 2);
          if (!line.startsWith("data:")) continue;
          const ev = JSON.parse(line.slice(5));
          if (ev.t === "delta") { begin(); text += ev.text; bub.textContent = text; scroll(row); }
          else { done = ev; }
        }
      }
      begin();
      if (!done) throw new Error("cut off");
      bub.textContent = done.reply;
      history.push({ role: "bot", text: done.reply });
      if (done.t === "down") { formButton(); return; }
      for (const [k, v] of Object.entries(done.pitch || {})) if (v && !(FIXED.includes(k) && pitch[k])) pitch[k] = v;
      progress();
      if (done.ready && pitch.what) { ready = true; progress(); showSummary(); draw(true); }
      else { const f = done.chips && !pitch[done.chips] ? done.chips : null; if (f) showChips(f); draw(); }
    } catch (_) {
      begin();
      bub.textContent = "Something went wrong on my end. Try again, or finish with the form; everything you said comes with you.";
      formButton();
    } finally {
      clearInterval(timer); busy = false; go.disabled = false;
    }
  };
  const slow = () => {
    const box = document.createElement("div");
    box.className = "pslow";
    box.innerHTML = "<b>This is taking longer than usual.</b> Your answers so far are saved. Keep waiting, or finish with the quick form: everything you said comes with you.<div><button type='button' class='pbtn hot'>Keep waiting</button><button type='button' class='pbtn'>Finish with the form</button></div>";
    const [keep, toForm] = box.querySelectorAll("button");
    keep.addEventListener("click", () => box.remove());
    toForm.addEventListener("click", () => { beacon("cta", "slow_to_form"); toFormPage(); });
    msgs.append(box); scroll(box);
    return box;
  };
  const formButton = () => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "pbtn"; b.textContent = "Finish with the form";
    b.addEventListener("click", toFormPage);
    msgs.append(b); scroll(b);
  };
  // The form picks this up (this tab only) and fills itself in.
  const toFormPage = () => {
    const said = history.filter((m) => m.role === "user").map((m) => m.text).join("\n");
    try { sessionStorage.setItem("pitch-draft", JSON.stringify({ ...pitch, what: pitch.what || said })); } catch (_) {}
    location.href = "/pitch/form";
  };
  $("toform").addEventListener("click", (e) => { if (history.length) { e.preventDefault(); toFormPage(); } });

  // ---------- the card beside the chat ----------
  const fields = (c) => c ? { name: c.name, tagline: c.tagline, f0: c.features[0], f1: c.features[1], f2: c.features[2], screen: JSON.stringify(c.screen) } : {};
  const draw = async (final = false) => {
    if (!pitch.what || pitch.type === "site idea") return;
    if (drawing) { finalWanted ||= final; return; }
    if (!final && card && answers - drawnAt < 2) return;
    drawing = true; drawnAt = answers;
    $("bnote").textContent = card ? "updating…" : "drawing your idea…";
    try {
      const r = await fetch("/pitch/card", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pitch, editable: ready }) });
      if (!r.ok) throw new Error(r.status);
      const out = await r.json(), before = fields(card);
      card = out.card; slot.innerHTML = out.html;
      const after = fields(card);
      if (Object.keys(before).length) {  // mark what changed
        const map = { name: ".pc-name", tagline: ".pc-tag", f0: ".pc-feat li:nth-child(1)", f1: ".pc-feat li:nth-child(2)", f2: ".pc-feat li:nth-child(3)", screen: ".pc-phone" };
        for (const k of Object.keys(map)) if (before[k] !== after[k]) slot.querySelector(map[k])?.classList.add("fresh");
      } else slot.querySelector(".pcard")?.classList.add("arrive");
      mini();
      $("bnote").textContent = ready ? "yours to edit" : "fills in as you talk";
      if (ready) { opts.hidden = false; $("namebox").hidden = !pitch.name; paintName(); }
    } catch (_) {
      $("bnote").textContent = card ? "fills in as you talk" : "the card will try again after your next answer";
    } finally {
      drawing = false;
      if (finalWanted) { finalWanted = false; draw(true); }
    }
  };
  const mini = () => {
    if (!card) return;
    $("miniic").innerHTML = slot.querySelector(".pc-ic")?.innerHTML || "";
    $("mininame").textContent = card.name;
    $("minilabel").textContent = slot.querySelector(".pc-kind")?.textContent || "";
    $("minitag").textContent = card.tagline;
  };
  $("mini").addEventListener("click", (e) => {
    const open = $("build").classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", open);
  });
  const paintName = () => {
    const by = slot.querySelector(".pc-by");
    if (!by) return;
    const first = (pitch.name || "").split(" ")[0], on = $("showname").checked && first;
    by.innerHTML = "pitched" + (on ? " by <b></b>" : "") + " on <b>MikeAdamsNC.com</b>";
    if (on) by.querySelector("b").textContent = first;
  };
  const editedCard = () => {
    if (!card || !ready) return null;
    const q = (f) => [...slot.querySelectorAll(`[data-f="${f}"]`)].map((e) => e.textContent.trim());
    return { ...card, name: q("name")[0] || card.name, tagline: q("tagline")[0] || card.tagline, features: q("feature").filter(Boolean) };
  };
  $("again").addEventListener("click", () => draw(true));
  $("showname").addEventListener("change", paintName);

  // ---------- summary + send ----------
  const showSummary = () => {
    list.innerHTML = "";
    if (pitch.type === "site idea") { const t = document.createElement("dt"); t.textContent = "Kind"; const v = document.createElement("dd"); v.textContent = "Idea for this site"; list.append(t, v); }
    for (const [k, label] of Object.entries(LABELS)) {
      if (!pitch[k]) continue;
      const t = document.createElement("dt"); t.textContent = label;
      const v = document.createElement("dd"); v.textContent = pitch[k];
      list.append(t, v);
    }
    summary.hidden = false; scroll(summary);
  };
  $("keep").addEventListener("click", () => { summary.hidden = true; ready = false; opts.hidden = true; progress(); say.focus(); });
  $("send").addEventListener("click", async (e) => {
    const b = e.currentTarget, c = editedCard();
    b.disabled = true; b.textContent = c ? "Sending… checking your card" : "Sending…";
    const r = await fetch("/pitch/chat/send", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pitch: { type: "pitch", ...pitch }, messages: history, card: c, show_name: $("showname").checked }) });
    if (r.ok) { const out = await r.json().catch(() => ({})); location.href = out.card_url || "/pitch/thanks"; return; }
    const out = await r.json().catch(() => ({}));
    botRow(out.error || "That didn't go through. Try again in a moment.");
    b.disabled = false; b.textContent = "Send it to Mike";
  });

  // ---------- typing, starters, talking ----------
  say.addEventListener("input", () => { say.style.height = "auto"; say.style.height = Math.min(say.scrollHeight, 160) + "px"; });
  say.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = say.value.trim();
    if (!text || busy) return;
    say.value = ""; say.style.height = "auto";
    clearChips();
    answer(text);
  });
  $("starters").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { beacon("cta", "starter"); answer(b.textContent); }));

  // The browser's own speech-to-text, where it has one.
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Rec) {
    const mic = $("mic"); mic.hidden = false;
    let rec = null;
    mic.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new Rec(); rec.interimResults = true; rec.lang = "en-US";
      const base = say.value ? say.value + " " : "";
      rec.onresult = (ev) => { say.value = base + [...ev.results].map((x) => x[0].transcript).join(""); say.dispatchEvent(new Event("input")); };
      rec.onend = () => { rec = null; mic.classList.remove("on"); say.focus(); };
      mic.classList.add("on"); rec.start(); beacon("cta", "mic");
    });
  }
  progress();
})();
