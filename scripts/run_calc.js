#!/usr/bin/env node
/**
 * bid-price-calc 无头测算引擎
 *
 * 在 Node 中以 vm + DOM stub 方式加载原工具页面（backend JS + HTML 内联脚本），
 * 无需浏览器即可运行蒙特卡洛报价模拟，输出结构化 JSON 结果。
 *
 * 用法:
 *   node run_calc.js --input input.json [--output result.json] [--tool-root PATH]
 *   node run_calc.js --list-inputs [--page base|pro] [--tool-root PATH]
 *
 * input.json schema:
 * {
 *   "page": "base" | "pro",          // 可省略，默认 base
 *   "seed": 12345,                    // 可省略；给定时 Math.random 可复现
 *   "inputs": {                       // 覆盖页面默认值，key = DOM id
 *     "benchmarkRule": "secondaryAverage",
 *     "scoringRule": 'deviationInterpolation',
 *     "ceilingPrice": "898.97",
 *     "maxPrice": "890",
 *     "minPrice": "760",
 *     "participantCount": "20",
 *     "simulationCount": "10000"
 *   }
 * }
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ---------------------------------------------------------------- arg parsing
function parseArgs(argv) {
  const args = { inputs: null, output: null, toolRoot: null, page: null, listInputs: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input') args.inputs = argv[++i];
    else if (a === '--output') args.output = argv[++i];
    else if (a === '--tool-root') args.toolRoot = argv[++i];
    else if (a === '--page') args.page = argv[++i];
    else if (a === '--list-inputs') args.listInputs = true;
    else if (a === '-h' || a === '--help') { printHelp(); process.exit(0); }
    else { fail(`未知参数: ${a}`); }
  }
  return args;
}

function printHelp() {
  console.log(`用法:
  node run_calc.js --input input.json [--output result.json] [--tool-root PATH]
  node run_calc.js --list-inputs [--page base|pro] [--tool-root PATH]`);
}

function fail(msg) {
  process.stderr.write(`ERROR: ${msg}\n`);
  process.exit(1);
}

// ---------------------------------------------------------- tool root resolve
function resolveToolRoot(cliRoot) {
  const candidates = [];
  if (cliRoot) candidates.push(cliRoot);
  if (process.env.BID_TOOL_ROOT) candidates.push(process.env.BID_TOOL_ROOT);
  const cfgPath = path.join(__dirname, '..', 'config.json');
  if (fs.existsSync(cfgPath)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      if (cfg.toolRoot) candidates.push(cfg.toolRoot);
    } catch (e) { /* config.json 损坏时忽略 */ }
  }
  candidates.push('D:\\32 投标研究\\01 报价测算\\统计工具');
  for (const c of candidates) {
    if (c && fs.existsSync(path.join(c, 'frontend'))) return c;
  }
  fail('找不到工具目录（frontend/）。请用 --tool-root、环境变量 BID_TOOL_ROOT 或 config.json 指定。尝试过: ' + candidates.join(' | '));
}

const PAGES = {
  base: { html: '投标报价概率计算.html', label: 'Base版' },
  pro:  { html: '投标报价概率计算 Pro.html', label: 'Pro版' },
};

// ---------------------------------------------------------------- html parse
function extractScripts(html) {
  const scripts = [];
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[1] || '';
    const srcMatch = /src\s*=\s*["']([^"']+)["']/i.exec(attrs);
    scripts.push({ src: srcMatch ? srcMatch[1] : null, body: m[2] });
  }
  return scripts;
}

