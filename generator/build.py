"""Build the static site from Airtable into public/.

Standard library only. Static files (CNAME, static/) are copied from site/.
Only games with the Approved box ticked get their own page; the hub lists show every game.

  python3 generator/build.py            # what the live site gets
  python3 generator/build.py --preview  # also builds pages for unapproved games, for checking locally
"""
import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))
from common import COMPAT_TABLE, GAMES_TABLE, REVIEWS_TABLE, Airtable, load_env  # noqa: E402
import media  # noqa: E402

# Flip to True when the data has been reviewed and the site should appear in search results.
LAUNCHED = False
SITE = "https://nintendocritic.com"
AMAZON_TAG = "magpie014-20"  # site.js swaps in the amazon.ca tag for Canadian visitors
# Newsletter Worker (~/Work/newsletter). Signup boxes stay hidden until this is set.
NEWSLETTER_API = "https://newsletter.crossplayguide.workers.dev"

NAV = [
    ("/game-key-cards/", "Game-key cards"),
    ("/compatibility/", "Compatibility"),
    ("/upgrades/", "Upgrades"),
    ("/coming-soon/", "Coming soon"),
    ("/is-switch-2-worth-it/", "Worth it?"),
]
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


# Small icons for what's in the box, so a list can be scanned without reading every label.
_CART = "M6 2.5h8.5l4.5 4.5v13a1.5 1.5 0 0 1-1.5 1.5h-11.5a1.5 1.5 0 0 1-1.5-1.5v-16a1.5 1.5 0 0 1 1.5-1.5z"
ICONS = {
    "full": f'<path d="{_CART}" fill="currentColor" fill-opacity=".22" stroke="currentColor" stroke-width="1.6"/>'
            '<path d="M8.5 12.5l2.4 2.4 4.6-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "gkc": f'<path d="{_CART}" fill="none" stroke="currentColor" stroke-width="1.6"/>'
           '<circle cx="9.5" cy="12.5" r="2.3" fill="none" stroke="currentColor" stroke-width="1.7"/>'
           '<path d="M11.8 12.5h4.4M14.6 12.5v2.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    "code": '<rect x="3.5" y="4.5" width="17" height="15" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/>'
            '<path d="M7 10h10M7 14h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    "tba": f'<path d="{_CART}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="2.6 2"/>'
           '<path d="M10 10.2a2.2 2.2 0 1 1 3 2c-.7.3-1 .8-1 1.5v.3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>'
           '<circle cx="12" cy="17.2" r="1" fill="currentColor"/>',
}
CART_KIND = {"Full cartridge": "full", "Game-key card": "gkc", "Code in a box": "code"}


def icon(kind, size=18):
    return f'<svg class="ico" viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true">{ICONS[kind]}</svg>'


def badge(cart):
    """Cartridge-type pill with its icon. Unknown types show as 'Not announced'."""
    cart = cart if cart in CART_KIND else "Not announced"
    kind = CART_KIND.get(cart, "tba")
    return f'<span class="pill {kind} has-ico">{icon(kind, 16)}{e(cart)}</span>'


def cover(g, size="t_cover_big", w=264, h=352, cls="cover"):
    """Box art from IGDB, or a branded placeholder card with the game's name when there's none."""
    if g.get("cover"):
        return (f'<img class="{cls}" src="{media.img(g["cover"], size)}" width="{w}" height="{h}" '
                f'alt="{e(short_name(g["Name"]))} box art" loading="lazy" decoding="async">')
    return f'<span class="{cls} cover-ph" aria-hidden="true"><span>{e(short_name(g["Name"]))}</span></span>'


