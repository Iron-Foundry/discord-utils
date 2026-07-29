"""Every Valkey key the music module uses, in one place.

Session state is deliberately ephemeral: it exists while a bot is playing and
dies with the session. `SESSION_TTL_SECONDS` is what makes that true even when
the process is killed, and the pool heartbeat refreshes every key below for as
long as the session is genuinely alive.
"""

from __future__ import annotations

LEASE = "music:lease:{index}"
SESSION = "music:session:{voice_channel_id}"
QUEUE = "music:queue:{voice_channel_id}"
ACTIVITY = "music:activity:{voice_channel_id}"
HISTORY = "music:history:{voice_channel_id}"
VOICE = "music:voice:{voice_channel_id}"
NAMES = "music:names"
EVENTS = "music:events"

# The two pubsub channels the web surface rides on. Commands travel one way and
# state notices the other, so neither side ever reads the other's process.
COMMANDS = "music:commands"
STATE = "music:state"

SESSION_TTL_SECONDS = 300

# Keys that belong to one live session, refreshed and swept together.
SESSION_KEYS = (SESSION, QUEUE, ACTIVITY, HISTORY, VOICE)
STALE_PATTERNS = tuple(
    template.format(voice_channel_id="*") for template in SESSION_KEYS
)


def session_keys(voice_channel_id: int) -> tuple[str, ...]:
    """Every key holding state for one voice channel's session."""
    return tuple(
        template.format(voice_channel_id=voice_channel_id) for template in SESSION_KEYS
    )
