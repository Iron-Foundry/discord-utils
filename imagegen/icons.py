from __future__ import annotations

from enum import Enum
from pathlib import Path

BASE_DIR = Path(__file__).parent


class _IconEnum(Enum):
    @property
    def path(self) -> Path:
        return BASE_DIR / self.value

    def __str__(self) -> str:
        return str(self.path)


class SkillIcon(_IconEnum):
    AGILITY = "assets/icons/Skills/Agility.png"
    ATTACK = "assets/icons/Skills/Attack.png"
    CONSTRUCTION = "assets/icons/Skills/Construction.png"
    COOKING = "assets/icons/Skills/Cooking.png"
    CRAFTING = "assets/icons/Skills/Crafting.png"
    DEFENCE = "assets/icons/Skills/Defence.png"
    FARMING = "assets/icons/Skills/Farming.png"
    FIREMAKING = "assets/icons/Skills/Firemaking.png"
    FISHING = "assets/icons/Skills/Fishing.png"
    FLETCHING = "assets/icons/Skills/Fletching.png"
    HERBLORE = "assets/icons/Skills/Herblore.png"
    HITPOINTS = "assets/icons/Skills/Hitpoints.png"
    HUNTER = "assets/icons/Skills/Hunter.png"
    MAGIC = "assets/icons/Skills/Magic.png"
    MINING = "assets/icons/Skills/Mining.png"
    PRAYER = "assets/icons/Skills/Prayer.png"
    RANGED = "assets/icons/Skills/Ranged.png"
    RUNECRAFT = "assets/icons/Skills/Runecraft.png"
    SAILING = "assets/icons/Skills/Sailing.png"
    SLAYER = "assets/icons/Skills/Slayer.png"
    SMITHING = "assets/icons/Skills/Smithing.png"
    STRENGTH = "assets/icons/Skills/Strength.png"
    THIEVING = "assets/icons/Skills/Thieving.png"
    WOODCUTTING = "assets/icons/Skills/Woodcutting.png"


class BossIcon(_IconEnum):
    ABYSSAL_SIRE = "assets/icons/Bosses/Abyssal Sire.png"
    ALCHEMICAL_HYDRA = "assets/icons/Bosses/Alchemical Hydra.png"
    BRYOPHYTA = "assets/icons/Bosses/Bryophyta.png"
    CERBERUS = "assets/icons/Bosses/Cerberus.png"
    COMMANDER_ZILYANA = "assets/icons/Bosses/Commander Zilyana.png"
    CORPOREAL_BEAST = "assets/icons/Bosses/Corporeal Beast.png"
    CRYSTALLINE_HUNLEFF = "assets/icons/Bosses/Crystalline Hunleff.png"
    DAGANNOTH_KINGS = "assets/icons/Bosses/Dagannoth Kings.png"
    GENERAL_GRAARDOR = "assets/icons/Bosses/General Graardor.png"
    GIANT_MOLE = "assets/icons/Bosses/Giant Mole.png"
    COX = "assets/icons/Bosses/Great Olm.png"
    GROTESQUE_GUARDIANS = "assets/icons/Bosses/Grotesque Guardians.png"
    HESPORI = "assets/icons/Bosses/Hespori.png"
    KRIL_TSUTSAROTH = "assets/icons/Bosses/K'ril Tsutsaroth.png"
    KALPHITE_QUEEN = "assets/icons/Bosses/Kalphite Queen.png"
    KING_BLACK_DRAGON = "assets/icons/Bosses/King Black Dragon.png"
    KRAKEN = "assets/icons/Bosses/Kraken.png"
    KREEARRA = "assets/icons/Bosses/Kree'arra.png"
    NEX = "assets/icons/Bosses/Nex.png"
    OBOR = "assets/icons/Bosses/Obor.png"
    SARACHNIS = "assets/icons/Bosses/Sarachnis.png"
    SKOTIZO = "assets/icons/Bosses/Skotizo.png"
    TEMPOROSS = "assets/icons/Bosses/Tempoross.png"
    THE_MIMIC = "assets/icons/Bosses/The Mimic.png"
    THE_NIGHTMARE = "assets/icons/Bosses/The Nightmare.png"
    THERMONUCLEAR_SMOKE_DEVIL = "assets/icons/Bosses/Thermonuclear Smoke Devil.png"
    TOB = "assets/icons/Bosses/Verzik Vitur.png"
    VORKATH = "assets/icons/Bosses/Vorkath.png"
    TOA = "assets/icons/Bosses/Warden.png"
    WINTERTODT = "assets/icons/Bosses/Wintertodt.png"
    ZALCANO = "assets/icons/Bosses/Zalcano.png"
    ZULRAH = "assets/icons/Bosses/Zulrah.png"
