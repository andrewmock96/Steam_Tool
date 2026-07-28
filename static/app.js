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
    "Racing": ["Open World","Motorsport","Motocross","Cycling"]
};

let subgenreChildrenMap = {};

fetch("/api/taxonomy")
    .then(res => res.json())
    .then(data => {
        subgenreChildrenMap = data.children_by_subgenre || {};
        if (document.getElementById("compare-type")?.value === "tag") populateCompareValueOptions();
    })
    .catch(() => {});

function populateCompareSubOptions(genre) {
    const subSelect = document.getElementById("compare-sub-value");
    const controls  = document.getElementById("compare-controls");
    if (!subSelect) return;
    const tags = SUBGENRES[genre] || [];
    const seen = new Set();
    let html = `<option value="">Subgenre (optional)…</option>`;
    tags.forEach(tag => {
        if (seen.has(tag)) return;
        seen.add(tag);
        html += `<option value="${tag}">${tag}</option>`;
        (subgenreChildrenMap[tag] || []).forEach(child => {
            if (seen.has(child)) return;
            seen.add(child);
            html += `<option value="${child}">↳ ${child}</option>`;
        });
    });
    subSelect.innerHTML = html;
    subSelect.style.display = "";
    controls.style.gridTemplateColumns = "minmax(0,1fr) minmax(0,1fr) auto";
}

function populateCompareValueOptions() {
    const valueSelect = document.getElementById("compare-value");
    const subSelect   = document.getElementById("compare-sub-value");
    const controls    = document.getElementById("compare-controls");
    if (!valueSelect) return;
    valueSelect.innerHTML = `<option value="">Pick genre…</option>`;
    Object.keys(SUBGENRES).forEach(g => {
        valueSelect.innerHTML += `<option value="${g}">${g}</option>`;
    });
    subSelect.style.display = "none";
    controls.style.gridTemplateColumns = "minmax(0,1fr) auto";
}

document.getElementById("compare-value")?.addEventListener("change", function () {
    const subSelect = document.getElementById("compare-sub-value");
    if (!subSelect) return;
    if (this.value) {
        populateCompareSubOptions(this.value);
    } else {
        subSelect.style.display = "none";
        document.getElementById("compare-controls").style.gridTemplateColumns = "minmax(0,1fr) auto";
    }
});

populateCompareValueOptions();

// ----------------------------
// Home: Genre Trend Chart
// ----------------------------

let genreChart = null;

const GENRE_COLORS = {
    "Action":     "#1781FF",
    "Adventure":  "#5eaaff",
    "Casual":     "#e05298",
    "Indie":      "#4ade80",
    "RPG":        "#d4a45a",
    "Simulation": "#38bdf8",
    "Strategy":   "#f87171",
    "Sports":     "#a57cd4",
    "Racing":     "#fbbf24"
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

    const subtitleEl = document.getElementById("chart-subtitle");

    if (labels.length === 0) {
        canvas.parentElement.innerHTML = `<p class="chart-empty">No trend data yet — run daily_snapshot.py to build history.</p>`;
        if (subtitleEl) subtitleEl.textContent = "";
        return;
    }

    if (subtitleEl) {
        const totalPlayers = genres.reduce((sum, g) => {
            const pts = trend[g] || [];
            return sum + (pts.length ? pts[pts.length - 1].players : 0);
        }, 0);
        subtitleEl.textContent = `${formatNumber(totalPlayers)} players across ${genres.length} genres · ${labels.length} day${labels.length !== 1 ? "s" : ""} tracked`;
    }

    const ctx = canvas.getContext("2d");

    const datasets = genres.map(genre => {
        const byDate = Object.fromEntries((trend[genre] || []).map(p => [p.date, p.players]));
        const color = GENRE_COLORS[genre];

        const gradient = ctx.createLinearGradient(0, 0, 0, 280);
        gradient.addColorStop(0, color + "30");
        gradient.addColorStop(1, color + "00");

        return {
            label:            genre,
            data:             labels.map(d => byDate[d] ?? null),
            borderColor:      color,
            backgroundColor:  gradient,
            borderWidth:      2.5,
            pointRadius:      0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: color,
            pointHoverBorderColor: "#fff",
            pointHoverBorderWidth: 2,
            fill: true,
            tension: 0.4,
            spanGaps: true
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
                legend: { display: false },
                tooltip: {
                    backgroundColor: "rgba(10, 14, 19, 0.95)",
                    borderColor: "rgba(23, 129, 255, 0.2)",
                    borderWidth: 1,
                    padding: { top: 10, bottom: 10, left: 14, right: 14 },
                    cornerRadius: 10,
                    titleFont: { family: "'RNS Sans', sans-serif", size: 12, weight: "600" },
                    titleColor: "#E7EFF7",
                    bodyFont: { family: "'RNS Sans', sans-serif", size: 11 },
                    bodyColor: "#7a8da3",
                    bodySpacing: 4,
                    boxWidth: 8,
                    boxHeight: 8,
                    boxPadding: 4,
                    usePointStyle: true,
                    pointStyle: "circle",
                    callbacks: {
                        title: items => items[0]?.label || "",
                        label: ctx => `  ${ctx.dataset.label}   ${formatNumber(ctx.parsed.y)} players`
                    }
                }
            },
            scales: {
                x: {
                    border: { display: false },
                    ticks: {
                        color: "#3a506e",
                        font: { family: "'RNS Sans', sans-serif", size: 10 },
                        autoSkip: false,
                        maxRotation: 60,
                        minRotation: 45,
                    },
                    grid: { display: false }
                },
                y: {
                    border: { display: false },
                    ticks: {
                        color: "#3a506e",
                        font: { family: "'RNS Sans', sans-serif", size: 10 },
                        callback: v => formatNumber(v),
                        maxTicksLimit: 5
                    },
                    grid: { color: "rgba(255,255,255,0.03)", drawTicks: false }
                }
            }
        }
    });

    buildChartLegend(genres, datasets);
}

function buildChartLegend(genres, datasets) {
    const container = document.getElementById("chart-legend");
    if (!container) return;
    container.innerHTML = "";

    genres.forEach((genre, i) => {
        const item = document.createElement("button");
        item.className = "chart-legend-item";
        item.innerHTML = `<span class="chart-legend-dot" style="background:${GENRE_COLORS[genre]}"></span>${genre}`;
        item.addEventListener("click", () => {
            const meta = genreChart.getDatasetMeta(i);
            meta.hidden = !meta.hidden;
            item.classList.toggle("dimmed", meta.hidden);
            genreChart.update();
        });
        container.appendChild(item);
    });
}

loadOverview();

// ----------------------------
// Home: Insight Search
// ----------------------------

const heroInput    = document.getElementById("hero-input");
const heroSend     = document.getElementById("hero-send");
const heroResponse = document.getElementById("hero-response");
const preferredAiTool = document.getElementById("preferred-ai-tool");
const briefModeSelect = document.getElementById("brief-mode-select");
const conceptInput = document.getElementById("concept-input");
const conceptAnalyzeBtn = document.getElementById("concept-analyze");
const conceptResults = document.getElementById("concept-results");
const AI_TOOL_STORAGE_KEY = "goingIndie.preferredAiTool";
const BRIEF_MODE_STORAGE_KEY = "goingIndie.briefMode";
let activeCompareState = null;
let latestConceptAnalysis = null;

function readPreferredAiTool() {
    try {
        return localStorage.getItem(AI_TOOL_STORAGE_KEY);
    } catch (err) {
        return null;
    }
}

function savePreferredAiTool(value) {
    try {
        localStorage.setItem(AI_TOOL_STORAGE_KEY, value);
    } catch (err) {
        console.warn("Could not save AI preference locally.", err);
    }
}

function getPreferredAiTool() {
    return readPreferredAiTool() || preferredAiTool?.value || "claude";
}

function getPreferredAiLabel() {
    const selected = preferredAiTool?.selectedOptions?.[0];
    return selected?.textContent || "AI";
}

function readBriefMode() {
    try {
        return localStorage.getItem(BRIEF_MODE_STORAGE_KEY);
    } catch (err) {
        return null;
    }
}

function saveBriefMode(value) {
    try {
        localStorage.setItem(BRIEF_MODE_STORAGE_KEY, value);
    } catch (err) {
        console.warn("Could not save brief mode locally.", err);
    }
}

