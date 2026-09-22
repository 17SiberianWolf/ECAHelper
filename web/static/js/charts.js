/* ECAHelper 原生 SVG 图表（决策 +1：无 ECharts / 无 CDN，纯离线）。
 * 暴露全局 ECACharts：bar / line / heatmap。
 * 全部以字符串构建 <svg> 并写入容器 innerHTML。
 */
(function (global) {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function trunc(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }
  function fmt(n) {
    if (n == null) return "0";
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(Math.round(n * 10) / 10);
  }

  function colorScale(t) {
    // 0 -> 浅蓝, 1 -> 深蓝
    t = Math.max(0, Math.min(1, t));
    var r = Math.round(235 - t * 180);
    var g = Math.round(243 - t * 175);
    var b = Math.round(255 - t * 110);
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  /* 条形图（Top N）。items: [{label, value}] */
  function bar(container, items, opts) {
    opts = opts || {};
    var W = Math.max(320, container.clientWidth || 640);
    var H = opts.height || 300;
    var pad = { l: 54, r: 14, t: 14, b: 70 };
    var iw = W - pad.l - pad.r;
    var ih = H - pad.t - pad.b;
    var max = Math.max(1, Math.max.apply(null, items.map(function (d) { return d.value; })));
    var n = items.length || 1;
    var gap = 6;
    var bw = Math.max(4, iw / n - gap);
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="xMinYMin meet">';
    // Y 轴网格
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var val = (max * t) / ticks;
      var y = pad.t + ih - (ih * t) / ticks;
      svg += '<line x1="' + pad.l + '" y1="' + y + '" x2="' + (W - pad.r) + '" y2="' + y +
        '" stroke="#e3e7ee"/>';
      svg += '<text x="' + (pad.l - 6) + '" y="' + (y + 3) + '" text-anchor="end" font-size="10" fill="#6b7785">' +
        fmt(val) + "</text>";
    }
    items.forEach(function (d, i) {
      var x = pad.l + (iw / n) * i + gap / 2;
      var bh = max > 0 ? (ih * d.value) / max : 0;
      var y = pad.t + ih - bh;
      svg += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + bh.toFixed(1) + '" rx="2" fill="#2f6fed"/>';
      svg += '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (y - 4).toFixed(1) +
        '" text-anchor="middle" font-size="9" fill="#1f2733">' + fmt(d.value) + "</text>";
      svg += '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (pad.t + ih + 12).toFixed(1) +
        '" text-anchor="end" font-size="9" fill="#6b7785" transform="rotate(-40 ' +
        (x + bw / 2).toFixed(1) + ' ' + (pad.t + ih + 12).toFixed(1) + ')">' +
        esc(trunc(d.label, 14)) + "</text>";
    });
    svg += "</svg>";
    container.innerHTML = svg;
  }

  /* 折线/面积图（按月趋势）。series: [{month, h}] */
  function line(container, series, opts) {
    opts = opts || {};
    var W = Math.max(320, container.clientWidth || 640);
    var H = opts.height || 300;
    var pad = { l: 54, r: 14, t: 14, b: 46 };
    var iw = W - pad.l - pad.r;
    var ih = H - pad.t - pad.b;
    var max = Math.max(1, Math.max.apply(null, series.map(function (d) { return d.h; })));
    var n = series.length || 1;
    function X(i) { return pad.l + (n <= 1 ? iw / 2 : (iw * i) / (n - 1)); }
    function Y(v) { return pad.t + ih - (ih * v) / max; }
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="xMinYMin meet">';
    for (var t = 0; t <= 4; t++) {
      var val = (max * t) / 4;
      var y = pad.t + ih - (ih * t) / 4;
      svg += '<line x1="' + pad.l + '" y1="' + y + '" x2="' + (W - pad.r) + '" y2="' + y +
        '" stroke="#e3e7ee"/>';
      svg += '<text x="' + (pad.l - 6) + '" y="' + (y + 3) + '" text-anchor="end" font-size="10" fill="#6b7785">' +
        fmt(val) + "</text>";
    }
    if (n > 0) {
      var pts = series.map(function (d, i) { return X(i) + "," + Y(d.h); }).join(" ");
      var area = "M" + X(0) + "," + (pad.t + ih) + " L" + pts.replace(/ /g, " L") +
        " L" + X(n - 1) + "," + (pad.t + ih) + " Z";
      svg += '<path d="' + area + '" fill="#2f6fed" opacity="0.12"/>';
      svg += '<polyline points="' + pts + '" fill="none" stroke="#2f6fed" stroke-width="2"/>';
      series.forEach(function (d, i) {
        svg += '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(d.h).toFixed(1) +
          '" r="2.5" fill="#2f6fed"/>';
        if (n <= 24 || i % Math.ceil(n / 12) === 0) {
          svg += '<text x="' + X(i).toFixed(1) + '" y="' + (pad.t + ih + 14).toFixed(1) +
            '" text-anchor="middle" font-size="9" fill="#6b7785">' + esc(d.month) + "</text>";
        }
      });
    }
    svg += "</svg>";
    container.innerHTML = svg;
  }

  /* 交叉矩阵（人员 × 项目 heatmap）。
   * projects/persons: [id...]; cells: { "pid|rid": h } */
  function heatmap(container, projects, persons, cells) {
    if (!projects.length || !persons.length) {
      container.innerHTML = '<div class="muted">无数据</div>';
      return;
    }
    var cw = 22, ch = 22, padL = 110, padT = 12;
    var W = padL + persons.length * cw + 12;
    var H = padT + projects.length * ch + 24;
    var max = 0;
    Object.keys(cells).forEach(function (k) { if (cells[k] > max) max = cells[k]; });
    max = Math.max(1, max);
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="xMinYMin meet">';
    projects.forEach(function (p, ri) {
      var y = padT + ri * ch;
      svg += '<text x="' + (padL - 6) + '" y="' + (y + ch / 2 + 3) + '" text-anchor="end" font-size="9" fill="#1f2733">' +
        esc(trunc(p, 16)) + "</text>";
      persons.forEach(function (r, ci) {
        var x = padL + ci * cw;
        var v = cells[p + "|" + r] || 0;
        var t = v / max;
        svg += '<rect class="heat-cell" x="' + x + '" y="' + y + '" width="' + (cw - 1) +
          '" height="' + (ch - 1) + '" fill="' + colorScale(t) + '"><title>' +
          esc(p + " / " + r + " : " + v.toFixed(1) + "h") + "</title></rect>";
      });
    });
    persons.forEach(function (r, ci) {
      var x = padL + ci * cw + cw / 2;
      svg += '<text x="' + x + '" y="' + (padT + projects.length * ch + 12) +
        '" text-anchor="end" font-size="8" fill="#6b7785" transform="rotate(-60 ' + x + ' ' +
        (padT + projects.length * ch + 12) + ')">' + esc(trunc(r, 12)) + "</text>";
    });
    svg += "</svg>";
    container.innerHTML = svg;
  }

  global.ECACharts = { bar: bar, line: line, heatmap: heatmap };
})(window);
