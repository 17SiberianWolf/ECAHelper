/* B. 日志页双容器分页桩测（零依赖 DOM 桩，无 jsdom / 无 npm 包）。
 * 验证 logs.js 的 renderPagerInto 同时渲染到 #logPagerTop 与 #logPager，
 * 空态双容器清空，点击行为一致，且翻页会带正确 page。
 * 用法: node tools/logs_pager_test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

/* ---------- DOM 桩 ---------- */
function classList() {
  const s = {};
  return {
    add(c) { s[c] = 1; },
    remove(c) { delete s[c]; },
    toggle(c, force) {
      if (force === undefined) { if (s[c]) delete s[c]; else s[c] = 1; }
      else if (force) s[c] = 1; else delete s[c];
    },
    contains(c) { return !!s[c]; },
  };
}

// 从容器 innerHTML 中解析 <button data-pg="..."> 生成可点击按钮桩，并收集 handler
function parsePgButtons(box) {
  const html = box._html || '';
  const re = /<button\b([^>]*)>/g;
  let m, list = [];
  while ((m = re.exec(html))) {
    const attrs = m[1];
    const pg = /data-pg="([^"]+)"/.exec(attrs);
    if (!pg) continue;
    const disabled = /\bdisabled\b/.test(attrs);
    const handlers = {};
    list.push({
      _pg: pg[1],
      disabled: disabled,
      attrs: {},
      getAttribute(k) { return k === 'data-pg' ? this._pg : this.attrs[k]; },
      setAttribute(k, v) { this.attrs[k] = v; if (k === 'disabled') this.disabled = true; },
      removeAttribute(k) { delete this.attrs[k]; if (k === 'disabled') this.disabled = false; },
      addEventListener(t, fn) { (handlers[t] = handlers[t] || []).push(fn); },
      dispatch(t, ev) { (handlers[t] || []).forEach((fn) => fn(ev || {})); },
    });
  }
  box._pgButtons = list;
  return list;
}

function makeEl(tag) {
  const e = {
    tag, attrs: {}, _html: '', value: '', textContent: '',
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
  };
  e.classList = classList();
  e.listeners = {};
  e.addEventListener = function (t, fn) { (e.listeners[t] = e.listeners[t] || []).push(fn); };
  e.removeEventListener = function () {};
  e.dispatch = function (t, ev) { (e.listeners[t] || []).forEach((fn) => fn(ev || {})); };
  e.setAttribute = function (k, v) { e.attrs[k] = v; };
  e.getAttribute = function (k) { return e.attrs[k]; };
  e.querySelectorAll = function (sel) { return sel === '[data-pg]' ? parsePgButtons(e) : []; };
  e.querySelector = function () { return null; };
  e.scrollIntoView = function () {};
  return e;
}

// 同一 id 返回同一对象（initLogs 注册监听、后续 dispatch 必须是同一对象）
const byId = {};
function getEl(id) { return byId[id] || (byId[id] = makeEl('div')); }

