// ----------------------------
// Mobile Sidebar Toggle
// ----------------------------

const menuToggle = document.getElementById("menu-toggle");
const sidebar    = document.querySelector(".sidebar");
const backdrop   = document.getElementById("sidebar-backdrop");

function closeSidebar() {
    sidebar.classList.remove("open");
    backdrop.classList.add("hidden");
    menuToggle.classList.remove("active");
}

menuToggle.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    backdrop.classList.toggle("hidden", !open);
    menuToggle.classList.toggle("active", open);
});

backdrop.addEventListener("click", closeSidebar);

// Subgenre definitions — mirrors STEAM_SUBGENRES in steam_api.py
const SUBGENRES = {
    "Action": ["Shooter","First-Person Shooter","Third-Person Shooter","Top-Down Shooter","Bullet Hell","Platformer","Precision Platformer","Run and Gun","Fighting","Hack and Slash","Beat 'em Up","Stealth","Soulslike","Battle Royale","Tower Defense","Action Roguelike","Rhythm","Side Scroller","Brawler","Open World","Survival","Looter Shooter","Military","Co-op","Parkour","Space","Sci-fi","Arena Shooter","2D","Metroidvania"],
    "Adventure": ["Point & Click","Visual Novel","Walking Simulator","Puzzle Platformer","Interactive Fiction","Escape Room","Mystery","Horror","Survival Horror","Psychological Horror","Story Rich","Exploration","Narrative","Dark","Open World","Thriller","Comedy","Supernatural","Detective","Anime","Sci-fi","Fantasy"],
    "Casual": ["Puzzle","Hidden Object","Idle","Clicker","Match 3","Relaxing","Mini Games","Word Game","Trivia","Cozy","Music","Anime","Cute","Board Game","Card Game","Family Friendly","2D","Cooking","Rhythm","Typing"],
    "Indie": ["Roguelike","Roguelite","Metroidvania","Pixel Art","Narrative","Experimental","Atmospheric","Cozy","Retro","Cyberpunk","Steampunk","Dark Fantasy","Horror","Survival","2D","Platformer","Open World","Cute","Anime","Story Rich","Puzzle","Exploration","Dark","Fantasy","Sci-fi","Hand-drawn","Top-Down","Mystery","Psychological","Comedy"],
    "RPG": ["JRPG","Action RPG","Turn-Based RPG","Dungeon Crawler","Western RPG","Tactical RPG","Isometric RPG","Dark Fantasy","Deckbuilding RPG","Creature Collector","Open World","Fantasy","Sci-fi","Anime","Story Rich","Co-op","Character Customization","Sandbox","MMORPG","Roguelike","Strategy RPG","Loot","Party-Based RPG"],
    "Simulation": ["City Builder","Farming Sim","Life Sim","Management","Tycoon","Space Sim","Flight Sim","Train Sim","Colony Sim","Base Building","Sandbox","God Game","Driving","Cooking","Fishing","Automation","Factory","Hospital","Business","Naval","Trucking","Hunting","Survival","Physics"],
    "Strategy": ["Turn-Based Strategy","Real-Time Strategy","4X","Grand Strategy","Tower Defense","Card Game","Deckbuilding","Wargame","Auto Battler","Puzzle Strategy","City Builder","Resource Management","Economic","Space","Military","Political","Base Building","Roguelike","Naval","Survival","Management","Sandbox"],
    "Sports": ["Soccer","Basketball","Baseball","Golf","Tennis","Wrestling","Fishing","Skating","Cycling","Track and Field","Boxing","Snowboarding","Football","Hockey","Rugby","Cricket","Volleyball","Skateboarding","Surfing","BMX","Extreme Sports","Hunting","Archery"],
    "Racing": ["Arcade Racing","Simulation Racing","Kart Racing","Off-Road","Motocross","Drag Racing","Street Racing","Rally","Open World","Bikes","Formula Racing"]
};

// ----------------------------
// Home: Genre Trend Chart
// ----------------------------

let genreChart = null;

const GENRE_COLORS = {
    "Action":     "#7c6fd4",
    "Adventure":  "#5a9fd4",
    "Casual":     "#d45a9f",
    "Indie":      "#7cc47c",
    "RPG":        "#d4a45a",
    "Simulation": "#5ac4c4",
    "Strategy":   "#d45a5a",
    "Sports":     "#a57cd4",
    "Racing":     "#5ad47c"
};

