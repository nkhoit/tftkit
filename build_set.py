#!/usr/bin/env python3
"""Build TFT set data.json for the TFT Trait Explorer.

This stitches:
  - set-specific champion roster (cost + traits)
  - CommunityDragon trait breakpoints + display names
  - CommunityDragon champion stats, abilities, and icons

Usage: python3 build_set.py --set N [--out web/traits/data.json]
"""
import argparse, json, os, re, sys, urllib.request, urllib.error, datetime, hashlib, concurrent.futures, html, tempfile
import subprocess
import xxhash

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "web", "traits", "data.json")
UA = {"User-Agent": "Mozilla/5.0 (kuro-tft-perfect)"}
PBE = "https://raw.communitydragon.org/pbe"
CD_TFT = PBE + "/cdragon/tft/en_us.json"
CD_FILES = PBE + "/cdragon/files.exported.txt"
TEAM_PLANNER = PBE + "/plugins/rcp-be-lol-game-data/global/default/v1/tftchampions-teamplanner.json"
ASSET = PBE + "/"
STRINGTABLE = PBE + "/game/en_us/data/menu/en_us/tft.stringtable.json"
BUILD_CACHE = os.path.join(tempfile.gettempdir(), "tft-trait-explorer")
STRINGTABLE_CACHE = os.path.join(BUILD_CACHE, "tft-pbe-en_us.stringtable.json")
LOLCHESS_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/131.0 Safari/537.36"}


