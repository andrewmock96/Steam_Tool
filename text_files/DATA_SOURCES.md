# Data Sources — Where Everything In The Database Comes From

This is the handoff doc for understanding *where the data comes from*: every
external API this project talks to, every MongoDB collection it writes,
which script writes it, and how often. If you're new to this project, read
this before touching `data_collection/`.

For what the *product* does with this data (the Flask app, the AI brief
flow, etc.), see [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) in this same folder.
This doc is only about data provenance.

---

## 1. The short version

Nothing in this database is typed in by hand. It all comes from four free,
public APIs, pulled in by standalone Python scripts in `data_collection/`,
written into one MongoDB Atlas cluster (database name: `steam_tool`). The
Flask app (`app.py` + `blueprints/`) only *reads* that data — it never calls
these APIs directly except SteamSpy/Steam Store on a cache-miss (see
`blueprints/games.py`).

```
Steam Store API  ─┐
SteamSpy API     ─┼─► data_collection/*.py ─► MongoDB (`steam_tool` db) ─► Flask app ─► you
IGDB (via Twitch)─┤
ITAD             ─┘
```

Four of the collection scripts run automatically on a schedule via Windows
Task Scheduler (see [§4](#4-scheduled-tasks)). The rest are run by hand when
needed (backfills, one-off enrichment passes).

---

## 2. External APIs

| API | What we use it for | Auth | Cost | Docs |
|---|---|---|---|---|
| **Steam Store API** (`store.steampowered.com/api/appdetails`) | The core game record: title, description, genres, price, screenshots, release date, platforms, feature flags, Metacritic link, DLC count. This is the *only* source that has this metadata — SteamSpy doesn't. | None needed | Free, no key | Undocumented but stable; endpoint takes `?appids=<id>&cc=us&l=en` |
| **SteamSpy API** (`steamspy.com/api.php`) | Everything Steam itself won't tell you: **estimated owner range**, **review counts** (positive/negative), **playtime** (avg/median), **current + peak concurrent players**, and community **tags** (the "Roguelike", "Cozy", etc. labels — Steam's own genres list is much shorter). This is where the revenue estimates ultimately come from — see [§5](#5-how-revenue-is-estimated). | None needed | Free, no key | https://steamspy.com/api.php |
| **Steam Web API** (`api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers`) | Live current-player-count for a single app id — more real-time than SteamSpy's `ccu` field. Used to refresh `players.current` daily. Also used by `expand_continuous.py`'s companion `IStoreService/GetAppList` endpoint to get the full list of every app id on Steam. | **Requires `STEAM_API_KEY`** (free — get one at https://steamcommunity.com/dev/apikey) | Free | https://steamcommunity.com/dev |
| **IGDB** (`api.igdb.com/v4`), via Twitch OAuth | Optional enrichment: themes, game modes, critic rating, "similar games" ids, and IGDB's own pre-release hype counter. Not required for the app's core features — most brief/market logic never touches the `igdb` field. | **Requires a Twitch Developer app** (`TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET`) — IGDB auth rides on Twitch's OAuth client-credentials grant. Free at https://dev.twitch.tv/console/apps | Free | https://api-docs.igdb.com |
| **IsThereAnyDeal (ITAD)** (`api.isthereanydeal.com`) | Historical low price *specifically on Steam* (see the correctness note in [§5](#5-how-revenue-is-estimated) — ITAD's low can be from a non-Steam store, and this project deliberately throws those away rather than pollute the revenue model). | **Requires `ITAD_API_KEY`** — free account at https://isthereanydeal.com/apps/my/ | Free (rate limit: 1000 req / 5 min) | https://docs.isthereanydeal.com |
| **steam250.com** | Not an API — a public website scraped with `requests` + regex (no official API exists). Gives independently-curated "Hidden Gems" / "Most Played" / yearly Top 250 rankings, which is the closest proxy this project has to "well-received indie games" as a standing list. | None | Free (scraped politely, ~1 req/2s) | n/a (HTML scrape — see `scrape_steam250.py` if the site layout ever changes and this breaks) |

**Every one of these is free.** There is no paid API in this pipeline —
that was a deliberate design choice (see `PROJECT_BRIEF.md`). The `.env`
file also has an `ANTHROPIC_API_KEY` — that's a leftover from an earlier,
abandoned design (`ai_assistant.py`, deleted) and **nothing in the current
codebase uses it.** Safe to leave blank.

---

## 3. MongoDB collections

Database: `steam_tool` (MongoDB Atlas, connection string in `.env` as
`MONGO_URI`). All 8 collections below are actively read/written by the
scripts in `data_collection/` and/or the Flask app — there's no dead weight
left in the database (`review_snapshots`, `sync_log`, and `genre_aggregates`
existed here previously but were confirmed unused and dropped).

| Collection | Written by | What's in it |
|---|---|---|
| **`games`** | `expand_continuous.py` (new games), `refresh_games.py` (weekly refresh), `refresh_players.py` (player counts only), `enrich_igdb.py`, `enrich_pricing.py`, plus the Flask app itself on a cache-miss (`blueprints/games.py`) | The core collection — one document per Steam app id. See [§5](#5-the-games-document-shape) for the full field list. This is what almost every page in the app ultimately reads. |
| **`upcoming_games`** | `scrape_upcoming_releases.py` (runs daily via Task Scheduler) | Snapshots of currently coming-soon games, tracked over time. Keyed by `steam_app_id`, keeps the original `first_seen` timestamp so you can measure "how long was this store page live before launch." |
| **`genre_snapshots`** | `daily_snapshot.py` (runs daily) | One row per (date, genre): total players + total games that day. Feeds the homepage's "Player Trends" chart. |
| **`tag_snapshots`** | `daily_snapshot.py` (same run as above) | Same idea as `genre_snapshots` but per curated subgenre tag (Cozy, 4X, Farming Sim, etc.) — powers "is Cozy growing?" style momentum questions. |
| **`player_snapshots`** | `refresh_players.py` (runs daily) | One row per (game, timestamp): a point-in-time current-player-count reading. Raw history behind player-count trend lines. |
| **`market_stats`** | `analyze_publish_timing.py` (run manually, not scheduled) | Derived stats computed *from* `games` — best month/day to publish, average price by genre. Small collection (~11 docs), each one a precomputed answer to a specific question. Safe to re-run anytime; it overwrites by `stat_id`. |
| **`curated_lists`** | `scrape_steam250.py` (run manually, not scheduled) | steam250.com's Top 250 (yearly)/Hidden Gems/Most Played rankings, keyed by (list_name, year, steam_app_id). |
| **`expansion_log`** | `expand_continuous.py` | One row per Steam app id ever checked during catalog expansion, with a status (`added` / `not_game` / `no_data` / `parse_failed` / `error`). This is what lets `expand_continuous.py` resume safely — an id already logged here is never re-fetched, so this collection existing and growing is a good sign, not a problem. |

**Note on review history:** there's no `review_snapshots`-style time series
for review counts — only the current reading, stored on each game's own
`review_summary` field in `games` (refreshed weekly by `refresh_games.py`).
If you ever want to chart review-score trends over time the way
`player_snapshots` does for player counts, that's new work (a small daily
script following the same pattern as `daily_snapshot.py`), not something
already half-built and just dormant.

---

## 4. Scheduled tasks

Four Windows Task Scheduler jobs keep the data fresh automatically. All run
under the logged-in user's own Windows account (no admin rights needed —
that's deliberate, see the comment in `setup_daily_task.ps1`), which means
**the machine has to actually be logged in and online at the trigger time**
for these to fire. Check via `Get-ScheduledTask` / `Get-ScheduledTaskInfo`
in PowerShell if something looks stale.

| Task name | Runs | Script | What it does |
|---|---|---|---|
| `SteamTool-RefreshPlayers` | Daily, 7:03 PM | `refresh_players.py` | Refreshes live player counts for the top 1000 games by revenue. |
| `SteamTool-DailySnapshot` | Daily, 7:00 PM | `daily_snapshot.py` | Refreshes top-500 live player counts, then rolls up `genre_snapshots` + `tag_snapshots` for that day. |
| `GoingIndie-DailyUpcomingSync` | Daily, 6:00 AM | `scrape_upcoming_releases.py` | Syncs `upcoming_games`, marks launched games, backfills tags for coming-soon titles. Logs to `data_collection/../logs/upcoming_sync.log`. |
| `SteamTool-RefreshGames` | Weekly | `refresh_games.py` | Re-fetches Steam Store + SteamSpy data for the top 2000 games by revenue — the "keep existing data from going stale" job. |

**Known quirk:** `GoingIndie-DailyUpcomingSync`'s 6:00 AM run occasionally
fails with a DNS/network error (`All nameservers failed to answer...`) —
this is the machine's network not being up yet at 6 AM, not a code bug. It
self-heals the next day. If it fails for several days in a row, check the
machine's actual network/sleep settings around that time, not the script.

Not scheduled (run by hand as needed): `expand_continuous.py` (long-running
full-catalog crawl — safe to stop/restart anytime with Ctrl+C),
`enrich_igdb.py`, `enrich_pricing.py`, `analyze_publish_timing.py`,
`scrape_steam250.py`.

---

## 5. The `games` document shape

Every document in `games` is built by **`steam_api.py`'s `parse_game()`**
— the single function that merges a Steam Store response + a SteamSpy
response into this app's schema. If you ever need to add a new field
sourced from Steam or SteamSpy, this is the one place to add it (every
fetch path — `expand_continuous.py`, `refresh_games.py`, the Flask
cache-miss path — all call this same function).

| Field group | Fields | Source |
|---|---|---|
| Identity | `steam_app_id`, `type`, `title`, `description`, `full_description`, `website` | Steam Store |
| Classification | `genres`, `tags`, `is_early_access`, `is_free`, `required_age` | `genres` = Steam Store; `tags` = SteamSpy community tags |
| Team | `developer`, `publisher` | Steam Store |
| Release | `release_date`, `coming_soon` | Steam Store |
| Platforms / languages | `platforms`, `supported_languages` | Steam Store |
| Pricing | `price` (initial/current/discount %) | Steam Store |
| Reviews | `review_summary` (counts + %), `score_rank` | SteamSpy (`positive`/`negative`), Steam Store (`review_score_desc`) |
| Metacritic | `metacritic.score`, `metacritic.url` | Steam Store |
| Players | `players.current`, `players.peak_alltime` | SteamSpy (`ccu`/`peak_ccu`), refreshed live daily by `refresh_players.py`/`daily_snapshot.py` via the Steam Web API |
| Playtime | `playtime.avg_forever`, `.avg_2weeks`, `.median_forever`, `.median_2weeks` | SteamSpy (minutes) |
| Market estimates | `estimated_owners` (low/high), `estimated_revenue` (low/high) | **Derived**, not fetched directly — see below |
| Steam features | `features.*` (multiplayer, co-op, PvP, achievements, cloud saves, controller support, VR, etc.) | Steam Store `categories` list, decoded by `parse_categories()` |
| Publishing indicators | `screenshot_count`, `has_trailer`, `dlc_count` | Steam Store |
| Media | `header_image_url`, `background_image_url`, `screenshots`, `store_url` | Steam Store |
| Content descriptors | `content_descriptors` | Steam Store |
| *(optional, added later)* `igdb` | themes, game modes, critic rating, similar games, hype count | IGDB (`enrich_igdb.py`) — only present on games this has been run against |
| *(optional, added later)* `price_history` | `steam_historical_low`, `market_low_price`/`market_low_shop` | ITAD (`enrich_pricing.py`) |

### How revenue is estimated

Nobody publishes real Steam sales numbers, so **every revenue/owner figure
in this app is a model, not a fact**:

1. `estimated_owners` comes straight from SteamSpy's own owner-range model
   (e.g. `"200,000 .. 500,000"`) — SteamSpy derives this from Steam's public
   review count using their own statistical model. We don't recompute it,
   just parse their range.
2. `avg_price` blends initial list price, current price, and (if
   `enrich_pricing.py` has run for that game) the ITAD-confirmed Steam
   historical low, weighted 35/35/30 — because list price alone overstates
   what most buyers actually paid (most units sell during a sale, not at
   launch).
3. `gross revenue = estimated_owners × avg_price`.
4. `estimated_revenue` (what's actually stored) is gross **minus Steam's
   cut**, using Steam's real tiered revenue share (70% dev / 30% Steam up
   to $10M lifetime gross, 75/25 on the next $40M, 80/20 above $50M) — see
   `_steam_dev_share()` in `steam_api.py`.

Because of step 1, `market_insights.py` deliberately rates every
sales/revenue figure as **lower confidence** than metadata or review counts
— those come straight from Steam and aren't modeled.

### Known data-quality issue

**Playtime is 0 for essentially every game**, including freshly-refreshed
ones (confirmed on Stardew Valley mid-project) — SteamSpy's
`average_forever`/`median_forever` fields appear to not be returned (or not
parsed correctly) for the vast majority of games. The `playtime` field is
stored and displayed in the UI, but treat it as unreliable/mostly-empty
until someone investigates `steam_api.py`'s SteamSpy response parsing
against a fresh live API response. Not fixed as of this doc.

---

## 6. Environment variables (`.env`)

None of this runs without a `.env` file in the project root (never
committed — see `.gitignore`). Required keys:

| Key | Used by | Get one at |
|---|---|---|
| `MONGO_URI` | Everything | Your MongoDB Atlas cluster's connection string |
| `STEAM_API_KEY` | `refresh_players.py`, `daily_snapshot.py`, `expand_continuous.py` (full app list) | https://steamcommunity.com/dev/apikey |
| `ITAD_API_KEY` | `enrich_pricing.py` | https://isthereanydeal.com/apps/my/ |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | `enrich_igdb.py` (IGDB rides Twitch's OAuth) | https://dev.twitch.tv/console/apps |
| `ANTHROPIC_API_KEY` | **Nothing, currently.** Leftover from a deleted, abandoned design. Leave blank or omit. | — |

`get_steam_game_details()` and every SteamSpy call in `steam_api.py` need
**no key at all** — those two are fully open.

---

## 7. If you're picking this project up cold

1. Get a MongoDB Atlas connection string and the three free API keys above,
   drop them in `.env`.
2. Run `python data_collection/expand_continuous.py` once to build (or
   rebuild) the core `games` catalog from scratch — it's safe to Ctrl+C and
   restart anytime, it picks up where it left off via `expansion_log`.
3. Register the four scheduled tasks (see `data_collection/setup_daily_task.ps1`
   for the coming-soon sync; the other three were registered by hand via
   `Register-ScheduledTask` — recreate them pointing at `refresh_players.py`,
   `daily_snapshot.py`, and `refresh_games.py` on the schedules in
   [§4](#4-scheduled-tasks) if setting this up on a new machine).
4. Everything else (`enrich_igdb.py`, `enrich_pricing.py`,
   `analyze_publish_timing.py`, `scrape_steam250.py`) is optional enrichment
   — run by hand whenever, in any order, none of it blocks the app from
   working.
