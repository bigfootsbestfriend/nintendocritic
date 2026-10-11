// Send Canadian visitors to amazon.ca (guessed from browser time zone / language), everyone else to amazon.com.
const CA_ZONES = /^America\/(Toronto|Montreal|Vancouver|Edmonton|Winnipeg|Regina|Swift_Current|Halifax|Glace_Bay|Moncton|Goose_Bay|St_Johns|Whitehorse|Dawson|Dawson_Creek|Fort_Nelson|Creston|Yellowknife|Inuvik|Cambridge_Bay|Rankin_Inlet|Iqaluit|Resolute|Atikokan|Blanc-Sablon|Nipigon|Thunder_Bay|Rainy_River|Pangnirtung)$/;
function isCanada() {
  try {
    if (CA_ZONES.test(Intl.DateTimeFormat().resolvedOptions().timeZone)) return true;
  } catch (e) {}
  return (navigator.languages || [navigator.language]).some(l => /-CA$/i.test(l || ""));
}
if (isCanada()) {
  document.querySelectorAll("a[data-amz]").forEach(a => {
    a.href = a.href.replace("https://www.amazon.com", "https://www.amazon.ca").replace("tag=magpie014-20", "tag=thekitmag-20");
    a.textContent = a.textContent.replace(/^Check price on Amazon$/, "Check price on Amazon.ca");
  });
}

// Search and filter for the hub tables. Rows carry data-q (search text) and data-kind (filter value).
document.querySelectorAll("[data-filterable]").forEach(box => {
  const input = box.querySelector("input[type=search]");
  const chips = box.querySelectorAll(".chip");
  const rows = box.querySelectorAll("[data-q]");
  const empty = box.querySelector(".empty");
  const count = box.querySelector("[data-count]");
  let kind = "all";
  function render() {
    const q = (input ? input.value : "").trim().toLowerCase();
    let shown = 0;
    rows.forEach(r => {
      const ok = (kind === "all" || r.dataset.kind === kind) && (!q || r.dataset.q.includes(q));
      r.hidden = !ok;
      if (ok) shown++;
    });
    if (empty) empty.hidden = shown > 0;
    if (count) count.textContent = q || kind !== "all" ? " · " + shown + " shown" : "";
  }
  if (input) input.addEventListener("input", render);
  chips.forEach(b => b.addEventListener("click", () => {
    kind = b.dataset.filter;
    chips.forEach(c => c.setAttribute("aria-pressed", String(c === b)));
    render();
  }));
});

// Trailer: swap the thumbnail for YouTube's player only when pressed.
document.querySelectorAll("[data-yt]").forEach(btn => btn.addEventListener("click", () => {
  const f = document.createElement("iframe");
  f.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(btn.dataset.yt)}?autoplay=1&rel=0`;
  f.title = btn.getAttribute("aria-label");
  f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
  f.allowFullscreen = true;
  btn.replaceWith(f);
}));

// Homepage search: answers "what's in the box?" right in the results, from /static/games.json.
document.querySelectorAll("[data-finder]").forEach(box => {
  const input = box.querySelector("[data-find]");
  const out = box.querySelector("[data-results]");
  const LABEL = { full: "Full cartridge", gkc: "Game-key card", code: "Code in a box", tba: "Not announced" };
  const ICON = JSON.parse(document.getElementById("cart-icons")?.textContent || "{}");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const norm = s => s.toLowerCase().normalize("NFKD").replace(/[^a-z0-9 ]/g, "");
  const date = d => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Date TBA";
  let games = null;
  const load = () => games || (games = fetch("/static/games.json").then(r => r.json()).then(list => list.map(g => ({ ...g, k: norm(g.n) }))));
  input.addEventListener("focus", load, { once: true });
  input.addEventListener("input", async () => {
    const q = norm(input.value.trim());
    if (q.length < 2) { out.hidden = true; return; }
    const list = await load();
    const words = q.split(" ").filter(Boolean);
    const hits = list.filter(g => words.every(w => g.k.includes(w)))
      .sort((a, b) => (b.k.startsWith(q) - a.k.startsWith(q)) || (b.c !== "tba") - (a.c !== "tba")).slice(0, 8);
    out.innerHTML = hits.length ? hits.map(g => {
      const thumb = g.i ? `<img class="thumb" src="https://images.igdb.com/igdb/image/upload/t_cover_small/${g.i}.jpg" alt="" loading="lazy">`
                        : `<span class="thumb cover-ph"></span>`;
      const icon = ICON[g.c] ? `<svg class="ico" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">${ICON[g.c]}</svg>` : "";
      const inner = `${thumb}<span class="rt">${esc(g.n)}<small>${esc(date(g.d))}${g.p ? " · " + esc(g.p) : ""}</small></span>` +
                    `<span class="pill ${g.c} has-ico">${icon}${LABEL[g.c]}</span>`;
      return g.s ? `<a class="r" href="/games/${g.s}/">${inner}</a>` : `<div class="r">${inner}</div>`;
    }).join("") : `<div class="none">No Switch 2 game matches that yet. Try a shorter name.</div>`;
    out.hidden = false;
  });
  document.addEventListener("click", ev => { if (!box.contains(ev.target)) out.hidden = true; });
  input.addEventListener("keydown", ev => { if (ev.key === "Escape") out.hidden = true; });
});