/** 从 HTML 属性预填 input/select/textarea 的默认值（模拟浏览器默认状态） */
function extractPrefill(html) {
  const map = Object.create(null);

  // <input ...>  —— value 与 id 顺序不定
  const inputRe = /<input\b[^>]*>/gi;
  let m;
  while ((m = inputRe.exec(html)) !== null) {
    const tag = m[0];
    const id = /\bid\s*=\s*["']([^"']+)["']/i.exec(tag);
    if (!id) continue;
    const val = /\bvalue\s*=\s*["']([^"']*)["']/i.exec(tag);
    if (val) map[id[1]] = decodeEntities(val[1]);
    else if (/\btype\s*=\s*["']checkbox["']/i.test(tag)) {
      map[id[1]] = /\bchecked\b/i.test(tag) ? 'true' : 'false';
    } else if (!map[id[1]]) map[id[1]] = '';
  }

  // <textarea id="x">default</textarea>
  const taRe = /<textarea\b([^>]*)>([\s\S]*?)<\/textarea>/gi;
  while ((m = taRe.exec(html)) !== null) {
    const id = /\bid\s*=\s*["']([^"']+)["']/i.exec(m[1]);
    if (id) map[id[1]] = decodeEntities(m[2].trim());
  }

  // <select id="x">… 选中项（selected 优先，否则第一个 option）
  const selectRe = /<select\b([^>]*)>([\s\S]*?)<\/select>/gi;
  while ((m = selectRe.exec(html)) !== null) {
    const id = /\bid\s*=\s*["']([^"']+)["']/i.exec(m[1]);
    if (!id) continue;
    const body = m[2];
    const optRe = /<option\b([^>]*)>([\s\S]*?)<\/option>/gi;
    let o; let chosen = null; let first = null;
    while ((o = optRe.exec(body)) !== null) {
      const attrs = o[1]; const text = decodeEntities(o[2].trim());
      const ov = /\bvalue\s*=\s*["']([^"']*)["']/i.exec(attrs);
      const value = ov ? ov[1] : text;
      if (first === null) first = value;
      if (/\bselected\b/i.test(attrs)) { chosen = value; break; }
    }
    map[id[1]] = chosen !== null ? chosen : (first !== null ? first : '');
  }
  return map;
}

// ----------------------------------------------------------------- dom stubs
const VOID_TAGS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);

function decodeEntities(s) {
  return String(s)
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&');
}

function encodeEntities(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function parseAttrs(raw) {
  const out = {};
  const re = /([a-zA-Z_:][-\w:.]*)\s*(?:=\s*("([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const v = m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : (m[5] !== undefined ? m[5] : undefined));
    out[m[1].toLowerCase()] = v !== undefined ? decodeEntities(v) : '';
  }
  return out;
}

function createEl(tag, attrs) {
  attrs = attrs || {};
  const el = {
    tagName: String(tag || 'div').toLowerCase(),
    nodeType: 1,
    id: attrs.id || '',
    className: attrs.class || '',
    type: attrs.type || '',
    checked: 'checked' in attrs,
    disabled: 'disabled' in attrs,
    hidden: 'hidden' in attrs,
    placeholder: attrs.placeholder || '',
    value: attrs.value !== undefined ? attrs.value : '',
    innerHTMLText: '',
    textContent: '',
    innerText: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    dataset: {},
    options: [],
    selectedIndex: 0,
    width: 800,
    height: 400,
    children: [],
    childNodes: null,
    parentNode: null,
    _html: '',
    _mutated: false,
    _listeners: {},
    _pendingText: '',
    _selected: 'selected' in attrs,
    addEventListener(type, fn) {
      (el._listeners[type] = el._listeners[type] || []).push(fn);
    },
    removeEventListener(type, fn) {
      const l = el._listeners[type];
      if (l) { const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); }
    },
    dispatchEvent(evt) {
      const type = typeof evt === 'string' ? evt : (evt && evt.type);
      const l = el._listeners[type] || [];
      for (const fn of l.slice()) {
        try { fn.call(el, evt && typeof evt === 'object' ? evt : { type, target: el }); }
        catch (e) { if (globalThis.__stubLogs) globalThis.__stubLogs.push('[el-listener-error] ' + (e && e.message)); }
      }
      const on = el['on' + type];
      if (typeof on === 'function') { try { on.call(el, evt); } catch (e) { /* ignore */ } }
      return true;
    },
    appendChild(child) {
      if (child && child.parentNode) child.parentNode.removeChild(child);
      if (child) { child.parentNode = el; el.children.push(child); el._mutated = true; }
      return child;
    },
    insertBefore(child, ref) {
      if (child && child.parentNode) child.parentNode.removeChild(child);
      if (child) {
        child.parentNode = el;
        const idx = ref ? el.children.indexOf(ref) : -1;
        if (idx >= 0) el.children.splice(idx, 0, child); else el.children.push(child);
        el._mutated = true;
      }
      return child;
    },
    removeChild(child) {
      const i = el.children.indexOf(child);
      if (i >= 0) { el.children.splice(i, 1); if (child) child.parentNode = null; el._mutated = true; }
      return child;
    },
    remove() {
      if (el.parentNode) el.parentNode.removeChild(el);
    },
    replaceChildren() { el.children = []; el._mutated = true; },
    contains(n) { return n === el || el.children.some((c) => c && c.contains && c.contains(n)); },
    setAttribute(k, v) {
      k = String(k).toLowerCase();
      if (k === 'id') el.id = String(v);
      else if (k === 'class') el.className = String(v);
      else if (k === 'value') el.value = String(v);
      else if (k === 'type') el.type = String(v);
      else el['attr_' + k] = String(v);
    },
    getAttribute(k) {
      k = String(k).toLowerCase();
      if (k === 'id') return el.id || null;
      if (k === 'class') return el.className || null;
      if (k === 'value') return el.value != null ? String(el.value) : null;
      if (k === 'type') return el.type || null;
      return el['attr_' + k] !== undefined ? el['attr_' + k] : null;
    },
    removeAttribute(k) { delete el['attr_' + String(k).toLowerCase()]; },
    hasAttribute(k) { return el.getAttribute(k) !== null; },
    getAttributeNode() { return null; },
    querySelector(sel) { return queryDescendants(el, sel, false); },
    querySelectorAll(sel) { return queryDescendants(el, sel, true); },
    getElementsByClassName() { return []; },
    getElementsByTagName() { return []; },
    focus() {}, blur() {}, click() { el.dispatchEvent({ type: 'click', target: el }); }, select() {},
    scrollIntoView() {},
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }; },
    getContext() { return makeCanvasContext(); },
    toDataURL() { return 'data:,'; },
    insertAdjacentHTML(where, html) {
      if (where === 'beforeend' || where === 'afterbegin') {
        parseFragmentInto(String(html), el);
        el._mutated = true;
      }
    },
    cloneNode() { return createEl(el.tagName, { id: el.id, class: el.className, value: el.value, type: el.type }); },
    closest(sel) {
      const parts = String(sel).split(',').map((s) => s.trim()).filter(Boolean).map(compileSelector);
      let n = el;
      while (n && n.tagName) {
        if (parts.some((m) => matchesSelector(n, m))) return n;
        n = n.parentNode;
      }
      return null;
    },
  };
  el.childNodes = el.children;
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._mutated ? serializeChildren(el) : el._html; },
    set(v) {
      el._html = String(v == null ? '' : v);
      el.children = [];
      if (el._html) parseFragmentInto(el._html, el);
      el._mutated = false; // 必须在解析之后复位：parse 内部的 appendChild 会置 true
    },
    configurable: true,
    enumerable: true,
  });
  return el;
}