async function loadOverview() {
    try {
        const res  = await fetch("/api/overview");
        const data = await res.json();
        renderGenreChart(data.genres, data.trend);
    } catch (err) {
        console.error("Overview load failed:", err);
    }
}

function renderGenreChart(genres, trend) {
    const canvas = document.getElementById("chart-genre");
    if (!canvas) return;
    if (genreChart) genreChart.destroy();

    const dateSet = new Set();
    genres.forEach(g => (trend[g] || []).forEach(p => dateSet.add(p.date)));
    const labels = [...dateSet].sort();

    if (labels.length === 0) {
        canvas.parentElement.innerHTML = `<p class="chart-empty">No trend data yet — run daily_snapshot.py to build history.</p>`;
        return;
    }

    const datasets = genres.map(genre => {
        const byDate = Object.fromEntries((trend[genre] || []).map(p => [p.date, p.players]));
        return {
            label:            genre,
            data:             labels.map(d => byDate[d] ?? null),
            borderColor:      GENRE_COLORS[genre],
            backgroundColor:  GENRE_COLORS[genre] + "22",
            borderWidth:      2,
            pointRadius:      labels.length <= 7 ? 4 : 2,
            pointHoverRadius: 6,
            pointBackgroundColor: GENRE_COLORS[genre],
            fill: false, tension: 0.4, spanGaps: true
        };
    });

    genreChart = new Chart(canvas, {
        type: "line",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#6b6b90", boxWidth: 10, boxHeight: 10, borderRadius: 2, useBorderRadius: true, padding: 14, font: { size: 11 } }
                },
                tooltip: {
                    backgroundColor: "#13131f", borderColor: "#2a2a4a", borderWidth: 1, padding: 12,
                    callbacks: { label: ctx => ` ${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)} players` }
                }
            },
            scales: {
                x: { ticks: { color: "#6b6b90", font: { size: 11 } }, grid: { color: "rgba(255,255,255,0.04)" } },
                y: { ticks: { color: "#6b6b90", font: { size: 11 }, callback: v => formatNumber(v) }, grid: { color: "rgba(255,255,255,0.04)" } }
            }
        }
    });
}

loadOverview();

// ----------------------------
// Home: AI Hero Search
// ----------------------------

const heroInput    = document.getElementById("hero-input");
const heroSend     = document.getElementById("hero-send");
const heroResponse = document.getElementById("hero-response");