def load_set_config(set_number):
    """Load sets/setN.py and return its values via a stable interface."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    path = os.path.join(HERE, "sets", f"set{set_number}.py")
    if not os.path.isfile(path):
        raise ValueError(f"no configuration found for set {set_number}: {path}")
    spec = importlib.util.spec_from_file_location(f"tftkit_set_{set_number}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.SET_NUMBER != set_number:
        raise ValueError(f"configuration {path} declares Set {module.SET_NUMBER}")
    required = ("SET_NAME", "TEAM_PLANNER_KEY", "ROSTER_FILE", "STYLE_NAMES",
                "TRAIT_ALIAS", "TRAIT_CATEGORIES", "TRAIT_TEAM_SIZE", "PATCH_TRAIT_TIERS",
                "ICON_OVERRIDE", "TRAIT_ICON_OVERRIDE", "LUX_ART", "LUX_BIN",
                "ABILITY_NAME_OVERRIDES", "BIN_OVERRIDE", "LOLCHESS_URL", "METADATA",
                "SPECIAL_TRAIT_HOOKS", "ability_sections", "validate_special",
                "bin_candidates", "lolchess_candidates", "team_planner_candidates",
                "champion_display_name", "shared_ability_bin")
    missing = [key for key in required if not hasattr(module, key)]
    if missing:
        raise ValueError(f"configuration {path} missing: {', '.join(missing)}")
    def candidates(name):
        result = list(module.bin_candidates(name))
        stem, number = name.lower(), set_number
        result.extend((f"da_{number}_{stem}", f"tft{number}_{stem}",
                       f"da_{number}_{stem}_ad", f"da_{stem}{number}",
                       f"da_{stem}{number}_ad", f"da_{stem}{number}_ap"))
        return result
    return SimpleNamespace(
        set_number=set_number, set_key=str(set_number), set_name=module.SET_NAME,
        team_planner_key=module.TEAM_PLANNER_KEY,
        roster_file=Path(HERE) / module.ROSTER_FILE,
        style_names=module.STYLE_NAMES, trait_aliases=module.TRAIT_ALIAS,
        trait_categories=module.TRAIT_CATEGORIES, trait_team_size=module.TRAIT_TEAM_SIZE,
        patch_trait_tiers=module.PATCH_TRAIT_TIERS, icon_overrides=module.ICON_OVERRIDE,
        trait_icon_overrides=module.TRAIT_ICON_OVERRIDE, lux_art=module.LUX_ART,
        lux_bin=module.LUX_BIN, ability_name_overrides=module.ABILITY_NAME_OVERRIDES,
        bin_overrides=module.BIN_OVERRIDE, lolchess_url=module.LOLCHESS_URL,
        lolchess_cache=os.path.join(BUILD_CACHE, f"lolchess-set{set_number}-champions.html"),
        metadata=module.METADATA, special_trait_hooks=module.SPECIAL_TRAIT_HOOKS,
        ability_sections=module.ability_sections, validate_special=module.validate_special,
        bin_candidates=candidates, lolchess_candidates=module.lolchess_candidates,
        team_planner_candidates=module.team_planner_candidates,
        champion_display_name=module.champion_display_name,
        shared_ability_bin=module.shared_ability_bin,
        lolchess_fallback_keys=getattr(module, "LOLCHESS_FALLBACK_KEYS", {}))


CONFIG = None
STYLE_NAMES = TRAIT_ALIAS = TRAIT_CATEGORIES = TRAIT_TEAM_SIZE = None
PATCH_TRAIT_TIERS = ICON_OVERRIDE = TRAIT_ICON_OVERRIDE = None
LUX_ART = LUX_BIN = ABILITY_NAME_OVERRIDES = BIN_OVERRIDE = None
REVEAL = LOLCHESS = LOLCHESS_CACHE = None
SPECIAL_TRAIT_HOOKS = None
UNIT_ROLES = {
    f"{damage}{role}"
    for damage in ("AD", "AP", "Hybrid")
    for role in ("Carry", "Caster", "Fighter", "Reaper", "Specialist", "Tank")
}


def configure(config):
    """Bind active per-set data after loading its config module."""
    global CONFIG, STYLE_NAMES, TRAIT_ALIAS, TRAIT_CATEGORIES, TRAIT_TEAM_SIZE
    global PATCH_TRAIT_TIERS, ICON_OVERRIDE, TRAIT_ICON_OVERRIDE, LUX_ART, LUX_BIN
    global ABILITY_NAME_OVERRIDES, BIN_OVERRIDE, REVEAL, LOLCHESS, LOLCHESS_CACHE
    global SPECIAL_TRAIT_HOOKS
    CONFIG = config
    STYLE_NAMES = config.style_names
    TRAIT_ALIAS = config.trait_aliases
    TRAIT_CATEGORIES = config.trait_categories
    TRAIT_TEAM_SIZE = config.trait_team_size
    PATCH_TRAIT_TIERS = config.patch_trait_tiers
    ICON_OVERRIDE = config.icon_overrides
    TRAIT_ICON_OVERRIDE = config.trait_icon_overrides
    LUX_ART = config.lux_art
    LUX_BIN = config.lux_bin
    ABILITY_NAME_OVERRIDES = config.ability_name_overrides
    BIN_OVERRIDE = config.bin_overrides
    REVEAL = str(config.roster_file)
    LOLCHESS = config.lolchess_url
    LOLCHESS_CACHE = config.lolchess_cache
    SPECIAL_TRAIT_HOOKS = config.special_trait_hooks


def get(url, raw=False, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return b if raw else json.loads(b)


def fnv1a(s):
    """Riot hashes most variable names in PBE data: `variables` keys arrive as
    "{a9a813e7}" instead of "BonusDamagePercentBase". It's FNV-1a 32-bit over
    the lowercased name, so the numbers were never missing -- just locked."""
    h = 0x811c9dc5
    for c in s.encode():
        h ^= c
        h = (h * 0x01000193) & 0xffffffff
    return h


def fmt_num(v):
    if isinstance(v, float):
        r = round(v, 4)
        return str(int(r)) if abs(r - int(r)) < 1e-6 else str(round(r, 2))
    return str(v)


def render_row(text, eff):
    """Substitute @Var@ / @Var*100@ / @MinUnits@ using this effect's variables.
    Unknown tokens stay as-is so the UI can render its own "?" marker; we never
    invent a number."""
    vals = {k.lower(): v for k, v in (eff.get("variables") or {}).items()}

    def sub(m):
        expr = m.group(1)
        mm = re.fullmatch(r"([A-Za-z0-9_]+)(?:\*(\d+(?:\.\d+)?))?", expr)
        if not mm:
            return m.group(0)
        key = mm.group(1).lower()
        if key == "minunits":
            return str(eff.get("minUnits"))
        val = vals.get(key)
        if val is None:
            val = vals.get("{%08x}" % fnv1a(key))
        if val is None:
            return m.group(0)
        if isinstance(val, list):
            val = val[0] if val else None
            if val is None:
                return m.group(0)
        if mm.group(2):
            val = val * float(mm.group(2))
        return fmt_num(val)

    return re.sub(r"@([^@]+)@", sub, text)


def clean(s):
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_lolchess(s, keep_icons=False, keep_breaks=False):
    s = html.unescape(s or "")
    if keep_breaks:
        s = re.sub(r"(?:\s*<br\s*/?>\s*){2,}", "\n\n", s, flags=re.I)
        s = re.sub(r"\s*<br\s*/?>\s*", "\n", s, flags=re.I)
    else:
        s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    if not keep_icons:
        s = re.sub(r"%i:\w+%", "", s, flags=re.I)
        # Icons often sit inside parens ("320(%i:scaleAD%)"); stripping the
        # icon alone would leave bare "()" litter in player-facing text.
        s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    if keep_breaks:
        s = re.sub(r"[^\S\n]+", " ", s)
        s = re.sub(r" *\n *", "\n", s)
        return re.sub(r"\n{3,}", "\n\n", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def lolchess_champions():
    """Load one cached Next.js payload; fetched HTML is parsed only as data."""
    if not os.path.exists(LOLCHESS_CACHE):
        os.makedirs(os.path.dirname(LOLCHESS_CACHE), exist_ok=True)
        req = urllib.request.Request(LOLCHESS, headers=LOLCHESS_UA)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            retry = e.headers.get("Retry-After")
            if e.code == 429:
                raise RuntimeError("LoLChess rate limited the single request"
                                   + (f" (Retry-After: {retry})" if retry else "")) from e
            raise
        tmp = LOLCHESS_CACHE + ".tmp"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, LOLCHESS_CACHE)

    raw = open(LOLCHESS_CACHE, encoding="utf-8").read()
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                      raw, re.S | re.I)
    if not match:
        raise RuntimeError("LoLChess __NEXT_DATA__ payload not found")
    queries = (json.loads(match.group(1))["props"]["pageProps"]
               ["dehydratedState"]["queries"])
    for query in queries:
        key = query.get("queryKey") or []
        if "championRefs" in key and "en" in key:
            data = query.get("state", {}).get("data", {})
            return data.get("champions") or []
    raise RuntimeError("LoLChess English championRefs query not found")


def rst_hash(key):
    """PBE uses RST v5: lowercase XXH3-64, retaining the low 38 bits."""
    return "{%010x}" % (xxhash.xxh3_64_intdigest(key.lower()) & ((1 << 38) - 1))


def stringtable():
    # This file is ~25MB. Cache it outside the repo so repeated builds do not
    # punish CommunityDragon (or us) with another download.
    if not os.path.exists(STRINGTABLE_CACHE):
        os.makedirs(os.path.dirname(STRINGTABLE_CACHE), exist_ok=True)
        req = urllib.request.Request(STRINGTABLE, headers=UA)
        tmp = STRINGTABLE_CACHE + ".tmp"
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
            f.write(r.read())
        os.replace(tmp, STRINGTABLE_CACHE)
    with open(STRINGTABLE_CACHE, encoding="utf-8") as f:
        return json.load(f)["entries"]


def ability_from(doc, strings):
    """Find the castable SpellObject, then resolve its generated RST keys."""
    spells = []
    for v in (doc or {}).values():
        if not isinstance(v, dict) or v.get("__type") != "SpellObject":
            continue
        script = v.get("mScriptName") or ""
        spell = v.get("mSpell") or {}
        tip = ((spell.get("mClientData") or {}).get("mTooltipData") or {})
        if tip and script.lower().endswith("spell"):
            spells.append((script, spell))
    if not spells:
        return None

    # Missile/helper SpellObjects can also have tooltip metadata. The player
    # ability is the shortest script ending in exactly "Spell".
    script, spell = min(spells, key=lambda x: len(x[0]))
    base = "generatedtip_spelltft_" + script.lower()
    name = strings.get(rst_hash(base + "_displayname"))
    raw = strings.get(rst_hash(base + "_tooltip"))
    if not name or not raw:
        return None

    m = re.search(r"<mainText>(.*?)</mainText>", raw, re.S | re.I)
    text = m.group(1) if m else raw
    values = {v.get("name", "").lower(): (v.get("values") or [])[1:4]
              for v in spell.get("DataValues") or []}

    def sub(match):
        token = match.group(1)
        mm = re.fullmatch(r"([A-Za-z0-9_]+)(?:\*(\d+(?:\.\d+)?))?", token)
        if not mm:
            return match.group(0)
        vals = values.get(mm.group(1).lower())
        if vals and len(vals) == 3:
            mult = float(mm.group(2) or 1)
            return "/".join(fmt_num(v * mult) for v in vals)
        # Runtime-only values are intentionally left visible; app.js renders
        # them as a '?' rather than inventing live PBE balance numbers.
        if token == "SpellModifierDescriptionAppend":
            return ""
        return match.group(0)

    text = re.sub(r"@([^@]+)@", sub, text)
    text = re.sub(r"%i:[^%]+%", "", text)
    # Stringtable JSON sometimes preserves Riot's literal "\\n" markup.
    text = text.replace("\\r", " ").replace("\\n", " ")
    text = html.unescape(text)
    return {"name": clean(name), "desc": clean(text)}


# Champion stats live in raw character bins, not in cdragon/tft/en_us.json.
def bin_candidates(name):
    """Return configured aliases and generic stems derived from the set number."""
    return CONFIG.bin_candidates(name)

def join_lolchess(names, refs):
    """Join Riot bin stems, then use an optional config-provided key fallback."""
    by_ingame = {(c.get("ingameKey") or "").lower(): c for c in refs
                 if c.get("ingameKey")}
    by_key = {c.get("key"): c for c in refs}
    joined, failures = {}, {}
    for name in names:
        candidates = bin_candidates(name)
        candidates.extend(CONFIG.lolchess_candidates(name))
        ref = next((by_ingame.get(stem.lower()) for stem in candidates
                    if by_ingame.get(stem.lower())), None)
        if not ref and name in CONFIG.lolchess_fallback_keys:
            ref = by_key.get(CONFIG.lolchess_fallback_keys[name])
        if ref:
            joined[name] = ref
        else:
            failures[name] = "no LoLChess ingameKey matched bin candidates"
    return joined, failures


def join_team_planner(names, refs):
    """Join Riot's stable 12-bit planner IDs through the internal character name."""
    by_character = {(c.get("character_id") or "").lower(): c for c in refs
                    if c.get("character_id")}
    joined, failures = {}, {}
    for name in names:
        candidates = bin_candidates(name)
        candidates.extend(CONFIG.team_planner_candidates(name))
        ref = next((by_character.get(stem.lower()) for stem in candidates
                    if by_character.get(stem.lower())), None)
        code = (ref or {}).get("team_planner_code")
        if isinstance(code, int) and 0 < code <= 0xfff:
            joined[name] = code
        else:
            failures[name] = "no valid team_planner_code matched bin candidates"
    return joined, failures


