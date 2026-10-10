"""Build the static site from Airtable into public/.

Standard library only. Static files (CNAME, static/) are copied from site/.
Only games with the Approved box ticked get their own page; the hub lists show every game.

  python3 generator/build.py            # what the live site gets
  python3 generator/build.py --preview  # also builds pages for unapproved games, for checking locally
"""
import argparse
import datetime as dt
import html
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))
from common import COMPAT_TABLE, GAMES_TABLE, REVIEWS_TABLE, Airtable, load_env  # noqa: E402

# Flip to True when the data has been reviewed and the site should appear in search results.
LAUNCHED = False
SITE = "https://nintendocritic.com"
AMAZON_TAG = "magpie014-20"  # site.js swaps in the amazon.ca tag for Canadian visitors
KIT_FORM_URL = None  # e.g. "https://app.kit.com/forms/1234567/subscriptions" once the Nintendo Critic Kit account exists

NAV = [
    ("/game-key-cards/", "Game-key cards"),
    ("/compatibility/", "Compatibility"),
    ("/upgrades/", "Upgrades"),
    ("/coming-soon/", "Coming soon"),
]
CART_CLASS = {"Full cartridge": "full", "Game-key card": "gkc", "Code in a box": "code"}
COMPAT_CLASS = {"Not compatible": "bad", "Partly compatible": "bad", "Partly": "bad",
                "Issues reported": "warn", "Fixed": "full", "Works": "full"}
LOGO = ('<svg viewBox="0 0 48 56" aria-hidden="true"><path d="M8 2H32.5L44 13.5V50Q44 54 40 54H8Q4 54 4 50V6Q4 2 8 2Z" fill="var(--accent)"/>'
        '<rect x="10" y="9" width="27" height="25" rx="3.5" fill="var(--gold)"/><path d="M15.5 21.5L21.5 27.5L31.5 15.5" fill="none" stroke="var(--check)" '
        'stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round"/>'
        + "".join(f'<rect x="{x}" y="44" width="3.2" height="7" rx="1" fill="var(--bg)" opacity=".6"/>' for x in (11.0, 16.6, 22.2, 27.8, 33.4))
        + "</svg>")

e = html.escape
TODAY = dt.date.today()


def slugify(name):
    name = re.sub(r"\s*[–-]\s*Nintendo Switch 2 Edition$", " Switch 2 Edition", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def short_name(name):
    return re.sub(r"\s*[–-]\s*Nintendo Switch 2 Edition$", "", name)


def amazon(name):
    q = urllib.parse.quote_plus(short_name(name) + " Nintendo Switch 2")
    return f"https://www.amazon.com/s?k={q}&amp;tag={AMAZON_TAG}"


def amz_link(name, text="Amazon ↗", cls="amz"):
    return f'<a class="{cls}" data-amz href="{amazon(name)}" target="_blank" rel="sponsored noopener">{text}</a>'


def fmt_date(iso, with_year=True):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b %-d, %Y" if with_year else "%b %-d")


def pub_small(g):
    return f"<small>{e(g['Publisher'])}</small>" if g.get("Publisher") else ""


def pill(text, cls):
    return f'<span class="pill {cls}">{e(text)}</span>'


def signup(uid):
    if not KIT_FORM_URL:
        return ""
    return f'''<div class="signup">
  <h2>Know what's in the box before you buy</h2>
  <p>One email a week: new Switch 2 releases, which ones are game-key cards, and compatibility fixes. Unsubscribe anytime.</p>
  <form action="{e(KIT_FORM_URL)}" method="post"><label for="email-{uid}" class="sr">Email address</label><input id="email-{uid}" name="email_address" type="email" required placeholder="you@example.com" autocomplete="email"><button type="submit">Sign me up</button></form>
</div>'''


def page(path, title, description, body, current=None, index=True):
    robots = "" if (LAUNCHED and index) else '<meta name="robots" content="noindex">\n'
    nav = "".join(f'<a href="{href}"{" aria-current=\"page\"" if href == current else ""}>{label}</a>' for href, label in NAV)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots}<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{SITE}{path}">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Atkinson+Hyperlegible:wght@400;700&family=JetBrains+Mono:wght@400;600&display=swap">