// Library checker (/my-switch-library/): the visitor's Switch 1 games, saved on this device, checked against the
// upgrade list, Nintendo's free updates and the compatibility problems. Data loads from /static/library.json.
document.querySelectorAll("[data-lib]").forEach(async box => {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const key = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/&/g, "and")
    .replace(/\s*[–-]?\s*nintendo switch 2 edition.*$/, "").replace(/[^a-z0-9]/g, "");
  const store = v => { try { if (v === undefined) return JSON.parse(localStorage.getItem("nc-library") || "[]"); localStorage.setItem("nc-library", JSON.stringify(v)); } catch (e) { return []; } };
  const input = box.querySelector("#lib-q"), sug = box.querySelector(".lib-sug"), out = box.querySelector(".lib-out");
  const mineBox = box.querySelector(".lib-mine"), chips = box.querySelector(".lib-chips");
  const data = await fetch(box.dataset.src).then(r => r.json()).catch(() => null);
  if (!data) { out.textContent = "Couldn't load the game list. Please try again later."; return; }
  const byKey = {};
  Object.entries(data.items).forEach(([n, v]) => byKey[key(n)] = { name: n, ...v });
  const names = data.names.map(n => [n, key(n)]);
  const find = n => {
    const k = key(n);
    if (byKey[k]) return byKey[k];
    if (k.length < 8) return null;
    const hit = Object.keys(byKey).find(x => x.length >= 8 && (x.startsWith(k) || k.startsWith(x)));
    return hit ? byKey[hit] : null;
  };
  const shared = new URLSearchParams(location.search).get("g");
  let mine = shared ? shared.split("|").filter(Boolean).slice(0, 300) : store();
  if (shared) store(mine);
  const save = () => { store(mine); draw(); };
  const add = n => {
    n = n.trim();
    if (!n || mine.some(x => key(x) === key(n))) return;
    mine.push(n); save();
    if (window.gtag) window.gtag("event", "library_add", { game: n });
  };
  const price = v => "$" + v.toFixed(2);
  const link = it => it && it.p ? `<a href="/games/${it.p}/">${esc(it.name)}</a>` : null;

  function draw() {
    mineBox.hidden = !mine.length;
    box.querySelector("[data-lib-n]").textContent = mine.length ? `(${mine.length})` : "";
    chips.innerHTML = mine.map((n, i) => `<span class="lib-chip">${esc(n)}<button type="button" data-rm="${i}" aria-label="Remove ${esc(n)}">×</button></span>`).join("");
    if (!mine.length) { out.innerHTML = `<p class="lib-empty">Your results show up here. Try adding <button type="button" class="linkish" data-try="Animal Crossing: New Horizons">Animal Crossing</button>, <button type="button" class="linkish" data-try="The Legend of Zelda: Tears of the Kingdom">Tears of the Kingdom</button> or <button type="button" class="linkish" data-try="Hollow Knight">Hollow Knight</button>.</p>`; return; }
    const g = { bad: [], paid: [], free: [], fine: [] };
    mine.forEach(n => {
      const it = find(n), label = link(it) || esc(n);
      if (it && it.c && it.cc !== "full") g.bad.push(`<li>${label} <span class="pill ${it.cc}">${esc(it.c)}</span>${it.cd ? `<span class="lib-note">${esc(it.cd)}</span>` : ""}</li>`);
      if (it && it.u > 0) g.paid.push([it.u, `<li>${label} <b class="lib-price">${price(it.u)}</b>${it.n ? `<span class="lib-note">${esc(it.n)}</span>` : ""}<a class="lib-note" href="/upgrade-or-buy/?g=${encodeURIComponent(it.name)}">Upgrade or rebuy? Compare →</a></li>`]);
      else if (it && (it.u === 0 || it.fu)) g.free.push(`<li>${label} <span class="pill full">${it.u === 0 ? "Free upgrade" : "Free update"}</span></li>`);
      else if (!(it && it.c && it.cc !== "full")) g.fine.push(`<li>${label}${it && it.c ? ` <span class="pill full">${esc(it.c)}</span>` : ""}</li>`);
    });
    g.paid.sort((a, b) => b[0] - a[0]);
    const total = g.paid.reduce((t, x) => t + x[0], 0);
    const sec = (cls, title, items, note = "") => items.length ? `<div class="lib-group ${cls}"><h2>${title} <span>${items.length}</span></h2>${note}<ul>${items.join("")}</ul></div>` : "";
    const stat = (n, t, cls) => `<div class="lib-stat ${cls}"><b>${n}</b><span>${t}</span></div>`;
    out.innerHTML = `<div class="lib-stats">${stat(g.paid.length, g.paid.length ? `paid upgrades · ${price(total)} total` : "paid upgrades", "paid")}${stat(g.free.length, "free upgrades", "free")}${stat(g.bad.length, "known problems", "bad")}${stat(g.fine.length, "run as they are", "fine")}</div>`
      + sec("bad", "Known problems on Switch 2", g.bad)
      + sec("paid", "Paid Switch 2 upgrades", g.paid.map(x => x[1]), `<p class="sub">Upgrading all of them costs <b>${price(total)}</b> at US eShop prices.</p>`)
      + sec("free", "Free Switch 2 upgrades and updates", g.free, `<p class="sub">Download the update or claim the free Switch 2 Edition on the eShop.</p>`)
      + sec("fine", "Run on Switch 2 as they are", g.fine, `<p class="sub">No Switch 2 upgrade that we know of, and no reported problems. Nearly all Switch 1 games work on Switch 2.</p>`);
  }

  let sel = -1, shown = [];
  const close = () => { sug.hidden = true; input.setAttribute("aria-expanded", "false"); sel = -1; };
  input.addEventListener("input", () => {
    const k = key(input.value);
    if (k.length < 2) { close(); return; }
    shown = names.filter(([, nk]) => nk.includes(k)).sort((a, b) => b[1].startsWith(k) - a[1].startsWith(k)).slice(0, 8).map(x => x[0]);
    sug.innerHTML = shown.map((n, i) => `<div role="option" id="lib-o${i}" data-n="${i}">${esc(n)}</div>`).join("")
      || `<div class="none">Not in our list. Press Add to check it anyway.</div>`;
    sug.hidden = false; input.setAttribute("aria-expanded", "true"); sel = -1;
  });
  input.addEventListener("keydown", ev => {
    const opts = sug.querySelectorAll("[role=option]");
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault(); if (!opts.length) return;
      sel = (sel + (ev.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
      opts.forEach((o, i) => o.setAttribute("aria-selected", i === sel));
      input.setAttribute("aria-activedescendant", `lib-o${sel}`);
    } else if (ev.key === "Enter") {
      ev.preventDefault(); add(sel >= 0 ? shown[sel] : shown[0] || input.value); input.value = ""; close();
    } else if (ev.key === "Escape") close();
  });
  sug.addEventListener("mousedown", ev => { const o = ev.target.closest("[data-n]"); if (o) { ev.preventDefault(); add(shown[+o.dataset.n]); input.value = ""; close(); input.focus(); } });
  input.addEventListener("blur", () => setTimeout(close, 150));
  box.querySelector("[data-lib-add]").addEventListener("click", () => { add(shown.find(n => key(n) === key(input.value)) || shown[0] || input.value); input.value = ""; close(); input.focus(); });
  box.querySelector("[data-lib-paste]").addEventListener("click", () => {
    const ta = box.querySelector(".lib-paste textarea");
    ta.value.split(/\n|,(?=\s*[A-Z])/).forEach(line => { const n = line.trim(); if (n) { const m = names.find(([, nk]) => nk === key(n)); add(m ? m[0] : n); } });
    ta.value = ""; box.querySelector(".lib-paste").open = false;
  });
  box.addEventListener("click", async ev => {
    const rm = ev.target.closest("[data-rm]"), t = ev.target.closest("[data-try]");
    if (rm) { mine.splice(+rm.dataset.rm, 1); save(); }
    if (t) add(t.dataset.try);
    if (ev.target.closest("[data-lib-clear]") && confirm("Remove all your games from this list?")) { mine = []; save(); }
    const sh = ev.target.closest("[data-lib-share]");
    if (sh) {
      const url = location.origin + location.pathname + "?g=" + encodeURIComponent(mine.join("|"));
      try {
        if (navigator.share) await navigator.share({ title: "My Switch 2 upgrade list", url });
        else { await navigator.clipboard.writeText(url); sh.textContent = "Link copied!"; setTimeout(() => sh.textContent = "Share list", 2500); }
      } catch (e) { /* share sheet closed */ }
    }
  });
  draw();
});

