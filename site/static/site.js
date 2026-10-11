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