<link rel="stylesheet" href="/static/site.css">
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="logo" href="/" aria-label="Nintendo Critic home">{LOGO}<span class="wm"><small>NINTENDO</small><b>Critic</b></span></a>
    <nav class="main" aria-label="Main">{nav}</nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer>
  <div class="wrap">
    <p><strong>Nintendo Critic</strong> is an independent buyer's guide. Not affiliated with, endorsed or sponsored by Nintendo. Game names are trademarks of their owners.</p>
    <p>As an Amazon Associate we earn from qualifying purchases. Questions or corrections: <a href="mailto:hello@nintendocritic.com">hello@nintendocritic.com</a></p>
  </div>
</footer>
<script src="/static/site.js" defer></script>
</body>
</html>
'''


# ---------- data ----------

def load(preview):
    at = Airtable()
    games = [dict(r["fields"], id=r["id"]) for r in at.all(GAMES_TABLE)]
    reviews = [r["fields"] for r in at.all(REVIEWS_TABLE)]
    compat = [r["fields"] for r in at.all(COMPAT_TABLE)]
    for g in games:
        g["slug"] = slugify(g.get("Name", ""))
        g["has_page"] = bool(g.get("Approved")) or (preview and g.get("Status") == "Needs review")
        g["reviews"] = [r for r in reviews if g["id"] in r.get("Game", [])]
    games = [g for g in games if g.get("Name")]
    games.sort(key=lambda g: g["Name"].lower())
    return games, compat


def game_link(g):
    name = e(g["Name"])
    return f'<a href="/games/{g["slug"]}/">{name}</a>' if g["has_page"] else name


# ---------- pages ----------

def game_page(g):
    name = short_name(g["Name"])
    cart = g.get("Cartridge") or "Not announced"
    is_edition = g.get("Game type") == "Switch 2 Edition"
    title_name = g["Name"] if is_edition else f"{name} on Switch 2"
    updated = TODAY.strftime("%b %Y")

    head = f'''<section aria-labelledby="g-title">
<div class="game-head">
  <div class="cart" aria-hidden="true"><div class="label"><small>SWITCH 2</small><b>{e(name)}</b></div><div class="pins"></div></div>
  <div>
    <div class="eyebrow">Switch 2 game check{" · " + e(g["Publisher"]) if g.get("Publisher") else ""} · Updated {updated}</div>
    <h1 id="g-title">{e(title_name)}</h1>
    <p class="lede">Is it a full cartridge? Does it run better? Should you buy it again? Everything to know before you buy.</p>
    <p style="margin:14px 0 0">{pill(cart, CART_CLASS.get(cart, "code"))}</p>
  </div>