function getBriefMode() {
    // The dropdown is the live source of truth: it's seeded from the saved
    // preference on load, then kept current by auto-detection or a manual
    // pick as the user types — so it should win over the stored default,
    // not the other way around.
    return briefModeSelect?.value || readBriefMode() || "general";
}

// Mirrors BRIEF_MODES in helpers.py — used for the on-page hint text only.
const BRIEF_MODE_DESCRIPTIONS = {
    general: "A rounded market read: demand, competition, pricing, risk, and opportunity.",
    quick: "A short, direct answer built from the 3-5 most decision-useful data points.",
    competition: "Focused on competitor shape, benchmark titles, and where to differentiate.",
    pricing: "Focused on pricing, review-score targets, wishlist signals, and launch timing.",
};

// Keyword hints used to auto-pick a brief mode from what's typed. Checked in
// this order (quick > pricing > competition) since a question can plausibly
// match more than one — brevity intent and launch/pricing topics are treated
// as stronger signals than a passing mention of competitors.
const MODE_KEYWORDS = {
    quick: ["quick", "quickly", "briefly", "short answer", "tl;dr", "tldr", "just tell me", "in a sentence"],
    pricing: ["price", "pricing", "cost", "charge", "review score", "wishlist", "launch", "revenue", "how much"],
    competition: ["competitor", "competitors", "compete", "competition", "rival", "benchmark", "similar games", "who else"],
};

function detectBriefMode(text) {
    const lowered = (text || "").toLowerCase();
    if (!lowered.trim()) return null;
    for (const mode of ["quick", "pricing", "competition"]) {
        if (MODE_KEYWORDS[mode].some(kw => lowered.includes(kw))) return mode;
    }
    return null;
}

function updateBriefModeHint(isAuto = false) {
    const hint = document.getElementById("brief-mode-hint");
    const badge = document.getElementById("brief-mode-auto-badge");
    const mode = briefModeSelect?.value || "general";
    if (hint) hint.textContent = BRIEF_MODE_DESCRIPTIONS[mode] || "";
    if (badge) badge.classList.toggle("hidden", !isAuto);
}

function syncPreferredAiTool() {
    if (!preferredAiTool) return;
    const saved = readPreferredAiTool();
    if (saved && [...preferredAiTool.options].some(option => option.value === saved)) {
        preferredAiTool.value = saved;
    }
}

syncPreferredAiTool();
if (briefModeSelect) {
    const savedMode = readBriefMode();
    if (savedMode && [...briefModeSelect.options].some(option => option.value === savedMode)) {
        briefModeSelect.value = savedMode;
    }
    updateBriefModeHint();
}

preferredAiTool?.addEventListener("change", () => {
    savePreferredAiTool(preferredAiTool.value);
});

briefModeSelect?.addEventListener("change", () => {
    saveBriefMode(briefModeSelect.value);
    updateBriefModeHint(false);
});

async function sendHeroMessage() {
    const message = (isSuggestedQuestion ? currentSuggestedQuestion : heroInput.value).trim();
    if (!message) return;

    // Match on the text itself, not just the isSuggestedQuestion flag — that
    // flag only reflects whether the typewriter/chip put this text in the
    // box, so typing (or pasting) the exact same question yourself would
    // otherwise silently lose the suggestion's known genre/tag/mode and fall
    // back to free-text inference, which can easily resolve to nothing.
    const matchedSuggestion = SUGGESTIONS.find(s => s.text === message);
    const suggestionContext = matchedSuggestion
        ? { genre: matchedSuggestion.genre || null, tag: matchedSuggestion.tag || null, mode: matchedSuggestion.mode || null }
        : null;

    acceptSuggestedQuestion();
    heroInput.value = message;
    heroSend.disabled  = true;
    heroSend.textContent = "…";
    heroResponse.classList.remove("hidden");

    try {
        const openedNewTab = copyChatGptBrief(message, suggestionContext);
        heroResponse.innerHTML = `
            <div class="hero-question">${escapeHtml(message)}</div>
            <div class="hero-answer">
                <p>${openedNewTab ? "Opened a brief loader tab." : "Your browser blocked the new tab."}</p>
                <p>It will copy the Steam market brief first, then move that tab to ${escapeHtml(getPreferredAiLabel())}.</p>
            </div>
        `;
        if (!openedNewTab) showPopupBlockedNotice(() => copyChatGptBrief(message, suggestionContext));
    } catch (err) {
        heroResponse.innerHTML = `<p style="color:var(--negative)">Could not open the AI brief loader.</p>`;
    } finally {
        heroSend.disabled = false;
        heroSend.textContent = "Ask AI";
    }
}

heroSend.addEventListener("click", sendHeroMessage);
heroInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendHeroMessage();
});

// Each suggestion carries the genre/tag its brief should resolve to, so
// clicking it doesn't depend on the server guessing a market from free text
// (that guess can miss — e.g. "FPS" never matches the tag "First-Person
// Shooter" — and generic strategy questions like "what review score should
// I target" mention no market at all, guaranteeing an unresolved brief).
// Cross-market questions (genre rankings, prominence, "tags doing well")
// intentionally have no genre/tag: those are answered from aggregate data
// that isn't scoped to a single market, and forcing one would narrow it.
// Concept-comparison questions ("audience for my game") intentionally have
// no genre/tag either: they need a concept description, not a market pick.
const SUGGESTIONS = [
    { text: "Ask AI which Steam genres look strongest right now" },
    { text: "Ask AI which Steam markets feel underserved" },
    { text: "Ask AI what genres are less prominent right now" },
    { text: "Ask AI whether cozy games are still growing", tag: "Cozy" },
    { text: "Ask AI whether FPS is oversaturated", tag: "First-Person Shooter" },
    { text: "Ask AI how competitive roguelikes are", tag: "Roguelike" },
    { text: "Ask AI about the metroidvania market", tag: "Metroidvania" },
    { text: "Ask AI how city builders perform on Steam", tag: "City Builder" },
    { text: "Ask AI about the survival game opportunity", tag: "Survival" },
    { text: "Ask AI whether horror games are profitable", tag: "Horror" },
    { text: "Ask AI what subgenres fit a solo developer best", genre: "Indie" },
    { text: "Ask AI which tags attract the same audience as my game" },
    { text: "Ask AI what audience usually buys games like this on Steam" },
    { text: "Ask AI which player tags overlap most with cozy players", tag: "Cozy" },
    { text: "Ask AI how I should position my game for the right Steam audience" },
    { text: "Ask AI what price range works best for indie strategy games", genre: "Strategy", mode: "pricing" },
    { text: "Ask AI for indie pricing advice", genre: "Indie", mode: "pricing" },
    { text: "Ask AI what review score I should target", genre: "Indie", mode: "pricing" },
    { text: "Ask AI how many wishlists I need before launch", genre: "Indie", mode: "pricing" },
    { text: "Ask AI what a strong revenue outcome looks like in my market", genre: "Indie", mode: "pricing" },
    { text: "Ask AI how crowded my genre is compared with similar subgenres", genre: "Indie" },
    { text: "Ask AI whether I should focus on a niche tag or a broader genre", genre: "Indie" },
    { text: "Ask AI which competitors I should study before launch", genre: "Indie", mode: "competition" },
    { text: "Ask AI what kind of market this concept would fit into" },
    { text: "Ask AI whether my game sounds more premium or niche" },
    { text: "Ask AI what risks stand out in this Steam market", genre: "Indie" },
    { text: "Ask AI what opportunity signals matter most before Next Fest", genre: "Indie", mode: "pricing" },
    { text: "Ask AI whether a demo is more important in this genre", genre: "Indie", mode: "pricing" },
    { text: "Ask AI what tags are doing well with players right now" },
    { text: "Ask AI about average indie RPG revenue", genre: "RPG" },
];

let suggestionTimer = null;
let isSuggestedQuestion = false;
let currentSuggestedQuestion = "";
let suggestionQueue = [];

function refillSuggestionQueue() {
    suggestionQueue = [...SUGGESTIONS];

    for (let i = suggestionQueue.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [suggestionQueue[i], suggestionQueue[j]] = [suggestionQueue[j], suggestionQueue[i]];
    }

    if (suggestionQueue.length > 1 && suggestionQueue[0].text === currentSuggestedQuestion) {
        [suggestionQueue[0], suggestionQueue[1]] = [suggestionQueue[1], suggestionQueue[0]];
    }
}

function setRandomSuggestion() {
    if (suggestionQueue.length === 0) refillSuggestionQueue();
    startSuggestedQuestion(suggestionQueue.shift());
}

