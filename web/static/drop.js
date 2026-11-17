// The drop box: send files to Mike through an upload link he made. No account is needed.
// The link's secret is the part after the #. Browsers never put that in a page address they
// send, so it only leaves this page inside the calls below. Each file goes straight from
// this browser to private storage, one at a time, and a dropped connection picks up where
// it stopped.
(() => {
  const $ = (id) => document.getElementById(id);
  const title = $("drop-title"), lede = $("drop-lede"), gate = $("drop-gate"), box = $("drop-box");
  const zone = $("drop-zone"), input = $("drop-input"), list = $("drop-list");
  const queue = [];
  let token = "", maxFile = 0, busy = false;

  const call = async (path, body = {}) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, ...body }) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.error || "Something went wrong. Please try again."), { status: r.status });
    return data;
  };
  const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
  const words = (n) => {
    for (const [unit, step] of [["GB", 1024 ** 3], ["MB", 1024 ** 2], ["KB", 1024]])
      if (n >= step) return (n / step).toFixed(1).replace(/\.0$/, "") + " " + unit;
    return n + " bytes";
  };
  const day = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  // ---- the link ----
  const open = async (text) => {
    text = (text || "").trim();
    token = text.includes("#") ? text.slice(text.lastIndexOf("#") + 1) : text;
    gate.hidden = box.hidden = true;
    if (!token) {
      lede.textContent = "An upload link from Mike Adams is required to send files here.";
      gate.hidden = false;
      return;
    }
    lede.textContent = "Checking your link…";
    try {
      const link = await call("/drop/open");
      maxFile = link.max_file;
      title.textContent = link.label;
      lede.textContent = `Files you add here go directly to Mike Adams. This link is valid until ${day(link.expires)}.`;
      history.replaceState(null, "", "#" + token);
      box.hidden = false;
    } catch (e) {
      token = "";
      lede.textContent = e.status === 404 ? "This link is no longer active. It may have expired or been closed. Please ask Mike Adams for a new one." : e.message;
      gate.hidden = false;
    }
  };
  gate.addEventListener("submit", (e) => { e.preventDefault(); open(gate.elements.code.value); });
  addEventListener("hashchange", () => { if (!busy) open(location.hash.slice(1)); });

  // ---- one file ----
  const put = (url, file, offset, progress) => new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", url);
    x.setRequestHeader("Content-Range", `bytes ${offset}-${file.size - 1}/${file.size}`);
    x.upload.onprogress = (e) => progress(offset + e.loaded);
    x.onload = () => (x.status === 200 || x.status === 201 ? resolve() : reject(Object.assign(new Error("upload"), { status: x.status })));
    x.onerror = x.onabort = x.ontimeout = () => reject(new Error("network"));
    x.send(file.slice(offset, file.size, "application/octet-stream")); // plain bytes, whatever the file claims to be
  });

  const send = async (item) => {
    const { file } = item;
    let s;
    try {
      s = await call("/drop/start", { name: file.name, size: file.size, from: $("drop-from").value, note: $("drop-note").value });
    } catch (e) {
      return item.say(e.message, "bad");
    }
    let offset = s.offset, tries = 0;
    for (;;) {
      try {
        item.progress(offset);
        if (offset < file.size) await put(s.url, file, offset, item.progress);
        await call("/drop/done", { id: s.id });
        item.progress(file.size);
        return item.say("Sent ✓", "ok");
      } catch (e) {
        // A refusal (the link was closed, the file didn't match) is final. A dropped
        // connection or a busy server is tried again from wherever storage got to.
        const final = e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429;
        if (final || ++tries > 8) return item.say(final && e.message !== "upload" ? e.message : "This file could not be sent. Please check your connection and try again.", "bad");
        item.say("Connection interrupted. Retrying…");
        await sleep(Math.min(30000, 2000 * 2 ** (tries - 1)));
        try {
          const kept = (await call("/drop/offset", { id: s.id })).offset;
          if (kept > offset) tries = 0; // it's getting somewhere
          offset = kept;
        } catch (e2) {
          if (e2.status === 404) return item.say(e2.message, "bad");
        }
      }
    }
  };

  const run = async () => {
    if (busy) return;
    busy = true;
    while (queue.length) await send(queue.shift());
    busy = false;
  };

  const add = (file, folder) => {
    const li = document.createElement("li");
    li.innerHTML = '<div class="dl-top"><b></b><span></span></div><div class="dl-bar"><i></i></div>';
    li.querySelector("b").textContent = file.name;
    const note = li.querySelector("span"), bar = li.querySelector("i");
    const item = {
      file,
      say: (text, cls) => { note.textContent = text; li.className = cls || ""; },
      progress: (n) => {
        const pct = Math.min(100, Math.floor((n / file.size) * 100));
        bar.style.width = pct + "%";
        note.textContent = `${words(Math.min(n, file.size))} of ${words(file.size)} · ${pct}%`;
      },
    };
    list.append(li);
    if (folder) return item.say("Folders can't be sent. Please select the files inside, or zip the folder first.", "bad");
    if (!file.size) return item.say("Empty file, skipped.", "bad");
    if (file.size > maxFile) return item.say(`Too large (${words(file.size)}). The limit is ${words(maxFile)} per file.`, "bad");
    item.say("Waiting");
    queue.push(item);
    run();
  };

  input.addEventListener("change", () => { [...input.files].forEach((f) => add(f)); input.value = ""; });
  for (const kind of ["dragenter", "dragover"]) zone.addEventListener(kind, (e) => { e.preventDefault(); zone.classList.add("over"); });
  for (const kind of ["dragleave", "drop"]) zone.addEventListener(kind, (e) => { e.preventDefault(); zone.classList.remove("over"); });
  zone.addEventListener("drop", (e) => {
    const items = [...(e.dataTransfer.items || [])];
    [...e.dataTransfer.files].forEach((f, i) => add(f, items[i]?.webkitGetAsEntry?.()?.isDirectory));
  });
  // A file dropped anywhere else on the page shouldn't replace the page with that file.
  for (const kind of ["dragover", "drop"]) addEventListener(kind, (e) => e.preventDefault());
  addEventListener("beforeunload", (e) => { if (busy) { e.preventDefault(); e.returnValue = ""; } });

  open(location.hash.slice(1));
})();
