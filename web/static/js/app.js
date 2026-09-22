/* ECAHelper 前端交互（原生 JS，无构建链）。
 * 负责：导入触发、查询表单、三层结果渲染、快捷区间、图表渲染、导出。
 * 依赖：charts.js（全局 ECACharts）。
 */
(function () {
  "use strict";

  var ECA = {};

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
    box.className = "spinner " + (kind ? "msg-" + kind : "");
  }

  /* ---------- 三层结果渲染 ---------- */
  function renderThreeLayer(target, result, opts) {
    opts = opts || {};
    var personLabel = opts.personLabel || "人员";
    var t = result.total || {};
    var html = "";
    html += '<div class="cards">';
    html += card("总工时 (h)", fmtH(t.total_h));
    html += card("明细行数", t.rows || 0);
    html += card(personLabel + "数", t.persons || 0);
    html += card("覆盖月份", t.months || 0);
    html += "</div>";

    html += sectionTitle("按月趋势", true);
    html += table(["月份", "工时(h)", "行数"],
      (result.by_month || []).map(function (m) {
        return [m.month, right(fmtH(m.h)), right(m.rows)];
      }));

    if (opts.projectRows && result.by_project) {
      html += sectionTitle("按项目", true);
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

    html += sectionTitle("按" + personLabel, true);
    html += table([personLabel + "标识", "名称", "工时(h)", "行数"],
      (result.by_person || []).map(function (p) {
        return [p.key, p.name || "", right(fmtH(p.h)), right(p.rows)];
      }));

    if (result.wbs) {
      html += sectionTitle("WBS 下一级下钻" + (result.wbs_prefix ? "（" + result.wbs_prefix + "）" : ""), true);
      html += table(["WBS 前缀", "工时(h)", "行数"],
        result.wbs.map(function (w) {
          return [w.wbs, right(fmtH(w.h)), right(w.rows)];
        }));
    }
    target.innerHTML = html;
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

  /* 折叠交互（事件委托） */
  document.addEventListener("click", function (e) {
    var h = e.target.closest && e.target.closest(".collapse-head");
    if (!h) return;
    h.classList.toggle("open");
    var tbl = h.nextElementSibling;
    if (tbl && tbl.tagName === "TABLE") {
      tbl.style.display = h.classList.contains("open") ? "" : "none";
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
        if (el(prefix + "Start")) { el(prefix + "Start").value = r[0]; el(prefix + "End").value = r[1]; }
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
    var btn = el("btnImport");
    var spin = el("importSpin");
    var res = el("importResult");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      setMsg(spin, "导入中…");
      res.innerHTML = "";
      api("/api/import", "POST", { paths: [], mode: "skip" })
        .then(function (rep) {
          setMsg(spin, "导入完成", "ok");
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
            rep.failed_files.forEach(function (f) { h += "<li>" + f[0] + " — " + f[1] + "</li>"; });
            h += "</ul>";
          }
          h += '<p style="margin-top:12px"><a class="link" href="/quality">前往数据质量面板 →</a></p>';
          res.innerHTML = h;
        })
        .catch(function (e) { setMsg(spin, "导入失败：" + e.message, "error"); })
        .finally(function () { btn.disabled = false; });
    });
  };

  ECA.initProject = function () {
    bindQuick("p");
    loadOptions("/api/options/projects", "projectId", function (p) { return p.pid; }, true);
    var btn = el("btnQuery");
    if (btn) btn.addEventListener("click", function () {
      var pid = (el("projectId").value || "").trim().toUpperCase();
      var start = el("pStart").value, end = el("pEnd").value;
      if (!pid || !start || !end) { alert("请填写项目号与月份区间"); return; }
      setMsg(el("pMsg"), "查询中…");
      api("/api/query/project", "POST", { project_id: pid, start: start, end: end, wbs_prefix: el("wbsPrefix") ? el("wbsPrefix").value : "" })
        .then(function (r) {
          setMsg(el("pMsg"), "", null);
          renderThreeLayer(el("result"), r, { personLabel: "人员", projectRows: false });
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
    bindQuick("e");
    loadOptions("/api/options/persons", "personId", function (p) { return p.resource_id_norm; }, false,
      function (p) { return p.resource_id_norm + (p.canonical_name ? " · " + p.canonical_name : ""); });
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
          renderThreeLayer(el("result"), r, { personLabel: "项目", projectRows: true });
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
    bindQuick("s");
    api("/api/options/filters", "GET").then(function (d) {
      fillSelect("orgSel", d.organizations || []);
      fillSelect("ccSel", d.cost_centers || []);
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
          renderThreeLayer(el("result"), r, { personLabel: "人员", projectRows: true });
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
  function loadOptions(url, selId, keyFn, isProject, labelFn) {
    var sel = el(selId); if (!sel) return;
    api(url, "GET").then(function (list) {
      list = list || [];
      var html = '<option value="">（选择）</option>';
      list.forEach(function (p) {
        var k = keyFn(p), lbl = labelFn ? labelFn(p) : k;
        html += '<option value="' + escText(k) + '">' + escText(lbl) + "</option>";
      });
      sel.innerHTML = html;
    }).catch(function (e) { sel.innerHTML = '<option>' + e.message + "</option>"; });
  }
  function fillSelect(id, arr) {
    var sel = el(id); if (!sel) return;
    var html = '<option value="">（不限）</option>' +
      (arr || []).map(function (x) { return '<option value="' + escText(x) + '">' + escText(x) + "</option>"; }).join("");
    sel.innerHTML = html;
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
        if (el("result")) el("result").style.display = which === "res" ? "" : "none";
        if (el("chartArea")) el("chartArea").style.display = which === "chart" ? "" : "none";
      });
    });
  }

  window.ECA = ECA;
  document.addEventListener("DOMContentLoaded", function () {
    ["initImport", "initProject", "initEmployee", "initSearch", "initQuality"].forEach(function (fn) {
      if (typeof ECA[fn] === "function") {
        try { ECA[fn](); } catch (e) { console.error(fn, e); }
      }
    });
  });
})();
