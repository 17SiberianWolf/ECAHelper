/* A. 静态 CSS 断言（零依赖，fs.readFileSync 读文本 + 正则逐条断言）。
 * 验证 web/static/css/style.css 的表头吸顶 + 分页常驻改动的硬约束。
 * 用法: node tools/logs_css_check.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const cssPath = path.resolve(__dirname, '..', 'web', 'static', 'css', 'style.css');
const css = fs.readFileSync(cssPath, 'utf8');

let pass = 0, fail = 0;
function chk(name, cond) {
  console.log((cond ? 'PASS' : 'FAIL') + ' | ' + name);
  if (cond) pass++; else fail++;
}

// 1. --topbar-h: 52px 出现在 :root 块内
const rootBlock = /:root\s*\{([\s\S]*?)\}/.exec(css);
chk('1  --topbar-h: 52px 出现在 :root 块内',
  !!rootBlock && /--topbar-h:\s*52px/.test(rootBlock[1]));

// 2. .topbar 使用 height: var(--topbar-h)
const topbarBlock = /\.topbar\s*\{([\s\S]*?)\}/.exec(css);
chk('2  .topbar 使用 height: var(--topbar-h)',
  !!topbarBlock && /height:\s*var\(--topbar-h\)/.test(topbarBlock[1]));

// 3. 吸顶规则：选择器必须是 table > thead > tr > th，且含 position: sticky / top: var(--topbar-h) / z-index: 20
const stickyRule = /table\s*>\s*thead\s*>\s*tr\s*>\s*th\s*\{([\s\S]*?)\}/.exec(css);
chk('3a 吸顶选择器为 table > thead > tr > th（能命中真实结构）', !!stickyRule);
chk('3b 吸顶规则含 position: sticky', stickyRule && /position:\s*sticky/.test(stickyRule[1]));
chk('3c 吸顶规则含 top: var(--topbar-h)', stickyRule && /top:\s*var\(--topbar-h\)/.test(stickyRule[1]));
chk('3d 吸顶规则含 z-index: 20', stickyRule && /z-index:\s*20/.test(stickyRule[1]));
// 关键负向：禁止出现缺失 tr 的 table > thead > th { 规则（注释里的文字不算）
chk('3e 不存在 table > thead > th { 规则（缺失 tr 无法命中元素）',
  !/table\s*>\s*thead\s*>\s*th\s*\{/.test(css));

// 4. 排除规则 table.child-table > thead > tr > th 含 position: static
const childRule = /table\.child-table\s*>\s*thead\s*>\s*tr\s*>\s*th\s*\{([\s\S]*?)\}/.exec(css);
chk('4a 存在 table.child-table > thead > tr > th 排除规则', !!childRule);
chk('4b 排除规则含 position: static', childRule && /position:\s*static/.test(childRule[1]));

// 5. .ss-pop 的 z-index: 30 未被改：出现在 .ss-pop 块内且全文件仅一次
const ssPopBlock = /\.ss-pop\s*\{([\s\S]*?)\}/.exec(css);
const z30Count = (css.match(/z-index:\s*30/g) || []).length;
chk('5a .ss-pop 保留 z-index: 30', ssPopBlock && /z-index:\s*30/.test(ssPopBlock[1]));
chk('5b 全文件 z-index: 30 仅出现一次（邻近 .ss-pop，未被误改）', z30Count === 1);

// 6. .topbar 的 z-index: 100 未被改
chk('6  .topbar 保留 z-index: 100', topbarBlock && /z-index:\s*100/.test(topbarBlock[1]));

// 7. 增量：#logPager 吸底分页条（fixed / bottom:0 / z-index:18）
const logPagerRule = /#logPager\s*\{([\s\S]*?)\}/.exec(css);
chk('7a 存在 #logPager 规则且含 position: fixed', logPagerRule && /position:\s*fixed/.test(logPagerRule[1]));
chk('7b #logPager 含 bottom: 0（吸视口底部）', logPagerRule && /bottom:\s*0/.test(logPagerRule[1]));
chk('7c #logPager 含 z-index: 18', logPagerRule && /z-index:\s*18/.test(logPagerRule[1]));

// 8. z-index 层级不被改小：30 与 100 仍各仅一次，且 18 < 30 < 100
function zOf(block) {
  const m = block && /z-index:\s*(\d+)/.exec(block[1]);
  return m ? parseInt(m[1], 10) : null;
}
const zLogPager = zOf(logPagerRule), zSsPop = zOf(ssPopBlock), zTopbar = zOf(topbarBlock);
const z100Count = (css.match(/z-index:\s*100/g) || []).length;
chk('8a 全文件 z-index: 100 仍仅一次（.topbar 未被改小）', z100Count === 1);
chk('8b z-index 顺序 18(#logPager) < 30(.ss-pop) < 100(.topbar)',
  zLogPager === 18 && zSsPop === 30 && zTopbar === 100 && zLogPager < zSsPop && zSsPop < zTopbar);

// 9. .footer padding 含 56px（避让吸底条，防遮挡页脚）
const footerBlock = /\.footer\s*\{([\s\S]*?)\}/.exec(css);
chk('9  .footer 的 padding 含 56px（避让吸底条）', footerBlock && /padding:.*56px/.test(footerBlock[1]));

// 10. 吸顶规则未被本次增量触碰
chk('10a 吸顶规则 table > thead > tr > th 仍存在', !!stickyRule);
chk('10b 吸顶规则仍 top: var(--topbar-h) 且 z-index: 20（未被触碰）',
  stickyRule && /top:\s*var\(--topbar-h\)/.test(stickyRule[1]) && /z-index:\s*20/.test(stickyRule[1]));

console.log('---- CSS TOTAL=' + (pass + fail) + ' PASS=' + pass + ' FAIL=' + fail);
process.exit(fail ? 1 : 0);