</div>'''

    verdict = ""
    if g.get("Verdict") or g.get("Verdict headline"):
        verdict = (f'<div class="verdict"><div class="tag">✓ VERDICT</div><p>'
                   f'{"<strong>" + e(g["Verdict headline"]) + "</strong> " if g.get("Verdict headline") else ""}{e(g.get("Verdict", ""))}</p></div>')

    facts = []
    cart_note = {
        "Game-key card": "The cartridge is a key. Download the game first, then it plays offline with the cart inserted.",
        "Full cartridge": "The whole game is on the cart. No download needed to start playing, and you can resell it.",
        "Code in a box": "No cartridge at all, just a download code in the box.",
    }.get(cart, "The publisher hasn't said yet whether the boxed version is a full cartridge or a game-key card.")
    if g.get("Cartridge confidence") in ("Press report", "Unverified"):
        cart_note += " Based on press reports; we'll confirm it against the store listing."
    facts.append(("What's in the box", cart, cart_note))
    if g.get("Release date"):
        # "Release date note" is for us (where the date came from), so it stays off the page.
        facts.append(("Release date", fmt_date(g["Release date"]),
                      "" if g["Release date"] < TODAY.isoformat() else "Release dates can still move."))
    if is_edition or (g.get("Upgrade path") and g["Upgrade path"] != "Not announced"):
        price = g.get("Upgrade price USD")
        v = g.get("Upgrade path") or "Not announced"
        facts.append(("If you own the Switch 1 version", v,
                      f"About ${price:g} USD." if price else "Price not confirmed yet." if v == "Paid upgrade pack" else ""))
    if g.get("Download size GB"):
        facts.append(("Download size", f'{g["Download size GB"]:g} GB', "From the Nintendo eShop listing. Over about 20 GB, you'll likely want a microSD Express card."))
    facts_html = '<div class="facts">' + "".join(
        f'<div class="fact"><span class="k">{e(k)}</span><span class="v">{e(v)}</span>{f"<p class=\"n\">{e(n)}</p>" if n else ""}</div>'
        for k, v, n in facts) + "</div>"

    played = ""
    if g.get("We played it"):
        played = f'<div class="played"><div class="who">We played it</div><p>{e(g["We played it"])}</p></div>'

    notes = f'<div class="panel"><h2>Good to know</h2><p class="notes">{e(g["Notes"])}</p></div>' if g.get("Notes") and g.get("Approved") else ""

    perf = ""
    if g.get("Performance"):
        rows = []
        for line in g["Performance"].splitlines():
            mode, _, rest = line.partition(":")
            parts = [p.strip() for p in rest.split(",")] if rest else []
            if len(parts) == 2:
                rows.append(f'<tr><td>{e(mode)}</td><td class="num">{e(parts[0])}</td><td class="num">{e(parts[1])}</td></tr>')
            else:
                rows.append(f'<tr><td colspan="3">{e(line)}</td></tr>')
        perf = ('<div class="panel"><h2>Performance on Switch 2</h2><table><thead><tr><th scope="col">Mode</th>'
                '<th scope="col">Resolution</th><th scope="col">Frame rate</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")

    q = urllib.parse.quote(name.lower())
    rev_rows = "".join(
        f'<tr><td><a href="{e(r["URL"])}" target="_blank" rel="noopener">{e(r.get("Outlet", "Review"))}</a></td>'
        f'<td>{e(r.get("Played on", "—"))}</td><td class="num">{e(str(r.get("Score", "—")))}</td><td>{e(r.get("Summary", ""))}</td></tr>'
        for r in g["reviews"] if r.get("URL"))
    reviews = '<div class="panel"><h2>What the reviews say</h2>'
    if rev_rows:
        reviews += ('<p class="sub">Reviews of the Switch 2 version, summarised in our own words. Follow the links for the full reviews.</p>'
                    '<div class="scroll"><table><thead><tr><th scope="col">Outlet</th><th scope="col">Played on</th><th scope="col">Score</th>'
                    f'<th scope="col">In short</th></tr></thead><tbody>{rev_rows}</tbody></table></div>')
    else:
        reviews += '<p class="sub">No Switch 2 reviews yet. We add them as they\'re published.</p>'
    reviews += (f'<p class="sub" style="margin:12px 0 0">Overall scores: <a href="https://www.metacritic.com/search/{q}/" target="_blank" rel="noopener">Metacritic</a>'
                f' · <a href="https://opencritic.com/search?criteria={q}" target="_blank" rel="noopener">OpenCritic</a></p></div>')

    buy = (f'<div class="buy">{amz_link(g["Name"], "Check price on Amazon", "btn")}'
           '<span class="aff-note">We earn a small commission if you buy through this link, at no cost to you.</span></div>')

    src_items = []
    for line in (g.get("Sources") or "").splitlines():
        m = re.match(r"(https?://\S+)\s*(?:\((.*)\))?", line.strip())
        if m:
            host = urllib.parse.urlparse(m.group(1)).netloc.removeprefix("www.")
            label = host + (": " + m.group(2) if m.group(2) else "")
            src_items.append(f'<li><a href="{e(m.group(1))}" target="_blank" rel="noopener">{e(label)}</a></li>')
    sources = f'<div class="sources"><strong>Sources · checked {updated}</strong><ul>{"".join(src_items)}</ul></div>' if src_items else ""

    body = head + verdict + facts_html + played + notes + perf + reviews + buy + signup("game") + sources + "</section>"
    desc = f"Is {name} a game-key card or a full cartridge on Switch 2? Release date, upgrade path, performance and reviews."
    return page(f"/games/{g['slug']}/", f"{title_name}: game-key card, upgrade and reviews | Nintendo Critic", desc, body,
                index=bool(g.get("Approved")))


def keycards_page(games):
    known = [g for g in games if g.get("Cartridge") in CART_CLASS]
    pending = sum(1 for g in games if g.get("Cartridge") == "Not announced")
    rows = "".join(
        f'<tr data-q="{e((g["Name"] + " " + g.get("Publisher", "")).lower())}" data-kind="{CART_CLASS[g["Cartridge"]]}">'
        f'<td class="game">{game_link(g)}</td><td class="pub">{e(g.get("Publisher", ""))}</td>'
        f'<td>{pill(g["Cartridge"], CART_CLASS[g["Cartridge"]])}</td><td>{amz_link(g["Name"])}</td></tr>' for g in known)
    gkc = sum(1 for g in known if g["Cartridge"] == "Game-key card")
    body = f'''<section aria-labelledby="k-title" data-filterable>