function serializeChildren(el) {
  return el.children.map(serializeNode).join('');
}

function serializeNode(n) {
  if (!n || !n.tagName) return '';
  const attrs = [];
  if (n.id) attrs.push(`id="${encodeEntities(n.id)}"`);
  if (n.className) attrs.push(`class="${encodeEntities(n.className)}"`);
  if (n.type) attrs.push(`type="${encodeEntities(n.type)}"`);
  if (n.tagName !== 'select' && n.tagName !== 'textarea' && n.value !== undefined && n.value !== '') {
    attrs.push(`value="${encodeEntities(n.value)}"`);
  }
  const open = `<${n.tagName}${attrs.length ? ' ' + attrs.join(' ') : ''}`;
  if (n.tagName === 'input' || VOID_TAGS.has(n.tagName)) return open + '>';
  if (n.tagName === 'option') return `${open}>${encodeEntities(n.value == null ? '' : n.value)}</option>`;
  if (n.tagName === 'textarea') return `${open}>${encodeEntities(n.value == null ? '' : n.value)}</textarea>`;
  return `${open}>${serializeChildren(n)}</${n.tagName}>`;
}

function scanOpenTag(html, lt) {
  let i = lt + 1;
  let name = '';
  while (i < html.length && /[a-zA-Z]/.test(html[i])) { name += html[i]; i++; }
  if (!name) return null;
  let quote = null;
  const attrsStart = i;
  while (i < html.length) {
    const c = html[i];
    if (quote) { if (c === quote) quote = null; }
    else if (c === '"' || c === "'") quote = c;
    else if (c === '>') return { name: name.toLowerCase(), attrsRaw: html.slice(attrsStart, i), end: i + 1 };
    i++;
  }
  return null;
}

