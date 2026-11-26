"""Set 18 data and parsing hooks for the generic TFT data builder."""

import re


SET_NUMBER = 18
SET_NAME = "Enchanted Wilds"
TEAM_PLANNER_KEY = "TFTSet18"
ROSTER_FILE = "set18-roster.json"

STYLE_NAMES = {1: "bronze", 2: "silver", 3: "silver", 4: "unique",
               5: "gold", 6: "prismatic"}
TRAIT_ALIAS = {"Eldritch": "Blackthorn"}
TRAIT_CATEGORIES = {
    "Adaptor": "class", "ApexPredator": "origin", "Attuned": "origin",
    "Avatar": "origin", "Blackthorn": "origin", "Blossom": "origin",
    "BountySeeker": "origin", "Brawler": "class", "Caustic": "origin",
    "Coven": "origin", "Defender": "class", "Elderwood": "origin",
    "EmeraldAspect": "origin", "Executioner": "class", "Fae": "origin",
    "FloraFatalis": "origin", "Greenfather": "origin", "Hunter": "class",
    "Inferno": "origin", "Invoker": "class", "Juggernaut": "class",
    "Lunar": "origin", "Monolith": "origin", "OldGrowth": "origin",
    "Primal": "origin", "Rapidfire": "class", "Ravager": "class",
    "Riftbeast": "origin", "Rival": "origin", "Solar": "origin",
    "Spellweaver": "class", "Sprykin": "origin", "Summoner": "class",
    "Thornmaiden": "origin", "Vanguard": "class",
}
TRAIT_TEAM_SIZE = {"Riftbeast": [{"min": 10, "slots": 2}]}
PATCH_TRAIT_TIERS = {
    "Coven": {2: "3 per kill, 30 per loss", 3: "10 per kill, 80 per loss"},
}
ICON_OVERRIDE = {
    "TFT18_Pebbles": "game/assets/characters/tft18_sentry/tft18_sentry_square.png",
    "TFT18_AncientSentinel": "game/assets/characters/tft18_sentinel/tft18_sentinel_square.png",
}
TRAIT_ICON_OVERRIDE = {
    "Invoker": "game/assets/ux/traiticons/trait_icon_16_invoker.png",
}
LUX_ART = {
    "Blossom": "blossom", "Coven": "coven", "Elderwood": "elderwood",
    "Eldritch": "blackthorn", "Fae": "fae", "Inferno": "inferno",
    "Lunar": "moonbeam", "Primal": "primal", "Solar": "sunbeam",
}
LUX_BIN = dict(LUX_ART)
for _origin, _art in LUX_ART.items():
    ICON_OVERRIDE[f"TFT18_Lux{_origin}"] = (
        f"game/assets/characters/tft18_lux/tft18_lux_{_art}_square.png")
ABILITY_NAME_OVERRIDES = {
    "Raptor": "Flock Family",
    **{f"Lux{origin}": "Final Spark" for origin in LUX_ART},
}
BIN_OVERRIDE = {
    "Pebbles": "da_18_sentry", "AncientSentinel": "da_sentinel18",
    "KogMaw": "da_kogmaw18_ad", "Raptor": "da_crimsonraptor18",
    "Gnar": "da_18_gnarbig", "Krug": "da_krug18",
    "Akali": "da_18_akali_ad",
}
LOLCHESS_FALLBACK_KEYS = {"Raptor": "CrimsonRaptorMini"}
LOLCHESS_URL = "https://lolchess.gg/champions/set18/yorick?hl=en-US"
METADATA = {
    "set": "set18",
    "setName": SET_NAME,
    "teamPlannerSet": TEAM_PLANNER_KEY,
    "gameBuild": "PBE TFTSet18",
    "source": ("checked-in reveal roster + CommunityDragon PBE TFTSet18 "
               "+ Riot team planner + LoLChess + checked-in Blitz trait taxonomy "
               "+ checked-in MetaTFT ability names"),
    "note": "PBE data — breakpoints are live-PBE and may shift before 18.1 launch (2026-08-12).",
    "abilityNote": ("Ability numbers and structured stat lines sourced from "
                    "LoLChess championRefs en/set18 on {date}; bin-derived ability "
                    "name and token-placeholder desc are retained."),
}


def bin_candidates(name):
    """Set 18 bin aliases that supplement the engine's number-derived patterns."""
    out = [BIN_OVERRIDE[name]] if name in BIN_OVERRIDE else []
    if name == "Gnar":
        out.append("da_18_gnarsmall")
    if name.startswith("Lux") and name != "Lux":
        art = LUX_BIN.get(name[3:], name[3:].lower())
        out.extend((f"da_18_lux_{art}", f"da_lux18_{art}"))
    return out


def lolchess_candidates(name):
    if name.startswith("Lux") and name != "Lux":
        return [f"tft18_lux_{LUX_BIN.get(name[3:], name[3:].lower())}",
                f"tft18_lux_{name[3:].lower()}"]
    return []


