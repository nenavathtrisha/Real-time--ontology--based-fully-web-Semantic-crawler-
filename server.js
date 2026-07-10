const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { URL } = require("url");

const PORT = process.env.PORT || 3000;
const dataDir = path.join(__dirname, "data");
const usersFile = path.join(dataDir, "users.json");
const historyFile = path.join(dataDir, "history.json");
const sessions = new Map();

const ontology = {
  healthcare: {
    label: "Healthcare",
    concepts: {
      diagnosis: ["disease", "symptom", "screening", "clinical diagnosis", "assessment"],
      treatment: ["therapy", "medication", "intervention", "rehabilitation", "care plan"],
      patient: ["patient", "case", "medical history", "record", "wellbeing"],
      research: ["trial", "journal", "evidence", "study", "dataset"]
    }
  },
  education: {
    label: "Education",
    concepts: {
      learning: ["course", "lesson", "curriculum", "module", "skill"],
      assessment: ["exam", "quiz", "grading", "evaluation", "rubric"],
      pedagogy: ["teaching", "classroom", "instruction", "engagement", "method"],
      research: ["paper", "academic", "publication", "citation", "knowledge"]
    }
  },
  research: {
    label: "Research",
    concepts: {
      discovery: ["innovation", "finding", "breakthrough", "analysis", "insight"],
      methods: ["methodology", "experiment", "framework", "validation", "model"],
      data: ["dataset", "measurement", "observation", "statistics", "benchmark"],
      publication: ["conference", "journal", "preprint", "peer review", "citation"]
    }
  }
};

const pageCorpus = [
  {
    id: "hc-1",
    url: "https://health.example.org/ai-diagnosis-screening",
    title: "AI Screening Support for Early Diagnosis",
    domain: "healthcare",
    snippet: "Clinical screening workflows combine patient records, symptom analysis, and evidence-based assessment.",
    terms: ["diagnosis", "screening", "patient", "clinical diagnosis", "assessment", "evidence"]
  },
  {
    id: "hc-2",
    url: "https://health.example.org/personalized-treatment-plans",
    title: "Personalized Treatment Planning",
    domain: "healthcare",
    snippet: "Therapy recommendations and medication pathways adapt to patient history and rehabilitation goals.",
    terms: ["treatment", "therapy", "medication", "patient", "care plan", "rehabilitation"]
  },
  {
    id: "ed-1",
    url: "https://edu.example.org/adaptive-learning-systems",
    title: "Adaptive Learning Systems in Digital Classrooms",
    domain: "education",
    snippet: "Course modules personalize lessons, classroom instruction, and learner engagement using analytics.",
    terms: ["learning", "course", "lesson", "classroom", "instruction", "engagement"]
  },
  {
    id: "ed-2",
    url: "https://edu.example.org/assessment-analytics",
    title: "Assessment Analytics for Student Evaluation",
    domain: "education",
    snippet: "Quiz data, grading rubrics, and evaluation dashboards support skill growth and curriculum decisions.",
    terms: ["assessment", "quiz", "grading", "evaluation", "rubric", "curriculum"]
  },
  {
    id: "rs-1",
    url: "https://research.example.org/semantic-methodology-benchmarks",
    title: "Semantic Benchmarking Methodology",
    domain: "research",
    snippet: "Experiments compare framework validation, dataset quality, and model performance across studies.",
    terms: ["methods", "methodology", "experiment", "validation", "dataset", "model"]
  },
  {
    id: "rs-2",
    url: "https://research.example.org/knowledge-discovery-publications",
    title: "Knowledge Discovery Across Publications",
    domain: "research",
    snippet: "Journal papers and conference citations reveal emerging findings, insights, and innovation patterns.",
    terms: ["discovery", "publication", "journal", "conference", "citation", "insight"]
  },
  {
    id: "mix-1",
    url: "https://innovation.example.org/medical-education-research",
    title: "Medical Education Research Exchange",
    domain: "research",
    snippet: "Academic studies connect clinical training, course design, and evidence for healthcare learning outcomes.",
    terms: ["academic", "study", "course", "evidence", "learning", "clinical diagnosis"]
  }
];

