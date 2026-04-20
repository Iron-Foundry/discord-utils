from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import discord
import httpx
from loguru import logger
from valkey.asyncio import Valkey
from valkey.exceptions import TimeoutError as ValkeyTimeoutError

from chat_events.lookups import (
    all_clue_tiers,
    resolve_boss,
    resolve_clue_tier,
    resolve_skill,
)
from chat_events.models import ClanEventsConfig
from chat_events.repository import PgChatEventsRepository
from core.service_base import Service

if TYPE_CHECKING:
    pass

_WOM_BASE = "https://api.wiseoldman.net/v2"
_WOM_HEADERS = {"User-Agent": "IronFoundry/1.0"}

_IMG_TAG_RE = re.compile(r"<img=\d+>\s*")
_LEAGUES_IMG_TAG_RE = re.compile(r"<img=22>")

_WIKI_BASE = "https://oldschool.runescape.wiki/images"
_LEAGUES_ICON_URL = f"{_WIKI_BASE}/Leagues_icon.png"

# ANSI escape codes for Discord ```ansi``` code blocks
_ANSI_RESET = "\u001b[0m"
_CHAT_COLORS = (
    "\u001b[1;31m",  # red
    "\u001b[1;32m",  # green
    "\u001b[1;33m",  # gold
    "\u001b[1;34m",  # light blue
    "\u001b[1;35m",  # pink
    "\u001b[1;36m",  # teal
)


def _wiki_name(name: str) -> str:
    return quote(name.replace(" ", "_"), safe="")


def _wiki_item_url(item_name: str) -> str:
    return f"{_WIKI_BASE}/{_wiki_name(item_name)}_detail.png"


def _wiki_rank_url(rank: str) -> str:
    name = "Deputy_owner" if rank == "Deputy Owner" else _wiki_name(rank)
    return f"{_WIKI_BASE}/Clan_icon_-_{name}.png"


def _wiki_quest_scroll_url(quest: str) -> str:
    return f"{_WIKI_BASE}/{_wiki_name(quest)}_reward_scroll.png"


def _wiki_skill_icon_url(skill: str) -> str:
    return f"{_WIKI_BASE}/{_wiki_name(skill)}_icon_(detail).png"


STREAM_KEY = "foundry:clan_events"
CONSUMER_GROUP = "discord-utils"
CONSUMER_NAME = "discord-utils-1"
BLOCK_MS = 5000
DEDUP_TTL_SECONDS = 30
DEDUP_KEY_PREFIX = "foundry:dedup:"


