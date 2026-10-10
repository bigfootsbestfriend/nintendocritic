# Handoff: where Nintendo Critic stands

Last updated 2026-10-10. To pick this up in a new Claude Code session, open this repo and say:
**"Read HANDOFF.md and carry on with the next step."**

## What the site is

An independent Switch 2 buyer's guide at nintendocritic.com. For each game it covers:
- full cartridge vs game-key card
- Switch 1 → 2 compatibility
- upgrade paths and cost
- performance
- a review roundup (links plus our own one-line summaries, never copied text or aggregator scores)
- a short verdict, and an optional "We played it" note written by a person

Revenue comes from Amazon affiliate links: amazon.com tag `magpie014-20`, amazon.ca tag `thekitmag-20`.
Canadian visitors are detected in the browser by time zone or language.
Footer carries a "Not affiliated with Nintendo" line and the Amazon disclosure.

Keyword research (Semrush, US) drove the focus:
- backwards compatibility: ~15k searches/month
- game-key cards: ~12k/month, low difficulty
- "is switch 2 worth it": ~20k/month
- avoided: deals (DekuDeals owns it) and score aggregation (low demand)

## Done

- **Brand:** cartridge logo in `brand/`. Palette is grape `#4a23b5`, marigold `#ffb627` and ink `#1d1433`. Fonts are Bricolage Grotesque, Atkinson Hyperlegible and JetBrains Mono.
- **Mockup:** `mockup/index.html`, approved design with five views: game page, game-key cards, compatibility, upgrades, coming soon.
- **Airtable base "Nintendo Critic"** (`appSsH1VGhRnPpTc3`), in the non-Kitchen-Magpie workspace. Tables:
  - Games (~518 rows; Status, Approved checkbox, Cartridge + confidence, upgrade fields, Sources)
  - Compatibility (12)
  - Reviews (1)
  - Change log
- **Nightly IGDB sync:** `collector/igdb_sync.py` runs via `.github/workflows/nightly.yml` at 09:17 UTC.
  - Adds new Switch 2 games as Draft rows and logs release-date changes.
  - Filters eShop filler using `collector/quality.py`; add real games IGDB misses to its `ALWAYS` set.
  - Full backfill since launch already done: `--days-back 500 --prune`.
- **GitHub secrets set:** `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET`, `AIRTABLE_TOKEN`.

## Site generator (built 2026-10-10)

- `generator/build.py` reads Airtable and writes `public/` (gitignored). `.github/workflows/pages.yml` runs it on push and daily at 09:47 UTC.
- Pages: home, /game-key-cards/, /compatibility/, /upgrades/, /coming-soon/, and /games/<slug>/ for **Approved** games only.
- `python3 generator/build.py --preview --out /some/dir` also builds pages for "Needs review" games so you can check them locally.
- **Whole site is noindex** until `LAUNCHED = True` in build.py. Flip it once the data is reviewed and a few games are approved.
- Signup boxes appear once `KIT_FORM_URL` is set.
- Optional Games fields the page uses if present: `We played it`, `Download size GB`, plus `Score` on Reviews.

## Added 2026-10-10 (reviews/upgrades/guide decision)

Mike decided: no standalone reviews. Instead:
- **Game pages:** the verdict and a "Played on Switch 2 · Mike Johnston" note (Games fields `We played it`, optional `Played date`)
  sit under "Is X worth it on Switch 2?". Performance sits under "How does X run on Switch 2?". FAQPage schema is built from
  the visible answers. These match the searches people make (Semrush: per-game "worth it / how does it run" long tail;
  the game's main search, e.g. "cyberpunk 2077 switch 2", is 8.1k a month).
- **/upgrades/:** built from `data/upgrades.json` (69 paid, 60 free, Nintendo's 15 free Switch 1 updates, upcoming).
  Prices come from Nintendo Everything (Oct 3, 2026), cross-checked with Nintendo Life. Update the file when new packs
  are announced and bump `checked`.
- **Review feeds:** `collector/reviews_sync.py`, run nightly, adds Switch 2 reviews from Nintendo Life, Nintendo
  Everything and Nintendo World Report to the Reviews table. It stores outlet, headline and link only; `Summary` is written
  later in our own words. It logs reviews for games missing from the Games table: Kingdom Hearts, The Witcher 3, Diablo IV,
  MGS Master Collection Vol. 2 and others were missing on 2026-10-10.
- **/is-switch-2-worth-it/:** sourced facts (US price $499.99 since Sep 1, 2026; Nintendo specs), live counts and an FAQ.
  Mike's first-hand parts come from `content/worth-it.json` (short_answer, my_experience, worth_it_if, wait_if); empty
  fields are left off the page.

## Waiting on Mike

1. **A second, free Kit account** just for Nintendo Critic, separate from the Kitchen Magpie account so it doesn't inflate those numbers.
   - Sign up with e.g. `hello@nintendocritic.com`, set up through Namecheap's free email forwarding.
   - Create an API key and add it as the `KIT_API_KEY` repo secret.
   - The claude.ai Kit connector is the **Magpie** account. Don't use it for this.
2. **Namecheap DNS**, done in one sitting once the site exists: GitHub Pages records plus Kit's sending-domain records.

## Next steps, in order

1. **Nintendo checks:**
   - the compatibility list (status changes go to the Change log)
   - store listings: the game-key card badge → Cartridge confidence "Store badge", plus download size
2. **Review feeds:** RSS from Nintendo Life, Nintendo World Report and Nintendo Everything → the Reviews table (link and score only, summaries written in our own words).
4. **Scheduled Claude Code task** (runs on the Max plan, no API key): drafts verdicts and review summaries, and the weekly email draft in the new Kit account. Mike presses Send.

## Running locally

Create `.env` in the repo root. It's gitignored, so never commit it.

```
IGDB_CLIENT_ID=...
IGDB_CLIENT_SECRET=...
AIRTABLE_TOKEN=...
```

The values are in the Twitch dev console (dev.twitch.tv), Airtable (airtable.com/create/tokens) and the original machine's `~/Work/nintendocritic/.env`.
GitHub secrets can't be read back, so copy that file across or make new keys.

Then:
- `python3 collector/igdb_sync.py --dry-run`: preview only
- the same command without `--dry-run`: writes to Airtable

## Gotchas

- **The repo is public.** Git here uses the GitHub no-reply email:
  `git config user.email "209829115+bigfootsbestfriend@users.noreply.github.com"`
- **The Airtable token lacks `schema.bases:read`,** so metadata API calls fail. Record reads and writes work.
- **IGDB dates:**
  - Only `date_format` 0 is an exact day; vague dates go in "Release date note".
  - North American or worldwide dates are preferred.
  - Always page with `sort id asc`.
- **Airtable free plan caps a base at 1,000 rows.** ~518 are used, growing about 30 a month.
