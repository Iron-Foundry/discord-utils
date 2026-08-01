# Changelog

All notable changes to discord-utils are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`pyproject.toml` holds the version and is the single source of truth for it.
Bump with `uv version --bump patch|minor` (or `alpha|beta|rc` for a
prerelease, `stable` to drop the tag). A MAJOR bump is the maintainer's call
and is never made automatically. The bump happens once, when the accumulated
work is about to be pushed - not per component. Entries land under Unreleased
until then.

## [1.0.2] - 2026-08-01

### Security

- aiohttp 3.13.3 -> 3.14.3, pillow 12.1.1 -> 12.3.0 and idna 3.11 -> 3.18,
  clearing all 40 Dependabot advisories. Lockfile only - no declared
  constraint moved, and `kaleido==0.2.1` / `plotly<6` are untouched, neither
  being a dependant of any upgraded package. wavelink and discord.py both
  accept aiohttp `<4`, so the music path is unaffected.

## [1.0.1] - 2026-07-29

### Changed

- A session now holds its bot for 15 minutes without playback before wavelink
  calls it inactive, up from 5. The pool heartbeat refreshes every session key
  each minute, so the 300 second Valkey TTL still covers the longer wait.
- Session nickname vocabulary trimmed and retuned. A word may now be more than
  one token, so a nickname can run to three words; it still may not carry
  punctuation or padding, and every possible pair is still asserted against
  Discord's 32 character nickname limit.

## [1.0.0] - 2026-07-29

First stable release. The module has carried the clan's Discord utilities in
production for some time; 1.0.0 marks the music feature landing and the public
surface being one the other services are now pinned to - the panel, the command
bridge and the Valkey session contract.

### Added

- A track carries the name of whoever asked for it, not only their id. It is
  stamped once, when the track is queued, from the guild the main bot holds -
  the only process that can see a per-server nickname at all. A player bot's own
  guild could not: they run without the members intent. Requeueing from the
  history clears the name with the id, so the new request is credited to
  whoever pressed the button.
- Activity entries carry the actor's name as well as their id, resolved the
  same way and at the same moment. The panel renders a `<@id>` mention and lets
  Discord resolve it; the website has no way to do that, so what it needs is
  attached at write time.
- A track that arrives without cover art takes one from the audio resolved for
  it at play time. A track queued from the website or restored from a saved
  playlist carries metadata only, and that resolution was the one moment a cover
  was in reach and being thrown away.
- Saved playlist rows carry their cover through `SavedTrack`, so a playlist
  queued from Discord shows the art it was saved with rather than waiting for
  each track to play.
- Saved playlists, read from api-backend: a `/playlist` command and a Playlists
  button on the panel, both opening the same per-viewer list of the playlists
  that caller may load. Selecting one queues every track in it.
- Playlist reads are per-viewer and ephemeral rather than a select on the panel.
  The panel is one shared message, so a select on it could only ever have
  offered the public playlists.
- `API_BACKEND_URL` and `METRICS_API_KEY`. Both are needed for playlists; with
  either missing the playlist controls are simply absent and playback is
  unaffected.
- A command bridge, so the website can drive a session. It subscribes to
  `music:commands` and runs pause, skip, stop, seek, volume, loop, shuffle,
  remove, move, jump and playlist loads against the session named. The "you must
  be in the voice channel" rule is re-checked here rather than trusted from the
  publisher, so both surfaces answer it identically.
- A state notice on `music:state` whenever a session moves or ends. It names the
  channel and carries nothing else: api-backend reads the session out of Valkey
  itself, so there is exactly one place the web payload is shaped.
- The session hash now records what only the player knows - paused, position and
  when that position was taken - plus the guild and channel name. A reader with
  no Lavalink player and no gateway can render a progress bar from those without
  polling anything.
- An `add` command, queueing tracks the website already resolved. They arrive as
  metadata and are looked up when each one plays, exactly as a saved playlist
  row is, so the bot never re-runs the search that produced them.
- A keepalive re-announces every live session once a minute. A session that ends
  cleanly says so, but a killed process publishes nothing at all - its keys just
  expire - so without a heartbeat a watcher cannot tell a quiet session from a
  dead one and keeps showing a player for a bot that left. It also refreshes the
  stored position, so a browser extrapolating between state changes cannot drift
  on a long track.
- A join or a leave now publishes a state notice too. Who is in the channel is
  who may control it, so without this the website kept whatever answer it got
  when the page was opened and someone joining afterwards stayed locked out of a
  session they were sitting in.
- Session history: a capped list of what has already played, written the moment
  a track ends or is skipped. A History button on the panel opens the last ten
  with a numbered button each that queues that track again, credited to whoever
  pressed it. The list is ephemeral like the rest of the session and expires
  with it; the website reads the whole of it.
- A re-queued track carries metadata only. The stored entry drops the Lavalink
  payload, so it takes the same path a saved playlist row does and its audio is
  looked up when it reaches the front of the queue - which also keeps the
  history key smaller than the session it belongs to.

### Changed

- The panel is laid out in three rows by what a control does rather than by how
  many fit: the playhead (pause, skip, stop, seek), then the modes (volume,
  loop, shuffle), then the views (Queue, History, Activity, Playlists). The
  Playlists button lost its emoji.
