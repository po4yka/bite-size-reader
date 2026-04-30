/**
 * Ratatoskr Defuddle sidecar — minimal Fastify server.
 *
 * Routes:
 *   GET /health       → 200 {"status":"ok"}
 *   GET /*            → fetch URL via Playwright, parse with Defuddle,
 *                       return text/markdown with YAML frontmatter
 *
 * The target URL is everything after the leading slash, e.g.:
 *   GET /https://example.com/article
 *
 * Response shape (matches defuddle.md public service and DefuddleProvider parser):
 *   ---
 *   title: ...
 *   author: ...
 *   description: ...
 *   url: ...
 *   ---
 *
 *   <markdown body>
 */

import { chromium } from 'playwright';
import { Defuddle } from 'defuddle';
import Fastify from 'fastify';
import pLimit from 'p-limit';

const PORT = parseInt(process.env.PORT ?? '3003', 10);
const PAGE_GOTO_TIMEOUT_MS = parseInt(process.env.PAGE_GOTO_TIMEOUT_MS ?? '25000', 10);
const REQUEST_TIMEOUT_MS = parseInt(process.env.REQUEST_TIMEOUT_MS ?? '30000', 10);

// Concurrency cap: at most N Playwright browser contexts open simultaneously
const limit = pLimit(Number(process.env.DEFUDDLE_MAX_CONCURRENCY ?? 4));

const USER_AGENT =
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// ---------------------------------------------------------------------------
// Browser singleton — launched once at startup, closed on SIGTERM/SIGINT
// ---------------------------------------------------------------------------
let browser;

async function launchBrowser() {
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ?? undefined,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--single-process',
    ],
    headless: true,
  });
  console.log('[defuddle] browser launched');
}

async function closeBrowser() {
  if (browser) {
    await browser.close().catch(() => {});
    console.log('[defuddle] browser closed');
  }
}

// ---------------------------------------------------------------------------
// Private/RFC1918 network SSRF guard
// ---------------------------------------------------------------------------
const PRIVATE_HOST_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^169\.254\./,
  /^10\./,
  /^192\.168\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^\[::1\]$/,
];

function isPrivateHost(hostname) {
  return PRIVATE_HOST_PATTERNS.some((re) => re.test(hostname));
}

// ---------------------------------------------------------------------------
// HTML fetch via Playwright
// ---------------------------------------------------------------------------
async function fetchHtml(url) {
  const context = await browser.newContext({
    userAgent: USER_AGENT,
    viewport: { width: 1280, height: 800 },
    javaScriptEnabled: true,
  });
  const page = await context.newPage();
  try {
    await page.goto(url, {
      timeout: PAGE_GOTO_TIMEOUT_MS,
      waitUntil: 'domcontentloaded',
    });
    return await page.content();
  } finally {
    await context.close().catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// YAML-safe scalar serialisation (no external dep)
// ---------------------------------------------------------------------------
function yamlScalar(value) {
  if (!value) return '""';
  const str = String(value);
  // Quote if contains special YAML characters
  if (/[:#\[\]{}|>&*!,?'"\n\r]/.test(str) || str.trim() !== str) {
    return JSON.stringify(str);
  }
  return str;
}

function buildFrontmatter(fields) {
  const lines = ['---'];
  for (const [key, value] of Object.entries(fields)) {
    lines.push(`${key}: ${yamlScalar(value)}`);
  }
  lines.push('---');
  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Fastify server
// ---------------------------------------------------------------------------
const fastify = Fastify({ logger: false });

fastify.get('/health', async (_req, reply) => {
  return reply.code(200).send({ status: 'ok' });
});

// Wildcard route: capture target URL from the raw path
fastify.get('/*', { config: { rawBody: false } }, async (req, reply) => {
  // --- Bearer auth (opt-in: only enforced when DEFUDDLE_AUTH_TOKEN is set) ---
  const configuredToken = process.env.DEFUDDLE_AUTH_TOKEN;
  if (configuredToken) {
    const authHeader = req.headers.authorization ?? '';
    const providedToken = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';
    if (providedToken !== configuredToken) {
      return reply.code(401).send({ error: 'unauthorized' });
    }
  }

  // req.params['*'] gives us everything after the leading /
  const rawParam = req.params['*'] ?? '';

  // Reconstruct the full URL including query string
  const queryString = req.url.slice(1 + rawParam.length); // strip leading /
  const targetUrl = rawParam + (queryString || '');

  if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
    return reply.code(400).send({ error: 'Target URL must start with http:// or https://' });
  }

  // --- SSRF guard: block private/loopback targets ---
  let parsedTarget;
  try {
    parsedTarget = new URL(targetUrl);
  } catch {
    return reply.code(400).send({ error: 'Invalid target URL' });
  }
  if (isPrivateHost(parsedTarget.hostname)) {
    return reply
      .code(400)
      .send({ error: 'Target URL resolves to a private or reserved network address' });
  }

  let html;
  try {
    html = await Promise.race([
      limit(() => fetchHtml(targetUrl)),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('request timeout')), REQUEST_TIMEOUT_MS)
      ),
    ]);
  } catch (err) {
    const status = err.message === 'request timeout' ? 504 : 502;
    return reply.code(status).send({ error: err.message });
  }

  let parsed;
  try {
    // Defuddle 0.x API: new Defuddle(document, options).parse()
    // In Node (no real DOM) we pass the HTML string; Defuddle uses its own parser.
    parsed = new Defuddle(html, { url: targetUrl }).parse();
  } catch (err) {
    return reply.code(502).send({ error: `Defuddle parse error: ${err.message}` });
  }

  const frontmatter = buildFrontmatter({
    title: parsed.title ?? '',
    author: parsed.author ?? '',
    description: parsed.description ?? '',
    url: targetUrl,
  });

  const body = parsed.content ?? '';
  const response = `${frontmatter}\n\n${body}`;

  return reply
    .code(200)
    .header('Content-Type', 'text/markdown; charset=utf-8')
    .send(response);
});

// ---------------------------------------------------------------------------
// Startup / shutdown
// ---------------------------------------------------------------------------
async function start() {
  await launchBrowser();

  const shutdown = async (signal) => {
    console.log(`[defuddle] received ${signal}, shutting down`);
    await fastify.close();
    await closeBrowser();
    process.exit(0);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  await fastify.listen({ port: PORT, host: '0.0.0.0' });
  console.log(`[defuddle] listening on 0.0.0.0:${PORT}`);
}

start().catch((err) => {
  console.error('[defuddle] startup failed:', err);
  process.exit(1);
});
