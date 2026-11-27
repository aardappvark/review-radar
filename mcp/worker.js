// Review Radar MCP server (Cloudflare Worker, stateless Streamable HTTP, JSON-RPC 2.0).
// Read-only. It serves the analysis published at https://aardappvark.github.io/review-radar/data/,
// so it is always exactly what the web page shows. Add it to Claude Code with:
//   claude mcp add --transport http review-radar https://review-radar.aardappvark.workers.dev/mcp

const DATA = "https://aardappvark.github.io/review-radar/data";
const PROTOCOL = "2025-06-18";
const SERVER = { name: "review-radar", version: "0.2.0" };
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Mcp-Session-Id, Mcp-Protocol-Version, Accept",
};

const APP_ARG = { type: "string", description: "App slug from list_apps, e.g. letterboxd, serato-dj, stamped" };
const TOOLS = [
  { name: "list_apps", description: "Every Tiny app Review Radar covers: store, rating, how many written reviews were read, and the window used.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false } },
  { name: "top_problems", description: "The top problems in an app's recent reviews, ranked by 1-2 star reviews: headline, what people report, where to look, the smallest next step, evidence quotes and counts.",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "incidents", description: "Days when an app got far more reviews than normal (often an outage), with the main complaint, the version, and when a three-report alert would have fired.",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "versions", description: "Written-review average per release, flagging releases that dropped half a star or more (App Store apps only).",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "did_the_fix_work", description: "For an App Store app's complaints, their share of each release's reviews, release by release, with a verdict read from the numbers (fell after vX, easing, still open, too early). A drop is consistent with a fix, not proof.",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "review_stats", description: "The statistics behind an app's reviews: star mix this period vs the one before, written reviews and average stars per month (18 months), reviewer countries, share of three-word reviews, median length, publisher reply rate (Shopify), and reviews in other languages with English translations.",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "themes", description: "Every complaint and praise theme in an app's reviews with recent and earlier counts and average stars.",
    inputSchema: { type: "object", properties: { app: APP_ARG }, required: ["app"], additionalProperties: false } },
  { name: "draft_reply", description: "A public reply ready to post to a real review, for one of an app's top problems (rank 1-5).",
    inputSchema: { type: "object", properties: { app: APP_ARG, rank: { type: "integer", minimum: 1, maximum: 5 } }, required: ["app"], additionalProperties: false } },
];

async function getJson(path, ctx) {
  const url = `${DATA}/${path}`;
  const cache = caches.default;
  let res = await cache.match(url);
  if (!res) {
    res = await fetch(url, { cf: { cacheTtl: 300 } });
    if (!res.ok) throw new Error(res.status === 404 ? "not found" : `data fetch failed (${res.status})`);
    res = new Response(res.body, res);
    res.headers.set("Cache-Control", "public, max-age=300");
    ctx.waitUntil(cache.put(url, res.clone()));
  }
  return res.json();
}

async function app(args, ctx) {
  const slug = String(args?.app || "").trim().toLowerCase();
  if (!/^[a-z0-9-]{2,40}$/.test(slug)) throw new Error("app must be a slug from list_apps");
  try { return await getJson(`${slug}.json`, ctx); }
  catch (e) { throw new Error(`no app '${slug}'; call list_apps for the slugs`); }
}

const label = (a) => a.window?.recent_label || "90 days";

async function callTool(name, args, ctx) {
  switch (name) {
    case "list_apps": {
      const idx = await getJson("index.json", ctx);
      return { generated: idx.generated, apps: idx.apps };
    }
    case "top_problems": {
      const a = await app(args, ctx);
      if (a.sample_only) return { app: a.name, sample_only: true, note: a.sample_note, store_rating: a.store?.avg,
        sample: a.sample.map((q) => ({ stars: q.stars, date: q.date, title: q.title, text: q.text })) };
      return {
        app: a.name, company: a.company, store: a.store_kind, window: `last ${label(a)}`,
        store_rating: a.store?.avg, written_reviews_average: a.written_avg_recent,
        problems: a.themes.filter((t) => t.brief).map((t, i) => ({
          rank: i + 1, theme: t.label, headline: t.brief.headline, what_people_report: t.brief.happening,
          where_to_look: t.brief.where_to_look, smallest_next_step: t.brief.action,
          reviews: t.n_recent, one_or_two_stars: t.low_recent, previous_period: t.n_prior, average_stars: t.avg_recent,
          evidence: t.quotes.map((q) => ({ stars: q.stars, date: q.date, version: q.version || undefined, text: q.text_en || q.text,
            original: q.text_en ? q.text : undefined, translated_from: q.language || undefined })),
        })),
        note: "Drafted by a local model; every number and version is checked against the data. Reviews are a loud minority: they show where to look.",
      };
    }
    case "incidents": {
      const a = await app(args, ctx);
      return { app: a.name, normal_day: a.bursts[0]?.base ?? null, incidents: a.bursts.map((b) => ({
        date: b.date, reviews: b.n, one_or_two_stars: b.low, main_complaint: b.theme, version: b.version || undefined,
        first_review: b.first || undefined, three_report_alert_at: b.alert_at || undefined, evidence: b.quotes.map((q) => q.text) })) };
    }
    case "versions": {
      const a = await app(args, ctx);
      if (!a.versions?.length) return { app: a.name, versions: [], note: "This store does not publish a version with each review." };
      return { app: a.name, versions: a.versions.slice().reverse().map((v) => ({ version: v.version, first_seen: v.first, last_seen: v.last,
        reviews: v.n, average_stars: v.avg, change: v.delta, dropped_half_a_star: v.flag, reports_something_broken: v.bug_share, main_complaints: v.top })) };
    }
    case "did_the_fix_work": {
      const a = await app(args, ctx);
      if (!a.fixes?.length) return { app: a.name, tracked: [], note: a.sample_only ? a.sample_note : "Needs per-release reviews (App Store apps) and a complaint that spiked on some release." };
      return { app: a.name, note: "Share of each release's written reviews (releases with 5+ reviews). A drop after a release is consistent with a fix, not proof of one.",
        tracked: a.fixes.map((f) => ({ complaint: f.label, verdict: f.verdict === "fell" ? `fell after v${f.after}` : f.verdict === "early" ? "too early to tell" : f.verdict === "open" ? "still open" : "easing",
          spike: { version: f.peak.version, share: f.peak.share, mentions: f.peak.hits, reviews: f.peak.n }, latest: { version: f.latest.version, share: f.latest.share },
          by_release: f.series.map((x) => ({ version: x.version, share: x.share, mentions: x.hits, reviews: x.n })) })) };
    }
    case "review_stats": {
      const a = await app(args, ctx);
      if (!a.stats) return { app: a.name, note: a.sample_note || "No statistics for this app yet." };
      return { app: a.name, window: `last ${label(a)}`, ...a.stats, other_languages: a.other_languages, around_the_world: a.world || undefined };
    }
    case "themes": {
      const a = await app(args, ctx);
      return { app: a.name, window: `last ${label(a)}`, themes: a.themes.map((t) => ({ theme: t.label, describe: t.describe,
        recent: t.n_recent, previous_period: t.n_prior, average_stars: t.avg, all_in_window: t.n })) };
    }
    case "draft_reply": {
      const a = await app(args, ctx);
      const tops = a.themes.filter((t) => t.brief);
      const rank = Math.min(Math.max(parseInt(args?.rank ?? 1, 10) || 1, 1), tops.length || 1);
      const t = tops[rank - 1];
      if (!t) return { app: a.name, note: "No ranked problems for this app." };
      const q = t.quotes[t.brief.reply_to] || t.quotes[0];
      return { app: a.name, problem: t.label, review: q && { stars: q.stars, date: q.date, text: q.text }, draft_reply: t.brief.reply,
        note: "A suggestion to check before posting; it never promises work or dates." };
    }
    default:
      throw Object.assign(new Error(`unknown tool ${name}`), { code: -32602 });
  }
}

async function rpc(msg, ctx) {
  const { id, method, params } = msg || {};
  const isNote = id === undefined || id === null;
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  const err = (code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
  if (!msg || msg.jsonrpc !== "2.0" || typeof method !== "string") return err(-32600, "invalid request");
  if (isNote) return null; // notifications/initialized and friends need no answer
  try {
    switch (method) {
      case "initialize":
        return ok({ protocolVersion: params?.protocolVersion || PROTOCOL, capabilities: { tools: { listChanged: false } }, serverInfo: SERVER,
          instructions: "Review Radar: public app-store reviews of every Tiny company's apps, turned into ranked problems, incidents, version regressions and draft replies. Start with list_apps." });
      case "ping":
        return ok({});
      case "tools/list":
        return ok({ tools: TOOLS });
      case "tools/call": {
        const data = await callTool(params?.name, params?.arguments || {}, ctx);
        return ok({ content: [{ type: "text", text: JSON.stringify(data, null, 1) }], structuredContent: data });
      }
      default:
        return err(-32601, `method not found: ${method}`);
    }
  } catch (e) {
    if (method === "tools/call" && e.code !== -32602) return ok({ content: [{ type: "text", text: `Error: ${e.message}` }], isError: true });
    return err(e.code || -32603, e.message);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (url.pathname === "/" && request.method === "GET") {
      return new Response("Review Radar MCP server. Add it with:\n  claude mcp add --transport http review-radar https://review-radar.aardappvark.workers.dev/mcp\nWeb: https://aardappvark.github.io/review-radar/\n",
        { headers: { "Content-Type": "text/plain; charset=utf-8", ...CORS } });
    }
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404, headers: CORS });
    if (request.method !== "POST") return new Response(JSON.stringify({ error: "POST JSON-RPC to /mcp (stateless)" }), { status: 405, headers: { "Content-Type": "application/json", Allow: "POST", ...CORS } });
    let body;
    try { body = await request.json(); } catch { return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, { status: 400, headers: CORS }); }
    const out = Array.isArray(body) ? (await Promise.all(body.map((m) => rpc(m, ctx)))).filter(Boolean) : await rpc(body, ctx);
    if (out === null || (Array.isArray(out) && !out.length)) return new Response(null, { status: 202, headers: CORS });
    return Response.json(out, { headers: CORS });
  },
};
