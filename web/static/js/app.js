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
      html += sectionTitle("按项目明细（点击父项目号展开子项目）", true);
      html += projectTable(result.by_project, opts);
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

  /* ---------- 「按项目」表：父项目号可展开 → 子项目号明细（US-R2-04 / AC-02-4） ----------
   * 每行父号带展开开关，紧随其后是占位 child-row（默认 .hidden，首次展开时懒加载）。 */
  function projectTable(rows, opts) {
    var start = (opts && opts.start) || "";
    var end = (opts && opts.end) || "";
    var h = "<thead><tr><th>项目号</th><th>项目名称</th>" +
      "<th class='num'>工时(h)</th><th class='num'>行数</th></tr></thead><tbody>";
    (rows || []).forEach(function (p) {
      var key = p.key == null ? "" : String(p.key);
      h += "<tr>" +
        "<td><span class='proj-toggle' data-proj-expand data-pid='" + escAttr(key) +
          "' data-start='" + escAttr(start) + "' data-end='" + escAttr(end) + "' data-loaded='0'>" +
          "<span class='arrow'>▶</span>" + escText(key) + "</span></td>" +
        "<td>" + escText(p.name || "") + "</td>" +
        "<td class='num'>" + fmtH(p.h) + "</td>" +
        "<td class='num'>" + (p.rows == null ? "" : p.rows) + "</td>" +
      "</tr>" +
      "<tr class='child-row hidden'><td class='child-cell' colspan='4'></td></tr>";
    });
    return "<table class='proj-table'>" + h + "</tbody></table>";
  }

  function loadProjChildren(toggle, cell) {
    toggle.setAttribute("data-loaded", "1");
    var pid = toggle.getAttribute("data-pid");
    var start = toggle.getAttribute("data-start");
    var end = toggle.getAttribute("data-end");
    if (!start || !end) { cell.innerHTML = '<div class="muted">缺少月份区间，无法下钻。</div>'; return; }
    cell.innerHTML = '<div class="muted">加载中…</div>';
    api("/api/query/project/children?project_id=" + encodeURIComponent(pid) +
        "&start=" + encodeURIComponent(start) + "&end=" + encodeURIComponent(end), "GET")
      .then(function (d) {
        var kids = (d && d.children) || [];
        if (!kids.length) {
          cell.innerHTML = '<div class="muted">该项目号名下无子项目号明细。</div>';
          return;
        }
        var s = "<table class='child-table'><thead><tr><th>子项目号</th><th>项目名称</th>" +
          "<th class='num'>工时(h)</th><th class='num'>行数</th></tr></thead><tbody>";
        kids.forEach(function (k) {
          s += "<tr><td>" + escText(k.key || "") + "</td><td>" + escText(k.name || "") +
            "</td><td class='num'>" + fmtH(k.h) + "</td><td class='num'>" + (k.rows || 0) + "</td></tr>";
        });
        s += "</tbody></table>";
        cell.innerHTML = s;
      })
      .catch(function (e) { cell.innerHTML = '<div class="msg-error">' + e.message + "</div>"; });
  }

  /* 项目号展开（事件委托）：child-row 可见性一律走 ECA.toggleEl（classList），懒加载一次。 */
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-proj-expand]");
    if (!t) return;
    var tr = t.closest("tr");
    var childRow = tr ? tr.nextElementSibling : null;
    if (!childRow || !childRow.classList.contains("child-row")) return;
    var open = t.classList.toggle("open");
    ECA.toggleEl(childRow, open);
    if (open && t.getAttribute("data-loaded") === "0") {
      loadProjChildren(t, childRow.querySelector(".child-cell"));
    }
  });

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
    var pickBtn = el("btnPickImport");
    var allBtn = el("btnImport");
    var picker = el("filePicker");
    var hintEl = el("pickHint");
    var sumEl = el("importSummary");

    function fmtSize(bytes) {
      var b = Number(bytes) || 0;
      if (b >= 1048576) return (b / 1048576).toFixed(1) + " MB";
      if (b >= 1024) return (b / 1024).toFixed(0) + " KB";
      return b + " B";
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
      if (rep.rejected && rep.rejected.length) {
        h += '<h3 style="margin-top:14px">未接收的文件</h3><ul class="muted">';
        rep.rejected.forEach(function (x) { h += "<li>" + escText(x) + "</li>"; });
        h += "</ul>";
      }
      if (rep.failed_files && rep.failed_files.length) {
        h += '<h3 style="margin-top:14px">失败文件</h3><ul class="muted">';
        rep.failed_files.forEach(function (f) { h += "<li>" + escText(f[0]) + " — " + escText(f[1]) + "</li>"; });
        h += "</ul>";
      }
      h += '<p style="margin-top:12px"><a class="link" href="/quality">前往数据质量面板 →</a></p>';
      return h;
    }
    /* 无论成败都弹窗提示（用户明确要求）。 */
    function notify(rep) {
      var line = "导入完成：已导入 " + (rep.files_imported || 0) + " 个，跳过(已存在) " +
        (rep.files_skipped || 0) + " 个，失败 " + (rep.files_failed || 0) + " 个；" +
        "新增 " + (rep.new_rows || 0) + " 行。";
      if (rep.files_failed > 0 || (rep.failed_files && rep.failed_files.length)) {
        var fl = (rep.failed_files || []).map(function (f) { return "  " + f[0] + " — " + f[1]; });
        alert(["导入失败（部分或全部）：", line, "", "失败文件："].concat(fl).join("\n"));
        return;
      }
      alert(line);
    }
    function refreshSummary() {
      if (!sumEl) return;
      api("/api/import/candidates", "GET").then(function (d) {
        var fs = (d && d.files) || [];
        var n = fs.length, done = 0, skip = 0;
        fs.forEach(function (f) {
          if (f.status === "imported") done++;
          else if (f.status === "skip") skip++;
        });
        sumEl.textContent = "数据目录共 " + n + " 个文件，其中 " + done +
          " 个已导入" + (skip ? "、" + skip + " 个为主数据/锁文件（自动跳过）" : "") + "。";
      }).catch(function () { if (sumEl) sumEl.textContent = ""; });
    }
    /* 上传：不能用 api()（它强设 JSON Content-Type，会破坏 multipart 边界）。 */
    function upload(files, btn) {
      if (!files || !files.length) return;
      var fd = new FormData();
      for (var i = 0; i < files.length; i++) fd.append("files", files[i], files[i].name);
      if (btn) btn.disabled = true;
      setMsg(spin, "导入中…（" + files.length + " 个文件）");
      if (res) res.innerHTML = "";
      fetch("/api/import/upload", { method: "POST", body: fd })
        .then(function (r) {
          return r.json().then(function (d) {
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
            return d;
          });
        })
        .then(function (rep) {
          setMsg(spin, "导入完成", "ok");
          if (res) res.innerHTML = renderReport(rep);
          notify(rep);
          refreshSummary();
        })
        .catch(function (e) {
          setMsg(spin, "导入失败", "error");
          if (res) res.innerHTML = '<div class="msg-error">' + escText(e.message) + "</div>";
          alert("导入失败：" + e.message);
        })
        .finally(function () { if (btn) btn.disabled = false; });
    }

    if (pickBtn && picker) {
      pickBtn.addEventListener("click", function () { picker.click(); });
      picker.addEventListener("change", function () {
        var fs = picker.files;
        if (!fs || !fs.length) { if (hintEl) hintEl.textContent = ""; return; }
        var total = 0, names = [];
        for (var i = 0; i < fs.length; i++) { total += fs[i].size; names.push(fs[i].name); }
        if (hintEl) hintEl.textContent = "已选 " + fs.length + " 个文件（" + fmtSize(total) + "）" +
          (fs.length <= 3 ? "：" + names.join("、") : "");
        upload(fs, pickBtn);
        picker.value = "";   /* 允许下次重复选同一文件也触发 change */
      });
    }
    if (allBtn) allBtn.addEventListener("click", function () {
      if (!confirm("将导入数据目录下全部 .xlsx 工时表（已导入的同名文件会自动跳过）。继续吗？")) return;
      if (allBtn) allBtn.disabled = true;
      setMsg(spin, "导入中…");
      if (res) res.innerHTML = "";
      api("/api/import", "POST", { paths: [], mode: "skip" })
        .then(function (rep) {
          setMsg(spin, "导入完成", "ok");
          if (res) res.innerHTML = renderReport(rep);
          notify(rep);
          refreshSummary();
        })
        .catch(function (e) {
          setMsg(spin, "导入失败", "error");
          alert("导入失败：" + e.message);
        })
        .finally(function () { if (allBtn) allBtn.disabled = false; });
    });

    refreshSummary();
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
        // AC-08-3：日期型脏项目号在下拉里带「可疑」标识（仅视觉，value 与提交值不变）
        return { value: p.pid, label: p.pid + (p.name ? " · " + p.name : ""),
                 badge: p.suspicious ? "可疑" : "" };
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
          // 项目页：把查询的父项目号作为「按项目」表的一行（可展开看子项目号明细）。
          // 接口 total 已按父号子树聚合，故该行 = 整棵子树合计（AC-02-3 / AC-02-4）。
          if (!r.by_project) {
            r.by_project = [{
              key: r.project_id || pid,
              name: r.project_name || "",
              h: (r.total || {}).total_h || 0,
              rows: (r.total || {}).rows || 0,
            }];
          }
          renderThreeLayer(el("result"), r, { personLabel: "人员", start: start, end: end });
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
          renderThreeLayer(el("result"), r, { cardMode: "employee", start: start, end: end });
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
      allowCustom: false, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤组织…", onChange: refreshFacets,
    });
    var ccSel = ECA.SearchableSelect({
      mount: "ccSelBox", hiddenId: "ccSel", candidates: [],
      allowCustom: false, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤成本中心…", onChange: refreshFacets,
    });
    var taskSel = ECA.SearchableSelect({
      mount: "taskSelBox", hiddenId: "taskSel", candidates: [],
      allowCustom: true, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤任务类别…", onChange: refreshFacets,
    });
    var personSel = ECA.SearchableSelect({
      mount: "personSelBox", hiddenId: "personSel", candidates: [],
      allowCustom: false, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤人员…", onChange: refreshFacets,
    });
    var projectSel = ECA.SearchableSelect({
      mount: "projectSelBox", hiddenId: "projectSel", candidates: [],
      allowCustom: false, emptyLabel: "（不限）", maxRender: 50,
      placeholder: "输入关键字过滤项目…", onChange: refreshFacets,
    });

    function currentFilter() {
      return {
        start: el("sStart").value, end: el("sEnd").value,
        organization: el("orgSel").value || null,
        cost_center: el("ccSel").value || null,
        task: el("taskSel").value || null,
        resource_id: el("personSel").value || null,
        project_id: el("projectSel").value || null,
        include_empty_project: el("incEmpty") ? el("incEmpty").checked : false,
        include_sub_organization: el("incSub") ? el("incSub").checked : false
      };
    }

    // 联动计数：用 /api/search/facets 给各下拉注入「N 行」并剔除零行项
    var _pruning = false;
    function refreshFacets() {
      if (_pruning) return;
      var f = currentFilter();
      if (!f.start || !f.end) return;
      api("/api/search/facets", "POST", f).then(function (fac) {
        if (orgSel) orgSel.setCandidates((fac.organization || []).map(function (x) {
          return { value: x.value, label: x.label, badge: x.count + " 行" };
        }));
        if (ccSel) ccSel.setCandidates((fac.cost_center || []).map(function (x) {
          return { value: x.value, label: x.label, badge: x.count + " 行" };
        }));
        if (taskSel) taskSel.setCandidates((fac.task || []).map(function (x) {
          var zh = taskZh(x.value);
          return { value: x.value, label: x.value + (zh ? " · " + zh : ""), badge: x.count + " 行" };
        }));
        if (personSel) personSel.setCandidates((fac.person || []).map(function (x) {
          return { value: x.value, label: (x.label || x.value) + "（" + x.value + "）", badge: x.count + " 行" };
        }));
        if (projectSel) projectSel.setCandidates((fac.project || []).map(function (x) {
          return { value: x.value, label: (x.label || x.value), badge: x.count + " 行" };
        }));
        // 自动清除「在其他条件下已无共现行」的已选值（根治含下级切换等残留空组合）。
        // 仅对精确单值维度（组织/成本中心/人员/项目）生效；任务为包含匹配、允许列表外值，跳过。
        var stale = [];
        function chk(sel, dimKey, field) {
          var v = el(field).value;
          if (!v) return;
          var ok = (fac[dimKey] || []).some(function (x) { return x.value === v; });
          if (!ok) stale.push(sel);
        }
        chk(orgSel, "organization", "orgSel");
        chk(ccSel, "cost_center", "ccSel");
        chk(personSel, "person", "personSel");
        chk(projectSel, "project", "projectSel");
        if (stale.length) {
          _pruning = true;
          stale.forEach(function (s) { s.commit(""); });
          _pruning = false;
          refreshFacets(); // 清掉残留后重算一次（已无空组合）
          return;
        }
      }).catch(function () {});
    }

    // 任一筛选变化（含下级开关）→ 刷新候选计数（保证下拉不再通向死路）
    if (el("incSub")) el("incSub").addEventListener("change", refreshFacets);

    refreshFacets(); // 初始播种计数

    function renderZeroGuide(r) {
      var g = el("zeroGuide");
      if (!g) return;
      if (r && r.total && r.total.rows > 0) { g.classList.add("hidden"); g.innerHTML = ""; return; }
      var f = currentFilter();
      var parts = [];
      if (f.organization) parts.push("组织=" + f.organization + (f.include_sub_organization ? "（含下级）" : ""));
      if (f.cost_center) parts.push("成本中心=" + f.cost_center);
      if (f.task) parts.push("任务=" + f.task);
      if (f.resource_id) parts.push("人员=" + f.resource_id);
      if (f.project_id) parts.push("项目=" + f.project_id);
      var why = parts.length
        ? "这些条件叠加后无共现行（组织与成本中心/人员/项目彼此正交，任意两值常无交集）。"
        : "当前月份区间内无数据。";
      g.innerHTML =
        '<div class="msg-warn">' +
        '<b>当前条件下无数据。</b> ' + escText(why) + '<br>' +
        '已选：' + (parts.join("；") || "（无）") +
        '<div style="margin-top:8px">' +
        '<button class="secondary" id="btnRelax">放宽：清除 成本中心 / 任务 / 人员 / 项目</button>' +
        '</div></div>';
      g.classList.remove("hidden");
      var relax = el("btnRelax");
      if (relax) relax.addEventListener("click", function () {
        if (ccSel) ccSel.commit("");
        if (taskSel) taskSel.commit("");
        if (personSel) personSel.commit("");
        if (projectSel) projectSel.commit("");
        refreshFacets();
        el("btnQuery").click();
      });
    }

    var btn = el("btnQuery");
    if (btn) btn.addEventListener("click", function () {
      var start = el("sStart").value, end = el("sEnd").value;
      if (!start || !end) { alert("请填写月份区间"); return; }
      var payload = currentFilter();
      setMsg(el("sMsg"), "查询中…");
      api("/api/query/search", "POST", payload)
        .then(function (r) {
          setMsg(el("sMsg"), "", null);
          renderZeroGuide(r);
          renderThreeLayer(el("result"), r, { start: start, end: end });
          renderCharts("search", { start: start, end: end });
        })
        .catch(function (e) { setMsg(el("sMsg"), e.message, "error"); });
    });
    var bf = el("btnFacets");
    if (bf) bf.addEventListener("click", refreshFacets);
    bindExport("btnExport", function () {
      return {
        start: el("sStart").value, end: el("sEnd").value,
        organization: el("orgSel").value || null,
        cost_center: el("ccSel").value || null,
        task: el("taskSel") ? el("taskSel").value || null : null,
        resource_id: el("personSel").value || null,
        project_id: el("projectSel").value || null,
        include_empty_project: el("incEmpty") ? el("incEmpty").checked : false,
        include_sub_organization: el("incSub") ? el("incSub").checked : false,
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