<div class="eyebrow">Switch 2 buyer's guide · Updated {TODAY.strftime("%b %Y")}</div>
<h1 id="k-title">Every Switch 2 game-key card</h1>
<p class="lede">Some boxed Switch 2 games don't have the game on the cartridge. Search any game to see what you're actually buying.</p>
<div class="explainer">
  <div>{pill("Full cartridge", "full")}<p>The whole game is on the cart. Plays straight away, no download, and you can resell it.</p></div>
  <div>{pill("Game-key card", "gkc")}<p>The cart is a key. You download the game first, and the cart must be inserted to play.</p></div>
  <div>{pill("Code in a box", "code")}<p>No cartridge at all, just a download code. Can't be resold.</p></div>
</div>
<div class="controls" role="search">
  <label for="q" class="eyebrow" style="flex-basis:100%">Search games</label>
  <input id="q" type="search" placeholder="Try a game or publisher" autocomplete="off">
  <button type="button" class="chip" data-filter="all" aria-pressed="true">All</button>
  <button type="button" class="chip" data-filter="full" aria-pressed="false">Full cartridge</button>
  <button type="button" class="chip" data-filter="gkc" aria-pressed="false">Game-key card</button>
</div>
<div class="table-wrap">
  <table class="list"><thead><tr><th scope="col">Game</th><th scope="col">Publisher</th><th scope="col">Cartridge</th><th scope="col">Buy</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="empty" hidden>No games match. Try a shorter search.</div>
</div>
<div class="count">{len(known)} games with a confirmed cartridge type · {gkc} game-key cards · {pending} more not announced yet<span data-count></span></div>
{signup("keycards")}
</section>'''
    return page("/game-key-cards/", "Every Switch 2 game-key card: full list | Nintendo Critic",
                "Which Switch 2 games are game-key cards and which are full cartridges? Searchable list, updated daily.", body, "/game-key-cards/")


def compat_page(compat):
    rows = "".join(
        f'<tr data-q="{e(c.get("Game or app", "").lower())}" data-kind="x"><td class="game">{e(c.get("Game or app", ""))}'
        f'{" (app)" if c.get("Kind") == "App" else ""}</td><td>{pill(c.get("Status", ""), COMPAT_CLASS.get(c.get("Status"), "warn"))}</td>'
        f'<td>{e(c.get("Details", ""))}</td></tr>' for c in sorted(compat, key=lambda c: c.get("Game or app", "").lower()))
    body = f'''<section aria-labelledby="c-title" data-filterable>
<div class="eyebrow">Switch 1 games on Switch 2 · Updated {TODAY.strftime("%b %Y")}</div>
<h1 id="c-title">Does my Switch 1 game work on Switch 2?</h1>
<p class="lede">Nearly all Switch 1 games work. Search yours to see if it's one of the few with problems, and whether it's been fixed.</p>
<div class="controls" role="search">
  <label for="cq" class="eyebrow" style="flex-basis:100%">Search Switch 1 games and apps</label>
  <input id="cq" type="search" placeholder="Try a game or app" autocomplete="off">