async function sendHeroMessage() {
    const message = heroInput.value.trim();
    if (!message) return;

    heroSend.disabled  = true;
    heroSend.textContent = "…";
    heroResponse.innerHTML = `<div class="hero-loading"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
    heroResponse.classList.remove("hidden");

    try {
        const res = await fetch("/api/chat", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ message })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: "Request failed" }));
            heroResponse.innerHTML = `<p style="color:var(--negative)">${escapeHtml(err.error || "Something went wrong.")}</p>`;
        } else {
            const data = await res.json();
            heroResponse.innerHTML = `
                <div class="hero-question">${escapeHtml(message)}</div>
                <div class="hero-answer">${renderMarkdown(data.response || "No response.")}</div>
            `;
        }
    } catch (err) {
        heroResponse.innerHTML = `<p style="color:var(--negative)">Network error — is the server running?</p>`;
    } finally {
        heroSend.disabled = false;
        heroSend.textContent = "Ask AI";
    }
}

heroSend.addEventListener("click", sendHeroMessage);
heroInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendHeroMessage();
});

document.querySelectorAll(".suggestion-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        heroInput.value = chip.textContent.trim();
        heroInput.focus();
        sendHeroMessage();
    });
});

// ----------------------------
// Search
// ----------------------------

document.getElementById("search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        const query = e.target.value.trim();
        if (query) {
            clearActiveGenre();
            document.getElementById("overview-section").classList.add("hidden");
            fetchGames(`/api/games/search?q=${encodeURIComponent(query)}`, `Results for "${query}"`);
        }
    }
});

// ----------------------------
// Genre Nav (sidebar)
// ----------------------------

let activeGenre = null;

function clearActiveGenre() {
    document.querySelectorAll(".genre-item").forEach(i => i.classList.remove("active"));
    const existing = document.querySelector(".subgenre-nav");
    if (existing) existing.remove();
    activeGenre = null;
}

document.querySelectorAll(".genre-item").forEach(item => {
    item.addEventListener("click", () => {
        const genre = item.dataset.genre;

        // Toggle off if already active
        if (item.classList.contains("active")) {
            clearActiveGenre();
            document.getElementById("overview-section").classList.remove("hidden");
            document.getElementById("market-section").classList.add("hidden");
            document.getElementById("results-header").classList.add("hidden");
            document.getElementById("results-grid").innerHTML = "";
            document.getElementById("pagination").innerHTML = "";
            return;
        }

        clearActiveGenre();
        item.classList.add("active");
        activeGenre = genre;

        document.getElementById("overview-section").classList.add("hidden");
        closeSidebar();
        fetchGames(`/api/games/genre/${encodeURIComponent(genre)}`, `${genre} Games`);
        fetchMarketOverview(genre);
        loadSubgenres(genre, item);
    });
});

function loadSubgenres(genre, afterElement) {
    const nav = document.createElement("div");
    nav.className = "subgenre-nav";
    nav.innerHTML = `<span class="subgenre-loading">Loading…</span>`;
    afterElement.after(nav);

    fetch(`/api/subgenres/${encodeURIComponent(genre)}`)
        .then(res => res.json())
        .then(available => {
            nav.innerHTML = "";
            if (available.length === 0) { nav.remove(); return; }

            available.forEach(({ tag, count }) => {
                const btn = document.createElement("button");
                btn.className = "subgenre-nav-item";
                btn.innerHTML = `<span class="subgenre-nav-name">${tag}</span><span class="subgenre-nav-count">${count}</span>`;
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    document.querySelectorAll(".subgenre-nav-item").forEach(p => p.classList.remove("active"));
                    btn.classList.add("active");
                    fetchGames(`/api/games/tag/${encodeURIComponent(tag)}?genre=${encodeURIComponent(genre)}`, `${tag} Games`);
                    fetchMarketOverview(tag, true, genre);
                });
                nav.appendChild(btn);
            });
        });
}

// ----------------------------
// Market Overview
// ----------------------------

async function fetchMarketOverview(name, isSubgenre = false, parentGenre = null) {
    try {
        let url = isSubgenre
            ? `/api/market/tag/${encodeURIComponent(name)}${parentGenre ? `?genre=${encodeURIComponent(parentGenre)}` : ""}`
            : `/api/market/genre/${encodeURIComponent(name)}`;

        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById("market-title").textContent = `${name} Market`;
        document.getElementById("market-section").classList.remove("hidden");

        document.getElementById("market-grid").innerHTML = isSubgenre ? `
            <div class="market-card">
                <div class="market-label">Games in Subgenre</div>
                <div class="market-value">${data.total_games}</div>
                <div class="market-desc">${data.paid_games} paid · Avg $${data.avg_price} · ${data.avg_review_score}% positive</div>
            </div>
            <div class="market-card">
                <div class="market-label">Serviceable Market (SAM)</div>
                <div class="market-value">${formatMoney(data.SAM.low)} – ${formatMoney(data.SAM.high)}</div>
                <div class="market-desc">${data.SAM.description}</div>
            </div>
            <div class="market-card highlight">
                <div class="market-label">Your Realistic Capture (SOM)</div>
                <div class="market-value">${formatMoney(data.SOM.low)} – ${formatMoney(data.SOM.high)}</div>
                <div class="market-desc">${data.SOM.description}</div>
            </div>
        ` : `
            <div class="market-card">
                <div class="market-label">Games in Genre</div>
                <div class="market-value">${data.total_games}</div>
                <div class="market-desc">${data.paid_games} paid · Avg $${data.avg_price} · ${data.avg_review_score}% positive</div>
            </div>
            <div class="market-card highlight">
                <div class="market-label">Total Addressable Market (TAM)</div>
                <div class="market-value">${formatMoney(data.TAM.low)} – ${formatMoney(data.TAM.high)}</div>
                <div class="market-desc">${data.TAM.description}</div>
            </div>
        `;
    } catch (err) {
        console.error("Market fetch failed:", err);
    }
}

// ----------------------------
// Fetch & Render Games
// ----------------------------

let activeLimit  = 50;
let currentPage  = 0;
let totalGames   = 0;
let currentBaseUrl = "";
let activeSort   = "revenue";
let activeFilters = {};

function totalPages() {
    return Math.max(1, Math.ceil(totalGames / activeLimit));
}

function renderGrid(games) {
    const grid = document.getElementById("results-grid");
    grid.innerHTML = "";

    if (!games || games.length === 0) {
        document.getElementById("no-results").classList.remove("hidden");
        document.getElementById("pagination").innerHTML = "";
        document.getElementById("results-count").textContent = "0 games";
        return;
    }

    document.getElementById("no-results").classList.add("hidden");
    games.forEach(game => grid.appendChild(buildCard(game)));

    const start = currentPage * activeLimit;
    const end   = Math.min(start + games.length, totalGames);
    document.getElementById("results-count").textContent =
        `${start + 1}–${end} of ${totalGames.toLocaleString()} games`;

    document.querySelectorAll(".limit-btn").forEach(btn => {
        btn.classList.toggle("active", parseInt(btn.dataset.limit) === activeLimit);
    });

    renderPagination();
}

function renderPagination() {
    const el    = document.getElementById("pagination");
    const pages = totalPages();
    if (pages <= 1) { el.innerHTML = ""; return; }

    const p = currentPage;
    const nums = new Set([0, pages - 1, p, p - 1, p + 1].filter(n => n >= 0 && n < pages));
    const sorted = [...nums].sort((a, b) => a - b);

    let html = `<button class="page-btn" data-page="${p - 1}" ${p === 0 ? "disabled" : ""}>‹ Prev</button>`;
    let prev = -1;
    for (const n of sorted) {
        if (n - prev > 1) html += `<span class="page-ellipsis">…</span>`;
        html += `<button class="page-btn ${n === p ? "active" : ""}" data-page="${n}">${n + 1}</button>`;
        prev = n;
    }
    html += `<button class="page-btn" data-page="${p + 1}" ${p >= pages - 1 ? "disabled" : ""}>Next ›</button>`;
    el.innerHTML = html;
}

function buildToolbar() {
    if (document.getElementById("results-toolbar")) return;

    const toolbar = document.createElement("div");
    toolbar.id = "results-toolbar";
    toolbar.className = "results-toolbar";
    toolbar.innerHTML = `
        <div class="toolbar-left">
            <select id="sort-select" class="toolbar-select">
                <option value="revenue">Sort: Revenue</option>
                <option value="reviews">Sort: Most Reviews</option>
                <option value="score">Sort: Best Rated</option>
                <option value="newest">Sort: Newest</option>
                <option value="price_low">Sort: Price Low→High</option>
                <option value="price_high">Sort: Price High→Low</option>
            </select>
            <button id="filter-toggle" class="toolbar-btn">Filters</button>
            <button id="export-btn" class="toolbar-btn export-btn">Export CSV</button>
        </div>
        <div class="toolbar-right">
            <span class="limit-label">Show:</span>
            <button class="limit-btn active" data-limit="50">50</button>
            <button class="limit-btn" data-limit="100">100</button>
            <button class="limit-btn" data-limit="150">150</button>
        </div>
    `;

    const filterRow = document.createElement("div");
    filterRow.id = "filter-row";
    filterRow.className = "filter-row hidden";
    filterRow.innerHTML = `
        <label>Price: <input type="number" id="f-min-price" placeholder="Min" min="0" step="1" class="filter-input"></label>
        <span class="filter-dash">–</span>
        <label><input type="number" id="f-max-price" placeholder="Max" min="0" step="1" class="filter-input"></label>
        <label>Min Score: <input type="number" id="f-min-score" placeholder="e.g. 70" min="0" max="100" class="filter-input"></label>
        <label>Year: <input type="number" id="f-year" placeholder="e.g. 2024" min="2000" max="2030" class="filter-input"></label>
        <button id="apply-filters" class="toolbar-btn apply-btn">Apply</button>
        <button id="clear-filters" class="toolbar-btn">Clear</button>
    `;

    const section = document.querySelector(".results-section");
    section.insertBefore(filterRow, document.getElementById("results-grid"));
    section.insertBefore(toolbar, filterRow);

    document.getElementById("sort-select").addEventListener("change", (e) => {
        activeSort = e.target.value;
        currentPage = 0;
        showLoading();
        loadPage();
    });

    toolbar.querySelector(".toolbar-right").addEventListener("click", (e) => {
        const btn = e.target.closest(".limit-btn");
        if (!btn) return;
        activeLimit = parseInt(btn.dataset.limit);
        currentPage = 0;
        showLoading();
        loadPage();
    });

    document.getElementById("filter-toggle").addEventListener("click", () => {
        filterRow.classList.toggle("hidden");
    });

    document.getElementById("apply-filters").addEventListener("click", applyFilters);
    document.getElementById("clear-filters").addEventListener("click", () => {
        document.querySelectorAll(".filter-input").forEach(i => i.value = "");
        activeFilters = {};
        currentPage = 0;
        showLoading();
        loadPage();
    });

    document.getElementById("export-btn").addEventListener("click", () => {
        if (!activeGenre) return;
        const params = new URLSearchParams(activeFilters);
        window.open(`/api/export/genre/${encodeURIComponent(activeGenre)}?${params}`, "_blank");
    });
}

function applyFilters() {
    const minPrice = document.getElementById("f-min-price").value;
    const maxPrice = document.getElementById("f-max-price").value;
    const minScore = document.getElementById("f-min-score").value;
    const year     = document.getElementById("f-year").value;

    activeFilters = {};
    if (minPrice) activeFilters.min_price = minPrice;
    if (maxPrice) activeFilters.max_price = maxPrice;
    if (minScore) activeFilters.min_score = minScore;
    if (year)     activeFilters.year = year;

    currentPage = 0;
    showLoading();
    loadPage();
}

document.getElementById("pagination").addEventListener("click", (e) => {
    const btn = e.target.closest(".page-btn");
    if (!btn || btn.disabled) return;
    const page = parseInt(btn.dataset.page);
    if (page >= 0 && page < totalPages()) {
        currentPage = page;
        loadPage();
        document.querySelector(".main-content").scrollTo({ top: 0, behavior: "smooth" });
    }
});

function buildQueryString() {
    const params = new URLSearchParams();
    params.set("page", currentPage);
    params.set("limit", activeLimit);
    params.set("sort", activeSort);
    for (const [k, v] of Object.entries(activeFilters)) {
        if (v !== "" && v !== undefined) params.set(k, v);
    }
    return params.toString();
}

async function loadPage() {
    try {
        const sep = currentBaseUrl.includes("?") ? "&" : "?";
        const url = `${currentBaseUrl}${sep}${buildQueryString()}`;
        const res  = await fetch(url);
        const data = await res.json();

        if (Array.isArray(data)) {
            totalGames = data.length;
            renderGrid(data);
        } else {
            totalGames = data.total;
            renderGrid(data.games);
        }
    } catch (err) {
        console.error("Failed to load page:", err);
    }
}

function showLoading() {
    const grid = document.getElementById("results-grid");
    grid.innerHTML = `<div class="loading-state"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
    document.getElementById("no-results").classList.add("hidden");
    document.getElementById("pagination").innerHTML = "";
}