ensureDataStore();

function ensureDataStore() {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }

  if (!fs.existsSync(usersFile)) {
    fs.writeFileSync(usersFile, "[]");
  }

  if (!fs.existsSync(historyFile)) {
    fs.writeFileSync(historyFile, "[]");
  }
}

function readJsonFile(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJsonFile(filePath, value) {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1e6) {
        reject(new Error("Payload too large"));
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        reject(new Error("Invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}

function hashPassword(password) {
  return crypto.createHash("sha256").update(password).digest("hex");
}

function createToken() {
  return crypto.randomBytes(24).toString("hex");
}

function parseCookies(req) {
  const cookieHeader = req.headers.cookie || "";
  return cookieHeader.split(";").reduce((acc, cookie) => {
    const [rawKey, ...rest] = cookie.trim().split("=");
    if (!rawKey) {
      return acc;
    }
    acc[rawKey] = decodeURIComponent(rest.join("="));
    return acc;
  }, {});
}

function setSessionCookie(res, token) {
  res.setHeader("Set-Cookie", `sessionToken=${token}; HttpOnly; Path=/; SameSite=Lax; Max-Age=86400`);
}

function clearSessionCookie(res) {
  res.setHeader("Set-Cookie", "sessionToken=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0");
}

function getSessionUser(req) {
  const cookies = parseCookies(req);
  const token = cookies.sessionToken;
  if (!token) {
    return null;
  }
  return sessions.get(token) || null;
}

function sanitizeUser(user) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    createdAt: user.createdAt
  };
}

function saveCrawlHistory(entry) {
  const history = readJsonFile(historyFile, []);
  history.unshift(entry);
  writeJsonFile(historyFile, history.slice(0, 100));
}

function getUserHistory(userId) {
  return readJsonFile(historyFile, []).filter((entry) => entry.userId === userId).slice(0, 8);
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function serveFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const types = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8"
  };

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    res.writeHead(200, { "Content-Type": types[ext] || "text/plain; charset=utf-8" });
    res.end(data);
  });
}

function unauthorized(res) {
  sendJson(res, 401, { error: "Unauthorized" });
}

