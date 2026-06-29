#!/usr/bin/env node
/**
 * DeepSeek Source Extractor
 *
 * Connects to an already-running Chrome instance via CDP, finds (or opens) the
 * DeepSeek share page (https://chat.deepseek.com/share/<id>), and extracts the
 * reference / citation sources from the share/content API.
 *
 * Extraction route (cdp_bridge, ADR-001 U4):
 *   DeepSeek 手机端的来源面板是原生 View，只显示 标题/站点/日期，不暴露真实 URL。
 *   因此连接桌面 Chrome，并在分享页上下文调用：
 *   GET https://chat.deepseek.com/api/v0/share/content?share_id=<id>
 *   以继承浏览器 Cookie、Origin 和风控环境；架构与千问提取器一致。
 */

const fs = require('fs');
const { chromium } = require('playwright-core');

const DEFAULT_CDP_URL = process.env.CDP_URL || 'http://127.0.0.1:9222';
const SHARE_CONTENT_API = 'https://chat.deepseek.com/api/v0/share/content';

function parseArgs(argv) {
  const args = {
    cdp: DEFAULT_CDP_URL,
    output: '',
    url: '',
    timeout: 15000,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--cdp') args.cdp = argv[++i];
    else if (arg === '--output') args.output = argv[++i];
    else if (arg === '--url') args.url = argv[++i];
    else if (arg === '--timeout') args.timeout = Number(argv[++i]);
    else if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function printHelp() {
  console.log(`Usage: node extract-sources.js [options]

Extract reference sources from an open DeepSeek share page via CDP and the
share/content API.

Options:
  --cdp <url>       CDP endpoint. Default: ${DEFAULT_CDP_URL}
  --url <url>       DeepSeek share URL (required). Used to locate the right tab.
  --timeout <ms>    Wait time for page readiness. Default: 15000
  --output <file>   Save JSON output to a file
  --help            Show this help

Example:
  node extract-sources.js --url "https://chat.deepseek.com/share/o7a2kswga666sdv2di" --output sources.json
`);
}

function extractShareId(url) {
  const match = String(url || '').match(/\/share\/([A-Za-z0-9]+)/);
  return match ? match[1] : '';
}

/**
 * Intercept the page's own share/content API response and extract sources.
 *
 * The share/content API returns different payloads depending on whether the
 * request carries an Authorization header. The page's own request includes a
 * Bearer token (injected by the SPA) and receives the full response with
 * `fragments[].results`; a bare fetch from page context only gets a redacted
 * response with `search_results: null`. Therefore we intercept the page's
 * network response instead of replaying the fetch.
 *
 * Full response structure:
 *   data.biz_data.messages[].fragments[]
 *   fragment.type === 'TOOL_SEARCH' → fragment.results[] (source objects)
 *   Each result: { url, title, snippet, site_name, site_icon,
 *                  published_at, cite_index, query_indexes }
 */
async function extractDeepSeekSourcesViaApi(page, shareId, timeout = 15000) {
  // Set up response interception before reloading.
  let capturedBody = null;
  const responsePromise = new Promise((resolve) => {
    const handler = async (resp) => {
      if (resp.url().includes('share/content') && resp.url().includes(shareId)) {
        try {
          capturedBody = await resp.text();
          page.off('response', handler);
          resolve(capturedBody);
        } catch {
          // keep waiting
        }
      }
    };
    page.on('response', handler);
    // Timeout fallback
    setTimeout(() => resolve(null), timeout);
  });

  // Reload to trigger the page's own API call.
  await page.reload({ waitUntil: 'domcontentloaded', timeout }).catch(() => {});
  await responsePromise;

  if (!capturedBody) {
    return { ok: false, reason: 'api-response-not-captured', shareId };
  }

  let json;
  try {
    json = JSON.parse(capturedBody);
  } catch {
    return { ok: false, reason: 'api-response-not-json', shareId, bodyPreview: capturedBody.slice(0, 500) };
  }

  const bizData = json && json.data && json.data.biz_data;
  const messages = bizData && Array.isArray(bizData.messages) ? bizData.messages : [];
  if (!bizData || !messages.length) {
    return { ok: false, reason: 'unexpected-api-structure', topKeys: json ? Object.keys(json) : [] };
  }

  // Collect sources from fragments[].results (full response format).
  const rawSources = [];
  let assistantContent = '';
  let thinkingContent = '';
  let thinkingElapsedSeconds = null;
  let searchEnabled = false;

  for (const message of messages) {
    const role = String(message.role || '').toUpperCase();

    // New format: fragments[].results
    if (Array.isArray(message.fragments)) {
      for (const frag of message.fragments) {
        if (/SEARCH/i.test(frag.type) && Array.isArray(frag.results)) {
          rawSources.push(...frag.results);
        }
        if (frag.type === 'RESPONSE' && typeof frag.content === 'string') {
          assistantContent = frag.content;
        }
        if (frag.type === 'THINK' && typeof frag.content === 'string') {
          thinkingContent += (thinkingContent ? '\n' : '') + frag.content;
        }
      }
    }

    // search_results appears in two shapes across API versions:
    //   - object form: { results: [...] }           (older full responses)
    //   - array form:  [ {url,title,snippet,...} ]   (current share-content API)
    // The array form is what the public/unauthenticated content API returns, so
    // the page's own request yields it whenever the desktop session is not
    // authenticated. Handle both, otherwise real sources are silently dropped
    // and the result is mislabelled "partial".
    const sr = message.search_results;
    if (Array.isArray(sr)) {
      rawSources.push(...sr);
    } else if (sr && Array.isArray(sr.results)) {
      rawSources.push(...sr.results);
    }

    if (role === 'ASSISTANT') {
      if (!assistantContent && typeof message.content === 'string') assistantContent = message.content;
      if (!thinkingContent && typeof message.thinking_content === 'string') thinkingContent = message.thinking_content;
      if (thinkingElapsedSeconds === null) thinkingElapsedSeconds = message.thinking_elapsed_secs || null;
      searchEnabled = Boolean(message.search_enabled);
    }
  }

  // Resilience fallback: if the intercepted (possibly unauthenticated) response
  // carried no sources, fetch the PUBLIC share-content API directly from the page
  // context. It reliably returns messages[].search_results[] even without a Bearer
  // token — exactly the case that produced false "partial" results when the desktop
  // Chrome session lost its login mid-run.
  if (!rawSources.length) {
    try {
      const publicJson = await page.evaluate(async (sid) => {
        const resp = await fetch(`/api/v0/share/content?share_id=${sid}`, { credentials: 'omit' });
        return resp.ok ? resp.json() : null;
      }, shareId);
      const publicMessages = publicJson && publicJson.data && publicJson.data.biz_data
        && Array.isArray(publicJson.data.biz_data.messages) ? publicJson.data.biz_data.messages : [];
      for (const message of publicMessages) {
        const sr = message.search_results;
        if (Array.isArray(sr)) rawSources.push(...sr);
        else if (sr && Array.isArray(sr.results)) rawSources.push(...sr.results);
        if (!assistantContent && String(message.role || '').toUpperCase() === 'ASSISTANT'
          && typeof message.content === 'string') {
          assistantContent = message.content;
        }
      }
    } catch {
      // best-effort; leave rawSources empty if the fallback fetch also fails
    }
  }

  // Deduplicate by URL and build normalized output.
  const seen = new Set();
  const sources = [];
  for (const item of rawSources) {
    const url = String(item.url || item.link || item.source_url || item.sourceUrl || item.uri || item.normalized_url || '');
    if (!url || !/^https?:\/\//i.test(url) || seen.has(url)) continue;
    seen.add(url);
    const platform = String(item.site_name || item.siteName || item.platform || item.source_name || item.sourceName || item.name || '').trim()
      || platformFromUrl(url);
    sources.push({
      index: sources.length + 1,
      title: String(item.title || item.name || item.snippet_title || item.page_title || '').trim() || url,
      url,
      normalizedUrl: String(item.normalized_url || item.normalizedUrl || url),
      rawUrl: String(item.raw_url || item.rawUrl || url),
      platform,
      summary: String(item.summary || item.snippet || item.description || item.excerpt || '').trim().slice(0, 2000),
      publishTime: String(item.publish_time || item.publishTime || item.date || item.published_at || '').trim(),
      siteIcon: String(item.site_icon || item.siteIcon || '').trim(),
      type: String(item.type || item.source_type || item.sourceType || '').trim(),
    });
  }

  return {
    ok: sources.length > 0,
    reason: sources.length ? '' : 'sources-not-found-in-api-response',
    url: page.url(),
    title: bizData.title || '',
    apiPath: 'data.biz_data.messages[].fragments[].results',
    sourceFormat: 'deepseek_share_content_api',
    shareId,
    messageCount: messages.length,
    answer: assistantContent,
    thinkingContent,
    thinkingElapsedSeconds,
    searchEnabled,
    count: sources.length,
    sources,
  };
}

function platformFromUrl(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; }
}

function pickDeepSeekPage(contexts, shareUrl) {
  const pages = contexts.flatMap(context => context.pages());
  const shareId = extractShareId(shareUrl);
  if (shareId) {
    const byId = pages.find(page => page.url().includes(shareId));
    if (byId) return byId;
  }
  const sharePage = pages.find(page => /deepseek\.com\/share\//.test(page.url()));
  if (sharePage) return sharePage;
  return pages.find(page => /deepseek\.com/.test(page.url())) || pages[0];
}

/**
 * Scrape the DeepSeek share page DOM for external reference links.
 * Runs in the page context so it carries the page origin/cookies.
 */
async function extractDeepSeekSourcesViaDom(page, shareId) {
  return page.evaluate((sid) => {
    function cleanText(text) {
      return String(text || '').replace(/\s+/g, ' ').trim();
    }

    // 域名关键词 → 中文平台名映射（兜底，宽松匹配：host 包含 key 即命中）
    const DOMAIN_PLATFORM_MAP = {
      'bjnews': '新京报', 'qianlong': '千龙网·中国首都网', 'cnpiw': '中国报业网',
      'sina': '新浪', 'sohu': '搜狐', '163.com': '网易', 'ifeng': '凤凰网',
      'thepaper': '澎湃新闻', 'caixin': '财新', 'people.com.cn': '人民网',
      'xinhuanet': '新华网', 'news.cn': '新华网', 'chinanews': '中国新闻网',
      'china.com.cn': '中国网', 'china.com': '中国网', 'huanqiu': '环球网',
      'cctv': '央视网', 'toutiao': '今日头条', '36kr': '36氪',
      'baidu': '百度', 'so.com': '360搜索', 'bing': '必应', 'sogou': '搜狗',
      'weibo': '微博', 'zhihu': '知乎', 'douban': '豆瓣', 'xiaohongshu': '小红书',
      'bilibili': '哔哩哔哩', 'douyin': '抖音', 'iqiyi': '爱奇艺', 'youku': '优酷',
      'taobao': '淘宝', 'tmall': '天猫', 'jd.com': '京东',
      '39.net': '39健康网', 'dxy.cn': '丁香园', 'babytree': '宝宝树', 'mama.cn': '妈妈网',
      'csdn': 'CSDN', 'juejin': '掘金', 'wikipedia': '维基百科',
      'qq.com': '腾讯网', 'tencent': '腾讯', 'weixin': '微信',
    };
    const DOMAIN_KEYS = Object.keys(DOMAIN_PLATFORM_MAP).sort((a, b) => b.length - a.length);

    function platformFromUrl(url) {
      try {
        const host = new URL(url).hostname.replace(/^www\./, '');
        for (const key of DOMAIN_KEYS) {
          if (host.includes(key)) return DOMAIN_PLATFORM_MAP[key];
        }
        const TLDS = new Set(['com', 'cn', 'net', 'org', 'gov', 'edu', 'info', 'biz', 'xyz', 'top', 'io', 'cc']);
        const parts = host.split('.').filter(p => !TLDS.has(p.toLowerCase()));
        return parts[parts.length - 1] || host;
      } catch {
        return '';
      }
    }

    // 只收集指向站外的 http(s) 链接，排除 DeepSeek 自身域名与锚点。
    const anchors = Array.from(document.querySelectorAll('a[href^="http"]'));
    const seen = new Set();
    const sources = [];
    for (const a of anchors) {
      let href = '';
      try {
        href = new URL(a.href, location.href).href;
      } catch {
        continue;
      }
      let host = '';
      try {
        host = new URL(href).hostname;
      } catch {
        continue;
      }
      if (/deepseek\.com$/.test(host) || /deepseek\.com\//.test(href)) continue;
      if (seen.has(href)) continue;
      seen.add(href);
      const title = cleanText(a.getAttribute('title') || a.textContent || a.getAttribute('aria-label') || '');
      sources.push({
        index: sources.length + 1,
        title,
        url: href,
        normalizedUrl: href,
        rawUrl: href,
        platform: platformFromUrl(href),
        summary: '',
        publishTime: '',
        type: '',
      });
    }

    return {
      ok: sources.length > 0,
      reason: sources.length > 0 ? '' : 'no-external-links-in-dom',
      url: location.href,
      title: document.title,
      sourceFormat: 'deepseek_share_dom_anchors',
      shareId: sid,
      count: sources.length,
      sources,
    };
  }, shareId);
}

async function waitForDeepSeekReady(page, timeout = 15000) {
  await page.waitForLoadState('domcontentloaded', { timeout }).catch(() => {});
}

/**
 * Extract sources from a DeepSeek share page.
 * @param {string} cdpUrl - CDP endpoint URL
 * @param {string} shareUrl - DeepSeek share URL
 * @param {number} timeout - Page readiness timeout in ms
 * @returns {Promise<object>} Extraction result with sources array
 */
async function extractSources(cdpUrl, shareUrl, timeout = 15000) {
  const browser = await chromium.connectOverCDP(cdpUrl);
  try {
    const shareId = extractShareId(shareUrl);
    if (!shareId) throw new Error('Could not extract share_id from --url argument.');

    let page = pickDeepSeekPage(browser.contexts(), shareUrl);
    const onSharePage = page && page.url().includes(shareId);
    if (!onSharePage) {
      const context = browser.contexts()[0];
      page = await context.newPage();
      await page.goto(shareUrl, { waitUntil: 'domcontentloaded', timeout });
    }

    await page.bringToFront();

    // extractDeepSeekSourcesViaApi reloads the page to intercept the API response.
    const result = await extractDeepSeekSourcesViaApi(page, shareId, timeout);

    await page.close().catch(() => {});
    return result;
  } finally {
    await browser.close().catch(() => {});
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.url) throw new Error('--url is required (DeepSeek share URL)');

  const result = await extractSources(args.cdp, args.url, args.timeout);
  const json = JSON.stringify(result, null, 2);
  if (args.output) fs.writeFileSync(args.output, `${json}\n`, 'utf8');
  console.log(json);
}

if (require.main === module) {
  main().catch(error => {
    console.error(`[extract-sources] failed: ${error.stack || error.message}`);
    process.exit(1);
  });
}

module.exports = { extractSources, extractDeepSeekSourcesViaApi, extractDeepSeekSourcesViaDom, pickDeepSeekPage, waitForDeepSeekReady, extractShareId };