async function fetchGames(baseUrl, title) {
    currentBaseUrl = baseUrl;
    activeLimit    = activeLimit || 50;
    currentPage    = 0;
    activeSort     = "revenue";
    activeFilters  = {};

    document.getElementById("results-title").textContent = title;
    document.getElementById("results-header").classList.remove("hidden");

    buildToolbar();

    const sortSelect = document.getElementById("sort-select");
    if (sortSelect) sortSelect.value = "revenue";
    document.querySelectorAll(".filter-input").forEach(i => i.value = "");
    const filterRow = document.getElementById("filter-row");
    if (filterRow) filterRow.classList.add("hidden");

    document.querySelectorAll(".limit-btn").forEach(btn => {
        btn.classList.toggle("active", parseInt(btn.dataset.limit) === activeLimit);
    });

    showLoading();
    await loadPage();
}

function buildCard(game) {
    const score      = game.review_summary?.positive_percent ?? 0;
    const scoreClass = score >= 70 ? "positive" : score >= 40 ? "mixed" : "negative";
    const scoreLabel = score > 0 ? `${score}% Positive` : "No reviews";

    const revLow  = game.estimated_revenue?.low;
    const revHigh = game.estimated_revenue?.high;
    const isFree  = game.is_free === true;
    const reviews = game.review_summary?.total_reviews ?? 0;

    let revenueText;
    if (isFree) {
        revenueText = `Free to Play · ${formatNumber(reviews)} reviews`;
    } else if (revHigh > 0) {
        revenueText = `Est. Revenue: ${formatMoney(revLow)} – ${formatMoney(revHigh)}`;
    } else {
        revenueText = `${formatNumber(reviews)} reviews`;
    }

    const topTags = (game.tags || []).slice(0, 3);
    const card = document.createElement("div");
    card.className = "game-card";
    card.innerHTML = `
        <img src="${game.header_image_url || ''}" alt="${game.title}" onerror="this.style.display='none'">
        <div class="game-card-body">
            <h3>${game.title}</h3>
            <div class="game-meta">
                <span>${(game.genres || []).join(", ") || "Unknown"}</span>
                <span>${isFree ? "Free" : game.price?.current > 0 ? "$" + game.price.current.toFixed(2) : ""}</span>
            </div>
            <div class="review-score ${scoreClass}">${scoreLabel}</div>
            <div class="revenue-estimate ${isFree ? "is-free" : ""}">${revenueText}</div>
            <div class="tags">${topTags.map(t => `<span class="tag">${t}</span>`).join("")}</div>
        </div>
    `;
    card.addEventListener("click", () => openDetail(game.steam_app_id));
    return card;
}

