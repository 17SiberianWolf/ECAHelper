/* C. 回归核对（静态）：确认 logs.js 改动未引入风格/链路问题。
 * 用法: node tools/logs_regress_check.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const js = fs.readFileSync(path.resolve(__dirname, '..', 'web', 'static', 'js', 'logs.js'), 'utf8');

let pass = 0, fail = 0;
function chk(name, cond) {
  console.log((cond ? 'PASS' : 'FAIL') + ' | ' + name);
  if (cond) pass++; else fail++;
}

// C1 可见性一律走 classList，严禁 style.display。
// 注意：文件头注释里有一句「严禁 style.display」，是开发者的规则说明而非代码使用。
// 因此先剥离注释再断言，避免把文档文字误判为违规。
function stripJsComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '') // 块注释
    .replace(/\/\/.*$/gm, '');        // 行注释
}
const codeOnly = stripJsComments(js);
chk('C1 logs.js 代码体未使用 style.display（可见性一律走 classList；注释中的规则说明不计）',
  !/\.style\s*\.\s*display/.test(codeOnly) && !/[^.\w]style\s*\.\s*display/.test(codeOnly));

// C2 render() 内部仍调用 renderPager()（无断链）
chk('C2 render() 内部调用 renderPager()（渲染链路未断）',
  /function render\(\)\s*\{[\s\S]*?renderPager\(\);/.test(js));

// C3 renderPagerInto 仅声明一次（无重复声明/全局符号冲突）
const declCount = (js.match(/function renderPagerInto/g) || []).length;
chk('C3a renderPagerInto 仅声明一次（无重复/冲突）', declCount === 1);

// C3b renderPager 内对 renderPagerInto 的调用次数为 2（双容器）。
// 注意：增量把 renderPager 改写为局部变量 top/bot 再调用 renderPagerInto(top/bot)，
// 因此用「renderPagerInto(」总出现次数 = 1(定义) + 2(调用) = 3 来断言，避免与字面 el( 绑定。
const callCount = (js.match(/renderPagerInto\(/g) || []).length;
chk('C3b renderPager 对 renderPagerInto 调用 2 次（落双容器）', callCount === 3);

console.log('---- REGRESS TOTAL=' + (pass + fail) + ' PASS=' + pass + ' FAIL=' + fail);
process.exit(fail ? 1 : 0);