function parseFragmentInto(html, parent) {
  let stack = [parent];
  let i = 0;
  const top = () => stack[stack.length - 1];

  const finalize = (el) => {
    if (el.tagName === 'textarea') el.value = el._pendingText || el.value || '';
    else if (el.tagName === 'option') {
      if (el.value === '' && el._pendingText) el.value = el._pendingText;
      // 找最近的 select 祖先（option 可能包在 optgroup 里）
      let p = el.parentNode;
      while (p && p.tagName && p.tagName !== 'select') p = p.parentNode;
      if (p && p.tagName === 'select') {
        p.options.push(el);
        if (el._selected) { p.value = el.value; p._selectChosen = true; }
        else if (!p._selectChosen && p.options.length === 1) p.value = el.value;
      }
    } else if (el.tagName === 'select') {
      if (!el._selectChosen && el.options.length) el.value = el.options[0].value;
    }
  };

  while (i < html.length) {
    const lt = html.indexOf('<', i);
    if (lt < 0) {
      const text = html.slice(i);
      const t = top();
      if (t && (t.tagName === 'textarea' || t.tagName === 'option')) t._pendingText += text;
      break;
    }
    if (lt > i) {
      const t = top();
      if (t && (t.tagName === 'textarea' || t.tagName === 'option')) t._pendingText += html.slice(i, lt);
      i = lt;
      continue;
    }
    if (html.startsWith('<!--', lt)) {
      const end = html.indexOf('-->', lt);
      i = end === -1 ? html.length : end + 3;
      continue;
    }
    if (html.startsWith('</', lt)) {
      const gt = html.indexOf('>', lt);
      const name = html.slice(lt + 2, gt === -1 ? html.length : gt).trim().toLowerCase();
      for (let k = stack.length - 1; k > 0; k--) {
        if (stack[k].tagName === name) { finalize(stack[k]); stack.length = k; break; }
      }
      i = gt === -1 ? html.length : gt + 1;
      continue;
    }
    const tag = scanOpenTag(html, lt);
    if (!tag) { i = lt + 1; continue; }
    const attrs = parseAttrs(tag.attrsRaw);
    const selfClosing = /\/\s*$/.test(tag.attrsRaw) || VOID_TAGS.has(tag.name);
    const el = createEl(tag.name, attrs);
    top().appendChild(el);
    if (!selfClosing) {
      // script/style 是原始文本块：跳到对应闭合标签，避免把 JS 里的字符串当 HTML 解析
      if (tag.name === 'script' || tag.name === 'style') {
        const closeRe = new RegExp('</' + tag.name, 'i');
        const rest = html.slice(tag.end);
        const cm = closeRe.exec(rest);
        const gtIdx = cm ? html.indexOf('>', tag.end + cm.index) : -1;
        i = gtIdx === -1 ? html.length : gtIdx + 1;
        continue;
      }
      stack.push(el);
    }
    i = tag.end;
  }
  // 未闭合的兜底收尾
  while (stack.length > 1) { finalize(stack[stack.length - 1]); stack.pop(); }
}