function startSuggestedQuestion(suggestion) {
    clearInterval(suggestionTimer);
    heroInput.value = "";
    heroInput.classList.add("suggested");
    isSuggestedQuestion = true;
    currentSuggestedQuestion = suggestion.text;

    const text = suggestion.text;
    let i = 0;
    suggestionTimer = setInterval(() => {
        if (!isSuggestedQuestion) {
            clearInterval(suggestionTimer);
            return;
        }

        heroInput.value = text.slice(0, i + 1);
        i += 1;

        if (i >= text.length) clearInterval(suggestionTimer);
    }, 26);
}

function clearSuggestedQuestion() {
    clearInterval(suggestionTimer);
    if (isSuggestedQuestion) heroInput.value = "";
    isSuggestedQuestion = false;
    heroInput.classList.remove("suggested");
}

function acceptSuggestedQuestion() {
    clearInterval(suggestionTimer);
    isSuggestedQuestion = false;
    heroInput.classList.remove("suggested");
}

setRandomSuggestion();

heroInput.addEventListener("keydown", (e) => {
    if (!isSuggestedQuestion) return;
    if (e.key === "Enter") return;

    const isTypingKey = e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey;
    const isDeleteKey = e.key === "Backspace" || e.key === "Delete";
    if (isTypingKey || isDeleteKey) clearSuggestedQuestion();
});

heroInput.addEventListener("paste", clearSuggestedQuestion);

// Auto-pick a brief mode as the user types their own question. Only runs
// for real user input — the suggested-question typewriter effect assigns
// heroInput.value directly, which doesn't fire "input" events, so it can't
// fight with a suggestion's own explicit mode (see SUGGESTIONS below).
heroInput.addEventListener("input", () => {
    if (isSuggestedQuestion || !briefModeSelect) return;
    const detected = detectBriefMode(heroInput.value);
    if (detected) {
        briefModeSelect.value = detected;
        updateBriefModeHint(true);
    } else if (!heroInput.value.trim()) {
        // Box is empty again — fall back to the saved/default mode instead
        // of leaving an earlier auto-pick stuck in place.
        briefModeSelect.value = readBriefMode() || "general";
        updateBriefModeHint(false);
    }
});

// Home button
document.getElementById("home-btn").addEventListener("click", (e) => {
    e.preventDefault();
    clearActiveGenre();
    document.getElementById("overview-section").classList.remove("hidden");
    document.getElementById("market-section").classList.add("hidden");
    document.getElementById("results-header").classList.add("hidden");
    document.getElementById("results-grid").innerHTML = "";
    document.getElementById("pagination").innerHTML = "";
    document.getElementById("no-results").classList.add("hidden");
    document.getElementById("detail-panel").classList.add("hidden");
    const toolbar = document.getElementById("results-toolbar");
    if (toolbar) toolbar.remove();
    const filterRow = document.getElementById("filter-row");
    if (filterRow) filterRow.remove();
    heroResponse.classList.add("hidden");
    heroInput.value = "";
    setRandomSuggestion();
    document.querySelector(".main-content").scrollTo({ top: 0, behavior: "smooth" });
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
let activeBriefContext = {};

function clearActiveGenre() {
    document.querySelectorAll(".genre-item").forEach(i => i.classList.remove("active"));
    const existing = document.querySelector(".subgenre-nav");
    if (existing) existing.remove();
    activeGenre = null;
    activeBriefContext = {};
    activeCompareState = null;
    document.getElementById("compare-results")?.classList.add("hidden");
    document.getElementById("market-explainer")?.classList.add("hidden");
    renderFollowUpPrompts([]);
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

        if (genre === "__coming_soon__") {
            openComingSoon(item);
            return;
        }

        fetchGames(`/api/games/genre/${encodeURIComponent(genre)}`, `${genre} Games`);
        fetchMarketOverview(genre);
        loadSubgenres(genre, item);
    });
});

function loadSubgenres(genre, afterElement) {
    const nav = document.createElement("div");
    nav.className = "subgenre-nav";
    nav.innerHTML = `<span class="subgenre-loading">${randomQuip(genre)}</span>`;
    afterElement.after(nav);

    fetch(`/api/subgenres/${encodeURIComponent(genre)}`)
        .then(res => res.json())
        .then(available => {
            nav.innerHTML = "";
            if (available.length === 0) { nav.remove(); return; }

            const childTags = new Set(
                available.flatMap(item => item.children || [])
            );
            const topLevel = available.filter(item => !childTags.has(item.tag));

            const clearActiveSubgenres = () => {
                document.querySelectorAll(".subgenre-nav-item, .subgenre-child-item").forEach(el => el.classList.remove("active"));
            };

            topLevel.forEach(({ tag, count, has_children }) => {
                const group = document.createElement("div");
                group.className = "subgenre-group";
                group.dataset.parentTag = tag;

                const row = document.createElement("div");
                row.className = "subgenre-row";

                const btn = document.createElement("button");
                btn.className = "subgenre-nav-item";
                btn.innerHTML = `<span class="subgenre-nav-name">${tag}</span><span class="subgenre-nav-count">${count}</span>`;
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    clearActiveSubgenres();
                    btn.classList.add("active");
                    fetchGames(`/api/games/tag/${encodeURIComponent(tag)}?genre=${encodeURIComponent(genre)}`, `${tag} Games`);
                    fetchMarketOverview(tag, { level: "subgenre", parentGenre: genre, hasChildren: has_children });
                    if (has_children) group.classList.add("expanded");
                });
                row.appendChild(btn);

                let childrenWrap = null;
                let toggle = null;
                if (has_children) {
                    toggle = document.createElement("button");
                    toggle.type = "button";
                    toggle.className = "subgenre-expand-btn";
                    toggle.setAttribute("aria-label", `Show ${tag} child subgenres`);
                    toggle.innerHTML = `<span class="subgenre-expand-icon">⌄</span>`;
                    toggle.addEventListener("click", async (e) => {
                        e.stopPropagation();
                        if (!group.dataset.childrenLoaded) {
                            await loadChildSubgenres(group, genre, tag);
                        }
                        if (group.dataset.childCount === "0") return;
                        group.classList.toggle("expanded");
                    });
                    row.appendChild(toggle);

                    childrenWrap = document.createElement("div");
                    childrenWrap.className = "subgenre-children";
                }

                group.appendChild(row);
                if (childrenWrap) group.appendChild(childrenWrap);
                nav.appendChild(group);

                if (has_children) {
                    loadChildSubgenres(group, genre, tag, toggle);
                }
            });
        });
}

async function loadChildSubgenres(group, genre, parentTag, toggleBtn = null) {
    const toggle = toggleBtn || group.querySelector(".subgenre-expand-btn");
    const wrap = group.querySelector(".subgenre-children");
    if (!wrap || group.dataset.childrenLoaded) return;

    wrap.innerHTML = `<span class="subgenre-loading">${randomQuip()}</span>`;

    try {
        const res = await fetch(`/api/insights/subgenre-children?genre=${encodeURIComponent(genre)}&subgenre=${encodeURIComponent(parentTag)}`);
        if (!res.ok) throw new Error("Could not load child subgenres");
        const data = await res.json();
        const items = data.children_found || [];
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = String(items.length);
        wrap.innerHTML = "";

        if (!items.length) {
            if (toggle) toggle.remove();
            wrap.remove();
            return;
        }

        items.forEach((item) => {
            const childTag = item.market;
            const childBtn = document.createElement("button");
            childBtn.type = "button";
            childBtn.className = "subgenre-child-item";
            childBtn.innerHTML = `<span class="subgenre-child-name">${childTag}</span><span class="subgenre-nav-count">${item.total_games}</span>`;
            childBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                document.querySelectorAll(".subgenre-nav-item, .subgenre-child-item").forEach(el => el.classList.remove("active"));
                childBtn.classList.add("active");
                group.classList.add("expanded");
                fetchGames(`/api/games/tag/${encodeURIComponent(childTag)}?genre=${encodeURIComponent(genre)}`, `${childTag} Games`);
                fetchMarketOverview(childTag, { level: "child", parentGenre: genre, parentTag });
            });
            wrap.appendChild(childBtn);
        });
    } catch (err) {
        console.error("Child subgenre load failed:", err);
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = "0";
        if (toggle) toggle.remove();
        wrap.remove();
    }
}