def signup(uid):
    if not NEWSLETTER_API:
        return ""
    return f'''<div class="signup">
  <h2>Know what's in the box before you buy</h2>
  <p>One email a week: new Switch 2 releases, which ones are game-key cards, and compatibility fixes. Unsubscribe anytime.</p>
  <form action="{e(NEWSLETTER_API)}/subscribe" method="post"><input type="hidden" name="site" value="nintendocritic"><input class="sr" name="website" tabindex="-1" autocomplete="off" aria-hidden="true"><label for="email-{uid}" class="sr">Email address</label><input id="email-{uid}" name="email" type="email" required placeholder="you@example.com" autocomplete="email"><button type="submit">Sign me up</button></form>
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
    <p><a href="/about/">About</a> · <a href="/privacy/">Privacy</a>{" · <a href=\"/newsletter/\">Weekly email</a>" if NEWSLETTER_API else ""}</p>
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
    art = media.fetch(g.get("IGDB ID") for g in games)
    for g in games:
        m = art.get(int(g["IGDB ID"])) if g.get("IGDB ID") else None
        g["cover"] = (m or {}).get("cover")
        g["shots"] = (m or {}).get("shots", [])
        g["art"] = (m or {}).get("art", [])
        g["videos"] = (m or {}).get("videos", [])
        g["trailer"] = None
        if g["has_page"]:  # only game pages show trailers, so only check those with YouTube
            g["trailer"] = next((v for v in media.trailer_candidates(g["videos"])[:3] if media.playable(v)), None)
    return games, compat


def game_link(g):
    name = e(g["Name"])
    return f'<a href="/games/{g["slug"]}/">{name}</a>' if g["has_page"] else name


def game_card(g):
    """Box-art card for grids: cover, release date, name, publisher and what's in the box."""
    d = fmt_date(g["Release date"], False) if g.get("Release date") else "TBA"
    tag, href = ("a", f' href="/games/{g["slug"]}/"') if g["has_page"] else ("div", "")
    return (f'<{tag} class="gcard"{href} data-q="{e((g["Name"] + " " + g.get("Publisher", "")).lower())}" data-kind="x">'
            f'<span class="art">{cover(g, "t_cover_big", 264, 352)}<span class="date">{d}</span></span>'
            f'<span class="t">{e(short_name(g["Name"]))}</span>{pub_small(g)}{badge(g.get("Cartridge"))}</{tag}>')


# ---------- pages ----------

def game_page(g):
    name = short_name(g["Name"])
    cart = g.get("Cartridge") or "Not announced"
    is_edition = g.get("Game type") == "Switch 2 Edition"
    title_name = g["Name"] if is_edition else f"{name} on Switch 2"
    updated = TODAY.strftime("%b %Y")

    # Key art (or a screenshot) as a dimmed banner behind the header; the box art sits inside the cartridge.
    banner = g["art"][0] if g["art"] else (g["shots"][0] if g["shots"] else None)
    banner_style = f' style="--banner:url({media.img(banner, "t_1080p")})"' if banner else ""
    label = (f'<img src="{media.img(g["cover"], "t_cover_big")}" width="264" height="352" alt="{e(name)} box art">'
             if g["cover"] else f'<small>SWITCH 2</small><b>{e(name)}</b>')
    head = f'''<section aria-labelledby="g-title">
<div class="game-head{" has-banner" if banner else ""}"{banner_style}>
  <div class="cart{" has-cover" if g["cover"] else ""}"><div class="label">{label}</div><div class="pins" aria-hidden="true"></div></div>
  <div>
    <div class="eyebrow">Switch 2 game check{" · " + e(g["Publisher"]) if g.get("Publisher") else ""} · Updated {updated}</div>
    <h1 id="g-title">{e(title_name)}</h1>
    <p class="lede">Is it a full cartridge? Does it run better? Should you buy it again? Everything to know before you buy.</p>
    <p style="margin:14px 0 0">{badge(cart)}</p>
  </div>