const docListeners = {};
global.document = {
  getElementById: getEl,
  addEventListener(t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
  removeEventListener() {},
  createElement: makeEl,
};

/* ---------- 可控 fetch 桩 ---------- */
const fetchUrls = [];
let currentPayload = null;
function sampleItems(n) {
  const a = [];
  for (let i = 0; i < n; i++) a.push({ id: i + 1, ts: '2024-01-0' + (i % 9 + 1) + ' 10:00', level: 'INFO', category: 'query', action: '查询', target: 'x', result: 'ok', duration_ms: 12 });
  return a;
}
global.fetch = function (url) {
  fetchUrls.push(url);
  return Promise.resolve({ ok: true, json() { return Promise.resolve(currentPayload); } });
};

/* ---------- window 桩 ---------- */
global.window = global;
global.location = {};
// ECA.showEl/hideEl 模拟 components.js 真实行为：切换 'hidden' class（严禁 style.display）
global.ECA = {
  showEl(e) { if (e && e.classList) e.classList.remove('hidden'); },
  hideEl(e) { if (e && e.classList) e.classList.add('hidden'); },
  toggleEl() {},
  YearMonth() {},
};

/* ---------- 载入 logs.js（IIFE，仅暴露 initLogs，不自动查询） ---------- */
const logsPath = path.resolve(__dirname, '..', 'web', 'static', 'js', 'logs.js');
require(logsPath);

/* ---------- 断言 ---------- */
let pass = 0, fail = 0;
function chk(name, cond) {
  console.log((cond ? 'PASS' : 'FAIL') + ' | ' + name);
  if (cond) pass++; else fail++;
}
function tick(n) {
  n = n || 4;
  let p = Promise.resolve();
  for (let i = 0; i < n; i++) p = p.then(() => new Promise((r) => setTimeout(r, 0)));
  return p;
}

(async function () {
  /* 阶段一：成功渲染（total:120, page_size:50 -> 3 页） */
  fetchUrls.length = 0;
  currentPayload = { total: 120, page: 1, page_size: 50, items: sampleItems(50) };
  global.ECA.initLogs();
  await tick(5);

  const top = byId['logPagerTop']._html;
  const bot = byId['logPager']._html;

  chk('1a 顶部分页含「第 1 / 3 页 · 共 120 条」', top.indexOf('第 1 / 3 页 · 共 120 条') !== -1);
  chk('1b 顶部分页含「上一页」', top.indexOf('上一页') !== -1);
  chk('1c 顶部分页含「下一页」', top.indexOf('下一页') !== -1);
  chk('1d 底部分页含「第 1 / 3 页 · 共 120 条」', bot.indexOf('第 1 / 3 页 · 共 120 条') !== -1);
  chk('1e 底部分页含「上一页」「下一页」', bot.indexOf('上一页') !== -1 && bot.indexOf('下一页') !== -1);

  /* 2. 上页禁用（page=1） */
  const topBtns = byId['logPagerTop']._pgButtons || [];
  const prevBtn = topBtns.filter((b) => b._pg === 'prev')[0];
  const nextBtn = topBtns.filter((b) => b._pg === 'next')[0];
  chk('2a page=1 时 prev 按钮带 disabled', !!prevBtn && prevBtn.disabled === true);
  chk('2b page=1 时 next 按钮未禁用', !!nextBtn && nextBtn.disabled === false);

  /* 5. 两容器内容一致 */
  chk('5 顶/底分页容器内容完全一致', top === bot && top.length > 0);

  /* C（增量）：有结果态两个容器都 showEl（classList 不含 hidden） */
  chk('C0a 有结果态 logPagerTop 经 showEl 显示（不含 hidden）', !byId['logPagerTop'].classList.contains('hidden'));
  chk('C0b 有结果态 logPager 经 showEl 显示（不含 hidden）', !byId['logPager'].classList.contains('hidden'));

  /* 阶段二：空态（total:0） */
  fetchUrls.length = 0;
  currentPayload = { total: 0, page: 1, page_size: 50, items: [] };
  byId['btnQuery'].dispatch('click'); // handler -> doQuery(1)
  await tick(5);
  chk('3a 空态下 顶部分页容器 innerHTML === ""', byId['logPagerTop']._html === '');
  chk('3b 空态下 底部分页容器 innerHTML === ""', byId['logPager']._html === '');

  /* C（增量）：空态两个容器都 hideEl（classList 含 hidden），否则吸底条会残留遮挡页脚 */
  chk('C1a 空态 logPagerTop 经 hideEl 隐藏（classList 含 hidden）', byId['logPagerTop'].classList.contains('hidden'));
  chk('C1b 空态 logPager 经 hideEl 隐藏（classList 含 hidden）', byId['logPager'].classList.contains('hidden'));

  /* 阶段三：翻页（点击下一页 -> 期望再次 fetch 且 query 含 page=2） */
  fetchUrls.length = 0;
  currentPayload = { total: 120, page: 1, page_size: 50, items: sampleItems(50) };
  byId['btnQuery'].dispatch('click');
  await tick(5);
  const next3 = (byId['logPagerTop']._pgButtons || []).filter((b) => b._pg === 'next')[0];
  chk('4a 重新渲染后存在可用的 next 按钮', !!next3 && next3.disabled === false);
  next3.dispatch('click'); // handler -> doQuery(page+1) = doQuery(2)
  await tick(5);
  const called2 = fetchUrls.some((u) => u.indexOf('/api/logs/query') !== -1 && u.indexOf('page=2') !== -1);
  chk('4b 点击下一页后 fetch 再次调用且 query 串含 page=2', called2 && fetchUrls.length >= 1);

  console.log('---- PAGER TOTAL=' + (pass + fail) + ' PASS=' + pass + ' FAIL=' + fail);
  process.exit(fail ? 1 : 0);
})();
