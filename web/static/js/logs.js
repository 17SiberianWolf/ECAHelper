/* ECAHelper 系统日志页交互（原生 JS，无构建链、零依赖、无 CDN）。
 *
 * 暴露 window.ECA.initLogs，由 web/templates/logs.html 的 {% block scripts %} 显式调用。
 *
 * 后端契约（后端另行实现，本文件只消费，不改 Python）：
 *   GET /api/logs/query?start=&end=&level=&category=&keyword=&ok=&page=&page_size=
 *     -> {"total":342,"page":1,"page_size":50,"items":[{id,ts,level,category,action,
 *         target,result,status_code,duration_ms,request_id,message,detail}]}
 *   GET /api/logs/export?（同上筛选参数，不含分页）
 *     -> {"path":"..","filename":"..","download":"/api/export/download?file=xxx.csv"}
 *
 * 依赖：components.js（window.ECA：可见性工具 showEl/hideEl/toggleEl + YearMonth）。
 * 约定：可见性切换一律用 ECA.showEl/hideEl/toggleEl（classList），严禁 style.display。
 */
(function () {
  "use strict";

  // 与 components.js / app.js 共享同一命名空间（components.js 先加载并创建 window.ECA）。
  var ECA = window.ECA = window.ECA || {};

  function el(id) { return document.getElementById(id); }

  function escText(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* 状态：服务端分页，前端只保存当前页与总数。 */
  var state = { page: 1, total: 0, page_size: 50, items: [] };

  var PAGE_SIZE = 50;

  /* 级别 -> (中文, tag 类)；未列出的按原样显示。 */
  var LEVEL_ZH = { INFO: "信息", WARNING: "警告", ERROR: "错误" };
  function levelClass(level) {
    if (level === "INFO") return "tag ok";
    if (level === "WARNING") return "tag warn";
    if (level === "ERROR") return "tag bad";
    return "tag grey";
  }
  /* 类别 -> 中文 */
  var CATEGORY_ZH = {
    query: "查询",
    import: "导入",
    export: "导出",
    quality: "质量",
    system: "系统",
  };
  function catZh(c) {
    if (!c) return "";
    return CATEGORY_ZH[c] || c;
  }
  function resultTag(result) {
    if (result === "fail") return '<span class="tag bad">失败</span>';
    if (result === "ok") return '<span class="tag ok">成功</span>';
    return '<span class="tag grey">' + (escText(result) || "—") + "</span>";
  }

  /* 统一的 JSON GET：非 2xx 时抛出后端给出的 error 文案。 */
  function apiGet(url) {
    return fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error((data && data.error) || ("HTTP " + r.status));
        return data;
      });
    });
  }

  function setMsg(text, isError) {
    var box = el("lgMsg");
    if (!box) return;
    box.textContent = text || "";
    box.classList.remove("msg-ok", "msg-error");
    if (isError) box.classList.add("msg-error");
  }

  /* 读取筛选条件（空值一律不传，等价于「不限」）。 */
  function buildParams() {
    var p = {};
    var s = el("lgStart") ? el("lgStart").value : "";
    var e = el("lgEnd") ? el("lgEnd").value : "";
    if (s) p.start = s;
    if (e) p.end = e;
    var lv = el("lgLevel") ? el("lgLevel").value : "";
    if (lv) p.level = lv;
    var cat = el("lgCategory") ? el("lgCategory").value : "";
    if (cat) p.category = cat;
    var kw = el("lgKeyword") ? el("lgKeyword").value : "";
    if (kw && kw.trim()) p.keyword = kw.trim();
    var ok = el("lgOk") ? el("lgOk").value : "";
    if (ok) p.ok = ok;
    return p;
  }

  function totalPages() {
    return Math.max(1, Math.ceil(state.total / (state.page_size || PAGE_SIZE)));
  }

  /* ---------- 渲染 ---------- */
  function renderTable() {
    var box = el("logResult");
    if (!box) return;

    if (!state.items.length) {
      box.innerHTML =
        '<p class="muted">没有符合条件的日志记录。可放宽时间范围，或把级别 / 类别 / 成败改回「全部」、清空关键词后重试。</p>';
      ECA.showEl(box);
      return;
    }

    var h = "<table><thead><tr>" +
      "<th>时间</th><th>级别</th><th>类别</th><th>操作</th><th>对象</th><th>结果</th>" +
      "<th class='num'>耗时</th></tr></thead><tbody>";

    state.items.forEach(function (it) {
      var hasDetail = !!it.detail;
      h += "<tr class='log-row" + (hasDetail ? " has-detail" : "") + "'" +
        (hasDetail ? " data-log-toggle" : "") + ">";
      h += "<td class='log-ts'>" +
        (hasDetail ? "<span class='arrow'>▸</span> " : "") + escText(it.ts || "") + "</td>";
      h += "<td><span class='" + levelClass(it.level) + "'>" +
        escText(LEVEL_ZH[it.level] || it.level || "") + "</span></td>";
      h += "<td>" + escText(catZh(it.category)) + "</td>";
      h += "<td>" + escText(it.action || "") + "</td>";
      h += "<td>" + escText(it.target || "") + "</td>";
      h += "<td>" + resultTag(it.result) + "</td>";
      h += "<td class='num'>" + (it.duration_ms == null ? "" : it.duration_ms + " ms") + "</td>";
      h += "</tr>";
      if (hasDetail) {
        h += "<tr class='log-detail hidden'><td colspan='7'>" +
          "<pre>" + escText(it.detail) + "</pre></td></tr>";
      }
    });

    h += "</tbody></table>";
    box.innerHTML = h;
    ECA.showEl(box);
  }

  /* 把分页控件渲染进指定容器（空态/边界态都在内部处理）。
   * 容器不存在时安全跳过，沿用现有 if (!box) return 风格。 */
  function renderPagerInto(box) {
    if (!box) return;

    var pages = totalPages();
    var h = '<div class="quick">';
    h += '<button data-pg="prev"' + (state.page <= 1 ? " disabled" : "") + ">上一页</button>";
    h += '<button data-pg="next"' + (state.page >= pages ? " disabled" : "") + ">下一页</button>";
    h += '<span class="muted">第 ' + state.page + " / " + pages + " 页 · 共 " +
      state.total + " 条</span>";
    h += "</div>";
    box.innerHTML = h;

    var btns = box.querySelectorAll("[data-pg]");
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener("click", function () {
        if (b.disabled) return;
        var kind = b.getAttribute("data-pg");
        doQuery(kind === "prev" ? state.page - 1 : state.page + 1);
      });
    });
  }

  /* 渲染一次、落两处：表格上方常驻分页条（logPagerTop）+ 表格下方吸底分页栏（logPager），
   * 两者点击行为完全一致（同样调用 doQuery(prev/next)）。
   * 空态（total 为 0）：两个容器清空并用 ECA.hideEl 隐藏（严禁 style.display）；
   * 有结果：先 ECA.showEl 再渲染，确保吸底条与顶部分页条都可见。 */
  function renderPager() {
    var top = el("logPagerTop"), bot = el("logPager");
    if (!state.total) {
      if (top) top.innerHTML = "";
      if (bot) bot.innerHTML = "";
      ECA.hideEl(top); ECA.hideEl(bot);
      return;
    }
    ECA.showEl(top); ECA.showEl(bot);
    renderPagerInto(top);
    renderPagerInto(bot);
  }

  function render() {
    renderTable();
    renderPager();
  }

  /* ---------- 取数 ---------- */
  function doQuery(page) {
    state.page = Math.max(1, page || 1);
    var p = buildParams();
    p.page = state.page;
    p.page_size = PAGE_SIZE;
    setMsg("查询中…");
    apiGet("/api/logs/query?" + new URLSearchParams(p).toString())
      .then(function (d) {
        state.total = d.total || 0;
        state.page = d.page || state.page;
        state.page_size = d.page_size || PAGE_SIZE;
        state.items = d.items || [];
        render();
        setMsg(state.items.length ? "" : "查询完成，无匹配记录");
      })
      .catch(function (err) {
        state.items = [];
        state.total = 0;
        render();
        setMsg("查询失败：" + err.message, true);
      });
  }

  function doExport() {
    var p = buildParams();
    var btn = el("btnExport");
    if (btn) btn.disabled = true;
    setMsg("导出中…");
    apiGet("/api/logs/export?" + new URLSearchParams(p).toString())
      .then(function (d) {
        if (d && d.download) {
          window.location.href = d.download;
          setMsg("已开始下载：" + (d.filename || ""));
        } else {
          setMsg("导出完成");
        }
      })
      .catch(function (err) { setMsg("导出失败：" + err.message, true); })
      .then(function () { if (btn) btn.disabled = false; });
  }

  /* 展开 / 收起异常堆栈：可见性走 classList，箭头用字符切换（不依赖任何新 CSS 类）。 */
  function onRowClick(e) {
    var tr = e.target.closest && e.target.closest("[data-log-toggle]");
    if (!tr) return;
    var d = tr.nextElementSibling;
    if (!d || !d.classList.contains("log-detail")) return;
    var nowHidden = d.classList.toggle("hidden");
    var arrow = tr.querySelector(".arrow");
    if (arrow) arrow.textContent = nowHidden ? "▸" : "▾";
  }

  /* ---------- 页面初始化 ---------- */
  ECA.initLogs = function () {
    var y = new Date().getFullYear();
    var lo = (y - 2) + "-01";
    var hi = y + "-12";
    // 年月双下拉（复用 components.js 的 ECA.YearMonth），允许「任意」= 不限时间。
    ECA.YearMonth({ mount: "lgStartBox", hiddenId: "lgStart", lo: lo, hi: hi, allowEmpty: true });
    ECA.YearMonth({ mount: "lgEndBox", hiddenId: "lgEnd", lo: lo, hi: hi, allowEmpty: true });

    var q = el("btnQuery");
    if (q) q.addEventListener("click", function () { doQuery(1); });

    var ex = el("btnExport");
    if (ex) ex.addEventListener("click", function () { doExport(); });

    var kw = el("lgKeyword");
    if (kw) {
      kw.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") doQuery(1);
      });
    }

    // 级别 / 类别 / 成败：变更即重新查询（回到第 1 页）。
    ["lgLevel", "lgCategory", "lgOk"].forEach(function (id) {
      var s = el(id);
      if (s) s.addEventListener("change", function () { doQuery(1); });
    });

    document.addEventListener("click", onRowClick);

    doQuery(1);
  };

  window.ECA = ECA;
})();