</div>'''

    verdict = ""
    if g.get("Verdict") or g.get("Verdict headline"):
        verdict = (f'<div class="verdict"><div class="tag">✓ VERDICT</div><p>'
                   f'{"<strong>" + e(g["Verdict headline"]) + "</strong> " if g.get("Verdict headline") else ""}{e(g.get("Verdict", ""))}</p></div>')
    # "Is X worth it on Switch 2?" is what people search, so the verdict and the hands-on note sit under that question.
    worth_q = f"Is {name} worth it on Switch 2?"

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
        if v == "Free with NSO Expansion Pack" and price:
            v, n = f"${price:.2f} upgrade pack", "Free if you have Nintendo Switch Online + Expansion Pack."
        else:
            n = f"${price:.2f} in the US." if price else "Price not confirmed yet." if v == "Paid upgrade pack" else ""
        facts.append(("If you own the Switch 1 version", v, n))
    if g.get("Download size GB"):
        facts.append(("Download size", f'{g["Download size GB"]:g} GB', "From the Nintendo eShop listing. Over about 20 GB, you'll likely want a microSD Express card."))
    kind = CART_KIND.get(cart, "tba")
    fact_cards = []
    for i, (k, v, n) in enumerate(facts):
        # The first fact is always what's in the box: it gets the cartridge icon and its type's colour.
        cls, ico = (f"fact box {kind}", icon(kind, 30)) if i == 0 else ("fact", "")
        note = f'<p class="n">{e(n)}</p>' if n else ""
        fact_cards.append(f'<div class="{cls}"><span class="k">{e(k)}</span><span class="v">{ico}{e(v)}</span>{note}</div>')
    facts_html = '<div class="facts">' + "".join(fact_cards) + "</div>"

    played = ""
    if g.get("We played it"):
        when = f' · {fmt_date(g["Played date"])}' if g.get("Played date") else ""
        played = (f'<div class="played"><div class="who">Played on Switch 2 · Mike Johnston{when}</div>'
                  f'<p>{e(g["We played it"])}</p></div>')
    worth = (f'<div class="panel worth"><h2>{e(worth_q)}</h2>{verdict}{played}</div>' if verdict or played else "")

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
        perf = (f'<div class="panel"><h2>How does {e(name)} run on Switch 2?</h2><table><thead><tr><th scope="col">Mode</th>'
                '<th scope="col">Resolution</th><th scope="col">Frame rate</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")

    # Trailer + screenshots. The YouTube player only loads when pressed (site.js), so YouTube sets no cookies until then.
    media_html = ""
    if g["trailer"] or g["shots"]:
        parts = []
        if g["trailer"]:
            parts.append(f'<button class="yt" type="button" data-yt="{e(g["trailer"])}" aria-label="Play the {e(name)} trailer">'
                         f'<img src="https://i.ytimg.com/vi/{e(g["trailer"])}/hqdefault.jpg" width="480" height="360" alt="" loading="lazy">'
                         '<span class="yt-play" aria-hidden="true"></span></button>')
        if g["shots"]:
            shots = g["shots"][:6]
            parts.append('<div class="shots">' + "".join(
                f'<a href="{media.img(s, "t_1080p")}" target="_blank" rel="noopener" aria-label="{e(name)} screenshot {i} of {len(shots)}">'
                f'<img src="{media.img(s, "t_screenshot_med")}" width="569" height="320" alt="" loading="lazy"></a>'
                for i, s in enumerate(shots, 1)) + "</div>")
        what = "Trailer and screenshots" if g["trailer"] and g["shots"] else "Trailer" if g["trailer"] else "Screenshots"
        media_html = (f'<div class="panel media"><h2>{what}</h2>' + "".join(parts)
                      + '<p class="sub" style="margin:10px 0 0">Images via IGDB.'
                      + (' The trailer plays from YouTube when you press play.' if g["trailer"] else "") + '</p></div>')

    q = urllib.parse.quote(name.lower())
    revs = sorted((r for r in g["reviews"] if r.get("URL")), key=lambda r: r.get("Outlet", ""))
    has_score = any(r.get("Score") for r in revs)
    rev_rows = "".join(
        f'<tr><td><a href="{e(r["URL"])}" target="_blank" rel="noopener">{e(r.get("Outlet", "Review"))}</a></td>'
        + (f'<td class="num">{e(str(r.get("Score", "—")))}</td>' if has_score else "")
        + f'<td>{e(r["Summary"]) if r.get("Summary") else "<a href=" + chr(34) + e(r["URL"]) + chr(34) + " target=_blank rel=noopener>Read the review ↗</a>"}</td></tr>'
        for r in revs)
    reviews = '<div class="panel"><h2>What the reviews say</h2>'
    if rev_rows:
        reviews += ('<p class="sub">Reviews of the Switch 2 version, summarised in our own words. Follow the links for the full reviews.</p>'
                    '<div class="scroll"><table><thead><tr><th scope="col">Outlet</th>'
                    + ('<th scope="col">Score</th>' if has_score else "")
                    + f'<th scope="col">In short</th></tr></thead><tbody>{rev_rows}</tbody></table></div>')
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

    # FAQ schema mirrors answers already visible on the page (no hidden text).
    qas = [(f"Is {name} a game-key card or a full cartridge?", f"{cart}. {cart_note}")]
    if g.get("Verdict") or g.get("We played it"):
        qas.append((worth_q, " ".join(x for x in (g.get("Verdict headline"), g.get("Verdict"), g.get("We played it")) if x)))
    if g.get("Performance"):
        qas.append((f"How does {name} run on Switch 2?", "; ".join(g["Performance"].splitlines())))
    if is_edition and g.get("Upgrade path"):
        up = g.get("Upgrade price USD")
        qas.append(("How much is the Switch 2 upgrade?",
                    (f"${up:.2f} in the US" + (", or free with Nintendo Switch Online + Expansion Pack." if "NSO" in g["Upgrade path"] else "."))
                    if up else g["Upgrade path"] + "."))
    schema = ('<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qas]},
              ensure_ascii=False) + "</script>")

    body = head + facts_html + worth + media_html + notes + perf + reviews + buy + signup("game") + sources + schema + "</section>"
    desc = f"Is {name} a game-key card or a full cartridge on Switch 2? Release date, upgrade path, performance and reviews."
    return page(f"/games/{g['slug']}/", f"{title_name}: game-key card, upgrade and reviews | Nintendo Critic", desc, body,
                index=bool(g.get("Approved")))


def keycards_page(games):
    known = [g for g in games if g.get("Cartridge") in CART_KIND]
    pending = sum(1 for g in games if g.get("Cartridge") == "Not announced")
    rows = "".join(
        f'<tr data-q="{e((g["Name"] + " " + g.get("Publisher", "")).lower())}" data-kind="{CART_KIND[g["Cartridge"]]}">'
        f'<td class="game"><span class="with-thumb">{cover(g, "t_cover_small", 90, 120, "thumb")}{game_link(g)}</span></td>'
        f'<td class="pub">{e(g.get("Publisher", ""))}</td>'
        f'<td>{badge(g["Cartridge"])}</td><td>{amz_link(g["Name"])}</td></tr>' for g in known)
    gkc = sum(1 for g in known if g["Cartridge"] == "Game-key card")
    body = f'''<section aria-labelledby="k-title" data-filterable>
