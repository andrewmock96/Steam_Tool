# Steam Analytics Tool — Project Brief

## What We're Building
A free web-based tool that helps solo indie developers and small indie studios (2–10 people) research their game market, analyze competitors, estimate revenue, and self-publish successfully on Steam. The tool funnels users into PaperOS when they start making money and need legal support.

---

## Business Goal
Free tool → trust/value → convert game devs into PaperOS customers when revenue estimates and publishing success trigger a need for legal structure (contracts, IP, business setup).

### PaperOS Funnel Touchpoint
When the tool displays revenue estimates (e.g. "your game could earn $40k–$150k"), surface a natural CTA:
> "When you're ready to protect that revenue with proper contracts and legal structure, PaperOS can help."

Non-pushy, value-driven. Exact copy/placement to be confirmed with boss.

---

## MVP Scope (v1)
- Steam only (Epic, Xbox, PlayStation, Nintendo = later phases)
- Web app — keeps funnel to PaperOS seamless
- AI-powered assistant (Claude) for natural language queries
- Target launch: ~6 weeks

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
| Source | What it provides |
|---|---|
| Steam Store API (store.steampowered.com/api) | Game details, price, genres, tags, descriptions, accessibility |
| Steam Web API (api.steampowered.com) | Player counts, reviews, news, workshop data |
| SteamSpy API (steamspy.com/api) | Estimated owners, playtime, revenue ranges |

No Steam Developer account currently — using public endpoints and SteamSpy for estimates.

**Data disclaimer:** Sales and revenue figures are estimates, not official Steam data. Steam does not publicly release sales numbers. Estimates are derived from SteamSpy, which reverse-engineers owner counts from public data — the same methodology used by SteamDB, GameDiscoverCo, and VG Insights. All data should be presented to users as estimates, not facts. Both the Steam Store API and SteamSpy API are free, public, and legal to use for research tooling.

---

## Data We Collect Per Game
- Title, description, genres, tags/subgenres
- Developer, publisher, release date
- Price, discounts
- Review scores + review text
- Current/peak player counts
- News & updates
- Workshop data
- Accessibility features

---

## Derived Outputs (Estimated — not available directly from Steam)
- **Estimated copies sold** — review ratio method: reviews × 30–50
- **Estimated revenue range** — owners × price × 0.7 (Steam's 70% cut to devs)
- **TAM / SAM / SOM** — for genre/subgenre segments

---

## AI Integration (Claude)
- Users type natural language questions or goals
- Claude queries the database to pull real data
- Outputs actionable results: gap analysis, checklists, recommendations

**Example interaction:**
> User: "I want to launch my game on Steam next month."
> Tool: Missing requirements, store page recommendations, launch checklist, marketing checklist

API key: TBD — PaperOS may already have an Anthropic key.

---

## Tech Stack
| Layer | Technology | Why |
|---|---|---|
| Frontend | HTML / CSS / JavaScript | Andrew's existing strength |
| Backend | Python + Flask | Prior Flask experience, great for APIs |
| Database | MongoDB Atlas | Cloud-hosted, document model fits Steam data, free tier |
| AI | Claude API (claude-sonnet-4-6) | Best-in-class reasoning, tool use for DB queries |
| Hosting | Render (or boss's preference) | Andrew has prior experience |

---

## Database Collections (MongoDB Atlas)
- `games` — full catalog data, synced regularly from Steam APIs
- `review_snapshots` — time-series review data for trend tracking
- `player_snapshots` — current/peak player history over time
- `genre_aggregates` — pre-computed market sizing by genre/tag

---

## Team
- **Primary builder:** Andrew — HTML/CSS/JS/Python/Flask/C#/C++/Rust, limited DB experience, learning as we go
- **Boss:** More experienced, occasional input on architecture and PaperOS integration
- **Others:** Occasional help as needed

---

## Open Items (confirm with boss)
- [ ] Exact PaperOS funnel CTA copy and placement in the tool
- [ ] Whether PaperOS has an existing Anthropic API key
- [ ] Final hosting preference
- [ ] Any PaperOS brand guidelines for the tool's design

---

## Build Order (Step by Step)
1. Set up MongoDB Atlas + define data schema
2. Build Steam API data pipeline (fetch + sync game data)
3. Build Flask backend (API routes for the frontend)
4. Build frontend (search, competitor analysis, market sizing views)
5. Add revenue estimation logic
6. Integrate Claude AI assistant
7. Add PaperOS funnel touchpoints
8. Deploy to Render
