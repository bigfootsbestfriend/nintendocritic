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