- The anonymous counter for a finished track is emitted alongside the history
  entry rather than from the session. Both records exist for the same reason at
  the same moment, and a track counted but not listed would make the panel and
  the stats page disagree about what played.
- Shuffle is a mode rather than a one-off reorder. While it is on, each next
  track is drawn at random from the queue instead of taken from the front, the
  button stays lit, and the panel's status line reports it alongside loop and
  volume. The queue keeps the order tracks were added in, so turning shuffle off
  resumes that order rather than leaving a scrambled queue behind. `/shuffle`
  toggles it too.
- A track can now be queued with metadata and no audio. A saved playlist stores
  no Lavalink payload, so its tracks are queued as they are and resolved when
  they reach the front of the queue - one request to load a playlist of any
  size, and no cost at all for a track nobody hears.
- A track restored from a playlist is looked up at its own URL first, then by
  ISRC, then by text, so a dead source id re-resolves instead of the track
  vanishing.

### Fixed

- A new session now writes its volume, loop and shuffle into the session hash.
  The player read the right defaults without it, but api-backend reads the hash
  rather than calling the accessors, so an unwritten default reached the website
  as 0% - a volume slider pinned to nothing on every untouched session.
- The ISRC lookup kept its hyphens. LavaSrc strips them before running the same
  query, and a hyphenated ISRC matches nothing on YouTube, so every mirrored
  track was silently falling through to the text search.

## [0.6.1] - 2026-07-28

### Fixed

- `/play` with a search term queued every result it found. It now shows the
  results with their artist, duration and source, and queues only what the
  caller picks. A link or a playlist is still queued directly, since neither
  offers a choice.
- A session that connected but never played held its bot indefinitely.
  wavelink starts its idle timer at a track end, so a player that never
  reached one was never a candidate for teardown.

## [0.6.0] - 2026-07-28

### Added

- Music slash commands: `/play`, `/pause`, `/resume`, `/skip`, `/stop`,
  `/seek`, `/queue`, `/nowplaying`, `/remove`, `/shuffle`, `/loop` and
  `/volume`, listed in `/help` under a new music group.
- `/play` starts a session when there is none, reuses the one already in the
  channel when there is, and reports pool exhaustion by naming the channels
  holding the bots.
- Every command takes its voice channel from the caller's own voice state, so
  resolving a channel is itself the authorisation check.
- 22 more tests, including one that fails if `/help` drifts from the set of
  commands actually registered.

## [0.5.0] - 2026-07-28

### Added

- Components V2 music panel, posted in the voice channel's own text chat so no
  other channel is touched and the panel dies with the channel. Transport,
  volume, seek, loop, shuffle, a jump-to-track select, and ephemeral queue and
  activity views.
- The queue view paginates and supports remove and move; seek and move are
  modals.
- Every control checks that the presser is in the voice channel first, reading
  the same roster the web surface will read.
- The panel redraws only when the session changes, never on a timer. Remaining
  time is a Discord relative timestamp, so the viewer's client counts it down.
- Orphaned panels from a previous process are swept before a new one is posted.
- 24 more tests, including the 40-component and 4000-character budget assertions.

### Changed

- Transport controls moved to `music/transport.py` so every one of them passes
  through a single state-change hook.

## [0.4.0] - 2026-07-28

### Added

- Playback core for the music service: track search across Spotify, YouTube and
  SoundCloud, a Valkey-backed queue, and pause, resume, skip, stop, seek,
  volume, loop, shuffle, remove and move.
- Spotify mirroring is resolved by the bot rather than by Lavalink, so the
  source the audio actually came from is visible instead of hidden inside the
  server. Tracks record where they were requested from and where they played
  from separately.
- Per-session activity feed and a voice roster that decides who may control a
  session, shared by Discord and the web.
- Idle and empty-channel teardown, including reacting to a temp VC being
  deleted mid-session.
- Counter events onto a Valkey stream for api-backend to consume. No user id is
  written.
- 32 more tests: queue and loop semantics, session state, teardown and the
  mirror provider chain.

### Changed

- Every key belonging to a session now expires and is swept together, so a
  killed process cannot leave a queue or activity feed behind with no bot.

## [0.3.0] - 2026-07-28

### Added

- Music bot pool (`music/`): Valkey `SET NX` leases bind one player bot to one
  voice channel, clients start lazily on first use, and each session draws a
  random two-word nickname that is unique across the live pool.
- Pool exhaustion reports which channels hold the bots instead of a bare refusal.
- Startup state reset, since sessions never survive a restart.
- First pytest suite for this module: 12 fast tests and 13 integration tests
  against a real Valkey container, wired into the root `./run-tests.sh`.

## [0.2.0] - 2026-07-28

### Added

- Configuration for the multi-bot music service: `MUSIC_BOT_TOKENS` (comma
  separated, max 5, count is the pool size), `LAVALINK_URI` and
  `LAVALINK_PASSWORD`. Music stays off while `MUSIC_BOT_TOKENS` is blank.
- `wavelink` 3.5.2 as the Lavalink v4 client.

Design and staged plan: `designs/MUSIC_BOTS.md` in the monorepo root.

## [0.1.0] - 2026-07-28

Versioning baseline. Stays pre-1.0 until the service has a stable feature set.