// Cartridge alerts on game pages: one email if the game's box type changes (newsletter Worker /watch, double opt-in).
document.querySelectorAll("[data-alert]").forEach(box => {
  const d = JSON.parse(box.dataset.alert);
  const open = box.querySelector("[data-alert-open]"), form = box.querySelector("[data-alert-form]"), msg = box.querySelector(".al-msg");
  open.addEventListener("click", () => {
    form.hidden = !form.hidden; open.setAttribute("aria-expanded", String(!form.hidden));
    if (!form.hidden) form.querySelector('input[type="email"]').focus();
  });
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const btn = form.querySelector('button[type="submit"]'); btn.disabled = true;
    const weekly = form.querySelector("[data-weekly]").checked;
    try {
      const r = await fetch(d.api + "/watch", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ site: "nintendocritic", item: d.item, label: d.label, weekly, email: form.querySelector('input[type="email"]').value, website: form.website.value }) });
      const s = (await r.json()).state;
      msg.textContent = { check: "Almost done: check your inbox and click the confirm button.", invalid: "That email address doesn't look right.",
        slow: "You've set a lot of alerts today. Try again tomorrow." }[s] || "Something went wrong. Please try again later.";
      if (s === "check") {
        form.querySelectorAll("input, button").forEach(x => x.disabled = true); msg.classList.add("ok");
        if (weekly) { try { localStorage.setItem("nl-subbed", "1"); } catch (e) {} }
        if (window.gtag) window.gtag("event", "cart_alert", { game: d.item, weekly });
        return;
      }
    } catch (e) { msg.textContent = "Something went wrong. Please try again later."; }
    btn.disabled = false;
  });
});