</div>
<div class="table-wrap">
  <table class="list"><thead><tr><th scope="col">Game or app</th><th scope="col">Status</th><th scope="col">Details</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="empty" hidden>Not on the problem list, so it should work fine. Nintendo reports nearly all Switch 1 games run on Switch 2.</div>
</div>
<div class="count">Statuses from press reports and Nintendo's compatibility list.</div>
{signup("compat")}
</section>'''
    return page("/compatibility/", "Switch 1 games on Switch 2: compatibility checker | Nintendo Critic",
                "Does your Switch 1 game work on Switch 2? Search the games and apps with known problems and fixes.", body, "/compatibility/")


def upgrades_page(games):
    eds = [g for g in games if g.get("Game type") == "Switch 2 Edition"]
    rows = []
    for g in eds:
        path = g.get("Upgrade path") or "Not announced"
        if g.get("Upgrade price USD"):
            path += f', about ${g["Upgrade price USD"]:g} USD'
        what = g.get("Performance") or g.get("Notes") or ""
        if g.get("Release date") and g["Release date"] > TODAY.isoformat():
            what = (what + " " if what else "") + f'Out {fmt_date(g["Release date"], False)}.'
        rows.append(f'<tr><td><strong>{game_link(dict(g, Name=short_name(g["Name"])))}</strong></td><td>{e(path)}</td><td>{e(what)}</td></tr>')
    body = f'''<section aria-labelledby="u-title">
<div class="eyebrow">Switch 2 Editions and upgrades · Updated {TODAY.strftime("%b %Y")}</div>
<h1 id="u-title">Switch 2 upgrades: what they cost and what you get</h1>
<p class="lede">Some Switch 1 games get a paid Switch 2 Edition upgrade, some get a free update, and some are free with Nintendo Switch Online + Expansion Pack.</p>
<div class="panel"><div class="scroll"><table>
<thead><tr><th scope="col">Game</th><th scope="col">If you own the Switch 1 version</th><th scope="col">What improves</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></div>
<p class="sub" style="margin-top:12px;color:var(--muted);font-size:14px">Prices in US dollars from Nintendo's announcements.</p>
</section>'''
    return page("/upgrades/", "Switch 2 Edition upgrades: prices and what you get | Nintendo Critic",
                "Every Switch 2 Edition and upgrade pack: what it costs if you own the Switch 1 version and what improves.", body, "/upgrades/")


def upcoming(games):
    soon = [g for g in games if g.get("Release date", "") >= TODAY.isoformat()]
    soon.sort(key=lambda g: g["Release date"])
    return soon


def radar_page(games):
    months = {}
    for g in upcoming(games):
        months.setdefault(dt.date.fromisoformat(g["Release date"]).strftime("%B %Y"), []).append(g)
    tba = [g for g in games if not g.get("Release date")]
    if tba:
        months["Date to be announced"] = tba
    out = []
    for m, gs in months.items():
        out.append(f'<div class="month"><h2>{m}</h2>')
        for g in gs:
            d = fmt_date(g["Release date"], False) if g.get("Release date") else "TBA"
            cart = g.get("Cartridge") or "Not announced"
            out.append(f'<div class="rel" data-q="{e(g["Name"].lower())}" data-kind="x"><span class="d">{d}</span>'
                       f'<span class="t">{game_link(g)}{pub_small(g)}</span>'
                       f'{pill(cart, CART_CLASS.get(cart, "code"))}</div>')
        out.append("</div>")
    body = f'''<section aria-labelledby="r-title" data-filterable>
<div class="eyebrow">Release radar · Updated {fmt_date(TODAY.isoformat())}</div>
<h1 id="r-title">Upcoming Switch 2 games</h1>
<p class="lede">Release dates and what's in the box. Cartridge types are added as soon as publishers confirm them, so you know before you pre-order.</p>
<div class="controls" role="search">
  <label for="rq" class="eyebrow" style="flex-basis:100%">Search upcoming games</label>
  <input id="rq" type="search" placeholder="Try a game" autocomplete="off">
