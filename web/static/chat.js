// The pitch chat. The conversation lives here in the page until the visitor sends the summary.
(() => {
  const msgs = document.getElementById("msgs"), form = document.getElementById("composer"), say = document.getElementById("say");
  const summary = document.getElementById("summary"), list = document.getElementById("sumlist"), go = document.getElementById("go");
  const history = [];
  let pitch = null, busy = false;
  const LABELS = { what: "What it is", kind: "Type", purpose: "For", payment: "Who pays", features: "Ideas", marketing: "Getting the word out", name: "Name", email: "Email" };

  const bubble = (role, text) => {
    const d = document.createElement("div");
    d.className = "bub " + (role === "user" ? "you" : "bot");
    d.textContent = text;
    msgs.append(d);
    d.scrollIntoView({ block: "end", behavior: "smooth" });
    return d;
  };
  const showSummary = (p) => {
    list.innerHTML = "";
    if (p.type === "site idea") { const t = document.createElement("dt"); t.textContent = "Kind"; const v = document.createElement("dd"); v.textContent = "Idea for this site"; list.append(t, v); }
    for (const [k, label] of Object.entries(LABELS)) {
      if (!p[k]) continue;
      const t = document.createElement("dt"); t.textContent = label;
      const v = document.createElement("dd"); v.textContent = p[k];
      list.append(t, v);
    }
    summary.hidden = false;
    summary.scrollIntoView({ block: "end", behavior: "smooth" });
  };

  say.addEventListener("input", () => { say.style.height = "auto"; say.style.height = Math.min(say.scrollHeight, 180) + "px"; });
  say.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = say.value.trim();
    if (!text || busy) return;
    busy = true; go.disabled = true; say.value = ""; say.style.height = "auto";
    bubble("user", text);
    history.push({ role: "user", text });
    const wait = bubble("bot", "…"); wait.classList.add("typing");
    try {
      const r = await fetch("/pitch/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }) });
      const out = await r.json();
      wait.remove();
      bubble("bot", out.reply);
      history.push({ role: "bot", text: out.reply });
      if (out.down) { const a = document.createElement("a"); a.href = "/pitch/form"; a.className = "btn b2"; a.textContent = "Use the form"; msgs.append(a); }
      if (out.ready && out.pitch && out.pitch.what) { pitch = out.pitch; showSummary(pitch); }
    } catch (_) {
      wait.remove();
      bubble("bot", "Something went wrong on my end. Try again, or use the form.");
    }
    busy = false; go.disabled = false; say.focus();
  });

  document.getElementById("keep").addEventListener("click", () => { summary.hidden = true; say.focus(); });
  document.getElementById("send").addEventListener("click", async (e) => {
    const b = e.currentTarget; b.disabled = true;
    const r = await fetch("/pitch/chat/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pitch, messages: history }) });
    if (r.ok) { location.href = "/pitch/thanks"; return; }
    const out = await r.json().catch(() => ({}));
    bubble("bot", out.error || "That didn't go through. Try again in a moment.");
    b.disabled = false;
  });
})();
