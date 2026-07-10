const authScreen = document.getElementById("auth-screen");
const dashboardScreen = document.getElementById("dashboard-screen");
const authForm = document.getElementById("auth-form");
const authMessage = document.getElementById("auth-message");
const authSubtitle = document.getElementById("auth-subtitle");
const authSubmit = document.getElementById("auth-submit");
const loginTab = document.getElementById("login-tab");
const registerTab = document.getElementById("register-tab");
const nameGroup = document.getElementById("name-group");
const nameInput = document.getElementById("name");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const welcomeUser = document.getElementById("welcome-user");
const logoutButton = document.getElementById("logout-button");
const accountSummary = document.getElementById("account-summary");
const historyList = document.getElementById("history-list");

const form = document.getElementById("crawl-form");
const queryInput = document.getElementById("query");
const domainFilter = document.getElementById("domain-filter");
const thresholdRange = document.getElementById("threshold-range");
const thresholdValue = document.getElementById("threshold-value");
const speedFilter = document.getElementById("speed-filter");
const ontologySummary = document.getElementById("ontology-summary");
const ontologyMatches = document.getElementById("ontology-matches");
const crawlStream = document.getElementById("crawl-stream");
const knowledgeBase = document.getElementById("knowledge-base");
const rankedResults = document.getElementById("ranked-results");
const statusPill = document.getElementById("crawl-status");
const progressLabel = document.getElementById("crawl-progress");
const totalScanned = document.getElementById("total-scanned");
const acceptedCount = document.getElementById("accepted-count");
const primaryDomain = document.getElementById("primary-domain");
const topScore = document.getElementById("top-score");

let activeStream = null;
let authMode = "login";
let currentUser = null;

