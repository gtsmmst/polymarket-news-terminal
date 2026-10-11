let eventGroups = [];
let selectedMarket = null;
let expandedGroups = new Set();

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${url} (${response.status})`);
  }
  return await response.json();
}

function formatCentsFromDecimal(value) {
  const num = Number(value || 0);
  return (num * 100).toFixed(1);
}

function formatMoney(value) {
  const num = Number(value || 0);
  return `$${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getFilters() {
  const minPriceCents = parseFloat(document.getElementById("min-price")?.value || "0");
  const maxPriceCents = parseFloat(document.getElementById("max-price")?.value || "100");
  const minLiquidity = parseFloat(document.getElementById("min-liquidity")?.value || "0");

  return {
    search: document.getElementById("search")?.value.trim() || "",
    category: document.getElementById("category")?.value || "politics_plus",
    sort_by: document.getElementById("sort-by")?.value || "liquidity",
    min_price: (minPriceCents / 100).toString(),
    max_price: (maxPriceCents / 100).toString(),
    min_liquidity: minLiquidity.toString(),
  };
}

function getPolymarketUrl(market) {
  if (market?.event_slug) return `https://polymarket.com/event/${market.event_slug}`;
  if (market?.slug) return `https://polymarket.com/event/${market.slug}`;
  return "#";
}

function renderEventGroups() {
  const container = document.getElementById("markets-list");
  if (!container) return;

  container.innerHTML = "";

  if (!eventGroups.length) {
    container.innerHTML = "<p>No markets match these filters.</p>";
    return;
  }

  eventGroups.forEach((group) => {
    const isExpanded = expandedGroups.has(group.event_id);

    const wrapper = document.createElement("div");
    wrapper.className = "event-group";

    const header = document.createElement("button");
    header.className = "event-group-header";
    header.type = "button";
    header.setAttribute("aria-expanded", isExpanded ? "true" : "false");

    header.innerHTML = `
      <div class="event-group-main">
        <div class="event-group-title">${escapeHtml(group.event_title)}</div>
        <div class="event-group-meta">
          ${group.max_opportunity ? `🔥 ${Number(group.max_opportunity).toFixed(0)} · ` : ""}${group.market_count} markets ·
          Price range: ${formatCentsFromDecimal(group.min_yes_price)}c - ${formatCentsFromDecimal(group.max_yes_price)}c ·
          Liquidity: ${formatMoney(group.total_liquidity)}
        </div>
      </div>
      <div class="event-group-toggle">${isExpanded ? "−" : "+"}</div>
    `;

    header.addEventListener("click", () => {
      if (expandedGroups.has(group.event_id)) {
        expandedGroups.delete(group.event_id);
      } else {
        expandedGroups.add(group.event_id);
      }
      renderEventGroups();
    });

    wrapper.appendChild(header);

    if (isExpanded) {
      const children = document.createElement("div");
      children.className = "event-group-children";

      group.markets.forEach((market) => {
        const card = document.createElement("div");
        card.className = "market-card" + (selectedMarket?.id === market.id ? " active" : "");

        card.innerHTML = `
          <div class="market-title-row">
            <a class="market-link" href="${getPolymarketUrl(market)}" target="_blank" rel="noopener noreferrer">
              ${escapeHtml(market.title)}
            </a>
          </div>
          <div class="market-meta">
            ${market.opportunity_score ? `🔥 ${Number(market.opportunity_score).toFixed(0)} · ` : ""}YES: ${formatCentsFromDecimal(market.yes_price)}c ·
            Spread: ${formatCentsFromDecimal(market.spread)}c ·
            Liquidity: ${formatMoney(market.liquidity)}
            ${market.news_velocity ? `· news ${Number(market.news_velocity).toFixed(0)}` : ""}
          </div>
        `;

        card.addEventListener("click", async (event) => {
          if (event.target.closest("a")) return;
          selectedMarket = market;
          renderEventGroups();
          await renderSelectedMarketData();
        });

        children.appendChild(card);
      });

      wrapper.appendChild(children);
    }

    container.appendChild(wrapper);
  });
}

function renderMarketDetails(score = null, alerts = []) {
  const container = document.getElementById("market-details");
  if (!container) return;

  if (!selectedMarket) {
    container.innerHTML = "<p>Select a market.</p>";
    return;
  }

  const alertsHtml = alerts.length
    ? alerts.map(alert => `<li><strong>${escapeHtml(alert.severity)}</strong>: ${escapeHtml(alert.alert_text)}</li>`).join("")
    : "<li>No active alerts</li>";

  const scoreHtml = score ? `
    <div class="label">Opportunity Score</div>
    <div class="value">${escapeHtml(score.opportunity_score)}</div>
    <div class="label">News Velocity</div>
    <div class="value">${escapeHtml(score.news_velocity)}</div>
    <div class="label">Source Quality</div>
    <div class="value">${escapeHtml(score.source_quality)}</div>
    <div class="label">Sentiment Shift</div>
    <div class="value">${escapeHtml(score.sentiment_shift)}</div>
  ` : `
    <div class="label">Opportunity Score</div>
    <div class="value">No score yet</div>
  `;

  container.innerHTML = `
    <div class="label">Event</div>
    <div class="value">${escapeHtml(selectedMarket.event_title || "N/A")}</div>

    <div class="label">Title</div>
    <div class="value">
      <a class="market-link" href="${getPolymarketUrl(selectedMarket)}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(selectedMarket.title)}
      </a>
    </div>

    <div class="label">Slug</div>
    <div class="value">${escapeHtml(selectedMarket.slug || "N/A")}</div>

    <div class="label">Category</div>
    <div class="value">${escapeHtml(selectedMarket.category || "N/A")}</div>

    <div class="label">Yes Price</div>
    <div class="value">${formatCentsFromDecimal(selectedMarket.yes_price)}c</div>

    <div class="label">No Price</div>
    <div class="value">${formatCentsFromDecimal(selectedMarket.no_price)}c</div>

    <div class="label">Spread</div>
    <div class="value">${formatCentsFromDecimal(selectedMarket.spread)}c</div>

    <div class="label">Liquidity</div>
    <div class="value">${formatMoney(selectedMarket.liquidity)}</div>

    <div class="label">24h Volume</div>
    <div class="value">${formatMoney(selectedMarket.volume_24h)}</div>

    <div class="label">End Date</div>
    <div class="value">${escapeHtml(selectedMarket.end_date || "N/A")}</div>

    <div class="label">Resolution Text</div>
    <div class="value">${escapeHtml(selectedMarket.resolution_text || "N/A")}</div>

    ${scoreHtml}

    <div class="label">Alerts</div>
    <div class="value"><ul>${alertsHtml}</ul></div>
  `;
}

async function renderHeadlines() {
  const container = document.getElementById("headlines-list");
  if (!container) return;

  container.innerHTML = "";

  if (!selectedMarket) {
    container.innerHTML = "<p>Select a market.</p>";
    return;
  }

  const [headlines, score, alerts] = await Promise.all([
    fetchJSON(`/api/markets/${selectedMarket.id}/headlines`),
    fetchJSON(`/api/markets/${selectedMarket.id}/score`),
    fetchJSON(`/api/markets/${selectedMarket.id}/alerts`)
  ]);

  renderMarketDetails(score, alerts);

  if (!headlines.length) {
    container.innerHTML = "<p>No headlines linked to this market.</p>";
    return;
  }

  headlines.forEach((headline) => {
    const card = document.createElement("div");
    card.className = "headline-card";
    card.innerHTML = `
      <div class="headline-title">
        <a class="market-link" href="${escapeHtml(headline.url)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(headline.title)}
        </a>
      </div>
      <div class="headline-meta">
        ${escapeHtml(headline.source_name)} · Tier ${escapeHtml(headline.source_tier)} · ${escapeHtml(headline.published_at)}
      </div>
      <p>${escapeHtml(headline.summary || "")}</p>
      <div class="headline-meta">
        Relevance: ${escapeHtml(headline.relevance_score)} · Match: ${escapeHtml(headline.matched_by)}
      </div>
    `;
    container.appendChild(card);
  });
}

async function renderSelectedMarketData() {
  renderMarketDetails();
  await renderHeadlines();
}

async function loadDashboard() {
  try {
    document.getElementById("status").textContent = "Loading data...";

    const filters = getFilters();
    const params = new URLSearchParams(filters);
    params.sort();

    eventGroups = await fetchJSON(`/api/event-groups?${params.toString()}`);

    if (eventGroups.length > 0) {
      const allMarkets = eventGroups.flatMap(group => group.markets);
      if (!selectedMarket || !allMarkets.find(m => m.id === selectedMarket.id)) {
        const firstGroupWithMarkets = eventGroups.find(g => g.markets.length > 0);
        if (firstGroupWithMarkets) {
          expandedGroups.add(firstGroupWithMarkets.event_id);
          selectedMarket = firstGroupWithMarkets.markets[0];
        }
      }
    } else {
      selectedMarket = null;
    }

    renderEventGroups();
    await renderSelectedMarketData();

    const totalMarkets = eventGroups.reduce((sum, group) => sum + group.market_count, 0);
    document.getElementById("status").textContent = `Connected · ${eventGroups.length} events · ${totalMarkets} markets`;
  } catch (error) {
    document.getElementById("status").textContent = "Error loading data";
    console.error(error);
  }
}

async function refreshMarkets() {
  try {
    document.getElementById("status").textContent = "Refreshing Polymarket...";
    await fetchJSON("/api/refresh/polymarket", { method: "POST" });
    await loadDashboard();
  } catch (error) {
    document.getElementById("status").textContent = "Refresh failed";
    console.error(error);
  }
}

async function refreshAll() {
  try {
    document.getElementById("status").textContent = "Pulling news + scoring mispricing… (~30-60s)";
    await fetchJSON("/api/refresh/all", { method: "POST" });
    await loadDashboard();
  } catch (error) {
    document.getElementById("status").textContent = "Refresh all failed (see console)";
    console.error(error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const applyButton = document.getElementById("apply-filters");
  const refreshButton = document.getElementById("refresh-markets");
  const searchInput = document.getElementById("search");

  if (applyButton) {
    applyButton.addEventListener("click", async () => {
      selectedMarket = null;
      expandedGroups.clear();
      await loadDashboard();
    });
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      selectedMarket = null;
      expandedGroups.clear();
      await refreshMarkets();
    });
  }

  const refreshAllButton = document.getElementById("refresh-all");
  if (refreshAllButton) {
    refreshAllButton.addEventListener("click", async () => {
      selectedMarket = null;
      expandedGroups.clear();
      await refreshAll();
    });
  }

  if (searchInput) {
    searchInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        selectedMarket = null;
        expandedGroups.clear();
        await loadDashboard();
      }
    });
  }

  loadDashboard();
});