// Upgrade calculator (/upgrade-or-buy/): upgrade pack vs Switch 2 Edition for the visitor's situation.
document.querySelectorAll("[data-calc]").forEach(form => {
  const games = JSON.parse(form.dataset.calc), out = document.querySelector(".calc-out");
  const f = k => form.querySelector(`[data-k="${k}"]`), num = k => parseFloat(f(k).value);
  const $ = v => "$" + Math.max(0, v).toFixed(2);
  const fill = () => {
    const g = games[+f("game").value];
    f("up").value = g[1].toFixed(2);
    f("ed").value = g[2] ? g[2].toFixed(2) : "";
    f("nso").closest("label").hidden = !g[3];
    if (!g[3]) f("nso").checked = false;
  };
  const want = new URLSearchParams(location.search).get("g");
  if (want) { const i = games.findIndex(g => g[0].toLowerCase() === want.toLowerCase()); if (i >= 0) f("game").value = i; }
  const run = () => {
    const g = games[+f("game").value], own = form.querySelector('input[name="own"]:checked').value;
    form.querySelectorAll("[data-show]").forEach(x => x.hidden = !x.dataset.show.split(" ").includes(own));
    const up = f("nso").checked ? 0 : (num("up") || 0), ed = num("ed"), resale = num("resale") || 0, s1 = num("s1"), paid = num("paid");
    const opts = [];
    if (own === "none") {
      if (isNaN(s1)) opts.push({ t: "Switch 1 version + upgrade pack", n: "The Switch 1 version plus the pack", c: null, why: "Add the Switch 1 price to compare." });
      else opts.push({ t: "Switch 1 version + upgrade pack", n: "The Switch 1 version plus the pack", c: s1 + up, why: `${$(s1)} + ${$(up)} for the pack.` });
    } else {
      opts.push({ t: "Buy the upgrade pack", n: "The upgrade pack", c: up, why: f("nso").checked ? "Included with your Expansion Pack." :
        own === "physical" ? "Keep the Switch 1 cartridge: it has to be in the console to play." : "Unlocks the Switch 2 version of your digital copy." });
    }
    if (isNaN(ed)) opts.push({ t: own === "physical" ? "Sell your copy, buy the Switch 2 Edition" : "Buy the Switch 2 Edition", n: "", c: null, why: "Add the Switch 2 Edition price to compare." });
    else if (own === "physical") opts.push({ t: "Sell your copy, buy the Switch 2 Edition", n: "Selling your copy and buying the Switch 2 Edition", c: ed - resale, why: resale ? `${$(ed)} minus ${$(resale)} from selling your copy.` : `${$(ed)}. Add what your copy would sell for to see the real cost.` });
    else opts.push({ t: "Buy the Switch 2 Edition", n: "The Switch 2 Edition", c: ed, why: own === "digital" ? "Digital copies can't be resold, so this means paying twice." : "No old copy needed." });
    if (own !== "none") opts.push({ t: "Keep playing the Switch 1 version", c: 0, why: "It runs on Switch 2, just without the Switch 2 improvements.", base: true });
    const real = opts.filter(o => o.c !== null && !o.base);
    const best = real.length > 1 ? real.reduce((a, b) => (b.c < a.c ? b : a)) : null;
    const other = best && real.find(o => o !== best);
    out.innerHTML = (best ? `<p class="calc-verdict">${best.n} ${best.n.startsWith("Selling") ? "works out" : "is"} cheaper${other && other.c - best.c >= 0.01 ? ` by <b>${$(other.c - best.c)}</b>` : " (it's a tie)"}.</p>` : "")
      + `<div class="calc-opts">${opts.map(o => `<div class="calc-opt${o === best ? " best" : ""}${o.base ? " base" : ""}"><b>${o === best ? "Best deal · " : ""}${o.t}</b>`
      + `<span class="calc-cost">${o.c === null ? "?" : $(o.c)}</span><span class="sub">${o.why}</span></div>`).join("")}</div>`
      + (!isNaN(paid) && best && own !== "none" ? `<p class="sub">All in, ${g[0]} will have cost you ${$(paid + best.c)} (${$(paid)} originally + ${$(best.c)} now).</p>` : "");
  };
  f("game").addEventListener("change", () => { fill(); run(); });
  form.addEventListener("input", run);
  fill(); run();
});

