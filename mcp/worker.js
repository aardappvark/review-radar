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
  { name: "top_problems", description: "The top problems in an app's recent reviews, ranked by 1-2 star reviews: headline, what people report, where to look, the smallest next step, evidence quotes and counts, plus action points: how many reviews name something specific vs too vague to act on, the specific requests with counts, and a direction, expected outcome and how to check.",
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
          action_points: t.actions ? {
            reviews_read: t.actions.n, specific: t.actions.specific, too_vague_to_act_on: t.actions.noise,
            requests: t.actions.requests.map((r) => ({ request: r.request, reviews: r.count, quote: r.quote || undefined, stars: r.stars ?? undefined })),
            no_pattern_yet: t.actions.single || undefined,
            direction: t.actions.direction, expected_outcome: t.actions.outcome, how_to_check: t.actions.check,
          } : undefined,
        })),
        note: "Drafted by a local model; every number and version is checked against the data. Action-point counts are computed from the reviews the model grouped; no_pattern_yet means no two reviews ask for the same thing. Reviews are a loud minority: they show where to look.",
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

// What a person sees on opening the server's address in a browser (mail apps turn the
// address in "claude mcp add ..." into a link). Agents never get this: they POST, or GET
// with Accept: text/event-stream, and keep the protocol's 405.
const HELP_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review Radar · MCP server</title><meta name="robots" content="noindex">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%230c0914' stroke='%2314f195' stroke-width='2'/%3E%3Cpath d='M16 16 L16 4 A12 12 0 0 1 27 12 Z' fill='%2314f195'/%3E%3C/svg%3E">
<style>
:root{--bg:#050407;--s1:#0c0914;--t:#f2eeff;--t2:#b7aed1;--t3:#7f77a0;--g:#14f195;--line:rgba(242,238,255,.12)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(800px 460px at 10% 0%,rgba(153,69,255,.14),transparent 60%),radial-gradient(700px 380px at 90% 20%,rgba(20,241,149,.07),transparent 70%),var(--bg);color:var(--t);font:16px/1.6 Manrope,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100vh}
main{max-width:760px;margin:0 auto;padding:clamp(48px,9vw,96px) 24px}
.k{display:inline-flex;align-items:center;gap:10px;font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--g)}.k:before{content:"";width:28px;height:2px;border-radius:2px;background:currentColor}
h1{font-size:clamp(34px,6vw,58px);font-weight:800;letter-spacing:-.045em;line-height:1;margin:18px 0 18px}
p{color:var(--t2);margin:0 0 14px}
pre{margin:22px 0;border:1px solid var(--line);border-radius:16px;background:#08060e;padding:16px 18px;font:13.5px/1.6 ui-monospace,"SF Mono",Menlo,monospace;color:#d9d2ee;white-space:pre-wrap;word-break:break-all}
pre .c{color:var(--t3)}pre .s{color:var(--g)}
ul{color:var(--t2);padding-left:20px}li{margin:4px 0}code{color:var(--t)}
a.btn{display:inline-flex;margin-top:18px;padding:13px 22px;border-radius:999px;background:var(--g);color:#03140b;font-weight:700;text-decoration:none}
</style></head><body><main>
<div class="k">Review Radar · MCP server</div>
<h1>This address is for AI agents.</h1>
<p>It's a Model Context Protocol server: Claude and other agents can query everything Review Radar found about Tiny's apps. There's nothing to see here in a browser. Add it to Claude Code with:</p>
<pre><span class="c"># then ask: "what's wrong with Letterboxd this week, and what should the team do first?"</span>
claude mcp add --transport http review-radar <span class="s">https://review-radar.aardappvark.workers.dev/mcp</span></pre>
<p>Eight tools, all read-only:</p>
<ul><li><code>list_apps</code>, <code>top_problems</code> (with action points), <code>incidents</code>, <code>versions</code></li>
<li><code>did_the_fix_work</code>, <code>review_stats</code>, <code>themes</code>, <code>draft_reply</code></li></ul>
<a class="btn" href="https://aardappvark.github.io/review-radar/">Open Review Radar</a>
</main></body></html>`;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (url.pathname === "/" && request.method === "GET" && /text\/html/.test(request.headers.get("Accept") || ""))
      return new Response(HELP_HTML, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300", ...CORS } });
    if (url.pathname === "/" && request.method === "GET") {
      return new Response("Review Radar MCP server. Add it with:\n  claude mcp add --transport http review-radar https://review-radar.aardappvark.workers.dev/mcp\nWeb: https://aardappvark.github.io/review-radar/\n",
        { headers: { "Content-Type": "text/plain; charset=utf-8", ...CORS } });
    }
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404, headers: CORS });
    if (request.method === "GET" && /text\/html/.test(request.headers.get("Accept") || "") && !/text\/event-stream/.test(request.headers.get("Accept") || ""))
      return new Response(HELP_HTML, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300", ...CORS } });
    if (request.method !== "POST") return new Response(JSON.stringify({ error: "POST JSON-RPC to /mcp (stateless)" }), { status: 405, headers: { "Content-Type": "application/json", Allow: "POST", ...CORS } });
    let body;
    try { body = await request.json(); } catch { return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, { status: 400, headers: CORS }); }
    const out = Array.isArray(body) ? (await Promise.all(body.map((m) => rpc(m, ctx)))).filter(Boolean) : await rpc(body, ctx);
    if (out === null || (Array.isArray(out) && !out.length)) return new Response(null, { status: 202, headers: CORS });
    return Response.json(out, { headers: CORS });
  },
};
