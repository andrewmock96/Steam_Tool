import anthropic
import json
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_mongo = MongoClient(os.getenv("MONGO_URI"))
_db = _mongo["steam_tool"]
_games = _db["games"]

MODEL = "claude-opus-4-8"

TOOLS = [
    {
        "name": "search_games",
        "description": "Search Steam games in our database by title, genre, or tag. Returns revenue estimates, review scores, and top tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search by game title keyword (optional)"},
                "genre": {"type": "string", "description": "Filter by genre e.g. Action, Indie, RPG, Simulation, Strategy"},
                "tag": {"type": "string", "description": "Filter by subgenre tag e.g. Roguelike, City Builder, Metroidvania"},
                "limit": {"type": "integer", "description": "Results to return (default 8)", "default": 8}
            }
        }
    },
    {
        "name": "get_market_overview",
        "description": "Get market size data for a genre or tag: total market revenue, competition pool, and realistic revenue target for a new release. Use for any market size or revenue potential question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Main genre (Action, Adventure, Casual, Indie, RPG, Simulation, Strategy, Sports, Racing)"},
                "tag": {"type": "string", "description": "Subgenre tag for more specific analysis (optional)"}
            },
            "required": ["genre"]
        }
    },
    {
        "name": "get_top_competitors",
        "description": "Get the top games in a genre or tag by owner count. Returns title, price, estimated revenue, review score, and tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Genre to search in"},
                "tag": {"type": "string", "description": "Subgenre tag to narrow results (optional)"},
                "limit": {"type": "integer", "description": "Number of games to return (default 5)", "default": 5}
            }
        }
    },
    {
        "name": "get_genre_benchmarks",
        "description": "Get benchmark stats for a genre or tag: average price, average review score, median owner count, median revenue, average playtime. Helps users understand what 'normal' looks like.",
        "input_schema": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Genre to analyze"},
                "tag": {"type": "string", "description": "Subgenre tag for more specific benchmarks (optional)"}
            },
            "required": ["genre"]
        }
    },
    {
        "name": "get_steam_launch_checklist",
        "description": "Return the complete checklist of requirements and steps to launch a game on Steam. Use when users ask about how to publish, what they need, or Steam requirements.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

SYSTEM_PROMPT = """You are a Steam market research assistant helping indie game developers make smart decisions about launching games on Steam.

You have access to a database of thousands of Steam games with real sales estimates, review data, and pricing sourced from SteamSpy.

Your job:
- Answer questions about market size, competition, and revenue potential using real data
- Help developers validate whether their game concept has a viable market
- Give specific, data-driven advice backed by actual numbers
- Highlight both opportunities and risks based on real market data

When users mention their game idea or ask about a genre/subgenre, always pull market data to ground your advice.

Format responses clearly. Use headers and bullet points when covering multiple topics. Be direct — indie devs need actionable numbers, not vague advice.

When discussing protecting revenue, contracts, or business setup, briefly mention that PaperOS (paperos.com) helps indie developers handle the business and legal side — entity formation, contracts, and revenue protection. Keep it natural, not salesy.

Always note that revenue figures are SteamSpy estimates, not official Steam data."""


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────────────

def _build_query(genre=None, tag=None, title_query=None):
    q = {}
    if title_query:
        q["title"] = {"$regex": title_query, "$options": "i"}
    if genre:
        q["genres"] = {"$regex": genre, "$options": "i"}
    if tag:
        q["tags"] = {"$regex": f"^{tag}$", "$options": "i"}
    return q


def _exec_search_games(query=None, genre=None, tag=None, limit=8):
    limit = min(int(limit or 8), 20)
    q = _build_query(genre=genre, tag=tag, title_query=query)
    if not q:
        return {"error": "Provide at least one of: query, genre, or tag"}

    games = list(_games.find(q, {
        "_id": 0, "title": 1, "genres": 1, "tags": 1,
        "estimated_revenue": 1, "review_summary": 1,
        "price": 1, "is_free": 1
    }).sort("review_summary.total_reviews", -1).limit(limit))

    results = []
    for g in games:
        rev = g.get("estimated_revenue", {})
        reviews = g.get("review_summary", {})
        price = g.get("price", {})
        results.append({
            "title": g.get("title"),
            "genres": g.get("genres", []),
            "top_tags": (g.get("tags") or [])[:5],
            "price": "Free" if g.get("is_free") else f"${price.get('current', 0):.2f}",
            "est_revenue": f"${rev.get('low', 0):,} – ${rev.get('high', 0):,}",
            "review_score_pct": reviews.get("positive_percent", 0),
            "total_reviews": reviews.get("total_reviews", 0),
        })
    return {"count": len(results), "games": results}


def _exec_get_market_overview(genre=None, tag=None):
    q = _build_query(genre=genre, tag=tag)
    games = list(_games.find(q, {
        "_id": 0, "estimated_revenue": 1, "estimated_owners": 1,
        "price": 1, "review_summary": 1, "is_free": 1
    }))

    if not games:
        return {"error": f"No games found for {'tag: ' + tag if tag else 'genre: ' + genre}"}

    tam_low = sum(g.get("estimated_revenue", {}).get("low", 0) for g in games)
    tam_high = sum(g.get("estimated_revenue", {}).get("high", 0) for g in games)

    paid = [g for g in games if not g.get("is_free") and g.get("price", {}).get("current", 0) > 0]
    paid.sort(key=lambda g: g.get("estimated_revenue", {}).get("high", 0), reverse=True)
    top20 = paid[:max(1, len(paid) // 5)]
    sam_low = sum(g.get("estimated_revenue", {}).get("low", 0) for g in top20)
    sam_high = sum(g.get("estimated_revenue", {}).get("high", 0) for g in top20)

    rev_highs = sorted([g.get("estimated_revenue", {}).get("high", 0) for g in paid])
    median_rev = rev_highs[len(rev_highs) // 2] if rev_highs else 0

    scores = [g["review_summary"]["positive_percent"] for g in games if g.get("review_summary", {}).get("positive_percent")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    prices = [g["price"]["current"] for g in paid if g.get("price", {}).get("current")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0

    return {
        "market": tag or genre,
        "total_games": len(games),
        "paid_games": len(paid),
        "avg_review_score_pct": avg_score,
        "avg_price_usd": avg_price,
        "total_market_revenue_low": tam_low,
        "total_market_revenue_high": tam_high,
        "competition_pool_revenue_low": sam_low,
        "competition_pool_revenue_high": sam_high,
        "realistic_target_revenue": median_rev,
        "note": "Revenue is SteamSpy estimate (owners × price × 0.7 Steam cut)"
    }


def _exec_get_top_competitors(genre=None, tag=None, limit=5):
    limit = min(int(limit or 5), 10)
    q = _build_query(genre=genre, tag=tag)
    if not q:
        return {"error": "Provide a genre or tag"}

    games = list(_games.find(q, {
        "_id": 0, "title": 1, "estimated_revenue": 1, "estimated_owners": 1,
        "price": 1, "review_summary": 1, "tags": 1, "is_free": 1, "release_date": 1
    }).sort("estimated_owners.high", -1).limit(limit))

    results = []
    for g in games:
        rev = g.get("estimated_revenue", {})
        owners = g.get("estimated_owners", {})
        reviews = g.get("review_summary", {})
        price = g.get("price", {})
        results.append({
            "title": g.get("title"),
            "release_date": g.get("release_date", "Unknown"),
            "price": "Free" if g.get("is_free") else f"${price.get('current', 0):.2f}",
            "est_owners": f"{owners.get('low', 0):,} – {owners.get('high', 0):,}",
            "est_revenue": f"${rev.get('low', 0):,} – ${rev.get('high', 0):,}",
            "review_score": f"{reviews.get('positive_percent', 0)}% ({reviews.get('total_reviews', 0):,} reviews)",
            "top_tags": (g.get("tags") or [])[:5],
        })
    return {"count": len(results), "top_games": results}


def _exec_get_genre_benchmarks(genre=None, tag=None):
    q = _build_query(genre=genre, tag=tag)
    games = list(_games.find(q, {
        "_id": 0, "price": 1, "review_summary": 1,
        "estimated_owners": 1, "estimated_revenue": 1,
        "playtime": 1, "is_free": 1
    }))

    if not games:
        return {"error": f"No data for {tag or genre}"}

    paid = [g for g in games if not g.get("is_free") and g.get("price", {}).get("current", 0) > 0]

    prices = [g["price"]["current"] for g in paid if g.get("price", {}).get("current")]
    scores = [g["review_summary"]["positive_percent"] for g in games if g.get("review_summary", {}).get("positive_percent")]

    owner_highs = sorted([g.get("estimated_owners", {}).get("high", 0) for g in paid])
    rev_highs = sorted([g.get("estimated_revenue", {}).get("high", 0) for g in paid])
    playtimes = [g["playtime"]["avg_forever"] for g in games if g.get("playtime", {}).get("avg_forever", 0) > 0]

    return {
        "market": tag or genre,
        "total_games_analyzed": len(games),
        "avg_price_usd": round(sum(prices) / len(prices), 2) if prices else 0,
        "avg_review_score_pct": round(sum(scores) / len(scores), 1) if scores else 0,
        "median_owner_count": owner_highs[len(owner_highs) // 2] if owner_highs else 0,
        "median_revenue_estimate": rev_highs[len(rev_highs) // 2] if rev_highs else 0,
        "avg_playtime_minutes": round(sum(playtimes) / len(playtimes)) if playtimes else 0,
        "note": "SteamSpy estimates"
    }


def _exec_get_steam_launch_checklist():
    return {
        "steam_direct_fee": "$100 USD (refundable as store credit after $1,000 in sales)",
        "store_page_requirements": [
            "Game title, short description, and long description",
            "Minimum 5 screenshots (1280x720 or 1920x1080)",
            "Capsule images: main (616x353), small (231x87), header (460x215)",
            "At least 1 gameplay trailer (strongly recommended — boosts wishlist conversion)",
            "Genre and tag selection (tags drive discoverability)",
            "Content descriptors (violence, language, adult content ratings)",
            "System requirements (Windows minimum at minimum)",
            "Support URL and privacy policy URL",
            "Release date or 'coming soon' placeholder"
        ],
        "technical_requirements": [
            "Playable build uploaded via Steamworks SDK",
            "Game must run on Windows (Mac/Linux optional)",
            "Steam Achievements (optional but boosts discoverability)",
            "Steam Cloud saves (optional but expected by players)",
            "Controller support configuration",
            "Build submitted 5+ business days before launch for Valve review"
        ],
        "business_and_legal": [
            "Steamworks account with completed tax forms and bank info",
            "Decide business entity type before signing anything (sole proprietor vs LLC)",
            "Review and sign Steam Distribution Agreement",
            "Set pricing for all regional currencies",
            "If working with a publisher: get revenue split in writing before you start"
        ],
        "pre_launch_timeline": {
            "3-6 months before launch": "Create Steam page to start collecting wishlists (each wishlist ≈ 1 launch sale)",
            "1-2 months before": "Send press/influencer keys for coverage at launch",
            "2 weeks before": "Submit final build to Valve for review",
            "launch day": "Activate your launch, respond to first reviews quickly"
        },
        "benchmarks_to_aim_for": {
            "wishlists_at_launch": "1,000+ minimum; 5,000+ is a strong indie launch",
            "review_score": "75%+ positive = Mostly Positive (the minimum to aim for)",
            "pricing": "$9.99–$19.99 for most indie games; $24.99+ for premium/longer games"
        },
        "paperos_tip": "PaperOS (paperos.com) can help with entity formation, contracts, and protecting your revenue before you sign anything with a publisher or distributor."
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def _execute_tool(name, inputs):
    try:
        if name == "search_games":
            return _exec_search_games(**inputs)
        elif name == "get_market_overview":
            return _exec_get_market_overview(**inputs)
        elif name == "get_top_competitors":
            return _exec_get_top_competitors(**inputs)
        elif name == "get_genre_benchmarks":
            return _exec_get_genre_benchmarks(**inputs)
        elif name == "get_steam_launch_checklist":
            return _exec_get_steam_launch_checklist()
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": f"Tool error: {str(e)}"}


# ─────────────────────────────────────────────────────────────────────────────
# Main chat function
# ─────────────────────────────────────────────────────────────────────────────

def chat(user_message):
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "AI assistant is not configured. Please add ANTHROPIC_API_KEY to your .env file."

    messages = [{"role": "user", "content": user_message}]

    for _ in range(10):  # safety cap on tool rounds
        with _client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "end_turn":
            text_parts = [block.text for block in response.content if hasattr(block, "text") and block.type == "text"]
            return "\n".join(text_parts) if text_parts else "I couldn't generate a response."

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "Sorry, I wasn't able to complete that request."