// ---- 选择器（支持 "tag" / ".class" / "#id" / "a, b" 组合，足够覆盖本工具） ----
function compileSelector(sel) {
  const m = { tag: null, id: null, classes: [] };
  const re = /([.#]?[\w-]+)/g;
  let t;
  while ((t = re.exec(sel)) !== null) {
    if (t[1][0] === '.') m.classes.push(t[1].slice(1));
    else if (t[1][0] === '#') m.id = t[1].slice(1);
    else m.tag = t[1].toLowerCase();
  }
  return m;
}

function matchesSelector(el, m) {
  if (!el || !el.tagName) return false;
  if (m.tag && el.tagName !== m.tag) return false;
  if (m.id && el.id !== m.id) return false;
  if (m.classes.length) {
    const cls = String(el.className || '').split(/\s+/);
    for (const c of m.classes) if (!cls.includes(c)) return false;
  }
  return true;
}

function queryDescendants(root, sel, all) {
  const parts = String(sel).split(',').map((s) => s.trim()).filter(Boolean).map(compileSelector);
  const out = [];
  const walk = (el) => {
    for (const child of el.children || []) {
      if (!child || !child.tagName) continue;
      if (parts.some((m) => matchesSelector(child, m))) {
        out.push(child);
        if (!all) return true;
      }
      if (walk(child)) return true;
    }
    return false;
  };
  walk(root);
  return all ? out : (out[0] || null);
}

function makeCanvasContext() {
  const noop = () => {};
  return new Proxy({
    canvas: null,
    measureText: () => ({ width: 0 }),
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
  }, {
    get(target, prop) {
      if (prop in target) return target[prop];
      return noop;
    },
    set(target, prop, val) { target[prop] = val; return true; },
  });
}

// ------------------------------------------------------------------ PRNG seed
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ------------------------------------------------------------------ main run
function buildSandbox(prefill, seed, logs, meta) {
  meta = meta || {};
  const elements = new Map();   // id → element（含树内与懒创建）
  let rootEl = null;
  let bodyRef = null;
  let headRef = null;
  let htmlRef = null;

  const getEl = (id) => {
    const key = String(id);
    if (elements.has(key)) return elements.get(key);
    const info = meta[key] || {};
    const el = createEl(info.tag || 'div', { id: key, class: info.class || '' });
    if (Object.prototype.hasOwnProperty.call(prefill, key)) el.value = prefill[key];
    elements.set(key, el);
    return el;
  };

  const walkIndex = (el) => {
    if (!el || !el.tagName) return;
    if (el.id && !elements.has(el.id)) elements.set(el.id, el);
    if (el.tagName === 'body' && !bodyRef) bodyRef = el;
    if (el.tagName === 'head' && !headRef) headRef = el;
    if (el.tagName === 'html' && !htmlRef) htmlRef = el;
    for (const c of el.children) walkIndex(c);
  };

  const winListeners = [];
  const docListeners = [];
  const fireEventList = (list, type) => {
    for (const l of list) {
      if (l.type !== type) continue;
      try { l.fn.call(null, { type, target: null }); }
      catch (e) { logs.push(`[${type}-listener-error] ${e && e.message}`); }
    }
  };

  const documentStub = {
    getElementById: (id) => getEl(id),
    querySelector: (sel) => {
      sel = String(sel).trim();
      const has = /:has\(\s*#([\w-]+)\s*\)/.exec(sel);
      if (has) return getEl(has[1]);
      if (rootEl) {
        const found = queryDescendants(rootEl, sel, false);
        if (found) return found;
      }
      if (sel[0] === '#') return getEl(sel.slice(1).split(/[\s.:\[]/)[0]);
      const m = compileSelector(sel);
      for (const [id, info] of Object.entries(meta)) {
        if (matchesSelector({ tagName: info.tag || 'div', id, className: info.class || '' }, m)) return getEl(id);
      }
      return null;
    },
    querySelectorAll: (sel) => (rootEl ? queryDescendants(rootEl, sel, true) : []),
    getElementsByClassName: (c) => (rootEl ? queryDescendants(rootEl, '.' + c, true) : []),
    getElementsByTagName: (t) => (rootEl ? queryDescendants(rootEl, String(t).toLowerCase(), true) : []),
    createElement: (tag) => createEl(tag, {}),
    createTextNode: (t) => ({ nodeType: 3, data: t, textContent: t }),
    createDocumentFragment: () => createEl('fragment', {}),
    get body() { return bodyRef || getEl('__body'); },
    get documentElement() { return htmlRef || getEl('__html'); },
    get head() { return headRef || getEl('__head'); },
    addEventListener(type, fn) { docListeners.push({ type, fn }); },
    removeEventListener() {},
    readyState: 'complete',
    title: '',
    cookie: '',
  };

  const sandbox = {
    console: {
      log: (...a) => logs.push(a.map(String).join(' ')),
      info: (...a) => logs.push(a.map(String).join(' ')),
      warn: (...a) => logs.push('[warn] ' + a.map(String).join(' ')),
      error: (...a) => logs.push('[error] ' + a.map(String).join(' ')),
      debug: () => {},
    },
    document: documentStub,
    navigator: { userAgent: 'bid-price-calc/1.0 (headless)', language: 'zh-CN', onLine: false },
    location: { href: 'about:blank', protocol: 'file:', search: '', hash: '' },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {}, clear() {} },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {}, clear() {} },
    history: { pushState() {}, replaceState() {} },
    performance: { now: () => Date.now() },
    requestAnimationFrame: (cb) => setTimeout(cb, 0),
    cancelAnimationFrame: (id) => clearTimeout(id),
    fetch: () => Promise.reject(new Error('headless: no network')),
    Image: function () { return createEl('img', {}); },
    FileReader: function () {},
    HTMLElement: function () {},
    Node: function () {},
    CustomEvent: function () { return {}; },
    Event: function (type) { return { type }; },
    matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
    devicePixelRatio: 1,
    innerWidth: 1440, innerHeight: 900,
    alert(msg) { logs.push('[alert] ' + String(msg)); },
    confirm() { return false; }, prompt() { return null; },
    print() {}, open() { return null; }, close() {},
    addEventListener(type, fn) { winListeners.push({ type, fn }); },
    removeEventListener() {},
    dispatchEvent() { return true; },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    scrollTo() {}, scrollX: 0, scrollY: 0,
    structuredClone: (x) => JSON.parse(JSON.stringify(x)),
  };

  // window === 全局
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  sandbox.parent = sandbox;
  sandbox.top = sandbox;
  sandbox.frames = sandbox;
  sandbox.__stubLogs = logs;

  // 把整页 HTML 解析为 mini-DOM 树（script/style 内容跳过）
  sandbox.__loadHtml = (html) => {
    rootEl = createEl('document-fragment', {});
    parseFragmentInto(String(html), rootEl);
    walkIndex(rootEl);
    return true;
  };

  // 生命周期事件触发（脚本加载完成后由 runPage 调用）
  sandbox.__fire = (type) => {
    fireEventList(docListeners, type);
    fireEventList(winListeners, type);
    if (type === 'load' && typeof sandbox.onload === 'function') {
      try { sandbox.onload(); } catch (e) { logs.push('[onload-error] ' + (e && e.message)); }
    }
  };

  // Chart.js 桩：记录最后一次配置，供调试
  const ChartStub = function (ctx, config) {
    ChartStub.lastConfig = config;
    ChartStub.instances = (ChartStub.instances || 0) + 1;
    return { destroy() {}, update() {}, resize() {} };
  };
  sandbox.Chart = ChartStub;

  // 随机数种子
  if (typeof seed === 'number' && Number.isFinite(seed)) {
    const mathObj = Object.create(Math);
    mathObj.random = mulberry32(seed);
    sandbox.Math = mathObj;
  }
  return sandbox;
}

/** 静态扫描 HTML：id → {tag, class}，供 document.querySelector 按类名查找 */
function extractStaticMeta(html) {
  const meta = Object.create(null);
  const tagRe = /<([a-zA-Z][\w-]*)\b((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let m;
  while ((m = tagRe.exec(html)) !== null) {
    const tag = m[1].toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'link' || tag === 'meta') continue;
    const attrs = m[2];
    const id = /\bid\s*=\s*["']([^"']+)["']/i.exec(attrs);
    if (!id) continue;
    const cls = /\bclass\s*=\s*["']([^"']*)["']/i.exec(attrs);
    meta[id[1]] = { tag, class: cls ? cls[1] : '' };
  }
  return meta;
}

function runPage(opts) {
  const { toolRoot, page, inputs, seed, deviationAnchors, fixedBid } = opts;
  const pageInfo = PAGES[page];
  if (!pageInfo) fail(`未知 page: ${page}（支持 base | pro）`);
  const htmlPath = path.join(toolRoot, 'frontend', pageInfo.html);
  if (!fs.existsSync(htmlPath)) fail(`页面不存在: ${htmlPath}`);
  const html = fs.readFileSync(htmlPath, 'utf8');

  const prefill = extractPrefill(html);
  const meta = extractStaticMeta(html);
  const scripts = extractScripts(html);
  const logs = [];
  const sandbox = buildSandbox(prefill, seed, logs, meta);
  sandbox.__loadHtml(html);
  const context = vm.createContext(sandbox);

  // 按文档顺序执行脚本（跳过 CDN；本地 src 相对 HTML 解析）
  let loadError = null;
  try {
    for (const s of scripts) {
      if (s.src) {
        if (/^https?:/i.test(s.src)) continue; // Chart.js 等 CDN，用桩替代
        const p = path.resolve(path.dirname(htmlPath), s.src);
        if (!fs.existsSync(p)) { logs.push(`[skip] 脚本不存在: ${p}`); continue; }
        runScript(fs.readFileSync(p, 'utf8'), p, context, logs);
      } else if (s.body.trim()) {
        runScript(s.body, `${pageInfo.html}#inline`, context, logs);
      }
    }
  } catch (e) {
    loadError = e && e.stack ? e.stack : String(e);
    logs.push('[load-error] ' + (e && e.message));
  }

  // 触发 DOMContentLoaded / load，让页面初始化逻辑（规则行等）执行
  // （在输入覆盖之后触发，确保初始化能读到选定的规则）
  // —— 见下方 applyInputs 之后的调用


  // 覆盖页面默认值
  const applied = {};
  if (loadError) {
    return { ok: false, page, pageLabel: pageInfo.label, error: loadError, applied, resultsHtml: '', histogram: null, logs: logs.slice(-200) };
  }
  for (const [k, v] of Object.entries(inputs || {})) {
    applied[k] = String(v);
  }
  // 直接通过 document 写入
  for (const [k, v] of Object.entries(applied)) {
    vm.runInContext(`document.getElementById(${JSON.stringify(k)}).value = ${JSON.stringify(v)};`, context);
  }

  // 触发 DOMContentLoaded / load（初始化动态规则行等）
  try {
    vm.runInContext('typeof __fire === "function" && __fire("DOMContentLoaded")', context);
    vm.runInContext('typeof __fire === "function" && __fire("load")', context);
    // 模拟页面上"切换规则"事件，触发规则专属初始化
    vm.runInContext(`
      ['benchmarkRule', 'scoringRule'].forEach(id => {
        const el = document.getElementById(id);
        if (el && typeof el.dispatchEvent === 'function') el.dispatchEvent(new Event('change'));
      });
    `, context);
  } catch (e) {
    logs.push('[lifecycle-error] ' + (e && e.message));
  }

  // 自定义偏差率插入法锚点（线性扣分规则的精确复刻）
  if (Array.isArray(deviationAnchors) && deviationAnchors.length) {
    const anchors = deviationAnchors.map(([k, score]) => [Number(k), Number(score)]);
    vm.runInContext(`window.__customDeviationAnchors = ${JSON.stringify(anchors)};
      window.getDeviationInterpolationConfig = function () {
        const A = window.__customDeviationAnchors.map(([k, score]) => ({ k, score }));
        const pointRules = A.map((a, i) => ({
          rowNumber: i + 1, rawK: String(a.k), score: a.score,
          label: a.k + '%', type: 'point', k: a.k
        }));
        return {
          rawRules: pointRules.map(p => ({ rowNumber: p.rowNumber, rawK: p.rawK, score: p.score, label: p.label, type: 'point' })),
          pointRules,
          rangeRules: [],
          anchors: A.map(a => ({ k: a.k, score: a.score, hidden: false, sourceRule: null }))
        };
      };`, context);
  }

  // 条件命中仿真：固定我方报价（bids[0]）
  const fixed = (typeof fixedBid === 'number' && Number.isFinite(fixedBid)) ? fixedBid : null;
  vm.runInContext(`window.__fixedBid = ${JSON.stringify(fixed)};`, context);

  // 劫持 drawHistogram：捕获概率数据而不绘制
  vm.runInContext(`
    if (typeof drawHistogram === 'function') {
      window.__histCapture = null;
      drawHistogram = function(probabilities, minPrice, riskZones) {
        window.__histCapture = {
          probabilities: probabilities.map(Number),
          minPrice: Number(minPrice),
          riskZones: riskZones
        };
      };
    }
  `, context);

  // 执行模拟
  const entry = vm.runInContext(
    'typeof prepareAndRunSimulation === "function" ? "prepareAndRunSimulation" : (typeof runEnhancedSimulation === "function" ? "runEnhancedSimulation" : null)',
    context
  );
  if (!entry) fail('页面脚本加载后未找到 prepareAndRunSimulation/runEnhancedSimulation');

  let error = null;
  try {
    vm.runInContext(`${entry}();`, context, { timeout: 600000 });
  } catch (e) {
    error = e && e.stack ? e.stack : String(e);
  }

  // 收集结果
  const resultsHtml = vm.runInContext('document.getElementById("results").innerHTML || ""', context);
  const hist = vm.runInContext('window.__histCapture || null', context);
  const out = {
    ok: !error,
    page,
    pageLabel: pageInfo.label,
    entry,
    seed: (typeof seed === 'number' && Number.isFinite(seed)) ? seed : null,
    applied,
    error,
    resultsHtml,
    histogram: hist,
    logs: logs.slice(-200),
  };

  if (!error && resultsHtml) {
    const sim = /模拟结果[（(](\d+)[次)）]/.exec(resultsHtml);
    const mean = /胜出报价参考值[：:]\s*([\d.]+)\s*万元/.exec(resultsHtml);
    if (sim) out.simulations = Number(sim[1]);
    if (mean) out.winningMean = Number(mean[1]);
    if (hist && hist.riskZones) {
      const rz = hist.riskZones;
      out.riskZones = {
        low:    { lower: rz.lowRiskLower,    upper: rz.lowRiskUpper },
        medium: { lower: rz.mediumRiskLower, upper: rz.mediumRiskUpper },
        high:   { lower: rz.highRiskLower,   upper: rz.highRiskUpper },
      };
      out.targetRange = { lower: rz.lowRiskLower, upper: rz.lowRiskUpper };
    }
    // 从结果 HTML 兜底解析风险区间文案
    if (!out.riskZones) {
      const low = /低风险区间[\s\S]{0,120}?(-?\d+)-(-?\d+)万元/.exec(resultsHtml);
      if (low) out.targetRange = { lower: Number(low[1]), upper: Number(low[2]) };
    }
  }

  if (hist && Array.isArray(hist.probabilities)) {
    out.prices = hist.probabilities.map((_, i) => hist.minPrice + i);
    // 条件中标概率：我方固定报价价位的胜出频率（对手为连续随机值，
    // 恰好落在同一整数价位的概率≈0，故该频率即我方中标频率）
    if (fixed !== null) {
      out.fixedBid = fixed;
      const idx = Math.round(fixed) - hist.minPrice;
      out.fixedBidHit = (idx >= 0 && idx < hist.probabilities.length)
        ? Math.round(hist.probabilities[idx] * 100) / 100
        : null;
      if (out.fixedBidHit === null) {
        logs.push(`[warn] fixedBid=${fixed} 不在模拟报价区间 [${hist.minPrice}, ${hist.minPrice + hist.probabilities.length - 1}] 内，无法取命中率`);
      }
    }
  }
  return out;
}

function runScript(code, filename, context, logs) {
  // 修补原工具已知 bug：enhanced_script(.pro).js 中 `const scoringRule` 声明在
  // 模拟循环块内，却在函数级（结果展示段）被引用 —— 浏览器/Node 都会抛
  // ReferenceError。这里在内存中降级为 var（函数作用域），不修改原文件。
  if (/enhanced_script(_pro)?\.js$/.test(filename)) {
    const before = code;
    code = code.replace(
      /const(\s+scoringRule\s*=\s*document\.getElementById\(["']scoringRule["']\)\.value;)/,
      'var$1'
    );
    if (code !== before) logs.push('[patch] scoringRule: const -> var（原工具作用域 bug）');
    // 条件命中仿真：把 window.__fixedBid 固定为我方报价（bids[0]），
    // 其余对手仍随机生成 —— 我方价位在直方图中的胜出频率 = 条件中标概率。
    const before2 = code;
    code = code.split('const bidder1Bid = bids[0];').join(
      'if (window.__fixedBid != null && Number.isFinite(window.__fixedBid)) { bids[0] = window.__fixedBid; }\n        const bidder1Bid = bids[0];'
    );
    if (code !== before2) logs.push('[patch] fixedBid hook installed');
    else logs.push('[warn] fixedBid hook 未命中（源码结构变化），条件仿真不生效');
  }
  try {
    vm.runInContext(code, context, { filename, timeout: 120000 });
  } catch (e) {
    logs.push(`[script-error] ${filename}: ${e && e.message ? e.message : e}`);
    throw e;
  }
}

function listInputs(toolRoot, page) {
  const htmlPath = path.join(toolRoot, 'frontend', PAGES[page].html);
  const html = fs.readFileSync(htmlPath, 'utf8');
  const prefill = extractPrefill(html);
  const rows = Object.keys(prefill).sort().map((k) => ({ id: k, default: prefill[k] }));
  return { page, html: path.basename(htmlPath), count: rows.length, inputs: rows };
}

// --------------------------------------------------------------------- entry
function main() {
  const args = parseArgs(process.argv);
  const toolRoot = resolveToolRoot(args.toolRoot);

  if (args.listInputs) {
    const page = args.page || 'base';
    const result = listInputs(toolRoot, page);
    const text = JSON.stringify(result, null, 2);
    if (args.output) fs.writeFileSync(args.output, text, 'utf8');
    else process.stdout.write(text + '\n');
    return;
  }

  if (!args.inputs) fail('缺少 --input input.json');
  if (!fs.existsSync(args.inputs)) fail(`输入文件不存在: ${args.inputs}`);
  let spec;
  try { spec = JSON.parse(fs.readFileSync(args.inputs, 'utf8').replace(/^﻿/, '')); }
  catch (e) { fail(`输入 JSON 解析失败: ${e.message}`); }

  const page = (spec.page || args.page || 'base').toLowerCase();
  const result = runPage({
    toolRoot, page,
    inputs: spec.inputs || {},
    seed: spec.seed,
    deviationAnchors: spec.deviationAnchors,
    fixedBid: (typeof spec.fixedBid === 'number') ? spec.fixedBid : Number(spec.fixedBid),
  });

  // 单位标签（引擎结果文案硬编码“万元”；按元仿真时替换，结构化字段本身已是该单位）
  if (spec.unitLabel && result.resultsHtml) {
    result.resultsHtml = result.resultsHtml.split('万元').join(spec.unitLabel);
    result.unitLabel = spec.unitLabel;
  } else if (!result.unitLabel) {
    result.unitLabel = '万元';
  }

  const text = JSON.stringify(result, null, 2);
  if (args.output) {
    fs.writeFileSync(args.output, text, 'utf8');
    process.stderr.write(`结果已写入 ${args.output}\n`);
  } else {
    process.stdout.write(text + '\n');
  }
  if (!result.ok) process.exit(2);
}

main();