// ----------------------------
// Coming Soon Nav (sidebar) — genre -> subgenre -> sub-subgenre, sourced
// from the coming-soon tracker (upcoming_games) instead of the main paid
// catalog. Reuses the same subgenre-nav visual classes at one extra level
// of nesting so it looks and behaves like the regular genre tree.
// ----------------------------

let comingSoonFilter = { genre: null, tag: null };
let comingSoonPage = 0;
const COMING_SOON_LIMIT = 30;

function clearActiveComingSoonNav() {
    document.querySelectorAll(".cs-nav-item").forEach(el => el.classList.remove("active"));
}

function openComingSoon(afterElement) {
    comingSoonFilter = { genre: null, tag: null };
    comingSoonPage = 0;

    document.getElementById("market-section").classList.add("hidden");
    document.getElementById("results-toolbar")?.remove();
    document.getElementById("filter-row")?.remove();

    loadComingSoonTree(afterElement);
    fetchComingSoonGames("Coming Soon — All Genres");
}

function loadComingSoonTree(afterElement) {
    const nav = document.createElement("div");
    nav.className = "subgenre-nav coming-soon-tree";
    nav.innerHTML = `<span class="subgenre-loading">Loading coming-soon genres…</span>`;
    afterElement.after(nav);

    fetch("/api/coming-soon/genres")
        .then(res => res.json())
        .then(data => {
            nav.innerHTML = "";
            const genres = data.genres || [];
            if (genres.length === 0) {
                nav.innerHTML = `<span class="subgenre-loading">No coming-soon games tracked yet.</span>`;
                return;
            }

            genres.forEach(({ genre, count }) => {
                const group = document.createElement("div");
                group.className = "subgenre-group";

                const row = document.createElement("div");
                row.className = "subgenre-row";

                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "subgenre-nav-item cs-nav-item";
                btn.innerHTML = `<span class="subgenre-nav-name">${genre}</span><span class="subgenre-nav-count">${count}</span>`;
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    clearActiveComingSoonNav();
                    btn.classList.add("active");
                    comingSoonFilter = { genre, tag: null };
                    comingSoonPage = 0;
                    fetchComingSoonGames(`Coming Soon — ${genre}`);
                    group.classList.add("expanded");
                });
                row.appendChild(btn);

                const toggle = document.createElement("button");
                toggle.type = "button";
                toggle.className = "subgenre-expand-btn";
                toggle.setAttribute("aria-label", `Show ${genre} subgenres`);
                toggle.innerHTML = `<span class="subgenre-expand-icon">⌄</span>`;
                toggle.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    if (!group.dataset.childrenLoaded) {
                        await loadComingSoonSubgenres(group, genre);
                    }
                    if (group.dataset.childCount === "0") return;
                    group.classList.toggle("expanded");
                });
                row.appendChild(toggle);

                const childrenWrap = document.createElement("div");
                childrenWrap.className = "subgenre-children";

                group.appendChild(row);
                group.appendChild(childrenWrap);
                nav.appendChild(group);

                loadComingSoonSubgenres(group, genre, toggle);
            });
        })
        .catch(err => {
            console.error("Coming-soon genre load failed:", err);
            nav.innerHTML = `<span class="subgenre-loading">Could not load coming-soon genres.</span>`;
        });
}

async function loadComingSoonSubgenres(group, genre, toggleBtn = null) {
    const wrap = group.querySelector(".subgenre-children");
    if (!wrap || group.dataset.childrenLoaded) return;

    wrap.innerHTML = `<span class="subgenre-loading">Loading…</span>`;

    try {
        const res = await fetch(`/api/coming-soon/subgenres/${encodeURIComponent(genre)}`);
        if (!res.ok) throw new Error("Could not load coming-soon subgenres");
        const items = await res.json();
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = String(items.length);
        wrap.innerHTML = "";

        if (!items.length) {
            if (toggleBtn) toggleBtn.remove();
            wrap.remove();
            return;
        }

        items.forEach(({ tag, count, has_children }) => {
            const subGroup = document.createElement("div");
            subGroup.className = "subgenre-group";

            const subRow = document.createElement("div");
            subRow.className = "subgenre-row";

            const subBtn = document.createElement("button");
            subBtn.type = "button";
            subBtn.className = "subgenre-child-item cs-nav-item";
            subBtn.innerHTML = `<span class="subgenre-child-name">${tag}</span><span class="subgenre-nav-count">${count}</span>`;
            subBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                clearActiveComingSoonNav();
                subBtn.classList.add("active");
                comingSoonFilter = { genre, tag };
                comingSoonPage = 0;
                fetchComingSoonGames(`Coming Soon — ${tag}`);
                if (has_children) subGroup.classList.add("expanded");
            });
            subRow.appendChild(subBtn);

            let subToggle = null;
            let subChildrenWrap = null;
            if (has_children) {
                subToggle = document.createElement("button");
                subToggle.type = "button";
                subToggle.className = "subgenre-expand-btn";
                subToggle.setAttribute("aria-label", `Show ${tag} child subgenres`);
                subToggle.innerHTML = `<span class="subgenre-expand-icon">⌄</span>`;
                subToggle.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    if (!subGroup.dataset.childrenLoaded) {
                        await loadComingSoonChildren(subGroup, genre, tag);
                    }
                    if (subGroup.dataset.childCount === "0") return;
                    subGroup.classList.toggle("expanded");
                });
                subRow.appendChild(subToggle);

                subChildrenWrap = document.createElement("div");
                subChildrenWrap.className = "subgenre-children";
            }

            subGroup.appendChild(subRow);
            if (subChildrenWrap) subGroup.appendChild(subChildrenWrap);
            wrap.appendChild(subGroup);

            if (has_children) {
                loadComingSoonChildren(subGroup, genre, tag, subToggle);
            }
        });
    } catch (err) {
        console.error("Coming-soon subgenre load failed:", err);
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = "0";
        if (toggleBtn) toggleBtn.remove();
        wrap.remove();
    }
}

async function loadComingSoonChildren(group, genre, parentTag, toggleBtn = null) {
    const wrap = group.querySelector(".subgenre-children");
    if (!wrap || group.dataset.childrenLoaded) return;

    wrap.innerHTML = `<span class="subgenre-loading">Loading…</span>`;

    try {
        const res = await fetch(`/api/coming-soon/subgenre-children?genre=${encodeURIComponent(genre)}&subgenre=${encodeURIComponent(parentTag)}`);
        if (!res.ok) throw new Error("Could not load coming-soon child subgenres");
        const data = await res.json();
        const items = data.children_found || [];
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = String(items.length);
        wrap.innerHTML = "";

        if (!items.length) {
            if (toggleBtn) toggleBtn.remove();
            wrap.remove();
            return;
        }

        items.forEach((item) => {
            const childTag = item.market;
            const childBtn = document.createElement("button");
            childBtn.type = "button";
            childBtn.className = "subgenre-child-item cs-nav-item";
            childBtn.innerHTML = `<span class="subgenre-child-name">${childTag}</span><span class="subgenre-nav-count">${item.total_games}</span>`;
            childBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                clearActiveComingSoonNav();
                childBtn.classList.add("active");
                comingSoonFilter = { genre, tag: childTag };
                comingSoonPage = 0;
                fetchComingSoonGames(`Coming Soon — ${childTag}`);
            });
            wrap.appendChild(childBtn);
        });
    } catch (err) {
        console.error("Coming-soon child subgenre load failed:", err);
        group.dataset.childrenLoaded = "true";
        group.dataset.childCount = "0";
        if (toggleBtn) toggleBtn.remove();
        wrap.remove();
    }
}