def char_record(doc):
    for v in (doc or {}).values():
        if isinstance(v, dict) and v.get("__type") == "TFTCharacterRecord":
            return v
    return None


def stats_from(rec):
    """Pull the handful of numbers a player actually reads off a unit card."""
    def mod(key):
        v = rec.get(key + "Modifiable")
        if isinstance(v, dict):
            return v.get("baseValue")
        return v if isinstance(v, (int, float)) else None

    def plain(key):
        v = rec.get(key)
        if isinstance(v, dict):          # baseMR arrives as a ModifiableFloat
            return v.get("baseValue")
        return v if isinstance(v, (int, float)) else None

    out = {
        "hp": mod("baseHP"),
        "ad": mod("baseDamage"),
        "armor": mod("baseArmor"),
        "mr": plain("baseMR"),
        "as": mod("attackSpeed"),
        "range": mod("attackRange"),
        "crit": plain("baseCritChance"),
    }
    # Attack range is in game units; 180 = melee, one hex is ~180.
    if out["range"]:
        out["hexRange"] = round(out["range"] / 180.0)
    return {k: v for k, v in out.items() if v is not None}


def fetch_champion_data(names, strings):
    """Resolve every champion bin once. Returns {name: {stats, ability}}."""
    import concurrent.futures

    def one(name):
        stats = ability = None
        for stem in bin_candidates(name):
            url = f"{PBE}/game/characters/{stem}.cdtb.bin.json"
            try:
                doc = get(url, timeout=120)
                rec = char_record(doc)
            except Exception:
                continue
            if rec and not stats:
                stats = stats_from(rec)
            candidate = ability_from(doc, strings)
            if candidate and (not ability or ability["name"] == "Placeholder Name"):
                ability = candidate
            if stats and ability and ability["name"] != "Placeholder Name":
                break
        if not ability:
            shared_bin = CONFIG.shared_ability_bin(name)
            if shared_bin:
                try:
                    doc = get(f"{PBE}/game/characters/{shared_bin}.cdtb.bin.json", timeout=120)
                    ability = ability_from(doc, strings)
                except Exception:
                    pass
        if ability and name in ABILITY_NAME_OVERRIDES:
            ability["name"] = ABILITY_NAME_OVERRIDES[name]
        return name, {"stats": stats, "ability": ability}

    out = {}
    with concurrent.futures.ThreadPoolExecutor(10) as ex:
        for name, data in ex.map(one, names):
            out[name] = data
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", type=int, required=True, help="TFT set number")
    ap.add_argument("--out", default=None, help="output data.json path")
    args = ap.parse_args(argv)
    configure(load_set_config(args.set))
    out_arg = args.out or OUT
    os.makedirs(BUILD_CACHE, exist_ok=True)

    print(f"loading Set {CONFIG.set_number} reveal roster ...")
    with open(REVEAL, encoding="utf-8") as f:
        reveal = json.load(f)

    print(f"fetching CommunityDragon PBE ({CONFIG.team_planner_key}) ...")
    cd = get(CD_TFT)
    set_data = cd["sets"][CONFIG.set_key]

    print("fetching exported-file manifest (~58MB, verifies icon paths) ...")
    files = set(get(CD_FILES, raw=True).decode("utf-8", "replace").split("\n"))
    print("fetching Riot team-planner champion IDs ...")
    planner_refs = get(TEAM_PLANNER).get(CONFIG.team_planner_key) or []

    # ---- traits: real breakpoints from PBE -----------------------------
    traits = {}
    bykey = {}
    for t in set_data["traits"]:
        name = t["name"]
        key = re.sub(r"[^A-Za-z0-9]", "", name)
        effects = sorted(t.get("effects") or [], key=lambda e: e.get("minUnits", 0))
        # Rival carries two effects at minUnits 1: an uncapped label row with
        # no variables, and the real 1/1 payload. Keeping both gave bp
        # [1, 1, 2] plus a phantom gold style that masked the capped bronze
        # tier. When several effects share a minUnits, keep only the ones
        # carrying variables -- a real tier always has some. Order-independent,
        # so it does not matter which way Riot lists them.
        by_min = {}
        for e in effects:
            by_min.setdefault(e.get("minUnits"), []).append(e)
        effects = [e for e in effects
                   if len(by_min[e.get("minUnits")]) == 1
                   or e.get("variables")]
        styles, bp, effs = [], [], []
        for e in effects:
            mn = e.get("minUnits")
            if not mn:
                continue
            mx = e.get("maxUnits")
            if mx and mx >= 25000:
                mx = None
            styles.append({"style": STYLE_NAMES.get(e.get("style"), "bronze"),
                           "min": mn, "max": mx})
            bp.append(mn)
            effs.append(e)

        # Riot splits the per-breakpoint text into <row> tags, one per effect,
        # in breakpoint order. Render each row against its own effect so the
        # numbers land on the right tier. If the counts don't line up we emit
        # nothing rather than risk pairing 5-unit numbers with the 3-unit text.
        rows = re.findall(r"<row>(.*?)</row>", t.get("desc") or "", re.S)
        tiers = []
        upgrades = []
        details = []
        if len(rows) == len(effs):
            # Each row opens with its own "(5)" which the UI already prints as
            # the breakpoint pip -- strip it so it isn't shown twice.
            tiers = [re.sub(r"^\s*\(\d+\)\s*", "", clean(render_row(r, e)))
                     for r, e in zip(rows, effs)]

        # Set-specific behavior is supplied by registered config hooks.
        lead = clean(render_row(
            re.split(r"<row>", t.get("desc") or "", maxsplit=1)[0],
            effs[0] if effs else {}))
        desc = clean(t.get("desc"))
        special_state = {"lead": lead, "desc": desc, "tiers": tiers,
                         "upgrades": upgrades, "details": details}
        hook = SPECIAL_TRAIT_HOOKS.get(key)
        if hook:
            hook(t, rows, effs, special_state,
                 {"re": re, "clean": clean, "render_row": render_row})
        lead, desc = special_state["lead"], special_state["desc"]
        tiers, upgrades, details = (special_state["tiers"],
                                    special_state["upgrades"],
                                    special_state["details"])

        icon = None
        # CommunityDragon gives the authoritative asset path in `icon`; the
        # name-derived guesses only cover the cases where it's missing.
        # An override wins outright -- it exists precisely because the
        # authoritative path resolves to stale art from an older set.
        cd_icon = (t.get("icon") or "").lower().replace(".tex", ".png")
        stem = re.sub(r"[^a-z0-9]", "", name.lower())
        override = TRAIT_ICON_OVERRIDE.get(key)
        if override and override not in files:
            # Falling through here would silently restore the wrong art, which
            # is exactly the bug the override exists to fix. Say so instead.
            raise SystemExit(
                f"TRAIT_ICON_OVERRIDE[{key!r}] -> {override} is not in the "
                "exported-file manifest; the override would silently fall back "
                "to CommunityDragon's stale art.")
        for cand in (override,
                     f"game/{cd_icon}" if cd_icon else None,
                     f"game/assets/ux/traiticons/trait_icon_{CONFIG.set_number}_{stem}.png",
                     f"game/assets/ux/traiticons/trait_icon_{CONFIG.set_number}_{t['apiName'].split('_')[-1].lower()}.png"):
            if cand and cand in files:
                icon = ASSET + cand
                break

        trait = {"key": key, "name": name, "icon": icon,
                 "category": TRAIT_CATEGORIES.get(key),
                 "bp": bp or [1], "styles": styles,
                 "lead": lead, "tiers": tiers,
                 "desc": desc}
        if upgrades:
            trait["upgrades"] = upgrades
        if details:
            trait["details"] = details
        if key in TRAIT_TEAM_SIZE:
            trait["teamSize"] = TRAIT_TEAM_SIZE[key]
        # Patch notes beat the mirror: stamp corrected tier strings last.
        for idx, text in (PATCH_TRAIT_TIERS.get(key) or {}).items():
            if idx < len(trait["tiers"]):
                trait["tiers"][idx] = text
        traits[key] = trait
        bykey[key] = key
        bykey[name] = key
        bykey[re.sub(r"[^A-Za-z0-9]", "", t["apiName"].split("_")[-1])] = key

    # ---- champions: reveal roster, resolve trait keys + icons ----------
    champions, unresolved, mechanic_errors = [], set(), []
    for c in reveal:
        api = c["apiName"]
        stem = api.lower()
        keys = []
        for t in c["traits"]:
            t = TRAIT_ALIAS.get(t, t)
            k = bykey.get(t) or bykey.get(re.sub(r"[^A-Za-z0-9]", "", t))
            if not k:
                unresolved.add(t)
                k = re.sub(r"[^A-Za-z0-9]", "", t)
                traits.setdefault(k, {"key": k, "name": t, "icon": None,
                                      "category": TRAIT_CATEGORIES.get(k),
                                      "bp": [2], "styles": [], "desc": ""})
            keys.append(k)

        icon = None
        for cand in (ICON_OVERRIDE.get(api),
                     f"game/assets/characters/{stem}/{stem}_square.png",
                     f"game/assets/characters/{stem}/hud/{stem}_square.png"):
            if not cand:
                continue
            if cand in files:
                icon = ASSET + cand
                break
        if not icon:
            pre = f"game/assets/characters/{stem}/skins/base/images/"
            tiles = sorted(f for f in files if f.startswith(pre) and "_splash_tile_" in f and f.endswith(".png"))
            if tiles:
                icon = ASSET + tiles[0]

        disp = CONFIG.champion_display_name(c["name"])

        champion = {"key": api.replace(f"TFT{CONFIG.set_number}_", ""), "name": disp,
                    "cost": c["cost"], "traits": keys, "icon": icon,
                    "mana": c.get("mana")}
        slots = c.get("slots", 1)
        if not isinstance(slots, int) or slots < 1:
            mechanic_errors.append(f"{api} has invalid slot cost {slots!r}")
        elif slots != 1:
            champion["slots"] = slots
        if c.get("group"):
            champion["group"] = c["group"]

        trait_points = {}
        for raw_name, points in (c.get("traitPoints") or {}).items():
            trait_name = TRAIT_ALIAS.get(raw_name, raw_name)
            trait_key = (bykey.get(trait_name)
                         or bykey.get(re.sub(r"[^A-Za-z0-9]", "", trait_name)))
            if not trait_key or trait_key not in keys:
                mechanic_errors.append(
                    f"{api} traitPoints references unowned trait {raw_name!r}")
                continue
            if not isinstance(points, int) or points < 1:
                mechanic_errors.append(
                    f"{api} has invalid {raw_name} trait points {points!r}")
                continue
            if points != 1:
                trait_points[trait_key] = points
        if trait_points:
            champion["traitPoints"] = trait_points
        champions.append(champion)

    print("loading cached PBE string table (~25MB) ...")
    strings = stringtable()
    print("fetching champion stat + ability bins (73 requests) ...")
    champion_data = fetch_champion_data([c["key"] for c in champions], strings)

    print("loading cached LoLChess set champion payload ...")
    lol_refs = lolchess_champions()
    lol_joined, lol_failures = join_lolchess(
        [c["key"] for c in champions], lol_refs)
    mana_disagreements = []
    for c in champions:
        data = champion_data.get(c["key"]) or {}
        if data.get("stats"):
            c["stats"] = data["stats"]
        if data.get("ability"):
            c["ability"] = data["ability"]
            c["ability"]["source"] = "communitydragon"

        ref = lol_joined.get(c["key"])
        skill = (ref or {}).get("skill") or {}
        role = (ref or {}).get("role")
        if role:
            if role in UNIT_ROLES:
                c["role"] = role
            else:
                mechanic_errors.append(f"{c['key']} has unknown unit role {role!r}")
        for source, target in (("health", "hpStars"),
                               ("attackDamage", "adStars")):
            values = (ref or {}).get(source)
            if (isinstance(values, list) and len(values) == 3
                    and all(isinstance(value, (int, float))
                            for value in values)):
                c.setdefault("stats", {})[target] = values
            else:
                mechanic_errors.append(
                    f"{c['key']} has invalid star-level {source}: {values!r}")
        resolved = clean_lolchess(
            skill.get("desc"), keep_icons=True, keep_breaks=True)
        if resolved:
            ability = c.setdefault("ability", {"name": skill.get("name") or "",
                                                "desc": ""})
            # Names come from Riot bins or checked-in overrides. Description
            # numbers remain explicitly third-party while PBE values are placeholders.
            ability.update({"descResolved": resolved,
                            "stats": [clean_lolchess(x)
                                      for x in skill.get("stats") or []],
                            "startingMana": skill.get("startingMana"),
                            "skillMana": skill.get("skillMana"),
                            "source": "lolchess"})
            sections = CONFIG.ability_sections(skill.get("desc"))
            if sections:
                ability["sections"] = sections
            expected = ((c.get("mana") or {}).get("start"),
                        (c.get("mana") or {}).get("max"))
            actual = (skill.get("startingMana"), skill.get("skillMana"))
            if None not in actual and actual != expected:
                mana_disagreements.append((c["key"], expected, actual))
                # The reveal capture is a fixed Jul-12 snapshot while mana is
                # tuned heavily through PBE, so prefer the live scrape and keep
                # the stale pair as provenance rather than silently dropping it.
                c["manaReveal"] = c.get("mana")
                c["mana"] = {"start": actual[0], "max": actual[1]}
                c["manaSource"] = "lolchess"

    nstats = sum("stats" in c for c in champions)
    nability = sum("ability" in c for c in champions)
    nresolved = sum(bool((c.get("ability") or {}).get("descResolved"))
                    for c in champions)
    print(f"  stats resolved for {nstats}/{len(champions)} champions")
    print(f"  abilities resolved for {nability}/{len(champions)} champions")
    print(f"  LoLChess numeric descriptions for {nresolved}/{len(champions)} champions")
    if lol_failures:
        for name, reason in sorted(lol_failures.items()):
            print(f"  ! LoLChess join failed: {name}: {reason}")
    if mana_disagreements:
        print("  ! mana disagreements (roster start/max vs LoLChess start/max):")
        for name, expected, actual in mana_disagreements:
            print(f"      {name}: {expected} vs {actual}")
    nostats = [c["key"] for c in champions if "stats" not in c]
    missing_roles = [c["key"] for c in champions if "role" not in c]
    if nostats:
        print("  ! no stat bin found:", nostats)

    champions.sort(key=lambda c: (c["cost"], c["name"]))

    planner_joined, planner_failures = join_team_planner(
        [c["key"] for c in champions], planner_refs)
    for c in champions:
        if c["key"] in planner_joined:
            c["teamPlannerCode"] = planner_joined[c["key"]]

    used = {t for c in champions for t in c["traits"]}
    traits = {k: v for k, v in traits.items() if k in used}

    missing_icon = [c["name"] for c in champions if not c["icon"]]
    missing_trait_icon = [t["name"] for t in traits.values() if not t["icon"]]
    missing_bp = [t["name"] for t in traits.values() if t["bp"] == [1] and not t["styles"]]
    missing_trait_categories = sorted(
        key for key, trait in traits.items()
        if trait.get("category") not in {"origin", "class"})
    unused_trait_categories = sorted(set(TRAIT_CATEGORIES) - set(traits))

    # ---- integrity checks ---------------------------------------------
    # A previous icon guess resolved to a real but incorrect file. A 200 OK
    # proves the path exists, not that it belongs to this unit -- so also
    # compare image bytes and flag any two units sharing one portrait.
    print("verifying icon uniqueness ...")

    def digest(c):
        try:
            return c["name"], hashlib.md5(get(c["icon"], raw=True, timeout=60)).hexdigest()
        except Exception as e:
            return c["name"], f"ERROR {e}"

    dupes, errs = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for name, h in ex.map(digest, [c for c in champions if c["icon"]]):
            if h.startswith("ERROR"):
                errs.append(f"{name}: {h}")
            else:
                dupes.setdefault(h, []).append(name)
    shared = [v for v in dupes.values() if len(v) > 1]

    # A unit with no ability text is usually a bad name guess on our side,
    # not missing upstream data -- that's exactly how Pebbles hid.
    no_ability = [c["name"] for c in champions if not c.get("ability")]
    duplicate_champions = sorted({c["key"] for c in champions
                                  if sum(x["key"] == c["key"] for x in champions) > 1})
    ability_name_failures = [
        f"{c['key']}: {(c.get('ability') or {}).get('name')!r}"
        for c in champions
        if c["key"] in ABILITY_NAME_OVERRIDES
        and (c.get("ability") or {}).get("name") != ABILITY_NAME_OVERRIDES[c["key"]]
    ]


    out = {**{key: value.format(date=datetime.date.today().isoformat())
              if isinstance(value, str) else value
              for key, value in CONFIG.metadata.items()},
           "builtAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "traits": traits, "champions": champions}

    errors = []
    if unresolved:
        errors.append(f"unresolved trait names: {sorted(unresolved)}")
    if missing_icon:
        errors.append(f"{len(missing_icon)} champions without icons: {missing_icon[:12]}")
    if missing_trait_icon:
        errors.append(f"{len(missing_trait_icon)} traits without icons: {missing_trait_icon[:12]}")
    if missing_bp:
        errors.append(f"{len(missing_bp)} traits without breakpoints: {missing_bp[:12]}")
    if missing_trait_categories:
        errors.append(f"traits without categories: {missing_trait_categories}")
    if unused_trait_categories:
        errors.append(f"category mappings without traits: {unused_trait_categories}")
    if shared:
        errors.append(f"{len(shared)} shared champion icons: " +
                      "; ".join(" == ".join(group) for group in shared))
    if errs:
        errors.append(f"{len(errs)} icons failed to fetch: {errs[:6]}")
    if no_ability:
        errors.append(f"{len(no_ability)} champions without ability text: {no_ability}")
    if duplicate_champions:
        errors.append(f"duplicate champion keys: {duplicate_champions}")
    if ability_name_failures:
        errors.append(f"ability name overrides failed: {ability_name_failures}")
    if nostats:
        errors.append(f"{len(nostats)} champions without stats: {nostats}")
    if missing_roles:
        errors.append(f"{len(missing_roles)} champions without roles: {missing_roles}")
    if lol_failures:
        errors.append(f"{len(lol_failures)} LoLChess joins failed: {lol_failures}")
    if planner_failures:
        errors.append(f"{len(planner_failures)} team-planner joins failed: {planner_failures}")
    if nresolved != len(champions):
        errors.append(f"numeric ability descriptions resolved for only {nresolved}/{len(champions)} champions")
    errors.extend(mechanic_errors)
    errors.extend(CONFIG.validate_special(traits, champions))
    for trait_key, tiers in TRAIT_TEAM_SIZE.items():
        trait = traits.get(trait_key)
        if not trait:
            errors.append(f"team-size rule references missing trait {trait_key}")
            continue
        invalid = [tier for tier in tiers if tier["min"] not in trait["bp"]
                   or not isinstance(tier["slots"], int) or tier["slots"] < 1]
        if invalid:
            errors.append(f"invalid team-size rule for {trait_key}: {invalid}")

    if errors:
        print("data validation failed; existing output was not changed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(1)

    out_path = os.path.abspath(out_arg)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    precomputed_path = os.path.join(
        os.path.dirname(out_path), "precomputed-default.json")
    precomputed_tmp = precomputed_path + ".tmp"
    try:
        subprocess.run([
            "node", os.path.join(HERE, "precompute_default.js"),
            "--data", tmp,
            "--out", precomputed_tmp,
        ], check=True)
        os.replace(precomputed_tmp, precomputed_path)
        os.replace(tmp, out_path)
    except Exception:
        for path in (tmp, precomputed_tmp):
            if os.path.exists(path):
                os.remove(path)
        raise
    print(f"wrote {out_path}: {len(champions)} champions, {len(traits)} traits")


if __name__ == "__main__":
    main()
