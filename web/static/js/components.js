/* ECAHelper 前端共享组件（原生 JS，无构建链）。
 *
 * 暴露 window.ECA：
 *   - 可见性工具 showEl / hideEl / toggleEl —— 全站唯一可见性入口，
 *     内部一律走 classList.add/remove/toggle("hidden")，严禁 style.display
 *     （.hidden{display:none} 是类规则，内联清空无法覆盖 → 缺陷根因）。
 *   - SearchableSelect：可搜索下拉（全量候选 + 内存包含匹配 + 只渲染前 N 条 + 允许列表外值）。
 *   - YearMonth：年 + 月双下拉（对外取值恒为 "YYYY-MM"）。
 *   - ymSet / ymGet：按隐藏域 id 取/设年月。
 *
 * 加载顺序：components.js 必须先于 app.js 引入（app.js 依赖 window.ECA）。
 */
(function (global) {
  "use strict";

  var ECA = global.ECA = global.ECA || {};

  function el(id) { return document.getElementById(id); }

  function escText(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escAttr(s) {
    return escText(s).replace(/"/g, "&quot;");
  }
  function resolve(idOrEl) {
    if (!idOrEl) return null;
    return typeof idOrEl === "string" ? el(idOrEl) : idOrEl;
  }

  /* ============================================================
   * 可见性工具（全站唯一入口）
   * ============================================================ */
  ECA.showEl = function (idOrEl) {
    var e = resolve(idOrEl);
    if (e) e.classList.remove("hidden");
  };
  ECA.hideEl = function (idOrEl) {
    var e = resolve(idOrEl);
    if (e) e.classList.add("hidden");
  };
  ECA.toggleEl = function (idOrEl, show) {
    if (show) ECA.showEl(idOrEl); else ECA.hideEl(idOrEl);
  };

  /* ============================================================
   * 可搜索下拉 ECA.SearchableSelect
   * ============================================================ */
  var _ssSeq = 0;
  ECA._ss = {}; // registry: hiddenId -> instance

  function normalizeCandidates(arr) {
    var out = [];
    (arr || []).forEach(function (x) {
      if (x == null) return;
      if (typeof x === "string") {
        out.push({ value: x, label: x });
        return;
      }
      var v = x.value != null ? String(x.value) : "";
      out.push({
        value: v,
        label: x.label != null ? String(x.label) : v,
        sub: x.sub,
        badge: x.badge,
      });
    });
    return out;
  }

  /**
   * 构造可搜索下拉。
   * @param {Object} opts
   * @param {string}  opts.mount       必填，可见 UI 容器 div 的 id。
   * @param {string}  opts.hiddenId    必填，隐藏域 id（组件保持其 .value 与当前值同步）。
   * @param {Array}   [opts.candidates=[]] 候选（元素为 string 或 {value,label,sub,badge}）。
   * @param {boolean} [opts.allowCustom=true] 允许提交列表外的值。
   * @param {number}  [opts.maxRender=50] 面板最多渲染的匹配条目数。
   * @param {string}  [opts.placeholder="输入关键字过滤…"]
   * @param {string}  [opts.emptyLabel="（不限）"] 空值显示文案；传 null 则不提供空选项。
   * @param {string}  [opts.matchMode="contains"] contains | prefix | exact。
   * @param {boolean} [opts.caseInsensitive=true]
   * @param {string}  [opts.value=""]
   * @param {Function} [opts.onChange] 值变更回调 function(value, item)。
   * @returns {Object|null} 实例（mount 不存在时返回 null）。
   */
  ECA.SearchableSelect = function (opts) {
    opts = opts || {};
    var mount = resolve(opts.mount);
    if (!mount) return null;

    var self = {};
    self.opts = opts;
    self.hidden = resolve(opts.hiddenId);
    self.candidates = normalizeCandidates(opts.candidates || []);
    self.badgeMap = {};
    self.maxRender = opts.maxRender || 50;
    self.allowCustom = opts.allowCustom !== false;
    self.matchMode = opts.matchMode || "contains";
    self.caseInsensitive = opts.caseInsensitive !== false;
    self.emptyLabel = opts.emptyLabel === undefined ? "（不限）" : opts.emptyLabel;
    self.onChange = typeof opts.onChange === "function" ? opts.onChange : null;
    self.value = opts.value != null ? String(opts.value) : (self.hidden ? self.hidden.value : "");
    self.activeIndex = -1;
    self.shown = [];
    self.open = false;

    var uid = "ss" + (++_ssSeq);
    mount.classList.add("ss");
    mount.innerHTML =
      '<input class="ss-input" id="' + uid + '_input" type="text" autocomplete="off" ' +
      'placeholder="' + escAttr(opts.placeholder || "输入关键字过滤…") + '" ' +
      'role="combobox" aria-expanded="false">' +
      '<span class="ss-clear hidden" id="' + uid + '_clear" title="清除">×</span>' +
      '<div class="ss-pop hidden" id="' + uid + '_pop" role="listbox"></div>';

    var input = mount.querySelector(".ss-input");
    var clearEl = mount.querySelector(".ss-clear");
    var pop = mount.querySelector(".ss-pop");

    /* --- 内部工具 --- */
    function haystacks(item) {
      var arr = [item.value, item.label || ""];
      if (item.sub) arr.push(item.sub);
      return arr;
    }
    function matchOne(item, q) {
      if (!q) return true;
      var needle = self.caseInsensitive ? q.toLowerCase() : q;
      var list = haystacks(item);
      for (var i = 0; i < list.length; i++) {
        var hay = self.caseInsensitive ? String(list[i]).toLowerCase() : String(list[i]);
        if (self.matchMode === "exact") {
          if (hay === needle) return true;
        } else if (self.matchMode === "prefix") {
          if (hay.indexOf(needle) === 0) return true;
        } else if (hay.indexOf(needle) !== -1) {
          return true;
        }
      }
      return false;
    }
    function highlight(label, q) {
      label = String(label == null ? "" : label);
      if (!q) return escText(label);
      var idx = self.caseInsensitive
        ? label.toLowerCase().indexOf(q.toLowerCase())
        : label.indexOf(q);
      if (idx < 0) return escText(label);
      return escText(label.slice(0, idx)) + "<mark>" +
        escText(label.slice(idx, idx + q.length)) + "</mark>" +
        escText(label.slice(idx + q.length));
    }
    function badgeOf(item) {
      return item.badge || self.badgeMap[item.value] || "";
    }
    function computeFiltered(q) {
      var out = [];
      if (self.emptyLabel && !q) out.push({ value: "", label: self.emptyLabel, isEmpty: true });
      for (var i = 0; i < self.candidates.length; i++) {
        if (matchOne(self.candidates[i], q)) out.push(self.candidates[i]);
      }
      if (self.allowCustom && q) {
        var exact = self.candidates.some(function (c) {
          return self.caseInsensitive
            ? String(c.value).toLowerCase() === q.toLowerCase()
            : String(c.value) === q;
        });
        if (!exact) {
          out.splice(self.emptyLabel ? 1 : 0, 0, { value: q, label: q, custom: true });
        }
      }
      return out;
    }
    function renderList() {
      var q = input.value.trim();
      var filtered = computeFiltered(q);
      self.shown = filtered.slice(0, self.maxRender);
      self.activeIndex = -1;
      var html = "";
      self.shown.forEach(function (item, i) {
        var label = item.label != null ? item.label : item.value;
        var badge = badgeOf(item);
        html += '<div class="ss-opt" role="option" data-i="' + i + '" data-value="' +
          escAttr(item.value) + '">' +
          '<span class="ss-opt-label">' + highlight(label, q) + "</span>" +
          (badge ? ' <span class="tag susp">' + escText(badge) + "</span>" : "") +
          "</div>";
      });
      if (!self.shown.length) html = '<div class="ss-empty muted">无匹配</div>';
      pop.innerHTML = html;
    }
    function displayFor(v) {
      if (v === "" || v == null) return "";
      for (var i = 0; i < self.candidates.length; i++) {
        if (self.candidates[i].value === v) return self.candidates[i].label || v;
      }
      return v;
    }
    function syncClear() {
      clearEl.classList.toggle("hidden", !self.value);
    }
    function openPop() {
      if (self.open) return;
      self.open = true;
      renderList();
      pop.classList.remove("hidden");
      input.setAttribute("aria-expanded", "true");
    }
    function closePop() {
      if (!self.open) return;
      self.open = false;
      pop.classList.add("hidden");
      input.setAttribute("aria-expanded", "false");
    }
    function setActive(i) {
      var optEls = pop.querySelectorAll(".ss-opt");
      if (!optEls.length) { self.activeIndex = -1; return; }
      if (i < 0) i = optEls.length - 1;
      if (i >= optEls.length) i = 0;
      self.activeIndex = i;
      for (var k = 0; k < optEls.length; k++) {
        optEls[k].classList.toggle("active", k === i);
      }
      if (optEls[i].scrollIntoView) optEls[i].scrollIntoView({ block: "nearest" });
    }
    function commit(value, item) {
      self.value = value == null ? "" : String(value);
      if (self.hidden) self.hidden.value = self.value;
      input.value = displayFor(self.value);
      syncClear();
      closePop();
      if (self.onChange) self.onChange(self.value, item || null);
    }

    /* --- 事件 --- */
    input.addEventListener("focus", function () { openPop(); });
    input.addEventListener("input", function () { renderList(); openPop(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!self.open) openPop();
        setActive(self.activeIndex + 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (!self.open) openPop();
        setActive(self.activeIndex - 1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (self.activeIndex >= 0 && self.shown[self.activeIndex]) {
          var it = self.shown[self.activeIndex];
          commit(it.value, it);
        } else if (self.allowCustom && input.value.trim()) {
          commit(input.value.trim(), null);
        }
      } else if (e.key === "Escape") {
        closePop();
        input.value = displayFor(self.value);
      } else if (e.key === "Tab") {
        if (self.activeIndex >= 0 && self.shown[self.activeIndex]) {
          commit(self.shown[self.activeIndex].value, self.shown[self.activeIndex]);
        } else if (self.allowCustom && input.value.trim() && self.value !== input.value.trim()) {
          commit(input.value.trim(), null);
        } else {
          input.value = displayFor(self.value);
        }
        closePop();
      }
    });
    pop.addEventListener("mousedown", function (e) {
      var opt = e.target.closest && e.target.closest(".ss-opt");
      if (!opt) return;
      e.preventDefault();
      var i = parseInt(opt.getAttribute("data-i"), 10);
      var it = self.shown[i];
      if (it) commit(it.value, it);
    });
    clearEl.addEventListener("click", function (e) {
      e.preventDefault();
      commit("", null);
      input.focus();
    });
    function onDocClick(e) {
      if (!mount.contains(e.target)) closePop();
    }
    document.addEventListener("click", onDocClick);

    /* --- 对外 API --- */
    self.getValue = function () {
      return self.hidden ? self.hidden.value : self.value;
    };
    self.setValue = function (v) {
      self.value = v == null ? "" : String(v);
      if (self.hidden) self.hidden.value = self.value;
      input.value = displayFor(self.value);
      syncClear();
    };
    self.setCandidates = function (arr) {
      self.candidates = normalizeCandidates(arr || []);
      if (self.open) renderList();
    };
    self.setBadge = function (v, badge) {
      if (v == null) return;
      self.badgeMap[String(v)] = badge;
      if (self.open) renderList();
    };
    self.open = function () { openPop(); };
    self.close = function () { closePop(); };
    self.focus = function () { input.focus(); };
    self.destroy = function () {
      document.removeEventListener("click", onDocClick);
      mount.innerHTML = "";
    };

    // 初值显示 + 注册
    input.value = displayFor(self.value);
    syncClear();
    if (opts.hiddenId) ECA._ss[opts.hiddenId] = self;
    return self;
  };

  /* ============================================================
   * 年 + 月双下拉 ECA.YearMonth
   * ============================================================ */
  var _ymInstances = {}; // hiddenId -> instance

  /**
   * 构造年+月双下拉。对外取值恒为 "YYYY-MM"（写入 hiddenId 隐藏域）。
   * @param {Object} opts
   * @param {string}  opts.mount     必填，可见 UI 容器 div 的 id。
   * @param {string}  opts.hiddenId  必填，隐藏域 id（沿用旧 id：pStart/pEnd/…）。
   * @param {string}  [opts.lo]      数据下界 "YYYY-MM"。
   * @param {string}  [opts.hi]      数据上界 "YYYY-MM"。
   * @param {boolean} [opts.allowEmpty=false] 是否允许「（任意）」空值。
   * @param {string}  [opts.value]   初始值；缺省取隐藏域现值，再退化为 lo。
   * @param {Function}[opts.onChange] 变更回调 function(value)。
   * @returns {Object|null}
   */
  ECA.YearMonth = function (opts) {
    opts = opts || {};
    var mount = resolve(opts.mount);
    if (!mount) return null;
    var hidden = resolve(opts.hiddenId);
    var self = {};
    self.opts = opts;
    self.hidden = hidden;
    self.allowEmpty = !!opts.allowEmpty;
    self.onChange = typeof opts.onChange === "function" ? opts.onChange : null;

    var lo = opts.lo || (hidden ? hidden.value : "") || "";
    var hi = opts.hi || (hidden ? hidden.value : "") || "";
    var nowY = new Date().getFullYear();
    var loY = lo ? parseInt(lo.split("-")[0], 10) : null;
    var hiY = hi ? parseInt(hi.split("-")[0], 10) : null;
    if (loY == null || isNaN(loY)) loY = nowY;
    if (isNaN(hiY)) hiY = nowY;
    /* 年份上界随当前日期自动扩展：至少到「当前年 + 2」。
     * 旧实现只取数据上界（数据到 2026-09 就只能选 2026），用户反馈"随年份增长
     * 能否自动扩展到 2029/2030"——现在与数据解耦：今天(2026)可选到 2028，
     * 到 2029 年自动变成 2031，无需改代码。下界保持数据最早年（查更早月份只会
     * 得到 0 工时，无害）。 */
    var minHi = nowY + 2;
    if (hiY < minHi) hiY = minHi;

    mount.classList.add("ym");
    mount.innerHTML = '<select class="ym-year"></select><select class="ym-month"></select>';
    var yearSel = mount.querySelector(".ym-year");
    var monthSel = mount.querySelector(".ym-month");
    yearSel.title = "年份范围随数据与当前日期自动扩展（至少到当前年 + 2）";

    function fillYears() {
      var html = "";
      if (self.allowEmpty) html += '<option value="">（任意）</option>';
      for (var y = loY; y <= hiY; y++) {
        html += '<option value="' + y + '">' + y + "</option>";
      }
      yearSel.innerHTML = html;
    }
    function fillMonths() {
      var html = "";
      if (self.allowEmpty) html += '<option value="">（任意）</option>';
      for (var m = 1; m <= 12; m++) {
        var mm = m < 10 ? "0" + m : "" + m;
        html += '<option value="' + mm + '">' + mm + "</option>";
      }
      monthSel.innerHTML = html;
    }
    function ensureYear(yy) {
      if (!yy) return;
      var exists = false;
      for (var i = 0; i < yearSel.options.length; i++) {
        if (yearSel.options[i].value === yy) { exists = true; break; }
      }
      if (!exists) {
        var opt = document.createElement("option");
        opt.value = yy;
        opt.textContent = yy;
        yearSel.appendChild(opt);
      }
    }
    function syncHidden() {
      var y = yearSel.value, m = monthSel.value;
      var v = (y && m) ? (y + "-" + m) : "";
      if (hidden) hidden.value = v;
      return v;
    }
    function setValue(v) {
      v = (v || "").trim();
      var mt = /^(\d{4})-(\d{2})$/.exec(v);
      if (mt) {
        ensureYear(mt[1]);
        yearSel.value = mt[1];
        monthSel.value = mt[2];
      } else if (self.allowEmpty) {
        yearSel.value = "";
        monthSel.value = "";
      }
      syncHidden();
    }
    function onChangeHandler() {
      var v = syncHidden();
      if (self.onChange) self.onChange(v);
    }
    yearSel.addEventListener("change", onChangeHandler);
    monthSel.addEventListener("change", onChangeHandler);

    fillYears();
    fillMonths();
    var initVal = opts.value != null ? opts.value : (hidden ? hidden.value : lo);
    setValue(initVal);

    self.getValue = function () {
      return hidden ? hidden.value : (yearSel.value && monthSel.value ? yearSel.value + "-" + monthSel.value : "");
    };
    self.setValue = setValue;
    self.setBounds = function (nlo, nhi) {
      var a = nlo ? parseInt(nlo.split("-")[0], 10) : loY;
      var b = nhi ? parseInt(nhi.split("-")[0], 10) : hiY;
      if (!isNaN(a)) loY = a;
      if (!isNaN(b)) hiY = b;
      var cur = self.getValue();
      fillYears();
      setValue(cur);
    };
    self.yearSelect = yearSel;
    self.monthSelect = monthSel;

    if (opts.hiddenId) _ymInstances[opts.hiddenId] = self;
    return self;
  };

  /** 按隐藏域 id 设置年月（供快捷按钮回填）。找不到实例时直接写隐藏域。 */
  ECA.ymSet = function (id, v) {
    var inst = _ymInstances[id];
    if (inst) { inst.setValue(v); return; }
    var h = el(id);
    if (h) h.value = v == null ? "" : v;
  };

  /** 按隐藏域 id 读取年月 "YYYY-MM"。 */
  ECA.ymGet = function (id) {
    var inst = _ymInstances[id];
    if (inst) return inst.getValue();
    var h = el(id);
    return h ? h.value : "";
  };
})(window);