<div class="eyebrow">Switch 2 buyer's guide · Updated {TODAY.strftime("%b %Y")}</div>
<h1 id="k-title">Every Switch 2 game-key card</h1>
<p class="lede">Some boxed Switch 2 games don't have the game on the cartridge. Search any game to see what you're actually buying.</p>
<div class="explainer">
  <div class="ex full">{icon("full", 40)}{badge("Full cartridge")}<p>The whole game is on the cart. Plays straight away, no download, and you can resell it.</p></div>
  <div class="ex gkc">{icon("gkc", 40)}{badge("Game-key card")}<p>The cart is a key. You download the game first, and the cart must be inserted to play.</p></div>
  <div class="ex code">{icon("code", 40)}{badge("Code in a box")}<p>No cartridge at all, just a download code. Can't be resold.</p></div>
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


def faq_block(qas):
    """Visible Q&A plus FAQPage schema. qas: [(question, answer_text)]."""
    items = "".join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q, a in qas)
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qas]}
    return (f'<div class="panel faq"><h2>Questions people ask</h2>{items}</div>'
            f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>')


def norm_name(n):
    return re.sub(r"[^a-z0-9]", "", short_name(n).lower().replace("&", "and"))


def upgrades_page(games):
    """Every Switch 2 upgrade pack and free upgrade, from data/upgrades.json (checked against two published lists)."""
    data = json.loads((ROOT / "data" / "upgrades.json").read_text())
    pages = {norm_name(g["Name"]): g for g in games if g["has_page"]}

    def name_cell(u):
        g = pages.get(norm_name(u["name"]))
        n = f'<a href="/games/{g["slug"]}/">{e(u["name"])}</a>' if g else e(u["name"])
        return n + (' <span class="pill nin">Nintendo</span>' if u.get("nintendo") else "")

    paid = sorted(data["paid"], key=lambda u: (-u["price"], u["name"].lower()))
    paid_rows = "".join(
        f'<tr data-q="{e(u["name"].lower())}" data-kind="{"nin" if u.get("nintendo") else "x"}">'
        f'<td class="game">{name_cell(u)}</td><td class="num">${u["price"]:.2f}</td><td>{e(u.get("note", ""))}</td></tr>'
        for u in paid)
    free = sorted(data["free"], key=lambda u: u["name"].lower())
    free_rows = "".join(f'<tr data-q="{e(u["name"].lower())}" data-kind="free"><td class="game">{name_cell(u)}</td>'
                        f'<td class="num">Free</td><td></td></tr>' for u in free)
    nin_free = ", ".join(data["nintendo_free_updates"])
    coming = "".join(f'<li><strong>{e(c["name"])}</strong>: {e(c["note"])}</li>' for c in data.get("coming", []))
    nin_paid = [u for u in paid if u.get("nintendo")]
    cheapest = min(u["price"] for u in paid)
    dearest = max(u["price"] for u in paid)
    checked = fmt_date(data["checked"])
    srcs = "".join(f'<li><a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["title"])}</a></li>' for x in data["sources"])
    qas = [
        ("How do Switch 2 upgrade packs work?",
         "If you own the Switch 1 version of a game, an upgrade pack unlocks its Switch 2 version, usually with better "
         "resolution and frame rate and sometimes new content. You buy it on the Nintendo eShop and keep your save. "
         "If you don't own the game yet, you can buy the Switch 2 Edition outright instead."),
        ("Are Switch 2 upgrades free?",
         f"Many are. {len(free)} games on this list upgrade for free, and Nintendo gave {len(data['nintendo_free_updates'])} "
         f"of its own Switch 1 games free Switch 2 updates. The other {len(paid)} cost between ${cheapest:.2f} and ${dearest:.2f}."),
        ("Which Switch 2 upgrades are free with Nintendo Switch Online?",
         "The Switch 2 Editions of The Legend of Zelda: Breath of the Wild and Tears of the Kingdom are included with "
         "Nintendo Switch Online + Expansion Pack. Without it, each costs $9.99."),
        ("How much are Nintendo's Switch 2 upgrade packs?",
         "; ".join(f'{short_name(u["name"])} ${u["price"]:.2f}' for u in nin_paid) + "."),
    ]
    body = f'''<section aria-labelledby="u-title" data-filterable>
<div class="eyebrow">Switch 2 Editions and upgrade packs · Prices checked {checked}</div>
<h1 id="u-title">Switch 2 upgrade packs: every price, plus the free upgrades</h1>
<p class="lede">Own a Switch 1 game? Here's what it costs to get its Switch 2 version: {len(paid)} paid upgrade packs from
${cheapest:.2f} to ${dearest:.2f}, and {len(free)} games that upgrade for free.</p>
<div class="controls" role="search">
  <label for="q" class="eyebrow" style="flex-basis:100%">Search upgrades</label>
  <input id="q" type="search" placeholder="Try a game" autocomplete="off">
  <button type="button" class="chip" data-filter="all" aria-pressed="true">All</button>
  <button type="button" class="chip" data-filter="nin" aria-pressed="false">Nintendo</button>
  <button type="button" class="chip" data-filter="free" aria-pressed="false">Free</button>
</div>
<div class="table-wrap">
  <table class="list"><thead><tr><th scope="col">Game</th><th scope="col">Upgrade price (US)</th><th scope="col">What you get</th></tr></thead>
  <tbody>{paid_rows}{free_rows}</tbody></table>
  <div class="empty" hidden>No games match. Try a shorter search.</div>
</div>
<div class="count">{len(paid)} paid upgrade packs · {len(free)} free upgrades<span data-count></span></div>
<div class="panel"><h2>Free Switch 2 updates for Nintendo's own games</h2>
<p>These Switch 1 games got a free update that improves them on Switch 2, such as sharper resolution, a steadier frame
rate or HDR, depending on the game: {e(nin_free)}.</p>
<p class="sub">Most other Switch 1 games run on Switch 2 without any update. See <a href="/compatibility/">the compatibility list</a> for the exceptions.</p></div>
{"<div class=\"panel\"><h2>Coming soon</h2><ul>" + coming + "</ul></div>" if coming else ""}
{faq_block(qas)}
<div class="sources"><strong>Sources · prices checked {checked}</strong><ul>{srcs}</ul>
<p class="sub">US eShop prices; they can differ by region and during sales.</p></div>
{signup("upgrades")}
</section>'''
    return page("/upgrades/", "Switch 2 upgrade pack prices: every paid and free upgrade | Nintendo Critic",
                f"Every Switch 2 upgrade pack price ({len(paid)} paid, {len(free)} free), which upgrades are free with "
                "Nintendo Switch Online, and what each Switch 2 Edition adds.", body, "/upgrades/")


def worth_it_page(games, compat):
    """'Is the Switch 2 worth it?': sourced facts and live counts, plus Mike's first-hand sections from content/worth-it.json."""
    mine = json.loads((ROOT / "content" / "worth-it.json").read_text())
    up = json.loads((ROOT / "data" / "upgrades.json").read_text())
    today = TODAY.isoformat()
    out_now = [g for g in games if g.get("Release date") and g["Release date"] <= today]
    gkc = sum(1 for g in games if g.get("Cartridge") == "Game-key card")
    known = sum(1 for g in games if g.get("Cartridge") in CART_KIND)
    paras = lambda t: "".join(f"<p>{e(x.strip())}</p>" for x in t.split("\n\n") if x.strip())
    lst = lambda xs: "<ul>" + "".join(f"<li>{e(x)}</li>" for x in xs) + "</ul>"

    short = (f'<div class="verdict"><div class="tag">SHORT ANSWER</div><p>{e(mine["short_answer"])}</p></div>'
             if mine.get("short_answer") else "")
    fit = ""
    if mine.get("worth_it_if") or mine.get("wait_if"):
        fit = ('<div class="two-col">'
               + (f'<div class="panel"><h2>Worth it if you…</h2>{lst(mine["worth_it_if"])}</div>' if mine.get("worth_it_if") else "")
               + (f'<div class="panel"><h2>Wait if you…</h2>{lst(mine["wait_if"])}</div>' if mine.get("wait_if") else "")
               + "</div>")
    exp = (f'<div class="panel played"><div class="who">Played on Switch 2 · Mike Johnston</div>{paras(mine["my_experience"])}</div>'
           if mine.get("my_experience") else "")
    paid = up["paid"]
    nin_paid = sorted({u["price"] for u in paid if u.get("nintendo")})
    qas = [
        ("How much is the Switch 2?",
         "$499.99 in the US. Nintendo raised the price from $449.99 on September 1, 2026; retailers can still run their own deals."),
        ("Do Switch 1 games work on Switch 2?",
         f"Almost all of them do. We track {len(compat)} games and apps with known problems or fixes on our compatibility list, "
         f"and {len(up['nintendo_free_updates'])} of Nintendo's own Switch 1 games got free updates that make them look or run better."),
        ("How much do Switch 2 upgrade packs cost?",
         f"If you already own a game on Switch 1, its Switch 2 upgrade costs between ${min(u['price'] for u in paid):.2f} and "
         f"${max(u['price'] for u in paid):.2f}, and {len(up['free'])} games upgrade for free. Nintendo's own packs cost "
         f"${nin_paid[0]:.2f} to ${nin_paid[-1]:.2f}."),
        ("Are Switch 2 games on the cartridge?",
         f"Not always. Of the {known} games where we know what's in the box, {gkc} are game-key cards: the cartridge "
         "unlocks a download, so you need an internet connection and storage space the first time you play."),
        ("Do I need a new memory card for Switch 2?",
         "Only if 256 GB isn't enough. The Switch 2 takes microSD Express cards (up to 2 TB); ordinary microSD cards from the "
         "Switch 1 can only be used to copy screenshots and videos across."),
    ]
    facts = [
        ("Price (US)", "$499.99", "Up from $449.99 on September 1, 2026."),
        ("Screen", '7.9" 1080p, up to 120 Hz', "LCD with HDR10 and variable refresh rate."),
        ("On the TV", "Up to 4K at 60 fps", "120 fps at 1080p or 1440p in games that support it."),
        ("Storage", "256 GB", "Expand with microSD Express only (up to 2 TB)."),
        ("Battery", "About 2 to 6.5 hours", "Depends on the game."),
        ("Games out now", f"{len(out_now)}", "Switch 2 games and Switch 2 Editions we track, not counting eShop filler."),
    ]
    fact_html = '<div class="facts">' + "".join(
        f'<div class="fact"><span class="k">{e(k)}</span><span class="v">{e(v)}</span><p class="n">{e(n)}</p></div>' for k, v, n in facts) + "</div>"
    costs = f'''<div class="panel"><h2>What it really costs</h2>
<p>The console is $499.99, but a few things change what you spend after that:</p>
<ul>
<li><strong>Game-key cards.</strong> {gkc} of the {known} boxed games whose cartridge type is known are game-key cards,
so the cartridge needs a download before it plays. See <a href="/game-key-cards/">the full list</a>.</li>
<li><strong>Upgrade packs.</strong> Already own Switch 1 games? Their Switch 2 versions cost from free to
${max(u["price"] for u in paid):.2f}. See <a href="/upgrades/">every upgrade price</a>.</li>
<li><strong>Storage.</strong> 256 GB fills up quickly with downloads. Extra space means a microSD Express card; your old
microSD cards won't run games.</li>
<li><strong>Your Switch 1 library.</strong> It comes with you. Check <a href="/compatibility/">the compatibility list</a>
for the handful of games and apps with problems.</li>
</ul></div>'''
    srcs = [("https://www.nintendo.com/us/whatsnew/price-revision-for-nintendo-switch-2-system/", "Price revision for Nintendo Switch 2 (Nintendo)"),
            ("https://www.nintendo.com/us/gaming-systems/switch-2/tech-specs/", "Nintendo Switch 2 tech specs (Nintendo)")]
    src_html = '<div class="sources"><strong>Sources</strong><ul>' + "".join(
        f'<li><a href="{u}" target="_blank" rel="noopener">{e(t)}</a></li>' for u, t in srcs) + "</ul></div>"
    body = f'''<section aria-labelledby="w-title">
<div class="eyebrow">Switch 2 buyer's guide · Updated {fmt_date(mine.get("updated") or today)}</div>
<h1 id="w-title">Is the Switch 2 worth it in {TODAY.year}?</h1>
<p class="lede">What you get for $499.99, what it really costs once you add games and storage, and who should wait.</p>
{short}{fact_html}{fit}{exp}{costs}{faq_block(qas)}{src_html}{signup("worth")}
</section>'''
    return page("/is-switch-2-worth-it/", f"Is the Switch 2 worth it in {TODAY.year}? Price, games and real costs | Nintendo Critic",
                "Is the Nintendo Switch 2 worth $499.99? What you get, what Switch 2 games and upgrades really cost, "
                "game-key cards, storage and who should wait.", body)


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
        out.append(f'<div class="month"><h2>{m} <small>{len(gs)} game{"s" if len(gs) != 1 else ""}</small></h2><div class="grid">')
        out += [game_card(g) for g in gs]
        out.append("</div></div>")
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


HUB_ICONS = {
    "compat": '<path d="M4 8h12l-3-3M20 16H8l3 3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "up": '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
          '<path d="M5 21h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    "cal": '<rect x="3.5" y="5" width="17" height="15.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/>'
           '<path d="M3.5 10h17M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
           '<rect x="7" y="13" width="3" height="3" rx=".6" fill="currentColor"/>',
}


def hub_icon(name):
    return f'<svg class="ico" viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">{HUB_ICONS[name]}</svg>'


def search_index(games):
    """Every game for the homepage search: name, page slug (if it has one), box type, date, cover."""
    return json.dumps([{"n": g["Name"], "p": g.get("Publisher", ""), "s": g["slug"] if g["has_page"] else "",
                        "c": CART_KIND.get(g.get("Cartridge"), "tba"), "d": g.get("Release date", ""), "i": g.get("cover") or ""}
                       for g in games], separators=(",", ":"))


def home_page(games, compat):
    count = {k: sum(1 for g in games if CART_KIND.get(g.get("Cartridge"), "tba") == k) for k in ("gkc", "full", "code", "tba")}
    eds = sum(1 for g in games if g.get("Game type") == "Switch 2 Edition")
    strip = "".join(game_card(g) for g in upcoming(games)[:12])
    body = f'''<section aria-labelledby="h-title">
<div class="hero">
  <div class="eyebrow">The Switch 2 game checker</div>
  <h1 id="h-title">Is it a game-key card?</h1>
  <p class="lede">Search any Switch 2 game to see what's really in the box, before you buy. Checked daily across {len(games)} games.</p>
  <div class="finder" data-finder>
    <label for="find" class="sr">Search Switch 2 games</label>
    <input id="find" type="search" placeholder="Type a game, e.g. Mario Kart World" autocomplete="off" data-find>
    <div class="results" data-results hidden></div>
    <script type="application/json" id="cart-icons">{json.dumps(ICONS).replace("</", "<\\/")}</script>
  </div>
  <div class="stats">
    <a class="stat gkc" href="/game-key-cards/">{icon("gkc", 34)}<b>{count["gkc"]}</b><span>game-key cards</span></a>
    <a class="stat full" href="/game-key-cards/">{icon("full", 34)}<b>{count["full"]}</b><span>full cartridges</span></a>
    <a class="stat tba" href="/coming-soon/">{icon("tba", 34)}<b>{count["tba"]}</b><span>not announced yet</span></a>
  </div>
</div>
<div class="month"><h2>Next up <a class="more" href="/coming-soon/">All upcoming games →</a></h2><div class="strip">{strip}</div></div>
<div class="hubs">
  <a href="/game-key-cards/">{icon("gkc", 34)}<b>Game-key cards</b><span>Which boxed games make you download first.</span></a>
  <a href="/compatibility/">{hub_icon("compat")}<b>Switch 1 compatibility</b><span>The {len(compat)} games and apps with known problems on Switch 2.</span></a>
  <a href="/upgrades/">{hub_icon("up")}<b>Switch 2 Editions</b><span>{eds} upgrades: what they cost and what improves.</span></a>
  <a href="/coming-soon/">{hub_icon("cal")}<b>Coming soon</b><span>Every upcoming Switch 2 release, with dates.</span></a>
</div>
{signup("home")}
</section>'''
    return page("/", "Nintendo Critic: the Switch 2 game checker", "Game-key cards, Switch 1 compatibility and Switch 2 upgrades, checked daily.", body)


NEWSLETTER_STATES = {
    "check": "Almost done: check your inbox for a confirmation email and click the button in it.",
    "invalid": "That email address doesn't look right. Please try again.",
    "confirming": "Confirming your subscription…",
    "confirmed": "You're subscribed. The next weekly email will land in your inbox.",
    "expired": "That confirmation link has expired. Sign up again below and we'll send a new one.",
    "error": "Something went wrong on our side. Please try again in a few minutes.",
}


def newsletter_page():
    states = "".join(f'<p class="lede" data-state="{k}" hidden><strong>{e(v)}</strong></p>' for k, v in NEWSLETTER_STATES.items())
    script = f"""<script>
(() => {{
  const show = s => {{
    document.querySelectorAll("[data-state]").forEach(p => p.hidden = p.dataset.state !== s);
    const form = document.querySelector(".signup");
    if (form) form.style.display = ["check", "confirming", "confirmed"].includes(s) ? "none" : "";
  }};
  const t = new URLSearchParams(location.search).get("confirm");
  if (t) {{
    show("confirming");
    history.replaceState(null, "", location.pathname);
    fetch({json.dumps(NEWSLETTER_API + "/confirm")}, {{method: "POST", headers: {{"content-type": "application/json"}}, body: JSON.stringify({{t}})}})
      .then(r => r.json()).then(d => show(d.state === "invalid" ? "expired" : d.state)).catch(() => show("error"));
  }} else if (location.hash) show(location.hash.slice(1));
}})();
</script>"""
    body = f'''<section aria-labelledby="n-title">
<div class="eyebrow">Weekly email</div>
<h1 id="n-title">The Nintendo Critic weekly</h1>
{states}
<p class="lede">One email a week: the Switch 2 games coming out next, which ones are game-key cards, and any Switch 1 compatibility fixes. No spam, and you can unsubscribe in one click.</p>
{signup("newsletter")}
</section>{script}'''
    return page("/newsletter/", "The Nintendo Critic weekly email", "A weekly email on new Switch 2 releases, game-key cards and compatibility fixes.", body)


def newsletter_json(games):
    """This week's content for the weekly email; the newsletter repo turns it into a Resend broadcast."""
    week = (TODAY + dt.timedelta(days=7)).isoformat()
    soon = [g for g in upcoming(games) if g["Release date"] <= week]
    sections = []
    if soon:
        sections.append({"title": "Out in the next 7 days", "items": [
            {"title": g["Name"], "url": f"{SITE}/games/{g['slug']}/" if g.get("Approved") else f"{SITE}/coming-soon/",
             "note": fmt_date(g["Release date"], False) + " · " + (g.get("Cartridge") or "Not announced"),
             "image": media.img(g["cover"], "t_cover_small") if g.get("cover") else ""} for g in soon]})
    gkc = [g for g in games if g.get("Cartridge") in CART_KIND]
    sections.append({"title": "Game-key card or full cartridge?", "items": [
        {"title": f"{len(gkc)} games checked so far", "url": f"{SITE}/game-key-cards/", "note": "Search any boxed Switch 2 game before you buy."}]})
    return json.dumps({
        "site": "nintendocritic",
        "date": TODAY.isoformat(),
        "subject": f"Switch 2 this week: {len(soon)} new release{'s' if len(soon) != 1 else ''}" if soon else "Switch 2 this week",
        "intro": "Here's what's coming to Switch 2, and what's in the box.",
        "sections": sections,
    }, indent=1)


ABOUT = """<section aria-labelledby="a-title" class="prose">
<div class="eyebrow">About</div>
<h1 id="a-title">About Nintendo Critic</h1>
<p class="lede">Short version: we check {n} Switch 2 games for what's actually in the box, whether your Switch 1
games still work, and what upgrades cost, and we show our sources on every page.</p>
<div class="author" id="who">
<img src="/static/mike-johnston.jpg" width="160" height="160" alt="Mike Johnston">
<div><h2>Who runs this site</h2>
<p>Nintendo Critic is run by Mike Johnston. My day job is running the tech side of
<a href="https://www.thekitchenmagpie.com/">The Kitchen Magpie</a>, a food blog. I built this site because the
Switch 2 made buying a boxed game confusing: some cartridges hold the whole game and some are just a key to a
download, and the box doesn't always make that clear.</p>
<p>The site is independent. It isn't affiliated with Nintendo or any publisher, and nobody pays for a verdict.</p></div>
</div>
<h2>How a game gets checked</h2>
<p>For each game I look at the publisher's announcements, the Nintendo eShop and retail listings, and press coverage,
and record whether the boxed version is a full cartridge, a game-key card or a code in a box. Where that only comes
from press reports so far, the page says so until a store listing confirms it. I use AI tools to help find and read
those sources, and each game page links the sources behind it so you can check them yourself.</p>
<h2>Reviews and verdicts</h2>
<p>We don't copy review text or publish aggregate scores. The review roundup links each outlet's own review with a
one-line summary in our own words, and links to Metacritic and OpenCritic if you want the averages. Our verdict is
about whether the Switch 2 version is worth buying, especially if you already own the game on Switch 1.</p>
<h2>Where the release data comes from</h2>
<p>Release dates, publishers and the list of upcoming games come from <a href="https://www.igdb.com/">IGDB</a>
and publisher announcements, re-checked every day. Dates for smaller games can move, so treat the coming-soon list
as a guide.</p>
<h2>How we make money</h2>
<p>Buy buttons link to Amazon. If you buy through them we earn a small commission, at no extra cost to you. It
doesn't change what we say about a game.</p>
<h2>Corrections</h2>
<p>Publishers change cartridge types between regions and print runs, and patches fix compatibility problems. If you
spot something wrong, email <a href="mailto:hello@nintendocritic.com">hello@nintendocritic.com</a> with a link or a
photo of the box and we'll fix it.</p>
</section>"""

PRIVACY = """<section aria-labelledby="p-title" class="prose">
<div class="eyebrow">Last updated {date}</div>
<h1 id="p-title">Privacy policy</h1>
<p>Nintendo Critic is a free website. We don't ask you to sign up, and we only have your email address if you email
us or subscribe to the weekly email.</p>
{newsletter}<h2>Amazon links</h2>
<p>Buy buttons go to Amazon with our affiliate tag, so Amazon can tell the sale came from us. Amazon may set cookies
when you visit its site; see <a href="https://www.amazon.com/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ">Amazon's
privacy notice</a>. To send Canadian visitors to amazon.ca, your browser checks its own time zone and language
setting; that check stays on your device.</p>
<h2>Fonts, images and trailers</h2>
<p>Fonts load from Google Fonts, and game box art and screenshots load from IGDB's image servers. Both receive your
IP address when your browser fetches the files. See <a href="https://policies.google.com/privacy">Google's privacy
policy</a>. Trailers show a preview image from YouTube, and the YouTube player (which may set YouTube cookies) only
loads after you press play.</p>
<h2>Contact</h2>
<p>Questions about privacy? Email <a href="mailto:hello@nintendocritic.com">hello@nintendocritic.com</a>.</p>
</section>"""

PRIVACY_NEWSLETTER = """<h2>Weekly email</h2>
<p>If you subscribe, we store your email address with <a href="https://resend.com/legal/privacy-policy">Resend</a>,
the service that sends the email, and use it only to send the weekly email. We ask you to confirm by clicking a link
first. Every email has a one-click unsubscribe link, and we never sell or share the list.</p>
"""


def about_page(games):
    body = ABOUT.format(n=len(games)) + "<script type=\"application/ld+json\">" + json.dumps({
        "@context": "https://schema.org", "@type": "AboutPage", "url": f"{SITE}/about/",
        "mainEntity": {"@type": "Person", "name": "Mike Johnston", "image": f"{SITE}/static/mike-johnston.jpg",
                       "url": f"{SITE}/about/#who"}}) + "</script>"
    return page("/about/", "About Nintendo Critic and how we check", "Who runs Nintendo Critic, where our Switch 2 game data comes from and how we check it.", body)


def privacy_page():
    body = PRIVACY.format(date=fmt_date(TODAY.isoformat()), newsletter=PRIVACY_NEWSLETTER if NEWSLETTER_API else "")
    return page("/privacy/", "Privacy policy | Nintendo Critic", "How Nintendo Critic handles your data.", body)


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
        "about/index.html": about_page(games),
        "is-switch-2-worth-it/index.html": worth_it_page(games, compat),
        "privacy/index.html": privacy_page(),
        "404.html": not_found_page(),
    }
    if NEWSLETTER_API:
        pages["newsletter/index.html"] = newsletter_page()
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

    (out / "newsletter.json").write_text(newsletter_json(games))
    (out / "static" / "games.json").write_text(search_index(games))
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