def team_planner_candidates(name):
    return ["da_lux18_base"] if name.startswith("Lux") else []


def special_solar(trait, rows, effects, state, helpers):
    if len(rows) != 1 or not effects:
        return
    re_module, clean, render_row = helpers["re"], helpers["clean"], helpers["render_row"]
    parts = [clean(part) for part in re_module.split(
        r"<br\s*/?>", render_row(rows[0], effects[0]), flags=re_module.I)]
    parts = [part for part in parts if part]
    parsed = []
    for part in parts[1:]:
        match = re.match(r"^(\d+)\s*:\s*(.*)$", part)
        if match:
            parsed.append({"count": int(match.group(1)), "desc": match.group(2)})
    if [upgrade["count"] for upgrade in parsed] == [1, 3, 5, 8]:
        state["tiers"] = [re.sub(r"^\s*\(\d+\)\s*", "", parts[0])]
        state["upgrades"] = parsed


def special_primal(trait, rows, effects, state, helpers):
    state["tiers"] = ["Choose a blessing.", "Choose a second blessing."]


def special_summoner(trait, rows, effects, state, helpers):
    if not effects:
        return
    re_module, clean, render_row = helpers["re"], helpers["clean"], helpers["render_row"]
    prefix = re_module.split(r"<row>", trait.get("desc") or "", maxsplit=1)[0]
    parts = [clean(part) for part in re_module.split(
        r"<br\s*/?>", render_row(prefix, effects[0]), flags=re_module.I)]
    parts = [part for part in parts if part]
    if len(parts) == 5:
        state["lead"], state["details"] = parts[0], parts[1:]


def special_adaptor(trait, rows, effects, state, helpers):
    re_module = helpers["re"]
    stat_choice = "%i:scaleAD% or %i:scaleAP%"
    state["tiers"] = [re.sub(r"\bOR\b", stat_choice, tier) for tier in state["tiers"]]
    state["desc"] = re.sub(r"\bOR\b", stat_choice, state["desc"])


def special_defender(trait, rows, effects, state, helpers):
    resist_icons = "%i:scaleArmor%%i:scaleMR%"
    state["tiers"] = [f"{tier} {resist_icons}" for tier in state["tiers"]]
    state["desc"] = state["desc"].replace(
        "@DefenderDefenseGain@", f"@DefenderDefenseGain@ {resist_icons}")


SPECIAL_TRAIT_HOOKS = {
    "Solar": special_solar,
    "Primal": special_primal,
    "Summoner": special_summoner,
    "Adaptor": special_adaptor,
    "Defender": special_defender,
}


def champion_display_name(name):
    if name.startswith("Lux") and name != "Lux":
        return f"Lux ({name[3:]})"
    return name


def shared_ability_bin(name):
    return f"da_lux{SET_NUMBER}_base" if name.startswith("Lux") and name != "Lux" else None


def ability_sections(description):
    """Preserve LoLChess's ordered shared, AD, and AP Adaptor paragraphs."""
    sections = []
    for part in re.split(r"(?:\s*<br\s*/?>\s*){2,}", description or "", flags=re.I):
        match = re.match(
            r"^\s*Adaptor\s*\(\s*%i:scale(AD|AP)%\s*\)\s*:\s*(.*)$",
            part, re.I | re.S)
        body = match.group(2) if match else part
        desc = _clean_lolchess(body, keep_icons=True)
        if not desc:
            continue
        section = {"desc": desc}
        if match:
            section["mode"] = match.group(1).upper()
        sections.append(section)
    modes = {section["mode"] for section in sections if section.get("mode")}
    return sections if modes == {"AD", "AP"} else []


def _clean_lolchess(text, keep_icons=False):
    import html
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    if not keep_icons:
        text = re.sub(r"%i:\w+%", "", text, flags=re.I)
        text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def validate_special(traits, champions):
    errors = []
    adaptor_mode_failures = [
        champion["key"] for champion in champions if "Adaptor" in champion["traits"]
        and {section["mode"] for section in
             (champion.get("ability") or {}).get("sections", [])
             if section.get("mode")} != {"AD", "AP"}
    ]
    if adaptor_mode_failures:
        errors.append(f"Adaptor ability modes missing: {adaptor_mode_failures}")
    solar_upgrades = (traits.get("Solar") or {}).get("upgrades", [])
    if [upgrade.get("count") for upgrade in solar_upgrades] != [1, 3, 5, 8]:
        errors.append("Solar three-star upgrades are missing or malformed")
    if (traits.get("Primal") or {}).get("tiers") != [
            "Choose a blessing.", "Choose a second blessing."]:
        errors.append("Primal tier descriptions are missing")
    if len((traits.get("Summoner") or {}).get("details", [])) != 4:
        errors.append("Summoner unit details are missing")
    return errors