class ChatEventsService(Service):
    """Consumes clan events from Valkey and posts Discord embeds."""

    def __init__(
        self,
        guild: discord.Guild,
        repo: PgChatEventsRepository,
        valkey: Valkey,
        valkey_uri: str,
        client: discord.Client,
    ) -> None:
        self._guild = guild
        self._repo = repo
        self._valkey = valkey
        self._valkey_uri = valkey_uri
        self._client = client
        self._config: ClanEventsConfig | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._presence_task: asyncio.Task[None] | None = None
        self._chat_color_index: int = 0

    async def initialize(self) -> None:
        """Load config, ensure tables, and create the consumer group."""
        await self._repo.ensure_tables()
        self._config = await self._repo.get_config(self._guild.id)
        if self._config is None:
            self._config = ClanEventsConfig(guild_id=self._guild.id)
        await self._ensure_consumer_group()
        logger.info("ChatEventsService: initialized")

    async def post_ready(self) -> None:
        """Start the background stream consumer after the bot is connected."""
        self._consumer_task = asyncio.create_task(
            self._consume(), name="clan-events-consumer"
        )
        self._presence_task = asyncio.create_task(
            self._presence_subscriber(), name="ws-presence-subscriber"
        )
        logger.info("ChatEventsService: consumer task started")

    async def _presence_subscriber(self) -> None:
        """Subscribe to WS presence events and post connect/disconnect notices."""
        while True:
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe("foundry:ws_presence")
                    logger.info("ChatEventsService: subscribed to foundry:ws_presence")
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            channel_id = self.channel_id
                            if not channel_id:
                                continue
                            channel = self._client.get_channel(channel_id)
                            if not isinstance(
                                channel, (discord.TextChannel, discord.Thread)
                            ):
                                continue
                            if data.get("hide_presence_notifications"):
                                continue
                            event = data.get("event")
                            user_id: int = data["discord_user_id"]
                            verb = (
                                "connected to"
                                if event == "connect"
                                else "disconnected from"
                            )
                            await channel.send(
                                f"<@{user_id}> {verb} the in-game clan chat.",
                                allowed_mentions=discord.AllowedMentions(users=False),
                            )
                        except Exception as exc:
                            logger.warning(
                                "ChatEventsService: presence handler error: {}", exc
                            )
            except asyncio.CancelledError:
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "ChatEventsService: presence subscriber lost ({}), reconnecting in 5s",
                    exc,
                )
                await sub.aclose()
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Config management
    # ------------------------------------------------------------------

    async def resolve_sender(
        self, user: discord.Member | discord.User
    ) -> tuple[str, str | None]:
        """Return (sender_name, clan_rank).

        sender_name is the linked RSN when available, otherwise the Discord
        display name. clan_rank is None when no profile or rank is stored.
        """
        info = await self._repo.get_sender_info(user.id)
        if info:
            return info
        fallback = user.display_name if isinstance(user, discord.Member) else user.name
        return fallback, None

    async def set_channel(self, channel_id: int) -> None:
        """Persist the configured Discord channel."""
        assert self._config is not None
        self._config.channel_id = channel_id
        await self._repo.save_config(self._config)

    @property
    def channel_id(self) -> int | None:
        """The configured channel ID, or None if not set."""
        return self._config.channel_id if self._config else None

    # ------------------------------------------------------------------
    # Stream consumer
    # ------------------------------------------------------------------

    async def _ensure_consumer_group(self) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            await self._valkey.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
            )
            logger.info(
                "ChatEventsService: consumer group '{}' created", CONSUMER_GROUP
            )
        except Exception as exc:
            # BUSYGROUP means the group already exists — that's fine
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "ChatEventsService: consumer group '{}' already exists",
                    CONSUMER_GROUP,
                )
            else:
                logger.error(
                    "ChatEventsService: failed to create consumer group: {}", exc
                )

    async def _consume(self) -> None:
        """Continuously read from the Valkey stream and dispatch events."""
        logger.info("ChatEventsService: consumer loop running")
        while True:
            try:
                results = await self._valkey.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=10,
                    block=BLOCK_MS,
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(msg_id, fields)
            except asyncio.CancelledError:
                logger.info("ChatEventsService: consumer task cancelled")
                return
            except (TimeoutError, ValkeyTimeoutError):
                continue
            except Exception as exc:
                logger.error("ChatEventsService: consumer error: {}", exc)
                await asyncio.sleep(2)

    async def _is_duplicate(self, event_type: str, data: dict[str, Any]) -> bool:
        """Return True if an identical event was dispatched within the dedup window."""
        dedup_data = {k: v for k, v in data.items() if k != "userkey"}
        raw = f"{event_type}:{json.dumps(dedup_data, sort_keys=True)}"
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        key = f"{DEDUP_KEY_PREFIX}{fingerprint}"
        result = await self._valkey.set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
        return result is None  # None → key already existed → duplicate

    async def _handle_message(self, msg_id: bytes, fields: dict[bytes, bytes]) -> None:
        """Dispatch a single stream message, then ACK it."""
        try:
            event_type = fields[b"type"].decode()
            data: dict[str, Any] = json.loads(fields[b"data"])
            if await self._is_duplicate(event_type, data):
                logger.debug(
                    "ChatEventsService: duplicate event '{}', skipping", event_type
                )
            else:
                await self._dispatch(event_type, data)
        except Exception as exc:
            logger.error(
                "ChatEventsService: failed to dispatch msg {}: {}", msg_id, exc
            )
        finally:
            await self._valkey.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, event_type: str, data: dict[str, Any]) -> None:
        """Route an event to the right embed builder and post to Discord."""
        if not self._config or not self._config.channel_id:
            logger.warning(
                "ChatEventsService: no channel configured, dropping '{}' event"
                " — run /chatevents setchannel",
                event_type,
            )
            return

        channel = self._guild.get_channel_or_thread(self._config.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning(
                "ChatEventsService: configured channel {} not found or not a text channel/thread",
                self._config.channel_id,
            )
            return

        if event_type == "chat":
            if not await self._try_chat_command(data, channel):
                content = self._chat_message(data)
                await channel.send(content)
        else:
            embed = self._build_embed(event_type, data)
            if embed:
                await channel.send(embed=embed)

    async def _try_chat_command(
        self,
        data: dict[str, Any],
        channel: discord.TextChannel | discord.Thread,
    ) -> bool:
        """Intercept !kc / !level / !lvl. Returns True if the message was a command."""
        raw: str = data.get("raw_message", "").strip()
        parts = raw.split(None, 1)
        if not parts:
            return False

        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd not in ("!kc", "!level", "!lvl", "!clues") or not arg:
            return False

        rsn = self._clean(data.get("player_name", ""))
        if not rsn:
            return False

        player = await self._fetch_wom_player(rsn)

        if cmd == "!kc":
            embed = self._kc_embed(rsn, arg, player)
        elif cmd == "!clues":
            embed = self._clue_embed(rsn, arg, player)
        else:
            embed = self._level_embed(rsn, arg, player)

        await channel.send(embed=embed)
        return True

    async def _fetch_wom_player(self, rsn: str) -> dict[str, Any] | None:
        """Fetch player data from WiseOldMan. Returns None on 404 or error."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{_WOM_BASE}/players/{rsn}",
                    headers=_WOM_HEADERS,
                )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except Exception:
            logger.exception("ChatEventsService: WOM fetch failed for {}", rsn)
            return None

    def _kc_embed(
        self,
        rsn: str,
        query: str,
        player: dict[str, Any] | None,
    ) -> discord.Embed:
        """Build a kill count embed for the given boss query."""
        boss = resolve_boss(query)
        if boss is None:
            return discord.Embed(
                description=f"No boss found matching **{query}**.",
                color=discord.Color.greyple(),
            )

        wom_key, display_name, wom_section = boss
        display_rsn = player.get("displayName") or rsn if player else rsn

        if player is None:
            return discord.Embed(
                description=f"**{display_rsn}** not found on WiseOldMan.",
                color=discord.Color.greyple(),
            )

        snapshot = (player.get("latestSnapshot") or {}).get("data") or {}
        entry: dict[str, Any] = (snapshot.get(wom_section) or {}).get(wom_key) or {}
        # Activities use "score"; bosses use "kills"
        count_key = "score" if wom_section == "activities" else "kills"
        count: int = entry.get(count_key) or -1
        rank: int = entry.get("rank") or -1
        ehb: float = entry.get("ehb") or 0.0

        embed = discord.Embed(color=discord.Color.dark_gold())
        embed.set_author(name=f"{display_name} KC — {display_rsn}")

        if count < 0:
            embed.description = "No kills recorded on WiseOldMan."
            embed.color = discord.Color.greyple()
        else:
            embed.add_field(name="Kill Count", value=f"{count:,}", inline=True)
            embed.add_field(
                name="Rank",
                value=f"#{rank:,}" if rank > 0 else "Unranked",
                inline=True,
            )
            if ehb > 0:
                embed.add_field(name="EHB", value=f"{ehb:.1f} hrs", inline=True)

        embed.set_footer(text="WiseOldMan")
        return embed

    def _clue_embed(
        self,
        rsn: str,
        query: str,
        player: dict[str, Any] | None,
    ) -> discord.Embed:
        """Build a clue scroll count embed. 'total'/'all' shows a tier breakdown."""
        display_rsn = player.get("displayName") or rsn if player else rsn

        if player is None:
            return discord.Embed(
                description=f"**{display_rsn}** not found on WiseOldMan.",
                color=discord.Color.greyple(),
            )

        tier = resolve_clue_tier(query)
        if tier is None:
            return discord.Embed(
                description=f"No clue tier found matching **{query}**.",
                color=discord.Color.greyple(),
            )

        wom_key, display_name = tier
        snapshot = (player.get("latestSnapshot") or {}).get("data") or {}
        activities: dict[str, Any] = snapshot.get("activities") or {}

        embed = discord.Embed(color=discord.Color.from_rgb(139, 90, 43))
        embed.set_footer(text="WiseOldMan")

        if wom_key == "clue_scrolls_all":
            embed.set_author(name=f"Clue Scrolls — {display_rsn}")
            for tier_key, tier_label in all_clue_tiers():
                data: dict[str, Any] = activities.get(tier_key) or {}
                score: int = data.get("score") or 0
                embed.add_field(
                    name=tier_label,
                    value=f"{score:,}" if score > 0 else "0",
                    inline=True,
                )
        else:
            embed.set_author(name=f"{display_name} — {display_rsn}")
            data = activities.get(wom_key) or {}
            score = data.get("score") or -1
            rank: int = data.get("rank") or -1
            if score < 0:
                embed.description = "No clues recorded on WiseOldMan."
                embed.color = discord.Color.greyple()
            else:
                embed.add_field(name="Count", value=f"{score:,}", inline=True)
                embed.add_field(
                    name="Rank",
                    value=f"#{rank:,}" if rank > 0 else "Unranked",
                    inline=True,
                )

        return embed

    def _level_embed(
        self,
        rsn: str,
        query: str,
        player: dict[str, Any] | None,
    ) -> discord.Embed:
        """Build a skill level embed for the given skill query."""
        skill_key = resolve_skill(query)
        if skill_key is None:
            return discord.Embed(
                description=f"No skill found matching **{query}**.",
                color=discord.Color.greyple(),
            )

        display_skill = skill_key.capitalize()
        display_rsn = player.get("displayName") or rsn if player else rsn

        if player is None:
            return discord.Embed(
                description=f"**{display_rsn}** not found on WiseOldMan.",
                color=discord.Color.greyple(),
            )

        snapshot = (player.get("latestSnapshot") or {}).get("data") or {}
        skill_data: dict[str, Any] = (snapshot.get("skills") or {}).get(skill_key) or {}
        level: int = skill_data.get("level") or -1
        xp: int = skill_data.get("experience") or -1
        rank: int = skill_data.get("rank") or -1

        embed = discord.Embed(color=discord.Color.blue())
        embed.set_author(name=f"{display_skill} — {display_rsn}")
        embed.set_thumbnail(url=_wiki_skill_icon_url(display_skill))

        if level < 0:
            embed.description = "No data on WiseOldMan."
            embed.color = discord.Color.greyple()
        else:
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(
                name="Rank",
                value=f"#{rank:,}" if rank > 0 else "Unranked",
                inline=True,
            )
            if xp >= 0:
                embed.add_field(name="XP", value=f"{xp:,}", inline=True)

        embed.set_footer(text="WiseOldMan")
        return embed

    @staticmethod
    def _clean(value: str | None) -> str:
        """Strip OSRS image tags (e.g. ``<img=2>``) from a string."""
        if not value:
            return ""
        return _IMG_TAG_RE.sub("", value).strip()

    @staticmethod
    def _is_leagues(data: dict[str, Any]) -> bool:
        """Return True if the event originated from a Leagues world."""
        if data.get("is_league_world"):
            return True
        raw: str = data.get("raw_message") or ""
        return bool(_LEAGUES_IMG_TAG_RE.search(raw))

    def _build_embed(
        self, event_type: str, data: dict[str, Any]
    ) -> discord.Embed | None:
        """Route to the correct embed builder by event type."""
        builders = {
            "loot": self._loot_embed,
            "levelup": self._levelup_embed,
            "achievement": self._achievement_embed,
            "pet": self._pet_embed,
            "new_member": self._new_member_embed,
            "xpmilestone": self._xpmilestone_embed,
            "collection_log": self._collection_log_embed,
            "loot_key": self._loot_key_embed,
            "clue_item": self._clue_item_embed,
            "pk": self._pk_embed,
            "personal_best": self._personal_best_embed,
            "left_clan": self._left_clan_embed,
            "expelled": self._expelled_embed,
            "coffer_donation": self._coffer_donation_embed,
            "coffer_withdrawal": self._coffer_withdrawal_embed,
            "hcim_death": self._hcim_death_embed,
        }
        builder = builders.get(event_type)
        if builder is None:
            logger.warning(
                "ChatEventsService: unhandled event type '{}', data={}",
                event_type,
                data,
            )
            return None
        embed = builder(data)
        if self._is_leagues(data):
            embed.set_footer(text="Leagues World", icon_url=_LEAGUES_ICON_URL)
        return embed

    # ------------------------------------------------------------------
    # Embed builders
    # ------------------------------------------------------------------

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Convert a duration in seconds to M:SS or H:MM:SS, with centiseconds when present."""
        total = int(seconds)
        cs = round((seconds - total) * 100)
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        base = f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"
        return f"{base}.{cs:02}" if cs else base

    def _loot_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        item = self._clean(data.get("item_name", "Unknown item"))
        gp: int | None = data.get("coin_value")
        source = self._clean(data.get("source", "Unknown source"))
        gp_clause = f" ({gp:,} gp)" if gp is not None else ""
        embed = discord.Embed(
            description=f"**{player}** received **{item}**{gp_clause} from **{source}**",
            color=discord.Color.gold(),
        )
        embed.set_author(name="Loot Drop")
        embed.set_thumbnail(url=_wiki_item_url(item))
        return embed

    def _levelup_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        skill = self._clean(data.get("skill", "Unknown skill"))
        level = data.get("new_level", "?")
        embed = discord.Embed(
            description=f"**{player}** reached level **{level} {skill}**",
            color=discord.Color.blue(),
        )
        embed.set_author(name="Level Up!")
        embed.set_thumbnail(url=_wiki_skill_icon_url(skill))
        return embed

    def _achievement_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        name = self._clean(data.get("name", "Unknown achievement"))
        embed = discord.Embed(
            description=f"**{player}** completed **{name}**",
            color=discord.Color.purple(),
        )
        embed.set_author(name="Achievement Unlocked")
        embed.set_image(url=_wiki_quest_scroll_url(name))
        return embed

    def _pet_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        pet_name: str | None = data.get("pet_name")
        description = (
            f"**{player}** received **{pet_name}**!"
            if pet_name
            else f"**{player}** received a pet!"
        )
        embed = discord.Embed(description=description, color=discord.Color.green())
        embed.set_author(name="Pet Drop!")
        if pet_name:
            embed.set_thumbnail(url=_wiki_item_url(pet_name))
        return embed

    def _new_member_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        rank: str | None = data.get("rank")
        embed = discord.Embed(
            description=f"**{player}** has joined the clan",
            color=discord.Color.teal(),
        )
        embed.set_author(name="New Member")
        if rank:
            embed.set_thumbnail(url=_wiki_rank_url(rank))
        return embed

    def _xpmilestone_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        skill = self._clean(data.get("skill", "Unknown skill"))
        xp: int = data.get("xp", 0)
        embed = discord.Embed(
            description=f"**{player}** reached **{xp:,} XP** in **{skill}**",
            color=discord.Color.blue(),
        )
        embed.set_author(name="XP Milestone")
        embed.set_thumbnail(url=_wiki_skill_icon_url(skill))
        return embed

    def _collection_log_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        item = self._clean(data.get("item_name", "Unknown item"))
        slots: int = data.get("log_slots", 0)
        slots_max: int = data.get("log_slots_max", 0)
        embed = discord.Embed(
            description=f"**{player}** added **{item}** to their collection log",
            color=discord.Color.og_blurple(),
        )
        embed.set_author(name="Collection Log")
        embed.set_footer(text=f"{slots}/{slots_max}")
        embed.set_thumbnail(url=_wiki_item_url(item))
        return embed

    def _loot_key_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        gp: int = data.get("coin_value", 0)
        embed = discord.Embed(
            description=f"**{player}** opened a loot key worth **{gp:,} gp**",
            color=discord.Color.gold(),
        )
        embed.set_author(name="Loot Key")
        embed.set_thumbnail(url=_wiki_item_url("Loot key"))
        return embed

    def _clue_item_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        item = self._clean(data.get("item_name", "Unknown item"))
        gp: int | None = data.get("coin_value")
        gp_clause = f" ({gp:,} gp)" if gp is not None else ""
        embed = discord.Embed(
            description=(
                f"**{player}** received **{item}** from a clue scroll{gp_clause}"
            ),
            color=discord.Color.gold(),
        )
        embed.set_author(name="Clue Scroll Reward")
        embed.set_thumbnail(url=_wiki_item_url(item))
        return embed

    def _pk_embed(self, data: dict[str, Any]) -> discord.Embed:
        winner = self._clean(data.get("winner", "Unknown"))
        loser = self._clean(data.get("loser", "Unknown"))
        gp: int | None = data.get("gp_exchanged")
        gp_clause = f" and looted **{gp:,} gp**" if gp is not None else ""
        embed = discord.Embed(
            description=f"**{winner}** defeated **{loser}**{gp_clause}",
            color=discord.Color.red(),
        )
        embed.set_author(name="PK")
        return embed

    def _personal_best_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        activity = self._clean(data.get("activity", "Unknown activity"))
        time_seconds: float = data.get("time_seconds", 0.0)
        variant: str | None = data.get("variant")
        activity_label = f"{activity} ({variant})" if variant else activity
        embed = discord.Embed(
            description=(
                f"**{player}** set a new **{activity_label}** PB:"
                f" **{self._format_time(time_seconds)}**"
            ),
            color=discord.Color.green(),
        )
        embed.set_author(name="Personal Best")
        return embed

    def _left_clan_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        rank: str | None = data.get("rank")
        embed = discord.Embed(
            description=f"**{player}** has left the clan",
            color=discord.Color.light_grey(),
        )
        embed.set_author(name="Member Left")
        if rank:
            embed.set_thumbnail(url=_wiki_rank_url(rank))
        return embed

    def _expelled_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        expelled_by = self._clean(data.get("expelled_by", "Unknown"))
        rank: str | None = data.get("rank")
        embed = discord.Embed(
            description=f"**{player}** was expelled from the clan by **{expelled_by}**",
            color=discord.Color.dark_red(),
        )
        embed.set_author(name="Member Expelled")
        if rank:
            embed.set_thumbnail(url=_wiki_rank_url(rank))
        return embed

    def _coffer_donation_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        amount: int = data.get("amount", 0)
        embed = discord.Embed(
            description=f"**{player}** deposited **{amount:,} gp** into the coffer",
            color=discord.Color.teal(),
        )
        embed.set_author(name="Coffer Donation")
        return embed

    def _coffer_withdrawal_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        amount: int = data.get("amount", 0)
        embed = discord.Embed(
            description=f"**{player}** withdrew **{amount:,} gp** from the coffer",
            color=discord.Color.orange(),
        )
        embed.set_author(name="Coffer Withdrawal")
        return embed

    def _hcim_death_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = self._clean(data.get("player_name", "Unknown"))
        embed = discord.Embed(
            description=(
                f"**{player}** has died and lost their Hardcore Ironman status"
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_author(name="Hardcore Ironman Death")
        embed.set_thumbnail(url=f"{_WIKI_BASE}/Hardcore_ironman_chat_badge.png")
        return embed

    # ------------------------------------------------------------------
    # Chat relay
    # ------------------------------------------------------------------

    def _chat_message(self, data: dict[str, Any]) -> str:
        player = self._clean(data.get("player_name", data.get("sender", "Unknown")))
        message = data.get("raw_message", "").replace("`", "")
        color = _CHAT_COLORS[self._chat_color_index % len(_CHAT_COLORS)]
        self._chat_color_index += 1
        return f"```ansi\n{color}{player}{_ANSI_RESET}: {message}\n```"
