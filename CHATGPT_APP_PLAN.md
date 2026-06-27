# ChatGPT App Plan

## Goal

Use ChatGPT as the AI surface so Going Indie does not pay for user LLM prompts. The Going Indie app should provide structured Steam market data, and ChatGPT should reason over that data when users choose to ask broader AI questions.

## Current No-Cost Implementation

The Flask app now exposes deterministic insight APIs. These do not call Claude, OpenAI, or any other paid LLM API.

### Data Catalog

`GET /api/insights/data-points`

Lists every type of fact or derived metric the product can safely expose.

### Market Brief

`GET /api/insights/market?genre=RPG&limit=10`

Returns a market summary and top competitors for a genre or tag.

Optional params:

- `genre=RPG`
- `tag=City%20Builder`
- `limit=10`

### Ranked Markets

`GET /api/insights/markets?type=genres`

`GET /api/insights/markets?type=tags&genre=Simulation`

Ranks genres or tags by estimated market size.

### Opportunities

`GET /api/insights/opportunities?genre=Simulation&limit=12`

Ranks tags with stronger demand signals and comparatively addressable competition.

### Smaller Subgenres

`GET /api/insights/smaller-subgenres?genre=Simulation&limit=15`

Filters out broad umbrella tags such as `Singleplayer`, `Action`, `RPG`, `Adventure`, and `Indie`, then ranks smaller tags with enough data to compare. This is the best endpoint for Cam's request about less prominent markets and smaller subgenre opportunities.

By default this uses Going Indie's curated subgenre list so the output stays closer to actual market categories instead of loose Steam tags like `Mod`, `Sequel`, or hardware/features. Add `raw_tags=true` to explore the wider Steam tag universe.

Optional params:

- `genre=Simulation`
- `limit=15`
- `min_games=25`
- `max_games=750`
- `raw_tags=true`

### Subgenre Taxonomy

`GET /api/taxonomy`

`GET /api/taxonomy?genre=Action`

Returns the curated hierarchy for genre -> subgenre -> child tags. Not every subgenre needs child tags. The goal is to split broad buckets only when the split changes market analysis, for example:

- `Shooter` -> `First-Person Shooter`, `Third-Person Shooter`, `Top-Down Shooter`, `Arena Shooter`, `Looter Shooter`
- `RPG` -> `JRPG`, `Action RPG`, `Turn-Based RPG`, `Tactical RPG`, `Dungeon Crawler`
- `Simulation` -> `City Builder`, `Farming Sim`, `Life Sim`, `Management`, `Tycoon`, `Colony Sim`

`GET /api/insights/subgenre-children?genre=Action&subgenre=Shooter`

Compares child tags for a broad parent subgenre.

### Prominence

`GET /api/insights/prominence?genre=Indie&limit=10`

Returns:

- markets doing well right now
- markets that are less prominent right now

### ChatGPT Brief

`GET /api/insights/chatgpt-brief?genre=RPG`

Bundles a compact JSON brief that can be pasted into ChatGPT. This is the bridge step before a full ChatGPT App/MCP integration.

### Accuracy Model

`GET /api/insights/accuracy`

Explains which fields are high-confidence public Steam facts and which fields are estimates. It also documents the current estimate methodology:

- total market size uses summed SteamSpy owner/revenue ranges
- realistic indie targets use paid-game revenue percentiles
- per-game target benchmarks trim the top 1% of outlier hits when the sample is large enough
- confidence scores are based on sample size, paid sample size, and top-10 revenue concentration

### Market Momentum

`GET /api/insights/momentum?tag=Cozy&days=30`

Returns player-snapshot momentum for a genre or tag. Use this for questions like "is Cozy growing?" Growth claims should only be made when the trend has enough stable snapshot coverage. Sparse `player_snapshots` should be treated as insufficient evidence.

`daily_snapshot.py` now records curated `tag_snapshots` in addition to genre snapshots. Run it daily so tags like `Cozy`, `Fishing`, `4X`, and `Farming Sim` build cleaner trend history over time.

## In-App Chat Policy

`POST /api/chat` now returns a no-cost, data-only response. It does not call a paid LLM.

This keeps the interface usable during development without creating API spend.

## ChatGPT App / MCP Path

When ready, expose these same APIs as MCP tools:

- `get_data_points`
- `get_market_summary`
- `get_ranked_markets`
- `get_market_opportunities`
- `get_smaller_subgenres`
- `get_subgenre_children`
- `get_taxonomy`
- `get_prominence_report`
- `get_top_competitors`
- `get_chatgpt_brief`
- `get_accuracy_model`

The MCP server should call the existing Flask endpoints or share the same Python insight functions. The safest first public version is read-only: no database writes, no user-generated actions, and no paid model calls from Going Indie.

## Suggested Prompt For ChatGPT

Paste JSON from `/api/insights/chatgpt-brief` into ChatGPT with:

```text
You are helping an indie game developer analyze Steam market data. Use only the JSON below as your data source. Treat revenue and owner figures as estimates, not official Steam data. Identify markets doing well, markets that are less prominent, risks, and practical opportunities for a small indie team.
```

## Notes

All revenue and owner data should be labeled as SteamSpy-based estimates. Avoid presenting estimates as official Steam sales numbers. Use the percentile-based `realistic_revenue_target` for indie planning instead of treating TAM/SAM totals as what one new game can capture.