function capitalize(text) {
  return String(text || "").charAt(0).toUpperCase() + String(text || "").slice(1);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function showAuthMessage(message, isError = false) {
  authMessage.textContent = message;
  authMessage.style.color = isError ? "var(--danger)" : "var(--muted)";
}

function setAuthMode(mode) {
  authMode = mode;
  const registerMode = mode === "register";
  nameGroup.classList.toggle("hidden", !registerMode);
  nameInput.required = registerMode;
  authSubmit.textContent = registerMode ? "Create Account" : "Login";
  loginTab.classList.toggle("active", !registerMode);
  registerTab.classList.toggle("active", registerMode);
  passwordInput.autocomplete = registerMode ? "new-password" : "current-password";
  authSubtitle.textContent = registerMode
    ? "Create a new account to start using the real-time semantic crawler."
    : "Sign in to access the real-time semantic crawler dashboard.";
  showAuthMessage(
    registerMode
      ? "Create your account here if you do not already have one."
      : "If you do not have an account, choose Create Account and register here."
  );
}

function showDashboard(user) {
  currentUser = user;
  welcomeUser.textContent = `Welcome, ${user.name}`;
  accountSummary.innerHTML = `
    <strong>${user.name}</strong><br />
    <span>${user.email}</span><br />
    <span>Account created: ${new Date(user.createdAt).toLocaleString()}</span>
  `;
  authScreen.classList.add("hidden");
  dashboardScreen.classList.remove("hidden");
}

function showAuth() {
  dashboardScreen.classList.add("hidden");
  authScreen.classList.remove("hidden");
}

function resetUi() {
  ontologySummary.textContent = "Interpreting query against the ontology...";
  ontologyMatches.innerHTML = "";
  crawlStream.innerHTML = "";
  knowledgeBase.innerHTML = "";
  rankedResults.innerHTML = "";
  totalScanned.textContent = "0";
  acceptedCount.textContent = "0";
  primaryDomain.textContent = "-";
  topScore.textContent = "0.00";
  progressLabel.textContent = "0 / 0";
  statusPill.textContent = "Running";
  statusPill.className = "status-pill running";
}

function setEmptyState(container, message) {
  container.innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderOntology(data) {
  primaryDomain.textContent = capitalize(data.primaryDomain);
  ontologySummary.innerHTML = `
    <strong>Semantic focus:</strong> ${capitalize(data.primaryDomain)} domain<br />
    <strong>Normalized query:</strong> ${data.normalized || "-"}<br />
    <strong>Detected concepts:</strong> ${data.matches.length}
  `;

  ontologyMatches.innerHTML = data.matches
    .map(
      (match) => `
        <span class="tag">
          ${match.domainLabel} / ${capitalize(match.conceptKey)}<br />
          matched: ${match.matchedTerms.join(", ")}
        </span>
      `
    )
    .join("");
}

function prependStreamItem(payload) {
  const item = document.createElement("article");
  item.className = "stream-item";
  item.innerHTML = `
    <strong>${payload.result.title}</strong>
    <div>${payload.seedUrl}</div>
    <div class="meta-row">
      <span class="relevance ${payload.result.fuzzyLabel}">${payload.result.fuzzyLabel}</span>
      <span>score ${payload.result.rawScore.toFixed(2)}</span>
      <span>${payload.accepted ? "stored in knowledge base" : "filtered out"}</span>
    </div>
  `;
  crawlStream.prepend(item);
}

function appendKnowledgeBase(entries) {
  if (!entries.length) {
    setEmptyState(knowledgeBase, "No pages passed the relevance threshold.");
    return;
  }

  knowledgeBase.innerHTML = entries
    .map(
      (entry) => `
        <article class="result-item">
          <strong>${entry.title}</strong>
          <div><a href="${entry.url}" target="_blank" rel="noreferrer">${entry.url}</a></div>
          <div class="meta-row">
            <span>${capitalize(entry.domain)}</span>
            <span class="relevance ${entry.relevance}">${entry.relevance}</span>
            <span>score ${entry.score.toFixed(2)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function appendRankedResults(entries) {
  rankedResults.innerHTML = entries
    .map(
      (entry, index) => `
        <article class="result-item">
          <strong>#${index + 1} ${entry.title}</strong>
          <div>${entry.snippet}</div>
          <div class="meta-row">
            <span>${capitalize(entry.domain)}</span>
            <span class="relevance ${entry.fuzzyLabel}">${entry.fuzzyLabel}</span>
            <span>semantic ${entry.semanticCoverage.toFixed(2)}</span>
            <span>lexical ${entry.lexicalCoverage.toFixed(2)}</span>
            <span>score ${entry.rawScore.toFixed(2)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderHistory(items) {
  if (!items.length) {
    setEmptyState(historyList, "No crawl history yet. Run a query to create your first session.");
    return;
  }

  historyList.innerHTML = items
    .map(
      (item) => `
        <article class="result-item">
          <strong>${item.query}</strong>
          <div class="meta-row">
            <span>domain ${capitalize(item.domain)}</span>
            <span>threshold ${Number(item.threshold).toFixed(2)}</span>
            <span>accepted ${item.accepted}/${item.scanned}</span>
            <span>top ${Number(item.topScore).toFixed(2)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

async function loadHistory() {
  try {
    const payload = await requestJson("/api/history");
    renderHistory(payload.items);
  } catch {
    setEmptyState(historyList, "Could not load crawl history.");
  }
}

async function startCrawl(query) {
  if (activeStream) {
    activeStream.close();
  }

  resetUi();
  const acceptedEntries = [];
  setEmptyState(crawlStream, "Connecting to live crawl stream...");
  setEmptyState(knowledgeBase, "Accepted semantic pages will be stored here.");
  setEmptyState(rankedResults, "Crawler is still ranking pages...");

  const params = new URLSearchParams({
    query,
    domain: domainFilter.value,
    threshold: thresholdRange.value,
    speed: speedFilter.value
  });

  activeStream = new EventSource(`/api/crawl?${params.toString()}`);

  activeStream.addEventListener("ontology", (event) => {
    renderOntology(JSON.parse(event.data));
  });

  activeStream.addEventListener("crawl", (event) => {
    const payload = JSON.parse(event.data);
    if (crawlStream.querySelector(".empty-state")) {
      crawlStream.innerHTML = "";
    }
    prependStreamItem(payload);
    progressLabel.textContent = `${payload.step} / ${payload.total}`;
    totalScanned.textContent = String(payload.step);

    if (payload.accepted) {
      acceptedEntries.unshift({
        title: payload.result.title,
        url: payload.result.url,
        domain: payload.result.domain,
        relevance: payload.result.fuzzyLabel,
        score: payload.result.rawScore
      });
      acceptedCount.textContent = String(acceptedEntries.length);
      appendKnowledgeBase(acceptedEntries);
    }
  });

  activeStream.addEventListener("complete", async (event) => {
    const payload = JSON.parse(event.data);
    appendKnowledgeBase(payload.knowledgeBase);
    appendRankedResults(payload.rankedResults);
    acceptedCount.textContent = String(payload.summary.accepted);
    totalScanned.textContent = String(payload.summary.totalScanned);
    topScore.textContent = Number(payload.summary.highestScore).toFixed(2);
    primaryDomain.textContent = capitalize(payload.summary.primaryDomain);
    statusPill.textContent = "Complete";
    statusPill.className = "status-pill complete";
    activeStream.close();
    await loadHistory();
  });

  activeStream.onerror = () => {
    statusPill.textContent = "Idle";
    statusPill.className = "status-pill idle";
    if (activeStream) {
      activeStream.close();
    }
    setEmptyState(crawlStream, "The crawl stream was interrupted. Please try again.");
  };
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const payload = {
    name: nameInput.value.trim(),
    email: emailInput.value.trim().toLowerCase(),
    password: passwordInput.value.trim()
  };

  if (!payload.email || !payload.password || (authMode === "register" && !payload.name)) {
    showAuthMessage("Please fill in all required fields.", true);
    return;
  }

  try {
    const endpoint = authMode === "register" ? "/api/register" : "/api/login";
    const response = await requestJson(endpoint, {
      method: "POST",
      body: JSON.stringify(payload)
    });
    authForm.reset();
    setAuthMode("login");
    showDashboard(response.user);
    await loadHistory();
  } catch (error) {
    showAuthMessage(error.message, true);
  }
}

async function initializeAuth() {
  loginTab.addEventListener("click", () => setAuthMode("login"));
  registerTab.addEventListener("click", () => setAuthMode("register"));
  authForm.addEventListener("submit", handleAuthSubmit);
  logoutButton.addEventListener("click", async () => {
    try {
      await requestJson("/api/logout", { method: "POST", body: JSON.stringify({}) });
    } catch {
      // Ignore logout cleanup errors.
    }
    currentUser = null;
    if (activeStream) {
      activeStream.close();
    }
    authForm.reset();
    setAuthMode("login");
    showAuth();
  });

  const session = await requestJson("/api/session");
  if (session.user) {
    showDashboard(session.user);
    await loadHistory();
  } else {
    setAuthMode("login");
    showAuth();
  }
}

thresholdRange.addEventListener("input", () => {
  thresholdValue.textContent = Number(thresholdRange.value).toFixed(2);
});

document.querySelectorAll(".chip").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    startCrawl(queryInput.value);
  });
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  startCrawl(queryInput.value.trim() || "semantic knowledge discovery");
});

thresholdValue.textContent = Number(thresholdRange.value).toFixed(2);
initializeAuth();