// ----------------------------
// Detail Panel
// ----------------------------

async function openDetail(appId) {
    const res  = await fetch(`/api/games/${appId}`);
    const game = await res.json();

    const score      = game.review_summary?.positive_percent ?? 0;
    const scoreClass = score >= 70 ? "positive" : score >= 40 ? "mixed" : "negative";
    const isFree     = game.is_free === true;
    const revLow     = game.estimated_revenue?.low;
    const revHigh    = game.estimated_revenue?.high;
    const revDisplay = isFree ? "Free to Play"
        : (revHigh > 0 ? `${formatMoney(revLow)} – ${formatMoney(revHigh)}` : "N/A");

    document.getElementById("detail-content").innerHTML = `
        <img class="detail-image" src="${game.header_image_url || ''}" alt="${game.title}">
        <h2 class="detail-title">${game.title}</h2>
        <p class="detail-developer">${(game.developer || []).join(", ")} · Released ${game.release_date || "Unknown"}</p>
        <p class="detail-description">${game.description || "No description available."}</p>

        <p class="section-title">Market Estimates</p>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="label">Est. Copies Sold</div>
                <div class="value">${formatNumber(game.estimated_owners?.low)} – ${formatNumber(game.estimated_owners?.high)}</div>
            </div>
            <div class="stat-box">
                <div class="label">Est. Revenue</div>
                <div class="value">${revDisplay}</div>
            </div>
            <div class="stat-box">
                <div class="label">Review Score</div>
                <div class="value ${scoreClass}">${score}% Positive</div>
            </div>
            <div class="stat-box">
                <div class="label">Total Reviews</div>
                <div class="value">${formatNumber(game.review_summary?.total_reviews)}</div>
            </div>
            <div class="stat-box">
                <div class="label">Current Players</div>
                <div class="value">${formatNumber(game.players?.current)}</div>
            </div>
            <div class="stat-box">
                <div class="label">Price</div>
                <div class="value">${isFree ? "Free" : "$" + (game.price?.current || 0).toFixed(2)}</div>
            </div>
        </div>

        <p class="section-title">Tags</p>
        <div class="tags">
            ${(game.tags || []).slice(0, 12).map(t => `<span class="tag">${t}</span>`).join("") || "<span style='color:var(--text-dim);font-size:0.8rem'>No tags</span>"}
        </div>

        <p class="section-title">Platforms</p>
        <div class="tags">
            ${game.platforms?.windows ? '<span class="tag">Windows</span>' : ""}
            ${game.platforms?.mac     ? '<span class="tag">Mac</span>'     : ""}
            ${game.platforms?.linux   ? '<span class="tag">Linux</span>'   : ""}
        </div>

        <p style="margin-top:22px; font-size:0.72rem; color:var(--text-muted);">
            Figures are estimates based on SteamSpy data, not official Steam numbers.
        </p>
    `;

    document.getElementById("detail-panel").classList.remove("hidden");
}

