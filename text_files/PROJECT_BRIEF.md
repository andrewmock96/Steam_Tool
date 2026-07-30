# Steam Analytics Tool — Project Brief

## What We're Building
A free web-based tool that helps solo indie developers and small indie studios (2–10 people) research their game market, analyze competitors, estimate revenue, and self-publish successfully on Steam. The tool funnels users into PaperOS when they start making money and need legal support.

---

## Business Goal
Free tool → trust/value → convert game devs into PaperOS customers when revenue estimates and publishing success trigger a need for legal structure (contracts, IP, business setup).

### PaperOS Funnel Touchpoint
When the tool displays revenue estimates (e.g. "your game could earn $40k–$150k"), surface a natural CTA:
> "When you're ready to protect that revenue with proper contracts and legal structure, PaperOS can help."

Non-pushy, value-driven. Exact copy/placement still to be confirmed with boss — this is the one open item carried over from the original plan.

---

## Status: MVP built and running

This started as a 6-week MVP plan (see the original build order at the
bottom of this doc). It's built: the Flask app is live, the database has
been continuously expanding since launch (168k+ games as of this writing),
and four scheduled jobs keep the data fresh automatically. A few decisions
from the original plan changed along the way — most notably the AI
approach — see [AI Integration](#ai-integration) below for what actually
shipped versus what was originally planned.

---

## MVP Scope (v1)
- Steam only (Epic, Xbox, PlayStation, Nintendo = later phases)
- Web app — keeps funnel to PaperOS seamless
- Free, no-API-cost AI handoff for natural language queries (see below —
  this replaced the originally-planned in-app Claude integration)

---

## Key User Jobs
1. Research game ideas
2. Estimate market size (TAM / SAM / SOM by genre)
3. Analyze competitors
4. Track industry trends
5. Prepare for publishing
6. Self-publish more successfully

---

## Data Sources

Full detail — every external API, what each field traces back to, how the
revenue model works, and every MongoDB collection — now lives in its own
doc: **[`DATA_SOURCES.md`](DATA_SOURCES.md)**. Short version: Steam Store
API + SteamSpy API (both free, no key) are the core; IGDB and
IsThereAnyDeal add optional enrichment; steam250.com is scraped for a
curated "well-received indie games" proxy list. No paid data source is used
anywhere in this pipeline.

**Data disclaimer:** Sales and revenue figures are estimates, not official Steam data. Steam does not publicly release sales numbers. Estimates are derived from SteamSpy, which reverse-engineers owner counts from public data — the same methodology used by SteamDB, GameDiscoverCo, and VG Insights. All data should be presented to users as estimates, not facts.

---

## Data We Collect Per Game
- Title, description, genres, tags/subgenres
- Developer, publisher, release date
- Price, discounts, historical low price (via ITAD)
- Review scores
- Current/peak player counts
- Playtime (currently unreliable — see `DATA_SOURCES.md`'s known-issues note)
- Steam feature flags (multiplayer, co-op, achievements, controller/VR support, etc.)
- Screenshots, DLC count, Metacritic score
- Optional: IGDB themes/game modes/critic rating (only for games `enrich_igdb.py` has run against)

---

## Derived Outputs (Estimated — not available directly from Steam)
- **Estimated owners** — SteamSpy's own modeled owner range
- **Estimated revenue range** — owners × blended average price, minus Steam's real tiered revenue cut (70/75/80% to devs depending on lifetime gross) — see `DATA_SOURCES.md` §5 for the exact formula
- **TAM / SAM / SOM** — for genre/subgenre segments, computed in `market_insights.py`

---

## AI Integration

**What actually shipped is not what was originally planned.** The original
plan was an in-app Claude API integration (Going Indie pays per query). That
was built once (`ai_assistant.py`) but abandoned before launch, over API
cost concerns for a free tool with no revenue yet.

**What's live instead:** a zero-API-cost design. The app builds a
structured JSON market brief server-side from real Steam data, and the user
copies/pastes it into their *own* ChatGPT or Claude account (or whichever
AI tool they prefer) — Going Indie never calls a paid LLM API itself. See
`templates/brief_loader.html` and the `/api/insights/chatgpt-brief` /
`/brief-loader` flow in `blueprints/insights.py` for how this works. There's
also a small free, no-LLM chat widget in the app itself
(`/api/chat` → `answer_without_llm()` in `market_insights.py`) that answers
simple questions directly from the database with zero AI cost at all.

If Going Indie ever has budget for a real per-query LLM cost, the original
in-app-Claude approach could be revisited — but the current design was a
deliberate choice, not a stopgap someone forgot to finish.

---

## Tech Stack
| Layer | Technology | Why |
|---|---|---|
| Frontend | HTML / CSS / JavaScript (no build step) | Andrew's existing strength |
| Backend | Python + Flask (blueprints) | Prior Flask experience, great for APIs |
| Database | MongoDB Atlas | Cloud-hosted, document model fits Steam data, free tier |
| AI | None called by the app itself — see [AI Integration](#ai-integration) above | Keeps the tool free to run regardless of usage volume |
| Data collection | Standalone Python scripts in `data_collection/`, run via Windows Task Scheduler | See `DATA_SOURCES.md` §4 for the full schedule |
| Hosting | TBD (was Render or boss's preference — unconfirmed) | — |

---

## Database Collections (MongoDB Atlas)

See **[`DATA_SOURCES.md`](DATA_SOURCES.md)** for the full, current table of
every collection, what writes it, and what's in it. Short version: `games`
is the core catalog; `player_snapshots`, `genre_snapshots`, and
`tag_snapshots` are time-series history; `upcoming_games`, `curated_lists`,
`market_stats`, and `expansion_log` support specific features. (An earlier
version of this list mentioned `review_snapshots` and `genre_aggregates` —
both were confirmed unused and dropped from the database.)

---

## Team
- **Primary builder:** Andrew — HTML/CSS/JS/Python/Flask/C#/C++/Rust, learning MongoDB/data-pipeline work as we go
- **Boss:** More experienced, occasional input on architecture and PaperOS integration
- **Others:** Occasional help as needed

---

## Open Items (confirm with boss)
- [ ] Exact PaperOS funnel CTA copy and placement in the tool
- [ ] Final hosting decision
- [ ] Any PaperOS brand guidelines for the tool's design

---

## Original Build Order (for history)
1. Set up MongoDB Atlas + define data schema — done
2. Build Steam API data pipeline (fetch + sync game data) — done
3. Build Flask backend (API routes for the frontend) — done
4. Build frontend (search, competitor analysis, market sizing views) — done
5. Add revenue estimation logic — done
6. ~~Integrate Claude AI assistant~~ → replaced with the no-cost brief-handoff design (see [AI Integration](#ai-integration)) — done, different from plan
7. Add PaperOS funnel touchpoints — **not started**, no PaperOS references exist in the codebase yet
8. Deploy — **not done**, hosting decision still open