function normalize(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenize(text) {
  return normalize(text).split(" ").filter(Boolean);
}

function parseQuery(query) {
  const normalized = normalize(query);
  const tokens = tokenize(query);
  const matches = [];

  Object.entries(ontology).forEach(([domainKey, domain]) => {
    Object.entries(domain.concepts).forEach(([conceptKey, synonyms]) => {
      const candidates = [conceptKey, ...synonyms];
      const matchedTerms = [...new Set(candidates.filter((term) => normalized.includes(normalize(term))))];
      if (matchedTerms.length > 0) {
        matches.push({
          domainKey,
          domainLabel: domain.label,
          conceptKey,
          conceptLabel: conceptKey[0].toUpperCase() + conceptKey.slice(1),
          matchedTerms
        });
      }
    });
  });

  if (matches.length === 0) {
    const fallbackDomainKey = tokens.some((token) => ["patient", "clinical", "therapy"].includes(token))
      ? "healthcare"
      : tokens.some((token) => ["course", "lesson", "student"].includes(token))
        ? "education"
        : "research";
    const domain = ontology[fallbackDomainKey];
    matches.push({
      domainKey: fallbackDomainKey,
      domainLabel: domain.label,
      conceptKey: Object.keys(domain.concepts)[0],
      conceptLabel: Object.keys(domain.concepts)[0][0].toUpperCase() + Object.keys(domain.concepts)[0].slice(1),
      matchedTerms: tokens.slice(0, 3)
    });
  }

  const primaryDomainKey = matches.reduce((acc, current) => {
    acc[current.domainKey] = (acc[current.domainKey] || 0) + current.matchedTerms.length;
    return acc;
  }, {});

  const rankedDomains = Object.entries(primaryDomainKey).sort((a, b) => b[1] - a[1]);

  return {
    original: query,
    normalized,
    tokens,
    matches,
    primaryDomain: rankedDomains[0] ? rankedDomains[0][0] : "research"
  };
}

function fuzzyMembership(score) {
  const low = score <= 0.35 ? 1 : score < 0.5 ? (0.5 - score) / 0.15 : 0;
  const medium = score <= 0.25 || score >= 0.85
    ? 0
    : score < 0.55
      ? (score - 0.25) / 0.3
      : score < 0.7
        ? 1
        : (0.85 - score) / 0.15;
  const high = score <= 0.55 ? 0 : score < 0.9 ? (score - 0.55) / 0.35 : 1;

  const levels = { low, medium, high };
  const label = Object.entries(levels).sort((a, b) => b[1] - a[1])[0][0];
  return { label, levels };
}

function evaluatePage(page, parsedQuery) {
  const normalizedSnippet = normalize(`${page.title} ${page.snippet} ${page.terms.join(" ")}`);
  const queryTermHits = parsedQuery.tokens.filter((token) => normalizedSnippet.includes(token)).length;
  const conceptHits = parsedQuery.matches.filter((match) =>
    page.terms.some((term) => normalize(term) === normalize(match.conceptKey)) ||
    match.matchedTerms.some((term) => normalizedSnippet.includes(normalize(term)))
  ).length;
  const domainBoost = page.domain === parsedQuery.primaryDomain ? 0.22 : 0.08;
  const semanticCoverage = Math.min(1, conceptHits / Math.max(parsedQuery.matches.length, 1));
  const lexicalCoverage = Math.min(1, queryTermHits / Math.max(parsedQuery.tokens.length, 1));
  const rawScore = Math.min(1, 0.48 * semanticCoverage + 0.3 * lexicalCoverage + domainBoost);
  const fuzzy = fuzzyMembership(rawScore);

  return {
    pageId: page.id,
    title: page.title,
    url: page.url,
    domain: page.domain,
    snippet: page.snippet,
    semanticCoverage: Number(semanticCoverage.toFixed(2)),
    lexicalCoverage: Number(lexicalCoverage.toFixed(2)),
    rawScore: Number(rawScore.toFixed(2)),
    fuzzyLabel: fuzzy.label,
    fuzzyLevels: Object.fromEntries(
      Object.entries(fuzzy.levels).map(([key, value]) => [key, Number(value.toFixed(2))])
    )
  };
}

function buildResults(query, options = {}) {
  const parsedQuery = parseQuery(query);
  const selectedDomain = options.domain && options.domain !== "all" ? options.domain : null;
  const minScore = Number.isFinite(Number(options.threshold)) ? Number(options.threshold) : 0.42;
  const acceptedThreshold = Math.max(0, Math.min(1, minScore));
  const filteredCorpus = selectedDomain ? pageCorpus.filter((page) => page.domain === selectedDomain) : pageCorpus;
  const results = filteredCorpus.map((page) => evaluatePage(page, parsedQuery));
  const ranked = [...results].sort((a, b) => b.rawScore - a.rawScore);
  const knowledgeBase = [];

  ranked.forEach((result) => {
    if (result.rawScore >= acceptedThreshold) {
      knowledgeBase.push({
        title: result.title,
        url: result.url,
        domain: result.domain,
        relevance: result.fuzzyLabel,
        score: result.rawScore
      });
    }
  });

  return {
    parsedQuery,
    ranked,
    knowledgeBase,
    acceptedThreshold
  };
}

function streamCrawl(res, req, query, options) {
  const user = getSessionUser(req);
  const { parsedQuery, ranked, knowledgeBase, acceptedThreshold } = buildResults(query, options);
  const crawlSpeed = Math.max(180, Number(options.speed) || 650);

  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive"
  });

  res.write(`event: ontology\n`);
  res.write(`data: ${JSON.stringify(parsedQuery)}\n\n`);

  ranked.forEach((result, index) => {
    setTimeout(() => {
      const page = pageCorpus.find((item) => item.id === result.pageId);
      const accepted = result.rawScore >= acceptedThreshold;

      res.write(`event: crawl\n`);
      res.write(`data: ${JSON.stringify({
        step: index + 1,
        total: ranked.length,
        accepted,
        seedUrl: page.url,
        result
      })}\n\n`);

      if (index === ranked.length - 1) {
        setTimeout(() => {
          if (user) {
            saveCrawlHistory({
              id: crypto.randomUUID(),
              userId: user.id,
              query,
              domain: options.domain || "all",
              threshold: acceptedThreshold,
              topScore: ranked[0] ? ranked[0].rawScore : 0,
              accepted: knowledgeBase.length,
              scanned: ranked.length,
              createdAt: new Date().toISOString()
            });
          }

          res.write(`event: complete\n`);
          res.write(`data: ${JSON.stringify({
            knowledgeBase,
            rankedResults: ranked,
            summary: {
              totalScanned: ranked.length,
              accepted: knowledgeBase.length,
              highestScore: ranked[0] ? ranked[0].rawScore : 0,
              primaryDomain: parsedQuery.primaryDomain,
              threshold: acceptedThreshold,
              selectedDomain: options.domain || "all"
            }
          })}\n\n`);
          res.end();
        }, 350);
      }
    }, index * crawlSpeed);
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === "POST" && url.pathname === "/api/register") {
    readBody(req)
      .then((body) => {
        const name = String(body.name || "").trim();
        const email = String(body.email || "").trim().toLowerCase();
        const password = String(body.password || "").trim();
        if (!name || !email || !password) {
          sendJson(res, 400, { error: "Name, email, and password are required." });
          return;
        }

        const users = readJsonFile(usersFile, []);
        if (users.some((user) => user.email === email)) {
          sendJson(res, 409, { error: "An account with this email already exists." });
          return;
        }

        const newUser = {
          id: crypto.randomUUID(),
          name,
          email,
          passwordHash: hashPassword(password),
          createdAt: new Date().toISOString()
        };
        users.push(newUser);
        writeJsonFile(usersFile, users);

        const token = createToken();
        const sessionUser = sanitizeUser(newUser);
        sessions.set(token, sessionUser);
        setSessionCookie(res, token);
        sendJson(res, 201, { user: sessionUser });
      })
      .catch((error) => sendJson(res, 400, { error: error.message }));
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/login") {
    readBody(req)
      .then((body) => {
        const email = String(body.email || "").trim().toLowerCase();
        const password = String(body.password || "").trim();
        const users = readJsonFile(usersFile, []);
        const user = users.find((item) => item.email === email && item.passwordHash === hashPassword(password));
        if (!user) {
          sendJson(res, 401, { error: "Invalid email or password." });
          return;
        }

        const token = createToken();
        const sessionUser = sanitizeUser(user);
        sessions.set(token, sessionUser);
        setSessionCookie(res, token);
        sendJson(res, 200, { user: sessionUser });
      })
      .catch((error) => sendJson(res, 400, { error: error.message }));
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/logout") {
    const cookies = parseCookies(req);
    if (cookies.sessionToken) {
      sessions.delete(cookies.sessionToken);
    }
    clearSessionCookie(res);
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/session") {
    const user = getSessionUser(req);
    sendJson(res, 200, { user });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/history") {
    const user = getSessionUser(req);
    if (!user) {
      unauthorized(res);
      return;
    }
    sendJson(res, 200, { items: getUserHistory(user.id) });
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/ontology") {
    sendJson(res, 200, ontology);
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/crawl") {
    const user = getSessionUser(req);
    if (!user) {
      unauthorized(res);
      return;
    }
    const query = url.searchParams.get("query") || "semantic healthcare diagnosis research";
    const domain = url.searchParams.get("domain") || "all";
    const threshold = url.searchParams.get("threshold") || "0.42";
    const speed = url.searchParams.get("speed") || "650";
    streamCrawl(res, req, query, { domain, threshold, speed });
    return;
  }

  if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
    serveFile(res, path.join(__dirname, "public", "index.html"));
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/")) {
    const safePath = path.normalize(url.pathname).replace(/^(\.\.[/\\])+/, "");
    serveFile(res, path.join(__dirname, "public", safePath));
    return;
  }

  res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Method not allowed");
});

server.listen(PORT, () => {
  console.log(`Semantic crawler demo running at http://localhost:${PORT}`);
});
