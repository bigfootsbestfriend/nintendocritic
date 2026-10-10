# Nintendo Critic

Source for [nintendocritic.com](https://nintendocritic.com): an independent Switch 2 buyer's guide.
For each game it answers whether the box has a full cartridge or a game-key card, whether a
Switch 1 game works on Switch 2, what upgrades cost, and what the reviews say.

Not affiliated with, endorsed or sponsored by Nintendo.

## Layout

- `brand/`: logo files (cartridge mark SVG/PNG, light and dark lockups)
- `mockup/`: the approved design mockup (single HTML file)

## Planned

- Data lives in Airtable. Nightly GitHub Actions collect from IGDB, Nintendo's
  compatibility list and store listings, and outlet RSS feeds.
- A scheduled Claude Code task drafts page text and review summaries. New pages go
  live only after someone ticks **Approved** in Airtable.
- The static site is built from that data and served on GitHub Pages.

Secrets (IGDB, Airtable) are stored as GitHub Actions secrets, never in this repo.
