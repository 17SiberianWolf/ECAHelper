/* SearchableSelect 开合状态回归测试（零依赖 DOM 桩）。
 * 用法: node _ss_test.js <components.js 路径>
 * 关键断言「构造后首次 focus 即弹面板」正是本次缺陷的窗口期：
 * 修复前该断言必 FAIL（openPop 被 self.open 函数恒真值挡住），修复后 PASS。 */
function classList() {
  var s = {};
  return {
    add: function (c) { s[c] = 1; },
    remove: function (c) { delete s[c]; },
    toggle: function (c, force) {
      if (force === undefined) { if (s[c]) delete s[c]; else s[c] = 1; }
      else if (force) s[c] = 1; else delete s[c];
    },
    contains: function (c) { return !!s[c]; },
  };
}
function makeEl(tag) {
  var e = {
    tag: tag, attrs: {}, listeners: {}, _html: "", value: "",
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
  };
  e.classList = classList();
  e.addEventListener = function (t, fn) { (e.listeners[t] = e.listeners[t] || []).push(fn); };
  e.dispatch = function (t, ev) { (e.listeners[t] || []).forEach(function (fn) { fn(ev || {}); }); };
  e.setAttribute = function (k, v) { e.attrs[k] = v; };
  e.getAttribute = function (k) { return e.attrs[k]; };
  e.querySelectorAll = function () { return []; };
  e.scrollIntoView = function () {};
  return e;
}
var docListeners = {};
var mount = makeEl("div");
mount.contains = function () { return false; };
var inputEl = makeEl("input"), clearEl = makeEl("span"), popEl = makeEl("div");
popEl.classList.add("hidden"); // 真实组件的初始态：class="ss-pop hidden"（否则断言空洞通过）
mount.querySelector = function (sel) {
  return sel === ".ss-input" ? inputEl : sel === ".ss-clear" ? clearEl
    : sel === ".ss-pop" ? popEl : null;
};
global.document = {
  getElementById: function (id) { return id === "m" ? mount : null; },
  addEventListener: function (t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
  removeEventListener: function () {},
  createElement: makeEl,
};
global.window = global;
require(process.argv[2]);
var inst = global.ECA.SearchableSelect({
  mount: "m", hiddenId: "h", candidates: ["O 1383.197", "O 1100.036", "D 1800.002"],
  allowCustom: true, emptyLabel: null, placeholder: "输入关键字过滤项目号…",
});
var pass = 0, fail = 0;
function chk(name, cond) {
  console.log((cond ? "PASS" : "FAIL") + " | " + name);
  if (cond) pass++; else fail++;
}
/* 关键回归：构造后「未经任何 closePop」直接 focus → 面板必须弹出。
 * 旧版此处 openPop 被 self.open 函数恒真值挡住 → 面板弹不出（用户报障场景）。 */
inputEl.dispatch("focus");
chk("1 构造后首次 focus 即弹面板（旧版缺陷窗口）", !popEl.classList.contains("hidden"));
chk("2 aria-expanded=true", inputEl.attrs["aria-expanded"] === "true");
inputEl.value = "1383";
inputEl.dispatch("input", {});
chk("3 输入关键字后面板保持弹出", !popEl.classList.contains("hidden"));
chk("4 候选按包含匹配渲染出 O 1383.197", popEl._html.indexOf("O 1383.197") !== -1);
chk("5 高亮 mark 存在", popEl._html.indexOf("<mark>") !== -1);
(docListeners["click"] || []).forEach(function (fn) { fn({ target: { tag: "body" } }); });
chk("6 点击面板外关闭", popEl.classList.contains("hidden"));
chk("7 isOpen() 暴露且为 false", inst.isOpen && inst.isOpen() === false);
inputEl.dispatch("focus");
chk("8 关闭后再次 focus 重新弹出", !popEl.classList.contains("hidden"));
inputEl.value = "1383";
inputEl.dispatch("input", {});
inputEl.dispatch("keydown", { key: "Enter", preventDefault: function () {} });
chk("9 Enter 提交后 value 同步", inst.getValue() === "1383" || inst.getValue() === "O 1383.197");
chk("10 提交后面板关闭", popEl.classList.contains("hidden"));
inputEl.dispatch("focus");
chk("11 提交后再 focus 仍能弹出（连续稳定性）", !popEl.classList.contains("hidden"));
console.log("---- TOTAL=" + (pass + fail) + " FAIL=" + fail);
process.exit(fail ? 1 : 0);