async function fetchComingSoonGames(title) {
    document.getElementById("results-title").textContent = title;
    document.getElementById("results-header").classList.remove("hidden");

    const grid = document.getElementById("results-grid");
    grid.innerHTML = `<div class="loading-state"><div class="chat-typing"><span></span><span></span><span></span></div><p class="loading-quip">Gathering what's coming soon…</p></div>`;
    document.getElementById("no-results").classList.add("hidden");
    document.getElementById("pagination").innerHTML = "";

    const params = new URLSearchParams();
    if (comingSoonFilter.genre) params.set("genre", comingSoonFilter.genre);
    if (comingSoonFilter.tag) params.set("tag", comingSoonFilter.tag);
    params.set("page", String(comingSoonPage));
    params.set("limit", String(COMING_SOON_LIMIT));

    try {
        const res = await fetch(`/api/coming-soon/games?${params.toString()}`);
        const data = await res.json();
        const games = data.games || [];
        const total = data.total || 0;

        grid.innerHTML = "";
        if (games.length === 0) {
            document.getElementById("no-results").classList.remove("hidden");
            document.getElementById("results-count").textContent = "0 games";
        } else {
            document.getElementById("no-results").classList.add("hidden");
            games.forEach(game => grid.appendChild(buildUpcomingCard(game)));
            const start = comingSoonPage * COMING_SOON_LIMIT;
            const end = Math.min(start + games.length, total);
            document.getElementById("results-count").textContent =
                `${start + 1}–${end} of ${total.toLocaleString()} games`;
        }

        renderComingSoonPagination(total, title);
    } catch (err) {
        console.error("Coming-soon games fetch failed:", err);
        grid.innerHTML = "";
        document.getElementById("no-results").classList.remove("hidden");
    }
}

function renderComingSoonPagination(total, title) {
    const pager = document.getElementById("pagination");
    pager.innerHTML = "";
    const totalPages = Math.max(1, Math.ceil(total / COMING_SOON_LIMIT));
    if (totalPages <= 1) return;

    const prevBtn = document.createElement("button");
    prevBtn.className = "page-btn";
    prevBtn.textContent = "‹ Prev";
    prevBtn.disabled = comingSoonPage <= 0;
    prevBtn.addEventListener("click", () => {
        comingSoonPage = Math.max(0, comingSoonPage - 1);
        fetchComingSoonGames(title);
    });

    const label = document.createElement("span");
    label.className = "page-ellipsis";
    label.textContent = `Page ${comingSoonPage + 1} of ${totalPages}`;

    const nextBtn = document.createElement("button");
    nextBtn.className = "page-btn";
    nextBtn.textContent = "Next ›";
    nextBtn.disabled = comingSoonPage >= totalPages - 1;
    nextBtn.addEventListener("click", () => {
        comingSoonPage = Math.min(totalPages - 1, comingSoonPage + 1);
        fetchComingSoonGames(title);
    });

    pager.appendChild(prevBtn);
    pager.appendChild(label);
    pager.appendChild(nextBtn);
}

// ----------------------------
// Market Overview
// ----------------------------

function marketDepthConfig(level, data, name, parentGenre = "", parentTag = "") {
    const hasChildren = arguments[5] || false;
    const sampleSize = data.sample_notes?.paid_revenue_sample_size || data.paid_games || 0;
    const confidence = formatConfidence(data.confidence);
    const captureLow = data.realistic_revenue_target?.conservative ?? data.SOM?.low;
    const captureHigh = data.realistic_revenue_target?.expected ?? data.SOM?.high;
    const strongOutcome = data.realistic_revenue_target?.strong;
    const sharedStats = `
        <div class="market-stats">
            <span>${data.total_games} total games</span>
            <span>${data.paid_games} paid</span>
            <span>Avg ${formatMoney(data.avg_price)}</span>
            <span>${data.avg_review_score}% positive</span>
        </div>
    `;

    if (level === "genre") {
        return {
            title: `${name} Market`,
            primaryLabel: "Total Addressable Market",
            primaryValue: `${formatMoney(data.TAM.low)} - ${formatMoney(data.TAM.high)}`,
            primaryDesc: `This is the broadest market size estimate for ${name} on Steam. Use this as the top-of-funnel ceiling before narrowing into a specific player segment.`,
            context: `${name} is the full genre view, so this area shows TAM instead of narrower SAM/SOM figures.`,
            cards: [
                {
                    label: "Games In Genre",
                    value: `${data.total_games}`,
                    desc: `${data.paid_games} paid games in sample`,
                },
                {
                    label: "Confidence",
                    value: confidence,
                    desc: `Based on sample size, paid-game coverage, and concentration among top performers.`,
                },
            ],
            sharedStats,
        };
    }

    if (level === "child") {
        return {
            title: `${name} Market`,
            primaryLabel: "Narrow Serviceable Market",
            primaryValue: `${formatMoney(data.SAM.low)} - ${formatMoney(data.SAM.high)}`,
            primaryDesc: `${name} is a more specific slice inside ${parentTag || parentGenre}. At this depth, the top market number shifts from TAM down to SAM so the estimate stays grounded in the reachable niche.`,
            context: `${parentGenre} -> ${parentTag} -> ${name}`,
            cards: [
                {
                    label: "Games In Niche",
                    value: `${data.total_games}`,
                    desc: `${data.paid_games} paid games in this narrower segment.`,
                },
                {
                    label: "Realistic Capture",
                    value: `${formatMoney(captureLow)} - ${formatMoney(captureHigh)}`,
                    desc: `Grounded indie capture range inside this narrow segment.`,
                },
                {
                    label: "Strong Outcome",
                    value: `${formatMoney(strongOutcome)}`,
                    desc: `75th percentile among comparable paid games in this segment.`,
                },
                {
                    label: "Confidence",
                    value: confidence,
                    desc: `${sampleSize} paid comps after trimming top outliers.`,
                },
            ],
            sharedStats,
        };
    }

    return {
        title: `${name} Market`,
        primaryLabel: "Subgenre Addressable Market",
        primaryValue: `${formatMoney(data.TAM.low)} - ${formatMoney(data.TAM.high)}`,
        primaryDesc: `${name} is narrower than ${parentGenre}, so this top number is a smaller TAM for the subgenre before stepping down to SAM and SOM.`,
        context: `${parentGenre} -> ${name}`,
        cards: hasChildren
            ? [
                {
                    label: "Games In Subgenre",
                    value: `${data.total_games}`,
                    desc: `${data.paid_games} paid games in this broader branch.`,
                },
                {
                    label: "Confidence",
                    value: confidence,
                    desc: `${sampleSize} paid comps after outlier trimming.`,
                },
            ]
            : [
                {
                    label: "Games In Subgenre",
                    value: `${data.total_games}`,
                    desc: `${data.paid_games} paid games in this subgenre.`,
                },
                {
                    label: "Serviceable Market",
                    value: `${formatMoney(data.SAM.low)} - ${formatMoney(data.SAM.high)}`,
                    desc: `Reachable market for this specific subgenre on Steam.`,
                },
                {
                    label: "Realistic Capture",
                    value: `${formatMoney(captureLow)} - ${formatMoney(captureHigh)}`,
                    desc: `More grounded capture range before the stronger upside case.`,
                },
                {
                    label: "Confidence",
                    value: confidence,
                    desc: `${sampleSize} paid comps after outlier trimming.`,
                },
            ],
        sharedStats,
    };
}

function renderMarketSummary(data, context) {
    const container = document.getElementById("market-grid");
    if (!container || !data) return;
    const config = marketDepthConfig(context.level, data, context.name, context.parentGenre, context.parentTag, context.hasChildren);

    const secondaryCards = config.cards.map(card => `
        <div class="market-card">
            <div class="market-label">${card.label}</div>
            <div class="market-value">${card.value}</div>
            <div class="market-desc">${card.desc}</div>
        </div>
    `).join("");

    container.innerHTML = `
        <div class="market-card market-card-primary">
            <div class="market-card-topline">
                <div class="market-label">${config.primaryLabel}</div>
                <div class="market-context">${config.context}</div>
            </div>
            <div class="market-value">${config.primaryValue}</div>
            <div class="market-desc">${config.primaryDesc}</div>
            ${config.sharedStats}
        </div>
        ${secondaryCards}
        <p class="steam-pc-note">Steam PC estimates only · Console, launcher, and MTX revenue not included</p>
    `;
}

async function fetchMarketOverview(name, options = {}) {
    const {
        level = "genre",
        parentGenre = null,
        parentTag = null,
        hasChildren = false,
    } = options;
    try {
        activeCompareState = null;
        const isSubgenre = level !== "genre";
        activeBriefContext = isSubgenre
            ? { genre: parentGenre || "", tag: name }
            : { genre: name, tag: "" };

        const marketGrid = document.getElementById("market-grid");
        if (marketGrid) marketGrid.innerHTML = `<div class="market-card market-card-primary"><p class="loading-quip" style="margin:0">${randomQuip(parentGenre || name)}</p></div>`;
        document.getElementById("market-section").classList.remove("hidden");

        let url = isSubgenre
            ? `/api/market/tag/${encodeURIComponent(name)}${parentGenre ? `?genre=${encodeURIComponent(parentGenre)}` : ""}`
            : `/api/market/genre/${encodeURIComponent(name)}`;

        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById("market-title").textContent = `${name} Market`;
        document.getElementById("market-section").classList.remove("hidden");
        renderMarketSummary(data, { level, name, parentGenre, parentTag, hasChildren });
        renderMarketExplainer(null);
        loadFollowUpPrompts();
        loadUpcoming(isSubgenre ? null : name, isSubgenre ? name : null);
    } catch (err) {
        console.error("Market fetch failed:", err);
    }
}