// Email signup prompts: "Tell me…" buttons open the signup box, and a small bar offers it once after a while
// on the page. The bar is easy to close and stays away for 14 days; it never shows to subscribers.
(() => {
  const box = document.querySelector(".signup");
  if (!box) return;
  const form = box.querySelector("form");
  const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  const open = () => {
    box.scrollIntoView({ behavior: "smooth", block: "center" });
    box.classList.remove("flash"); void box.offsetWidth; box.classList.add("flash");
    setTimeout(() => form.querySelector('input[type="email"]').focus({ preventScroll: true }), 500);
    if (bar) bar.hidden = true;
  };
  document.addEventListener("click", (ev) => { const b = ev.target.closest("[data-signup]"); if (b) { ev.preventDefault(); open(); } });
  form.addEventListener("submit", () => {
    store("nl-subbed", "1");
    if (window.gtag) window.gtag("event", "sign_up", { method: "email", page: location.pathname });
  });
  let bar = null;
  if (store("nl-subbed") || Date.now() - (+store("nl-bar") || 0) < 14 * 864e5) return;
  bar = document.createElement("div");
  bar.className = "signup-bar";
  bar.hidden = true;
  bar.innerHTML = `<span><b>Free weekly email</b> · ${box.dataset.bar || box.querySelector("h2").textContent}</span>` +
    `<button type="button" class="go" data-signup>Sign up</button><button type="button" class="x" aria-label="No thanks">×</button>`;
  document.body.appendChild(bar);
  bar.querySelector(".x").addEventListener("click", () => { store("nl-bar", String(Date.now())); bar.remove(); });
  let inView = false, shown = false;
  new IntersectionObserver(([en]) => { inView = en.isIntersecting; if (inView) bar.hidden = true; }).observe(box);
  const show = () => {
    if (shown || inView) return;
    shown = true;
    store("nl-bar", String(Date.now()));
    bar.hidden = false;
  };
  setTimeout(show, 25000);
  addEventListener("scroll", () => { if (scrollY > (document.documentElement.scrollHeight - innerHeight) * 0.5) show(); }, { passive: true });
})();
