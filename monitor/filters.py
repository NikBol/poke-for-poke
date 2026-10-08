from __future__ import annotations

import re

# Things worth alerting on: ETBs, multi-pack bundles/boxes, and anything 30th Celebration.
WANTED = re.compile(
    r"elite trainer|\betb\b|booster bundle|bundle|build & battle|collection|ultra[- ]premium|"
    r"booster box|display|displayer|tin\b|\bbox\b",
    re.I,
)
# Accessories are skipped unless they are 30th Celebration items.
ACCESSORY = re.compile(
    r"sleeve|binder|playmat|portfolio|deck box|plush|album|figur|pin\b|mugg|t-shirt|squishmallow|polaroid|lego|pussel|puzzle|storage",
    re.I,
)
# Non-English printings are skipped by default.
NON_ENGLISH = re.compile(r"japans|kinesis|korean|koreans|japanese|chinese|\(jp\)|\(cn\)", re.I)


# Sets released before 2025 (Prismatic Evolutions, Jan 2025, is the oldest we want). The list of old sets never
# grows, so a denylist keeps new sets working without any config change.
OLD_SETS = re.compile(
    r"(?:scarlet\s*&\s*violet|\bsv)\s*:?\s*0?[1-8](?![\d.])|"
    r"sword\s*&\s*shield|\bswsh|paldea evolved|obsidian flames|paradox rift|paldean fates|temporal forces|"
    r"twilight masquerade|shrouded fable|stellar crown|surging sparks|151|crown zenith|silver tempest|lost origin|"
    r"astral radiance|brilliant stars|fusion strike|evolving skies|chilling reign|battle styles|shining fates|"
    r"celebrations: |vivid voltage|darkness ablaze|rebel clash|pok[eé]mon go\b|"
    r"terapagos|trick or trade|halloween",
    re.I,
)
# Collectibles that are not cards.
NOT_CARDS = re.compile(r"funism|mystery box|blind box|pokemon center|pok[eé]mon center|special box|palmsize|peekring|"
    r"ticket|prerelease|pre-release|acrylic|alcove|ultra pro|\bcase\b|challenge", re.I)


def wanted_title(name: str, allow_non_english: bool = False) -> bool:
    if not allow_non_english and NON_ENGLISH.search(name):
        return False
    if OLD_SETS.search(name) or NOT_CARDS.search(name):
        return False
    is_30th = "30th" in name.lower()
    if ACCESSORY.search(name) and not is_30th:
        return False
    return is_30th or bool(WANTED.search(name))