async function loadUpcoming(genre, tag) {
    const section = document.getElementById("upcoming-section");
    const grid = document.getElementById("upcoming-grid");
    const empty = document.getElementById("upcoming-empty");
    if (!section || !grid) return;

    try {
        const params = new URLSearchParams();
        if (genre) params.set("genre", genre);
        if (tag) params.set("tag", tag);
        params.set("limit", "12");

        const res = await fetch(`/api/market/upcoming?${params.toString()}`);
        if (!res.ok) { section.classList.add("hidden"); return; }
        const data = await res.json();

        section.classList.remove("hidden");
        const items = data.upcoming || [];

        if (items.length === 0) {
            grid.innerHTML = "";
            empty.classList.remove("hidden");
            return;
        }

        empty.classList.add("hidden");
        grid.innerHTML = "";
        items.forEach(game => grid.appendChild(buildUpcomingCard(game)));
    } catch (err) {
        console.error("Upcoming fetch failed:", err);
        section.classList.add("hidden");
    }
}

function buildUpcomingCard(game) {
    const price = game.price_current_usd > 0 ? `$${game.price_current_usd.toFixed(2)}` : "";
    const dev = (game.developer || [])[0] || "";
    const releaseDate = game.release_date_raw || "Date TBA";
    const storeUrl = game.store_url || "";

    const card = document.createElement("div");
    card.className = "upcoming-card";
    card.innerHTML = `
        <img src="${game.header_image_url || ''}" alt="${game.title}" onerror="this.style.display='none'">
        <div class="upcoming-card-body">
            <h4>${game.title}</h4>
            <div class="upcoming-meta">
                <span class="upcoming-date">${releaseDate}</span>
                ${price ? `<span>${price}</span>` : ""}
            </div>
            <div class="upcoming-dev">${dev}</div>
        </div>
    `;
    if (storeUrl) {
        card.addEventListener("click", () => window.open(storeUrl, "_blank"));
    }
    return card;
}

// ----------------------------
// AI Handoff
// ----------------------------

function copyChatGptBrief(userQuestion = "", contextOverride = null) {
    const params = new URLSearchParams();
    // A suggested question's own genre/tag (when it has one) takes priority
    // over whatever market the user happens to be browsing — the suggestion
    // was written for a specific market, so it should resolve to that one.
    const genre = contextOverride?.genre || activeBriefContext.genre;
    const tag = contextOverride?.tag || activeBriefContext.tag;
    if (genre) params.set("genre", genre);
    if (tag) params.set("tag", tag);
    if (userQuestion) params.set("q", userQuestion);
    params.set("mode", contextOverride?.mode || getBriefMode());
    if (activeCompareState?.right) {
        params.set("compare_type", activeCompareState.right.type);
        params.set("compare_value", activeCompareState.right.value);
        if (activeCompareState.right.genre) params.set("compare_genre", activeCompareState.right.genre);
    }
    if (latestConceptAnalysis?.description) params.set("concept", latestConceptAnalysis.description);
    params.set("ai_tool", getPreferredAiTool());

    const url = `/brief-loader${params.toString() ? "?" + params.toString() : ""}`;

    // Open only the loader tab here. We used to also pre-open a blank
    // placeholder tab for the AI tool, so the loader page could redirect it
    // later without tripping the popup blocker on a delayed window.open().
    // That trick backfired: the placeholder competed with this tab for
    // focus, and no amount of deferred .focus()/.blur() timing reliably won
    // that race — it kept landing on the blank tab instead of this one.
    // Since opening a *single* popup here needs no such workaround (nothing
    // else is competing for focus), and the loader page's own later
    // window.open() call for the AI tool works fine once popups are
    // allowed for the site (which is the same requirement the placeholder
    // trick had anyway), we just let the loader page open that tab itself
    // when the brief is ready. See openAiToolInNewTab() in brief_loader.html.
    const tab = window.open(url, "_blank");

    flashBriefButtons("Opening");

    if (tab) {
        tab.opener = null;
        tab.focus();
        return true;
    }

    // Popup blocked: never hijack the current tab to get there — the home
    // page must stay open. The caller shows a message asking the user to
    // allow popups instead.
    return false;
}

function getPopupPermissionSteps() {
    const ua = navigator.userAgent;
    if (ua.includes("Edg/")) {
        return "Click the icon left of the address bar → Site permissions → set Pop-ups and redirects to Allow.";
    }
    if (ua.includes("Firefox/")) {
        return "Click the shield/info icon left of the address bar and turn off pop-up blocking for this site.";
    }
    if (ua.includes("Chrome/")) {
        return "Click the icon left of the address bar → Site settings → set Pop-ups and redirects to Allow.";
    }
    return "Open your browser's site settings for this page and allow pop-ups and redirects.";
}

function showPopupBlockedNotice(retry) {
    document.getElementById("popup-blocked-toast")?.remove();

    const toast = document.createElement("div");
    toast.id = "popup-blocked-toast";
    toast.className = "popup-blocked-toast";
    toast.innerHTML = `
        <div class="popup-blocked-toast-title">
            <span>Pop-ups are blocked</span>
            <button type="button" class="popup-blocked-toast-close" aria-label="Dismiss">&times;</button>
        </div>
        <div class="popup-blocked-toast-body">Your browser blocked the brief loader tab. Allow pop-ups for this site once, and it'll open automatically every time after that.</div>
        <div class="popup-blocked-toast-steps">${escapeHtml(getPopupPermissionSteps())}</div>
        <div class="popup-blocked-toast-actions">
            <button type="button" class="popup-blocked-dismiss">Dismiss</button>
            <button type="button" class="popup-blocked-retry">Try Again</button>
        </div>
    `;
    document.body.appendChild(toast);

    const close = () => toast.remove();
    toast.querySelector(".popup-blocked-toast-close").addEventListener("click", close);
    toast.querySelector(".popup-blocked-dismiss").addEventListener("click", close);
    toast.querySelector(".popup-blocked-retry").addEventListener("click", () => {
        close();
        retry?.();
    });
}

async function writeClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch (err) {
            console.warn("navigator.clipboard failed; trying textarea fallback.", err);
        }
    }

    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const copied = document.execCommand("copy");
    ta.remove();
    if (!copied) throw new Error("Clipboard copy was blocked by the browser.");
}

function flashBriefButtons(label) {
    const buttons = [
        document.getElementById("copy-chatgpt-brief"),
        document.getElementById("chat-copy-brief")
    ].filter(Boolean);

    buttons.forEach(btn => {
        const original = btn.dataset.originalLabel || btn.textContent;
        btn.dataset.originalLabel = original;
        btn.textContent = label;
        btn.disabled = true;
        setTimeout(() => {
            btn.textContent = original;
            btn.disabled = false;
        }, 1500);
    });
}

document.getElementById("copy-chatgpt-brief")?.addEventListener("click", () => {
    if (!copyChatGptBrief()) showPopupBlockedNotice(() => copyChatGptBrief());
});
document.getElementById("chat-copy-brief")?.addEventListener("click", () => {
    if (!copyChatGptBrief()) showPopupBlockedNotice(() => copyChatGptBrief());
});

function renderFollowUpPrompts(prompts = []) {
    const container = document.getElementById("follow-up-prompts");
    if (!container) return;
    container.innerHTML = "";
    prompts.forEach(prompt => {
        const btn = document.createElement("button");
        btn.className = "follow-up-chip";
        btn.type = "button";
        btn.textContent = prompt;
        btn.addEventListener("click", () => {
            heroInput.value = prompt;
            clearSuggestedQuestion();
            sendHeroMessage();
        });
        container.appendChild(btn);
    });
}

function renderMarketExplainer(data) {
    const container = document.getElementById("market-explainer");
    if (!container) return;
    container.classList.add("hidden");
    container.innerHTML = "";
}

