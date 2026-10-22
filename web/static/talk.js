// The "Talk to it" version: questions in, short answers with links out.
(() => {
  const msgs = document.getElementById("msgs"), form = document.getElementById("composer"), say = document.getElementById("say"), go = document.getElementById("go");
  const history = [];
  let busy = false;
  const bubble = (role, text) => { const d = document.createElement("div"); d.className = "bub " + (role === "user" ? "you" : "bot"); d.textContent = text; msgs.append(d); d.scrollIntoView({ block: "end", behavior: "smooth" }); return d; };
  const ask = async (text) => {
    if (!text || busy) return;
    busy = true; go.disabled = true;
    document.getElementById("sugg").hidden = true;
    bubble("user", text); history.push({ role: "user", text });
    const wait = bubble("bot", "…"); wait.classList.add("typing");
    try {
      const r = await fetch("/talk", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history }) });
      const out = await r.json();
      wait.remove();
      const b = bubble("bot", out.reply);
      history.push({ role: "bot", text: out.reply });
      if (out.links?.length) {
        const row = document.createElement("div"); row.className = "links";
        out.links.forEach((l) => { const a = document.createElement("a"); a.href = l.path; a.textContent = l.label + " →"; row.append(a); });
        b.after(row); row.scrollIntoView({ block: "end", behavior: "smooth" });
      }
    } catch (_) { wait.remove(); bubble("bot", "Something went wrong. Try again, or switch back to Classic."); }
    busy = false; go.disabled = false;
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); const t = say.value.trim(); say.value = ""; ask(t); });
  say.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  document.getElementById("sugg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
})();