document.getElementById("close-panel").addEventListener("click", () => {
    document.getElementById("detail-panel").classList.add("hidden");
});

// ----------------------------
// Helpers
// ----------------------------

function formatMoney(value) {
    if (!value) return "N/A";
    if (value >= 1_000_000_000) return "$" + (value / 1_000_000_000).toFixed(1) + "B";
    if (value >= 1_000_000)     return "$" + (value / 1_000_000).toFixed(1)     + "M";
    if (value >= 1_000)         return "$" + (value / 1_000).toFixed(0)         + "K";
    return "$" + value;
}

function formatNumber(value) {
    if (value == null || value === 0) return "N/A";
    if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + "M";
    if (value >= 1_000)     return (value / 1_000).toFixed(0)     + "K";
    return value.toString();
}

// ----------------------------
// AI Chat Widget
// ----------------------------

const chatPanel  = document.getElementById("chat-panel");
const chatToggle = document.getElementById("chat-toggle");
const chatClose  = document.getElementById("chat-close");
const chatInput  = document.getElementById("chat-input");
const chatSend   = document.getElementById("chat-send");
const chatMsgs   = document.getElementById("chat-messages");

chatToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    chatPanel.classList.toggle("hidden");
    if (!chatPanel.classList.contains("hidden")) chatInput.focus();
});