async function loadFollowUpPrompts(question = "") {
    if (!activeBriefContext.genre && !activeBriefContext.tag) return;
    const params = new URLSearchParams();
    if (activeBriefContext.genre) params.set("genre", activeBriefContext.genre);
    if (activeBriefContext.tag) params.set("tag", activeBriefContext.tag);
    if (question) params.set("q", question);
    try {
        const res = await fetch(`/api/insights/follow-ups?${params.toString()}`);
        if (!res.ok) return;
        const data = await res.json();
        renderFollowUpPrompts(data.prompts || []);
    } catch (err) {
        console.error("Follow-up prompt load failed:", err);
    }
}

function renderCompareResults(data) {
    const container = document.getElementById("compare-results");
    if (!container) return;
    container.classList.remove("hidden");
    container.innerHTML = `
        <div class="compare-grid">
            <div class="insight-card">
                <h4>${data.left.market}</h4>
                <p>${data.left.total_games} games · ${formatMoney(data.left.estimated_revenue_high)} est. market · ${data.left.avg_review_score_pct}% avg positive</p>
            </div>
            <div class="insight-card">
                <h4>${data.right.market}</h4>
                <p>${data.right.total_games} games · ${formatMoney(data.right.estimated_revenue_high)} est. market · ${data.right.avg_review_score_pct}% avg positive</p>
            </div>
            <div class="insight-card">
                <h4>Difference</h4>
                <p>Revenue: ${formatPct(data.delta.estimated_revenue_high_pct)} · Games: ${formatPct(data.delta.total_games_pct)} · Review score: ${signedNumber(data.delta.avg_review_score_pct)} pts</p>
            </div>
        </div>
    `;
    renderFollowUpPrompts(data.follow_up_prompts || []);
}

async function runCompare() {
    const genrePick = document.getElementById("compare-value")?.value;
    const tagPick   = document.getElementById("compare-sub-value")?.value;
    const isTag     = !!tagPick;
    const value     = isTag ? tagPick : genrePick;
    if (!genrePick || (!activeBriefContext.genre && !activeBriefContext.tag)) return;

    const btn = document.getElementById("compare-run");
    const originalLabel = btn?.textContent;
    if (btn) { btn.disabled = true; btn.textContent = randomQuip(genrePick || activeBriefContext.genre); }

    const params = new URLSearchParams();
    params.set("left_type", activeBriefContext.tag ? "tag" : "genre");
    params.set("left", activeBriefContext.tag || activeBriefContext.genre);
    if (activeBriefContext.tag && activeBriefContext.genre) params.set("left_genre", activeBriefContext.genre);
    params.set("right_type", isTag ? "tag" : "genre");
    params.set("right", value);
    if (isTag) params.set("right_genre", genrePick);

    const res = await fetch(`/api/insights/compare?${params.toString()}`);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const container = document.getElementById("compare-results");
        if (container) {
            container.classList.remove("hidden");
            container.innerHTML = `<p class="compare-error">${err.error || "No match found"} — couldn't load market data for "${value}".</p>`;
        }
        if (btn) { btn.disabled = false; btn.textContent = originalLabel; }
        return;
    }
    const data = await res.json();
    if (btn) { btn.disabled = false; btn.textContent = originalLabel; }
    activeCompareState = {
        left: {
            type: activeBriefContext.tag ? "tag" : "genre",
            value: activeBriefContext.tag || activeBriefContext.genre,
            genre: activeBriefContext.genre || "",
        },
        right: {
            type: isTag ? "tag" : "genre",
            value,
            genre: isTag ? genrePick : "",
        },
    };
    renderCompareResults(data);
}

function renderConceptResults(data) {
    conceptResults.classList.remove("hidden");
    latestConceptAnalysis = data;
    const market = data.likely_market?.market || "No clear market match yet";
    const confidence = data.likely_market?.confidence ? formatConfidence(data.likely_market.confidence) : "exploratory";
    const opportunities = (data.opportunities || []).slice(0, 3).map(item => `<li>${item.market}: ${item.signal}</li>`).join("");
    const followUps = (data.follow_up_prompts || []).slice(0, 4).map(prompt => `<button class="follow-up-chip" type="button">${prompt}</button>`).join("");
    conceptResults.innerHTML = `
        <div class="concept-grid">
            <div class="insight-card">
                <h3>Likely Market</h3>
                <p>${market}</p>
                <p>${confidence} confidence${data.inferred_context?.genre ? ` · Genre: ${data.inferred_context.genre}` : ""}${data.inferred_context?.tag ? ` · Tag: ${data.inferred_context.tag}` : ""}</p>
            </div>
            <div class="insight-card">
                <h3>Opportunity Read</h3>
                <ul>${opportunities || "<li>Describe a bit more about genre, tone, or mechanics to tighten this up.</li>"}</ul>
            </div>
            <div class="insight-card">
                <h3>What to Ask Next</h3>
                <div class="follow-up-prompts">${followUps}</div>
            </div>
        </div>
    `;
    conceptResults.querySelectorAll(".follow-up-chip").forEach((btn) => {
        btn.addEventListener("click", () => {
            const prompt = btn.textContent;
            heroInput.value = prompt;
            clearSuggestedQuestion();
            sendHeroMessage();
        });
    });
}

async function analyzeConcept() {
    const description = conceptInput?.value.trim();
    if (!description) return;
    conceptAnalyzeBtn.disabled = true;
    conceptAnalyzeBtn.textContent = "Analyzing...";
    try {
        const res = await fetch("/api/insights/concept", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description }),
        });
        if (!res.ok) return;
        const data = await res.json();
        renderConceptResults(data);
    } finally {
        conceptAnalyzeBtn.disabled = false;
        conceptAnalyzeBtn.textContent = "Analyze Concept";
    }
}

conceptAnalyzeBtn?.addEventListener("click", analyzeConcept);
document.getElementById("compare-run")?.addEventListener("click", runCompare);

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
    const nums = new Set([0, pages - 1, p, p - 1, p + 1, p + 2].filter(n => n >= 0 && n < pages));
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
                <option value="score">Sort: Review Score (% Positive)</option>
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
        <label>Min Review %: <input type="number" id="f-min-score" placeholder="e.g. 70" min="0" max="100" class="filter-input"></label>
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

const GENRE_QUIPS = {
    "Action": [
        "Counting explosions… there are a lot of explosions.",
        "Sorting 38,000 action heroes by how hard they punch.",
        "Dodging bullets while pulling your data…",
        "Loading. Don't worry, nobody respawns here.",
        "Wading through a sea of hack-and-slash titles…",
    ],
    "Adventure": [
        "Following the breadcrumb trail through thousands of adventures…",
        "Mapping every dungeon, cave, and mysterious island…",
        "Reading every journal entry so you don't have to.",
        "Consulting the ancient scroll of Steam data…",
        "Exploring the Adventure market. Watch out for traps.",
    ],
    "Casual": [
        "Matching tiles and counting coins… almost done.",
        "Rounding up every hidden object and cozy puzzle…",
        "Don't stress — we're almost done. Very on-brand for Casual.",
        "Counting match-3 levels. There are tens of thousands.",
        "Gathering all the chill games. This won't hurt.",
    ],
    "Indie": [
        "Listening to the chiptune soundtrack while we load…",
        "Sorting through every pixel art masterpiece on Steam…",
        "There are a LOT of Metroidvanias. Hang tight.",
        "Hand-crafting your results with love and lo-fi beats.",
        "Wading through heartfelt dev manifestos…",
    ],
    "RPG": [
        "Rolling for initiative on 10,000 RPGs…",
        "Grinding through the data so you don't have to.",
        "Consulting the ancient tome of Steam market lore…",
        "Loading. Your character's backstory is being generated.",
        "Calculating XP for every RPG on the platform…",
    ],
    "Simulation": [
        "Simulating the simulation… this gets philosophical.",
        "Managing the management games. Very meta.",
        "Running the numbers on every city builder and tycoon…",
        "Someone left a factory running. Cleaning that up first.",
        "Counting every virtual farm, hospital, and railroad.",
    ],
    "Strategy": [
        "Deploying scouts to survey the Strategy market…",
        "Moving pieces across a very large board…",
        "Calculating 40,000 possible outcomes. Almost there.",
        "The AI is plotting its next move. So are we.",
        "Executing a 12-step plan to fetch your data.",
    ],
    "Sports": [
        "Checking the stats on every sports title in the league…",
        "Blowing the whistle on thousands of sports games…",
        "Running the numbers. Literally — there's a lot of running.",
        "Reviewing the game tape… all of it.",
        "Warming up the Sports market data. Stretch first.",
    ],
    "Racing": [
        "Burning rubber through the Racing catalog…",
        "Checking lap times across thousands of titles…",
        "Pit stop — grabbing your data now.",
        "Flooring it through the Steam Racing market…",
        "No loading screen corners were cut. (Okay, maybe one.)",
    ],
    "default": [
        "Sifting through thousands of games… gimme a sec.",
        "Asking the Steam database very nicely…",
        "Crunching numbers. There are a lot of numbers.",
        "Interrogating SteamSpy. They're cooperating.",
        "Calculating your future millions… probably.",
        "Hold tight, doing math across the entire catalog.",
        "Bribing the algorithm with virtual coins…",
    ],
};

