/* ECAHelper 前端交互（原生 JS，无构建链）。
 * 负责：导入触发、查询表单、三层结果渲染、快捷区间、图表渲染、导出。
 * 依赖：components.js（window.ECA：可见性工具 / SearchableSelect / YearMonth）、
 *       charts.js（window.ECACharts）。
 * 注意：可见性切换一律用 ECA.showEl/hideEl/toggleEl（classList），严禁 style.display。
 */
(function () {
  "use strict";

  // 与 components.js 共享同一命名空间（components.js 先加载并创建 window.ECA）。
  var ECA = window.ECA = window.ECA || {};

  function el(id) { return document.getElementById(id); }
  function pad2(n) { return n < 10 ? "0" + n : "" + n; }

  function api(url, method, body) {
    var opt = { method: method || "GET", headers: { "Content-Type": "application/json" } };
    if (body) opt.body = JSON.stringify(body);
    return fetch(url, opt).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
        return data;
      });
    });
  }

  function fmtH(n) { return (Math.round((n || 0) * 10) / 10).toLocaleString(); }

  function setMsg(box, text, kind) {
    if (!box) return;
    box.textContent = text || "";
    // 不破坏其它 class（如 spinner/hidden）：仅增删消息相关类，用 classList 管理可见性。
    box.classList.remove("msg-ok", "msg-error");
    if (kind) box.classList.add("msg-" + kind);
    if (text) ECA.showEl(box);
  }

  /* ---------- 三层结果渲染 ---------- */
  /* 按接口实际返回的键动态渲染：
   *   - 有 by_person → 渲染「按人员」；有 by_project → 渲染「按项目明细」；
   *   - 键不存在时不输出任何空表头（修复员工页多渲染空「按项目」表）。
   * 顶部卡片按接口真实维度展示（修复把 persons 误标为「项目数」的缺陷）。
   */
  function renderThreeLayer(target, result, opts) {
    opts = opts || {};
    var t = result.total || {};
    var html = "";

    var cards = [];
    cards.push(card("总工时 (h)", fmtH(t.total_h)));
    if (opts.cardMode === "employee") {
      // 员工页顶部卡片对齐 PRD §4.2：总工时 / 项目工时 / 非项目工时 / 覆盖月份。
      // 单查一人时「人员数=1」无意义噪声，故不放人员数/项目数/明细行数卡。
      var projH = 0, nonH = 0;
      (result.by_project || []).forEach(function (p) { projH += (p.h || 0); });
      (result.non_project || []).forEach(function (p) { nonH += (p.h || 0); });
      cards.push(card("项目工时 (h)", fmtH(projH)));
      cards.push(card("非项目工时 (h)", fmtH(nonH)));
    } else {
      cards.push(card("明细行数", t.rows || 0));
      cards.push(card("人员数", t.persons || 0));       // t.persons = distinct resource_id_norm（真实口径）
      if (result.by_project) {
        cards.push(card("项目数", result.by_project.length)); // 项目维度以 by_project 长度为据
      }
    }
    cards.push(card("覆盖月份", t.months || 0));
    html += '<div class="cards">' + cards.join("") + "</div>";

    html += sectionTitle("按月趋势", true);
    html += table(["月份", "工时(h)", "行数"],
      (result.by_month || []).map(function (m) {
        return [m.month, right(fmtH(m.h)), right(m.rows)];
      }));

    if (result.by_project) {
      html += sectionTitle("按项目明细", true);
      html += table(["项目号", "项目名称", "工时(h)", "行数"],
        result.by_project.map(function (p) {
          return [p.key, p.name || "", right(fmtH(p.h)), right(p.rows)];
        }));
    }

    if (result.non_project) {
      html += sectionTitle("非项目工时（按任务）", true);
      html += table(["任务", "工时(h)", "行数"],
        result.non_project.map(function (p) {
          return [p.task || "（空）", right(fmtH(p.h)), right(p.rows)];
        }));
    }

    if (result.by_person) {
      html += sectionTitle("按人员", true);
      html += table(["人员标识", "名称", "工时(h)", "行数"],
        result.by_person.map(function (p) {
          return [p.key, p.name || "", right(fmtH(p.h)), right(p.rows)];
        }));
    }

    if (result.wbs) {
      html += sectionTitle("WBS 下一级下钻" + (result.wbs_prefix ? "（" + result.wbs_prefix + "）" : ""), true);
      html += table(["WBS 前缀", "工时(h)", "行数"],
        result.wbs.map(function (w) {
          return [w.wbs, right(fmtH(w.h)), right(w.rows)];
        }));
    }
    target.innerHTML = html;
    ECA.showEl(target);
  }

  function card(k, v) {
    return '<div class="card"><div class="k">' + k + '</div><div class="v">' + v + "</div></div>";
  }
  function sectionTitle(t, collapsible) {
    if (collapsible) {
      return '<h3 class="collapse-head" style="margin-top:14px">' +
        '<span class="arrow">▶</span>' + t + "</h3>";
    }
    return "<h3>" + t + "</h3>";
  }
  function table(heads, rows) {
    var h = "<thead><tr>" + heads.map(function (x) { return "<th>" + x + "</th>"; }).join("") + "</tr></thead>";
    var b = "<tbody>" + rows.map(function (r) {
      return "<tr>" + r.map(function (c) { return "<td>" + c + "</td>"; }).join("") + "</tr>";
    }).join("") + "</tbody>";
    return '<table>' + h + b + "</table>";
  }
  function right(s) { return '<span class="num">' + s + "</span>"; }

  /* 折叠交互（事件委托）：统一用 classList（.collapsed）控制表体可见性，避免内联 display。 */
  document.addEventListener("click", function (e) {
    var h = e.target.closest && e.target.closest(".collapse-head");
    if (!h) return;
    h.classList.toggle("open");
    var tbl = h.nextElementSibling;
    if (tbl && tbl.tagName === "TABLE") {
      tbl.classList.toggle("collapsed", !h.classList.contains("open"));
    }
  });

  /* ---------- 快捷区间 ---------- */
  function quickRange(kind, lo, hi) {
    var now = new Date();
    var y = now.getFullYear();
    if (kind === "thisyear") return [y + "-01", y + "-" + pad2(now.getMonth() + 1)];
    if (kind === "lastyear") return [(y - 1) + "-01", (y - 1) + "-12"];
    if (kind === "all") return [lo || (y + "-01"), hi || (y + "-" + pad2(now.getMonth() + 1))];
    if (kind === "quarter") {
      var q = Math.floor(now.getMonth() / 3);
      return [y + "-" + pad2(q * 3 + 1), y + "-" + pad2(q * 3 + 3)];
    }
    return [lo || (y + "-01"), hi || (y + "-12")];
  }
  function bindQuick(prefix) {
    document.querySelectorAll('[data-q]').forEach(function (btn) {
      btn.addEventListener("click", function () {
        var r = quickRange(btn.getAttribute("data-q"),
          el(prefix + "Lo") && el(prefix + "Lo").value, el(prefix + "Hi") && el(prefix + "Hi").value);
        // 回填到「年 + 月」双下拉（同时同步隐藏域，值恒为 YYYY-MM）
        if (el(prefix + "Start")) { ECA.ymSet(prefix + "Start", r[0]); ECA.ymSet(prefix + "End", r[1]); }
      });
    });
  }

  /* ---------- 图表 ---------- */
  function renderCharts(kind, payload) {
    var start = payload.start, end = payload.end;
    if (el("chartTrend")) {
      api("/api/chart/trend?start=" + start + "&end=" + end +
        (payload.project_id ? "&project_id=" + encodeURIComponent(payload.project_id) : "") +
        (payload.resource_id ? "&resource_id=" + encodeURIComponent(payload.resource_id) : ""), "GET")
        .then(function (d) { window.ECACharts.line(el("chartTrend"), d.series || []); })
        .catch(function (e) { el("chartTrend").innerHTML = '<div class="muted">' + e.message + "</div>"; });
    }
    if (el("chartTopn")) {
      var dim = (el("topnDim") ? el("topnDim").value : "project");
      var n = (el("topnN") ? el("topnN").value : 10);
      api("/api/chart/topn?dimension=" + dim + "&n=" + n + "&start=" + start + "&end=" + end, "GET")
        .then(function (d) {
          window.ECACharts.bar(el("chartTopn"),
            (d.data || []).map(function (x) { return { label: x.key, value: x.h }; }));
        }).catch(function (e) { el("chartTopn").innerHTML = '<div class="muted">' + e.message + "</div>"; });
    }
    if (el("chartMatrix")) {
      api("/api/chart/matrix?start=" + start + "&end=" + end, "GET")
        .then(function (d) {
          window.ECACharts.heatmap(el("chartMatrix"), d.projects || [], d.persons || [], d.cells || {});
        }).catch(function (e) { el("chartMatrix").innerHTML = '<div class="muted">' + e.message + "</div>"; });
    }
  }

  /* ---------- 导出 ---------- */
  function doExport(payload, btn) {
    if (btn) { btn.disabled = true; }
    api("/api/export", "POST", payload)
      .then(function (d) {
        if (d.filename) {
          var a = document.createElement("a");
          a.href = d.download;
          a.download = d.filename;
          document.body.appendChild(a); a.click(); a.remove();
        }
      })
      .catch(function (e) { alert("导出失败：" + e.message); })
      .finally(function () { if (btn) btn.disabled = false; });
  }

  /* ================= 页面初始化 ================= */
  ECA.initImport = function () {
    var res = el("importResult");
    var spin = el("importSpin");
    var listBox = el("importList");
    var countEl = el("selCount");
    var allBtn = el("btnImport");
    var selBtn = el("btnImportSelected");
    var selAllBtn = el("btnSelectAll");
    var candidates = [];

    function checkboxEls() {
      if (!listBox) return [];
      return listBox.querySelectorAll('input[type="checkbox"][data-path]');
    }
    function selectedPaths() {
      var a = [];
      Array.prototype.forEach.call(checkboxEls(), function (cb) {
        if (cb.checked) a.push(cb.getAttribute("data-path"));
      });
      return a;
    }
    function updateCount() {
      if (!countEl) return;
      countEl.textContent = "已选 " + selectedPaths().length + " 个文件";
    }
    function fmtSize(bytes) {
      var b = Number(bytes) || 0;
      if (b >= 1048576) return (b / 1048576).toFixed(1) + " MB";
      if (b >= 1024) return (b / 1024).toFixed(0) + " KB";
      return b + " B";
    }
    function statusTag(status) {
      if (status === "imported") return '<span class="tag ok">已导入</span>';
      if (status === "skip") return '<span class="tag warn">跳过</span>';
      return '<span class="tag grey">未导入</span>';
    }
    function renderList() {
      if (!listBox) return;
      if (!candidates.length) {
        listBox.innerHTML = '<p class="muted">目录内没有可导入的 .xlsx 文件。</p>';
        updateCount();
        return;
      }
      var h = '<table class="import-table"><thead><tr>' +
        '<th class="chk"></th><th>文件名</th><th class="num">大小</th>' +
        "<th>报告月份</th><th>状态</th></tr></thead><tbody>";
      candidates.forEach(function (f) {
        h += '<tr' + (f.skippable ? ' class="row-skip"' : "") + ">" +
          '<td class="chk"><input type="checkbox" data-path="' + escAttr(f.path) + '"' +
          (f.skippable ? " disabled" : "") + "></td>" +
          "<td>" + escText(f.name) + "</td>" +
          '<td class="num">' + fmtSize(f.size) + "</td>" +
          "<td>" + (f.parsed_month || "—") + "</td>" +
          "<td>" + statusTag(f.status) + "</td></tr>";
      });
      h += "</tbody></table>";
      listBox.innerHTML = h;
      Array.prototype.forEach.call(checkboxEls(), function (cb) {
        cb.addEventListener("change", updateCount);
      });
      updateCount();
    }
    function loadCandidates() {
      return api("/api/import/candidates", "GET").then(function (d) {
        candidates = (d && d.files) || [];
        renderList();
      }).catch(function (e) {
        if (listBox) listBox.innerHTML = '<div class="msg-error">' + e.message + "</div>";
      });
    }

    function renderReport(rep) {
      var h = "";
      h += '<div class="cards">';
      h += card("文件总数", rep.files_total);
      h += card("已导入", rep.files_imported);
      h += card("跳过(已存在)", rep.files_skipped);
      h += card("失败", rep.files_failed);
      h += card("新增行", rep.new_rows);
      h += card("重复标记", rep.duplicate_rows);
      h += card("异常标记", rep.anomaly_rows);
      h += card("0工时行", rep.zero_rows);
      h += card("空ID行", rep.empty_rid_rows);
      h += "</div>";
      if (rep.failed_files && rep.failed_files.length) {
        h += '<h3 style="margin-top:14px">失败文件</h3><ul class="muted">';
        rep.failed_files.forEach(function (f) { h += "<li>" + escText(f[0]) + " — " + escText(f[1]) + "</li>"; });
        h += "</ul>";
      }
      h += '<p style="margin-top:12px"><a class="link" href="/quality">前往数据质量面板 →</a></p>';
      return h;
    }

    function runImport(paths, btn) {
      if (paths && paths.length === 0) { alert("请先勾选要导入的文件"); return; }
      if (btn) btn.disabled = true;
      setMsg(spin, "导入中…");
      if (res) res.innerHTML = "";
      api("/api/import", "POST", { paths: paths || [], mode: "skip" })
        .then(function (rep) {
          setMsg(spin, "导入完成", "ok");
          if (res) res.innerHTML = renderReport(rep);
          return loadCandidates();
        })
        .catch(function (e) { setMsg(spin, "导入失败：" + e.message, "error"); })
        .finally(function () { if (btn) btn.disabled = false; });
    }

    if (allBtn) allBtn.addEventListener("click", function () { runImport([], allBtn); });
    if (selBtn) selBtn.addEventListener("click", function () { runImport(selectedPaths(), selBtn); });
    if (selAllBtn) selAllBtn.addEventListener("click", function () {
      var boxes = checkboxEls();
      var allChecked = Array.prototype.every.call(boxes, function (c) { return c.checked || c.disabled; });
      Array.prototype.forEach.call(boxes, function (c) { if (!c.disabled) c.checked = !allChecked; });
      updateCount();
    });

    loadCandidates();
  };

  ECA.initProject = function () {
    var lo = el("pLo") ? el("pLo").value : "";
    var hi = el("pHi") ? el("pHi").value : "";
    ECA.YearMonth({ mount: "pStartBox", hiddenId: "pStart", lo: lo, hi: hi });
    ECA.YearMonth({ mount: "pEndBox", hiddenId: "pEnd", lo: lo, hi: hi });
    bindQuick("p");
    var projSel = ECA.SearchableSelect({
      mount: "projectIdBox", hiddenId: "projectId", candidates: [],
      allowCustom: true, emptyLabel: null, maxRender: 50,
      placeholder: "输入关键字过滤项目号…",
      value: el("projectId") ? el("projectId").value : "",
    });
    api("/api/options/projects", "GET").then(function (list) {
      list = list || [];
      if (projSel) projSel.setCandidates(list.map(function (p) {
        return { value: p.pid, label: p.pid + (p.name ? " · " + p.name : "") };
      }));
      var c = el("projectCount");
      if (c) c.textContent = list.length.toLocaleString();
    }).catch(function () {});
    var btn = el("btnQuery");
    if (btn) btn.addEventListener("click", function () {
      var pid = (el("projectId").value || "").trim().toUpperCase();
      var start = el("pStart").value, end = el("pEnd").value;
      if (!pid || !start || !end) { alert("请填写项目号与月份区间"); return; }
      setMsg(el("pMsg"), "查询中…");
      api("/api/query/project", "POST", { project_id: pid, start: start, end: end, wbs_prefix: el("wbsPrefix") ? el("wbsPrefix").value : "" })
        .then(function (r) {
          setMsg(el("pMsg"), "", null);
          renderThreeLayer(el("result"), r, { personLabel: "人员" });
          renderCharts("project", { start: start, end: end, project_id: pid });
        })
        .catch(function (e) { setMsg(el("pMsg"), e.message, "error"); });
    });
    bindExport("btnExport", function () {
      return {
        start: el("pStart").value, end: el("pEnd").value,
        project_id: (el("projectId").value || "").trim().toUpperCase(),
        title: "项目工时_" + (el("projectId").value || ""),
        format: (el("expFmt") ? el("expFmt").value : "xlsx"),
        lang: (el("expLang") ? el("expLang").value : "both")
      };
    });
    bindTabs();
  };

  ECA.initEmployee = function () {
    var lo = el("eLo") ? el("eLo").value : "";
    var hi = el("eHi") ? el("eHi").value : "";
    ECA.YearMonth({ mount: "eStartBox", hiddenId: "eStart", lo: lo, hi: hi });
    ECA.YearMonth({ mount: "eEndBox", hiddenId: "eEnd", lo: lo, hi: hi });
    bindQuick("e");
    var personSel = ECA.SearchableSelect({
      mount: "personIdBox", hiddenId: "personId", candidates: [],
      allowCustom: true, emptyLabel: null, maxRender: 50,
      placeholder: "输入资源号/姓名过滤…",
      value: el("personId") ? el("personId").value : "",
    });
    api("/api/options/persons", "GET").then(function (list) {
      if (personSel) personSel.setCandidates((list || []).map(function (p) {
        return { value: p.resource_id_norm, label: p.resource_id_norm + (p.canonical_name ? " · " + p.canonical_name : "") };
      }));
    }).catch(function () {});
    var btn = el("btnQuery");
    if (btn) btn.addEventListener("click", function () {
      var rid = (el("personId").value || "").trim().toUpperCase();
      var q = (el("personQuery") ? el("personQuery").value : "");
      var start = el("eStart").value, end = el("eEnd").value;
      if ((!rid && !q) || !start || !end) { alert("请选择/输入人员与月份区间"); return; }
      setMsg(el("eMsg"), "查询中…");
      api("/api/query/employee", "POST", { resource_id: rid, q: q, start: start, end: end })
        .then(function (r) {
          setMsg(el("eMsg"), "", null);
          renderThreeLayer(el("result"), r, { cardMode: "employee" });
          renderCharts("employee", { start: start, end: end, resource_id: r.resource_id });
        })
        .catch(function (e) { setMsg(el("eMsg"), e.message, "error"); });
    });
    bindExport("btnExport", function () {
      return {
        start: el("eStart").value, end: el("eEnd").value,
        resource_id: (el("personId").value || "").trim().toUpperCase(),
        title: "员工工时", format: (el("expFmt") ? el("expFmt").value : "xlsx"),
        lang: (el("expLang") ? el("expLang").value : "both")
      };
    });
    bindTabs();
  };

  ECA.initSearch = function () {
    var lo = el("sLo") ? el("sLo").value : "";
    var hi = el("sHi") ? el("sHi").value : "";
    ECA.YearMonth({ mount: "sStartBox", hiddenId: "sStart", lo: lo, hi: hi });
    ECA.YearMonth({ mount: "sEndBox", hiddenId: "sEnd", lo: lo, hi: hi });
    bindQuick("s");
    var orgSel = ECA.SearchableSelect({
      mount: "orgSelBox", hiddenId: "orgSel", candidates: [],
      allowCustom: true, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤组织…",
    });
    var ccSel = ECA.SearchableSelect({
      mount: "ccSelBox", hiddenId: "ccSel", candidates: [],
      allowCustom: true, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤成本中心…",
    });
    var taskSel = ECA.SearchableSelect({
      mount: "taskSelBox", hiddenId: "taskSel", candidates: [],
      allowCustom: true, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤任务类别…",
    });
    api("/api/options/filters", "GET").then(function (d) {
      if (orgSel) orgSel.setCandidates((d.organizations || []).map(function (x) { return { value: x, label: x }; }));
      if (ccSel) ccSel.setCandidates((d.cost_centers || []).map(function (x) { return { value: x, label: x }; }));
    }).catch(function () {});
    api("/api/options/tasks", "GET").then(function (d) {
      var list = (d && d.tasks) || (Array.isArray(d) ? d : []);
      if (taskSel) taskSel.setCandidates(list.map(function (t) {
        var zh = taskZh(t.task);
        return { value: t.task, label: t.task + (zh ? " · " + zh : "") };
      }));
    }).catch(function () {});
    var btn = el("btnQuery");
    if (btn) btn.addEventListener("click", function () {
      var start = el("sStart").value, end = el("sEnd").value;
      if (!start || !end) { alert("请填写月份区间"); return; }
      var payload = {
        start: start, end: end,
        organization: el("orgSel").value || null,
        cost_center: el("ccSel").value || null,
        task: el("taskSel") ? el("taskSel").value || null : null,
        include_empty_project: el("incEmpty") ? el("incEmpty").checked : false
      };
      setMsg(el("sMsg"), "查询中…");
      api("/api/query/search", "POST", payload)
        .then(function (r) {
          setMsg(el("sMsg"), "", null);
          renderThreeLayer(el("result"), r, {});
          renderCharts("search", { start: start, end: end });
        })
        .catch(function (e) { setMsg(el("sMsg"), e.message, "error"); });
    });
    bindExport("btnExport", function () {
      return {
        start: el("sStart").value, end: el("sEnd").value,
        organization: el("orgSel").value || null,
        cost_center: el("ccSel").value || null,
        task: el("taskSel") ? el("taskSel").value || null : null,
        include_empty_project: el("incEmpty") ? el("incEmpty").checked : false,
        title: "检索", format: (el("expFmt") ? el("expFmt").value : "xlsx"),
        lang: (el("expLang") ? el("expLang").value : "both")
      };
    });
    bindTabs();
  };

  ECA.initQuality = function () {
    var summary = el("qSummary");
    var detail = el("qDetail");
    function loadSummary() {
      api("/api/quality/summary", "GET").then(function (s) {
        var h = '<div class="cards">';
        h += card("总行数", s.total_rows);
        h += card("总工时(h)", fmtH(s.total_hours));
        h += card("空项目号行", s.empty_pid);
        h += card("重复文件 / 行", s.duplicate_files + " / " + s.duplicate_rows);
        h += card("异常行", s.anomaly_rows);
        h += card("0工时行", s.zero_rows);
        h += card("人员总数", s.persons_total);
        h += card("有别名变体", s.persons_with_variants);
        h += card("已启用排除", s.active_exclusions);
        h += "</div>";
        summary.innerHTML = h;
      }).catch(function (e) { summary.innerHTML = '<div class="msg-error">' + e.message + "</div>"; });
    }
    loadSummary();

    document.querySelectorAll("[data-excl]").forEach(function (cb) {
      cb.addEventListener("change", function () {
        var cat = cb.getAttribute("data-excl");
        api("/api/quality/exclusion", "POST", { category: cat, excluded: cb.checked })
          .then(function () { loadSummary(); })
          .catch(function (e) { alert("操作失败：" + e.message); cb.checked = !cb.checked; });
      });
    });

    var catSel = el("qCat");
    var btnDetail = el("btnDetail");
    if (btnDetail) btnDetail.addEventListener("click", function () {
      var cat = catSel.value;
      api("/api/quality/detail?category=" + cat + "&limit=500", "GET").then(function (d) {
        var rows = d.rows || [];
        var h = "<p class='muted'>共 " + rows.length + " 条（最多 500）</p>";
        h += table(["源文件", "源行", "资源号", "姓名", "项目号", "工时(h)", "原始值"],
          rows.map(function (r) {
            return [r.source_file, r.source_row, r.resource_id_norm || "", r.name_snapshot || "",
              r.project_id_norm || "", right(fmtH(r.actuals_total_h)),
              right(escText(r.actuals_raw_text || ""))];
          }));
        detail.innerHTML = h;
      }).catch(function (e) { detail.innerHTML = '<div class="msg-error">' + e.message + "</div>"; });
    });
  };

  /* ---------- 小工具 ---------- */
  function escText(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escAttr(s) {
    return escText(s).replace(/"/g, "&quot;");
  }
  /* 任务 = 该行工时归属的工作类别。以下中文对照仅为展示用辅助文案，不改变数据值本身。 */
  var TASK_ZH = {
    "Leave": "休假",
    "Procurement services": "采购服务",
    "Application Software": "应用软件",
    "Aquisition (project in a offer phase)": "承接中（项目处于报价阶段）",
    "Sales projects": "销售项目",
    "Automation Hardware": "自动化硬件",
    "General activities": "一般性事务",
    "Project management": "项目管理",
    "Office Work": "办公室工作",
    "Site activities": "现场作业",
    "SCF (Annual Leave)": "年假",
    "SCF (Sick Leave)": "病假"
  };
  function taskZh(task) {
    if (task == null) return "";
    if (Object.prototype.hasOwnProperty.call(TASK_ZH, task)) return TASK_ZH[task];
    // 大小写不敏感兜底（数据中常见大小写差异，如 "Site Activities"）
    var low = String(task).toLowerCase();
    var keys = Object.keys(TASK_ZH);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].toLowerCase() === low) return TASK_ZH[keys[i]];
    }
    return "";
  }
  function bindExport(btnId, payloadFn) {
    var btn = el(btnId); if (!btn) return;
    btn.addEventListener("click", function () { doExport(payloadFn(), btn); });
  }
  function bindTabs() {
    var tabs = document.querySelectorAll(".tabs button[data-tab]");
    tabs.forEach(function (b) {
      b.addEventListener("click", function () {
        tabs.forEach(function (x) { x.classList.remove("active"); });
        b.classList.add("active");
        var which = b.getAttribute("data-tab");
        // 一律走 classList（.hidden）切换可见性：内联 style.display 无法覆盖 .hidden 类规则。
        ECA.toggleEl("result", which === "res");
        ECA.toggleEl("chartArea", which === "chart");
      });
    });
  }

  window.ECA = ECA;
  // 页面初始化由各页面模板的 {% block scripts %} 显式调用（window.ECA.initXxx()），
  // 避免“DOMContentLoaded 再跑一遍”造成组件重复挂载与跨页误绑定。
})();
