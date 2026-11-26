"""Set configuration loading and Set 18 compatibility checks."""
import unittest
from pathlib import Path

from build_set import load_set_config


class TestSetConfig(unittest.TestCase):
    def test_set18_config_preserves_existing_build_values(self):
        config = load_set_config(18)
        lux_art = {
            "Blossom": "blossom", "Coven": "coven", "Elderwood": "elderwood",
            "Eldritch": "blackthorn", "Fae": "fae", "Inferno": "inferno",
            "Lunar": "moonbeam", "Primal": "primal", "Solar": "sunbeam",
        }
        categories = {
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
        icon_overrides = {
            "TFT18_Pebbles": "game/assets/characters/tft18_sentry/tft18_sentry_square.png",
            "TFT18_AncientSentinel": "game/assets/characters/tft18_sentinel/tft18_sentinel_square.png",
            **{
                f"TFT18_Lux{origin}":
                    f"game/assets/characters/tft18_lux/tft18_lux_{art}_square.png"
                for origin, art in lux_art.items()
            },
        }

        self.assertEqual(config.set_number, 18)
        self.assertEqual(config.set_key, "18")
        self.assertEqual(config.set_name, "Enchanted Wilds")
        self.assertEqual(config.team_planner_key, "TFTSet18")
        self.assertEqual(config.roster_file.name, "set18-roster.json")
        self.assertEqual(config.style_names, {
            1: "bronze", 2: "silver", 3: "silver", 4: "unique",
            5: "gold", 6: "prismatic",
        })
        self.assertEqual(config.trait_aliases, {"Eldritch": "Blackthorn"})
        self.assertEqual(config.trait_categories, categories)
        self.assertEqual(config.trait_team_size, {"Riftbeast": [{"min": 10, "slots": 2}]})
        self.assertEqual(config.patch_trait_tiers, {
            "Coven": {2: "3 per kill, 30 per loss", 3: "10 per kill, 80 per loss"},
        })
        self.assertEqual(config.icon_overrides, icon_overrides)
        self.assertEqual(config.trait_icon_overrides, {
            "Invoker": "game/assets/ux/traiticons/trait_icon_16_invoker.png",
        })
        self.assertEqual(config.lux_art, lux_art)
        self.assertEqual(config.lux_bin, lux_art)
        self.assertEqual(config.bin_overrides, {
            "Pebbles": "da_18_sentry", "AncientSentinel": "da_sentinel18",
            "KogMaw": "da_kogmaw18_ad", "Raptor": "da_crimsonraptor18",
            "Gnar": "da_18_gnarbig", "Krug": "da_krug18",
            "Akali": "da_18_akali_ad",
        })
        self.assertEqual(config.ability_name_overrides, {
            "Raptor": "Flock Family",
            **{f"Lux{origin}": "Final Spark" for origin in lux_art},
        })
        self.assertEqual(config.lolchess_url,
                         "https://lolchess.gg/champions/set18/yorick?hl=en-US")
        self.assertEqual(config.lolchess_fallback_keys,
                         {"Raptor": "CrimsonRaptorMini"})
        self.assertEqual(config.metadata["set"], "set18")
        self.assertEqual(config.metadata["setName"], "Enchanted Wilds")
        self.assertEqual(config.metadata["teamPlannerSet"], "TFTSet18")
        self.assertIn("PBE TFTSet18", config.metadata["gameBuild"])
        self.assertIn("en/set18 on {date}", config.metadata["abilityNote"])
        self.assertEqual(set(config.special_trait_hooks), {
            "Solar", "Primal", "Summoner", "Adaptor", "Defender",
        })

    def test_set_derived_paths_and_stems_use_the_requested_number(self):
        config = load_set_config(18)
        self.assertEqual(Path(config.lolchess_cache).name,
                         "lolchess-set18-champions.html")
        self.assertEqual(config.bin_candidates("Akali")[:3], [
            "da_18_akali_ad", "da_18_akali", "tft18_akali",
        ])
        self.assertEqual(config.bin_candidates("Kennen")[0:2], [
            "da_18_kennen", "tft18_kennen",
        ])

    def test_missing_set_config_fails_with_the_requested_number(self):
        with self.assertRaisesRegex(ValueError, "set 999"):
            load_set_config(999)


if __name__ == "__main__":
    unittest.main()