function randomQuip(genre) {
    const pool = GENRE_QUIPS[genre] || GENRE_QUIPS["default"];
    return pool[Math.floor(Math.random() * pool.length)];
}

function showLoading() {
    const grid = document.getElementById("results-grid");
    grid.innerHTML = `<div class="loading-state"><div class="chat-typing"><span></span><span></span><span></span></div><p class="loading-quip">${randomQuip(activeGenre)}</p></div>`;
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
        revenueText = `Est. Revenue: ${formatMoney(revLow)} – ${formatMoney(revHigh)} · Steam PC`;
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
    card.addEventListener("dblclick", (e) => {
        e.preventDefault();
        window.open(`steam://store/${game.steam_app_id}`);
    });
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

    const discountPct = game.price?.discount_percent || 0;
    const priceValue = isFree ? "Free" : "$" + (game.price?.current || 0).toFixed(2);
    const priceDisplay = discountPct > 0
        ? `${priceValue} <span class="stat-subvalue">(-${discountPct}%)</span>`
        : priceValue;

    const metacriticScore = game.metacritic?.score;
    const metacriticDisplay = metacriticScore != null
        ? (game.metacritic?.url
            ? `<a href="${game.metacritic.url}" target="_blank" rel="noopener">${metacriticScore}</a>`
            : String(metacriticScore))
        : "N/A";

    const developer = (game.developer || []).join(", ") || "Unknown";
    const publisher = (game.publisher || []).join(", ");
    const metaLine = [
        `Developer: ${developer}`,
        publisher && publisher !== developer ? `Publisher: ${publisher}` : null,
        `Released ${game.release_date || "Unknown"}`,
    ].filter(Boolean).join(" · ");

    const featureList = [
        ["has_multiplayer", "Multiplayer"],
        ["has_co_op", "Co-op"],
        ["has_pvp", "PvP"],
        ["has_achievements", "Achievements"],
        ["has_cloud_saves", "Cloud Saves"],
        ["has_full_controller", "Full Controller Support"],
        ["has_partial_controller", "Partial Controller Support"],
        ["has_vr_support", "VR Support"],
    ].filter(([key]) => game.features?.[key]).map(([, label]) => label);

    const languages = game.supported_languages || [];
    const heroImageUrl = game.background_image_url || game.screenshots?.[0] || game.header_image_url || "";

    document.getElementById("detail-content").innerHTML = `
        <img class="detail-image" src="${game.header_image_url || ''}" data-full="${heroImageUrl}" alt="${game.title}">

        ${(game.screenshots || []).length ? `
        <div class="detail-screenshots">
            ${game.screenshots.slice(0, 10).map(s => `<img src="${s}" alt="${game.title} screenshot" loading="lazy">`).join("")}
        </div>` : ""}

        <div class="detail-title-row">
            <h2 class="detail-title">
                ${game.title}
                ${game.is_early_access ? '<span class="tag early-access-badge">Early Access</span>' : ""}
            </h2>
            <a href="steam://store/${game.steam_app_id}" class="steam-link">
                View on Steam
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 1h7v7M11 1L5 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </a>
        </div>
        <p class="detail-developer">${metaLine}</p>
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
                <div class="label">Peak Players (All-Time)</div>
                <div class="value">${formatNumber(game.players?.peak_alltime)}</div>
            </div>
            <div class="stat-box">
                <div class="label">Price</div>
                <div class="value">${priceDisplay}</div>
            </div>
            <div class="stat-box">
                <div class="label">Metacritic</div>
                <div class="value">${metacriticDisplay}</div>
            </div>
            <div class="stat-box">
                <div class="label">DLC Count</div>
                <div class="value">${game.dlc_count ?? 0}</div>
            </div>
        </div>

        <p class="steam-pc-note">Steam PC estimates only · Console, launcher, and MTX revenue not included</p>

        <p class="section-title">Playtime</p>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="label">Avg. Playtime</div>
                <div class="value">${formatPlaytime(game.playtime?.avg_forever)}</div>
            </div>
            <div class="stat-box">
                <div class="label">Median Playtime</div>
                <div class="value">${formatPlaytime(game.playtime?.median_forever)}</div>
            </div>
        </div>

        <p class="section-title">Steam Features</p>
        <div class="tags">
            ${featureList.map(f => `<span class="tag">${f}</span>`).join("") || "<span style='color:var(--text-dim);font-size:0.8rem'>No feature data</span>"}
            ${game.has_trailer ? '<span class="tag">Has Trailer</span>' : ""}
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

        <p class="section-title">Supported Languages</p>
        <div class="tags">
            ${languages.slice(0, 10).map(l => `<span class="tag">${l}</span>`).join("") || "<span style='color:var(--text-dim);font-size:0.8rem'>No language data</span>"}
            ${languages.length > 10 ? `<span class="tag">+${languages.length - 10} more</span>` : ""}
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

document.getElementById("detail-panel").addEventListener("click", (e) => {
    if (e.target.id === "detail-panel") {
        document.getElementById("detail-panel").classList.add("hidden");
    }
});

// ----------------------------
// Image Lightbox
// ----------------------------

const imageLightbox = document.getElementById("image-lightbox");
const lightboxImage = document.getElementById("lightbox-image");
const lightboxPrev = document.getElementById("lightbox-prev");
const lightboxNext = document.getElementById("lightbox-next");

let galleryImages = [];
let galleryIndex = 0;

function showGalleryImage(index) {
    if (!galleryImages.length) return;
    galleryIndex = (index + galleryImages.length) % galleryImages.length;
    lightboxImage.src = galleryImages[galleryIndex];
    const multi = galleryImages.length > 1;
    lightboxPrev.classList.toggle("hidden", !multi);
    lightboxNext.classList.toggle("hidden", !multi);
}

function openLightbox(images, startIndex, alt = "") {
    galleryImages = images.filter(Boolean);
    if (!galleryImages.length) return;
    lightboxImage.alt = alt;
    showGalleryImage(startIndex);
    imageLightbox.classList.remove("hidden");
}

function closeLightbox() {
    imageLightbox.classList.add("hidden");
    lightboxImage.src = "";
    galleryImages = [];
}

document.getElementById("detail-content").addEventListener("click", (e) => {
    const img = e.target.closest(".detail-image, .detail-screenshots img");
    if (!img) return;
    const allImgs = Array.from(document.querySelectorAll("#detail-content .detail-image, #detail-content .detail-screenshots img"));
    const images = allImgs.map(el => el.dataset.full || el.src);
    openLightbox(images, allImgs.indexOf(img), img.alt);
});

imageLightbox.addEventListener("click", (e) => {
    if (e.target === imageLightbox) closeLightbox();
});

document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
lightboxPrev.addEventListener("click", () => showGalleryImage(galleryIndex - 1));
lightboxNext.addEventListener("click", () => showGalleryImage(galleryIndex + 1));

document.addEventListener("keydown", (e) => {
    if (imageLightbox.classList.contains("hidden")) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") showGalleryImage(galleryIndex - 1);
    if (e.key === "ArrowRight") showGalleryImage(galleryIndex + 1);
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

function formatPlaytime(minutes) {
    if (!minutes) return "N/A";
    const hours = minutes / 60;
    return (hours >= 10 ? Math.round(hours) : hours.toFixed(1)) + "h";
}

function formatConfidence(confidence) {
    if (!confidence) return "estimate";
    return confidence.label || `${confidence.score || ""}/100`;
}

function formatPct(value) {
    if (value == null) return "N/A";
    return `${value > 0 ? "+" : ""}${value}%`;
}

function signedNumber(value) {
    if (value == null) return "N/A";
    return `${value > 0 ? "+" : ""}${value}`;
}

// ----------------------------
// Insight Widget
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