</div>
{"".join(out)}
<div class="empty" hidden>No upcoming games match.</div>
<div class="count">Dates from publisher announcements and the IGDB games database. Smaller titles can move.</div>
{signup("radar")}
</section>'''
    return page("/coming-soon/", "Upcoming Switch 2 games: release dates and cartridge types | Nintendo Critic",
                "Every upcoming Switch 2 game with its release date and whether it's a full cartridge or game-key card.", body, "/coming-soon/")


def home_page(games, compat):
    gkc = sum(1 for g in games if g.get("Cartridge") == "Game-key card")
    eds = sum(1 for g in games if g.get("Game type") == "Switch 2 Edition")
    soon = upcoming(games)[:6]
    rel = "".join(
        f'<div class="rel"><span class="d">{fmt_date(g["Release date"], False)}</span><span class="t">{game_link(g)}'
        f'{pub_small(g)}</span>'
        f'{pill(g.get("Cartridge") or "Not announced", CART_CLASS.get(g.get("Cartridge"), "code"))}</div>' for g in soon)
    body = f'''<section aria-labelledby="h-title">
<div class="eyebrow">The Switch 2 game checker</div>
<h1 id="h-title">Know what you're buying on Switch 2</h1>
<p class="lede">Game-key card or full cartridge? Does your Switch 1 game work? Is the upgrade worth it? Checked daily across {len(games)} Switch 2 games.</p>
<div class="hubs">
  <a href="/game-key-cards/"><b>Game-key cards</b><span>{gkc} confirmed so far. Which boxed games make you download first.</span></a>
  <a href="/compatibility/"><b>Switch 1 compatibility</b><span>The {len(compat)} games and apps with known problems on Switch 2.</span></a>
  <a href="/upgrades/"><b>Switch 2 Editions</b><span>{eds} upgrades: what they cost and what improves.</span></a>
  <a href="/coming-soon/"><b>Coming soon</b><span>Every upcoming Switch 2 release, with dates.</span></a>
</div>
<div class="month"><h2>Next up</h2>{rel}<p><a href="/coming-soon/">All upcoming games →</a></p></div>
{signup("home")}
</section>'''
    return page("/", "Nintendo Critic: the Switch 2 game checker", "Game-key cards, Switch 1 compatibility and Switch 2 upgrades, checked daily.", body)


def not_found_page():
    body = '''<section><div class="eyebrow">404</div><h1>That page isn't here</h1>
<p class="lede">The game may not have its own page yet. Try the <a href="/game-key-cards/">game-key card list</a> or <a href="/coming-soon/">upcoming games</a>.</p></section>'''
    return page("/404.html", "Page not found | Nintendo Critic", "Page not found.", body, index=False)


def build(out, preview):
    games, compat = load(preview)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site" / "static", out / "static")
    shutil.copy(ROOT / "site" / "CNAME", out / "CNAME")

    pages = {
        "index.html": home_page(games, compat),
        "game-key-cards/index.html": keycards_page(games),
        "compatibility/index.html": compat_page(compat),
        "upgrades/index.html": upgrades_page(games),
        "coming-soon/index.html": radar_page(games),
        "404.html": not_found_page(),
    }
    seen = set()
    for g in games:
        if g["has_page"]:
            if g["slug"] in seen:
                print(f"warning: duplicate slug {g['slug']}, skipping {g['Name']}")
                continue
            seen.add(g["slug"])
            pages[f"games/{g['slug']}/index.html"] = game_page(g)
    for rel, content in pages.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    approved = {f"games/{g['slug']}/index.html" for g in games if g.get("Approved")}
    urls = [rel.removesuffix("index.html") for rel in pages
            if rel != "404.html" and (not rel.startswith("games/") or rel in approved)]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE}/{u}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    # Crawling stays allowed before launch so search engines can see the noindex tags.
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {SITE}/sitemap.xml\n" if LAUNCHED else ""))
    print(f"Built {len(pages)} pages ({len(seen)} game pages) into {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="also build pages for 'Needs review' games (local checking only)")
    ap.add_argument("--out", default=str(ROOT / "public"))
    args = ap.parse_args()
    load_env(required=("AIRTABLE_TOKEN",))
    build(Path(args.out), args.preview)
