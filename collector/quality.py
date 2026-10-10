"""Decide whether an IGDB game is worth a page, i.e. not typical eShop filler.

A game passes if it has real attention (critic reviews, player ratings or pre-release hype)
or comes from an established publisher, and isn't one of the known filler series.
"""
import re

# Established publishers. Ports and remasters often have no ratings of their own on IGDB
# (ratings sit on the original), so publisher is the main signal for those.
PUBLISHERS = [
    "nintendo", "the pokemon company", "square enix", "sega", "atlus", "capcom", "konami", "bandai namco",
    "koei tecmo", "electronic arts", "ubisoft", "activision", "2k", "xbox game studios", "microsoft",
    "bethesda", "sony interactive", "warner bros", "level-5", "marvelous", "xseed", "nis america",
    "spike chunsoft", "nihon falcom", "aksys", "idea factory", "kadokawa", "arc system works", "snk",
    "annapurna", "devolver", "team17", "raw fury", "humble games", "focus entertainment", "nacon",
    "thq nordic", "plaion", "deep silver", "koch media", "atari", "digital eclipse", "limited run",
    "cd projekt", "mojang", "pqube", "outright games", "gameloft", "playstack", "fireshine", "kepler",
    "annapurna", "private division", "take-two", "rockstar", "epic games", "riot", "supergiant",
    "chucklefish", "finji", "dotemu", "aniplex", "furyu", "d3 publisher", "mages", "natsume",
    "inti creates", "wayforward", "nighthawk", "yacht club", "landfall", "tinybuild", "hooded horse",
    "paradox", "frontier", "sumo", "kalypso", "merge games", "modus", "maximum entertainment", "bandai",
    "cygames", "nexon", "netease", "krafton", "shift up", "game freak", "intelligent systems", "hal laboratory",
    "retro studios", "monolith soft", "creatures inc", "grasshopper", "platinumgames", "fromsoftware",
    "milestone", "giants software", "shin'en", "klei", "jupiter", "aquaplus", "sanrio", "5pb", "mages.",
    "gust", "koei", "genius sonority", "nippon ichi", "rising star", "red art", "dmm games", "kemco",
    "acquire", "success corp", "sunsoft", "jaleco", "taito", "irem", "city connection", "clear river",
    "bushiroad", "compile heart", "experience inc", "nis ", "zerodiv", "ziggurat",
    "gamemill", "mindscape", "bigben", "ravenscourt", "wired productions", "curve", "secret mode",
    "no more robots", "annapurna", "akupara", "dangen", "serenity forge", "joystick ventures",
]

# Re-release series and filler that should never get a page.
FILLER = re.compile(
    r"^(arcade archives|console archives|aca neogeo|egg console|g-mode archives|pixel game maker)"
    r"|bonus content|soundtrack|\bdemo\b|\btrial\b",
    re.I)


# Real games IGDB has too little data on to pass the checks below. Add to this as needed.
ALWAYS = {
    "the touryst: deluxe", "shenmue iii enhanced", "suika game planet", "culdcept begins",
    "lollipop chainsaw repop: nintendo switch 2 edition", "hello kitty: party land",
    "the lord of the rings: war in the north - legacy edition", "picross s climax",
}


def is_worth_a_page(game):
    name = game.get("name", "")
    if name.lower() in ALWAYS:
        return True
    if FILLER.search(name):
        return False
    if game.get("aggregated_rating_count", 0) >= 1:   # at least one critic review
        return True
    if game.get("total_rating_count", 0) >= 5:        # some player ratings
        return True
    if game.get("hypes", 0) >= 5:                     # people following it before release
        return True
    # Check developers too: IGDB often lists a port's developer but not its publisher.
    companies = " | ".join(c["company"]["name"].lower().replace("\u2019", "'") for c in game.get("involved_companies", []))
    return any(p in companies for p in PUBLISHERS)


# Extra IGDB fields the check needs, appended to game.* queries.
FIELDS = "game.aggregated_rating_count,game.total_rating_count,game.hypes"