chatClose.addEventListener("click", (e) => {
    e.stopPropagation();
    chatPanel.classList.add("hidden");
});

document.addEventListener("click", (e) => {
    if (!document.getElementById("chat-widget").contains(e.target)) {
        chatPanel.classList.add("hidden");
    }
});

chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
});

chatSend.addEventListener("click", sendChatMessage);

function appendMessage(role, html) {
    const wrap   = document.createElement("div");
    wrap.className = `chat-message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.innerHTML = html;
    wrap.appendChild(bubble);
    chatMsgs.appendChild(wrap);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
    return wrap;
}

function showTyping() {
    const wrap = document.createElement("div");
    wrap.className = "chat-message assistant";
    wrap.id = "chat-typing-indicator";
    wrap.innerHTML = `<div class="chat-typing"><span></span><span></span><span></span></div>`;
    chatMsgs.appendChild(wrap);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById("chat-typing-indicator");
    if (el) el.remove();
}

function renderMarkdown(text) {
    return text
        .replace(/```[\s\S]*?```/g, m => `<pre style="background:#0a0a14;padding:8px;border-radius:6px;overflow-x:auto;font-size:0.78rem;margin:5px 0">${m.replace(/```\w*\n?/g, "").replace(/</g,"&lt;")}</pre>`)
        .replace(/`([^`]+)`/g, '<code style="background:#0a0a14;padding:1px 5px;border-radius:3px;font-size:0.85em">$1</code>')
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm,  "<h2>$1</h2>")
        .replace(/^# (.+)$/gm,   "<h1>$1</h1>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g,   "<em>$1</em>")
        .replace(/^[-•] (.+)$/gm, "<li>$1</li>")
        .replace(/(<li>[\s\S]+?<\/li>)/g, "<ul>$1</ul>")
        .replace(/<\/ul>\s*<ul>/g, "")
        .replace(/\n\n+/g, "</p><p>")
        .replace(/\n(?!<)/g, "<br>")
        .replace(/^/, "<p>")
        .replace(/$/, "</p>");
}

function escapeHtml(str) {
    return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value    = "";
    chatInput.disabled = true;
    chatSend.disabled  = true;

    appendMessage("user", escapeHtml(message));
    showTyping();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message })
        });

        removeTyping();

        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: "Request failed" }));
            appendMessage("assistant", `<em style="color:#e05252">${escapeHtml(err.error || "Something went wrong.")}</em>`);
        } else {
            const data = await res.json();
            appendMessage("assistant", renderMarkdown(data.response || "No response received."));
        }
    } catch (err) {
        removeTyping();
        appendMessage("assistant", `<em style="color:#e05252">Network error. Is the server running?</em>`);
    } finally {
        chatInput.disabled = false;
        chatSend.disabled  = false;
        chatInput.focus();
    }
}
