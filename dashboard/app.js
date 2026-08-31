/* Dashboard client — zero external dependencies.
 * Three sections share one set of chart builders (line, horizontal bar,
 * 100%-stacked column, diverging bar): Produção Bruta and Produção
 * Beneficiada each get an interactive filtered view over their own embedded
 * rows; Beneficiamento renders the pre-aggregated Bruta×Beneficiada
 * cross-reference (computed server-side via DuckDB — see
 * etl/cross_reference.py) as a static executive summary.
 */
(function () {
  "use strict";

  var SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)", "var(--series-7)", "var(--series-8)"];

  // ---------------------------------------------------------------- format
  function fmtCompact(n) {
    var sign = n < 0 ? "-" : "";
    var a = Math.abs(n);
    if (a >= 1e12) return sign + (a / 1e12).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " tri";
    if (a >= 1e9) return sign + (a / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " bi";
    if (a >= 1e6) return sign + (a / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " mi";
    if (a >= 1e3) return sign + (a / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mil";
    return sign + a.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  function fmtBRL(n) { return "R$ " + fmtCompact(n); }
  function fmtT(n) { return fmtCompact(n) + " t"; }
  function fmtPct(n) { return (n * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%"; }
  function fmtInt(n) { return Math.round(n).toLocaleString("pt-BR"); }
  function fmtX(n) { return n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "x"; }

  // ---------------------------------------------------------------- dom/svg
  var SVGNS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, parent) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) { if (k === "html") e.innerHTML = attrs[k]; else e.setAttribute(k, attrs[k]); }
    if (parent) parent.appendChild(e);
    return e;
  }
  function svg(tag, attrs, parent) {
    var e = document.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function byId(id) { return document.getElementById(id); }

  // ---------------------------------------------------------------- tooltip
  var tooltipEl = byId("tooltip");
  function showTooltip(x, y, html) {
    clear(tooltipEl);
    var frag = document.createElement("div");
    frag.innerHTML = html; // built from trusted, hardcoded template strings only
    while (frag.firstChild) tooltipEl.appendChild(frag.firstChild);
    tooltipEl.style.opacity = "1";
    var pad = 14;
    var vw = window.innerWidth, vh = window.innerHeight;
    var rect = tooltipEl.getBoundingClientRect();
    var tx = x + pad, ty = y + pad;
    if (tx + rect.width > vw - 8) tx = x - rect.width - pad;
    if (ty + rect.height > vh - 8) ty = y - rect.height - pad;
    tooltipEl.style.transform = "translate(" + Math.max(4, tx) + "px," + Math.max(4, ty) + "px)";
  }
  function hideTooltip() { tooltipEl.style.opacity = "0"; tooltipEl.style.transform = "translate(-9999px,-9999px)"; }
  function ttRow(label, value, colorVar) {
    var key = colorVar ? '<span class="t-key" style="background:' + colorVar + '"></span>' : "";
    return '<div class="t-row"><span class="k">' + key + label + '</span><span class="v">' + value + "</span></div>";
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // ---------------------------------------------------------------- line chart
  function drawLineChart(container, years, values, colorVar, formatValue) {
    clear(container);
    var W = 560, H = 230, ML = 56, MR = 14, MT = 14, MB = 26;
    var plotW = W - ML - MR, plotH = H - MT - MB;
    var root = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, container);

    if (!years.length) { el("div", { class: "empty-msg", html: "Sem dados para o recorte selecionado." }, container); return; }

    var maxV = Math.max.apply(null, values.concat([0])) * 1.15 || 1;
    var n = years.length;
    function xAt(i) { return n === 1 ? ML + plotW / 2 : ML + (plotW * i) / (n - 1); }
    function yAt(v) { return MT + plotH - (plotH * v) / maxV; }

    var steps = 4;
    for (var s = 0; s <= steps; s++) {
      var v = (maxV * s) / steps;
      var y = yAt(v);
      svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, class: s === 0 ? "baseline" : "gridline" }, root);
      svg("text", { x: ML - 8, y: y + 3, "text-anchor": "end", class: "axis-label" }, root).textContent = formatValue(v);
    }

    var labelEvery = Math.ceil(n / 8) || 1;
    for (var i = 0; i < n; i++) {
      if (i % labelEvery === 0 || i === n - 1) {
        svg("text", { x: xAt(i), y: H - 6, "text-anchor": "middle", class: "axis-label" }, root).textContent = years[i];
      }
    }

    var d = "";
    for (i = 0; i < n; i++) d += (i === 0 ? "M" : "L") + xAt(i) + "," + yAt(values[i]) + " ";
    var areaD = "M" + xAt(0) + "," + yAt(0) + " " + d.slice(1) + " L" + xAt(n - 1) + "," + yAt(0) + " Z";
    svg("path", { d: areaD, style: "fill:" + colorVar + ";opacity:0.10;stroke:none" }, root);
    svg("path", { d: d, style: "fill:none;stroke:" + colorVar + ";stroke-width:2;stroke-linejoin:round;stroke-linecap:round" }, root);

    var crosshair = svg("line", { y1: MT, y2: MT + plotH, class: "gridline", style: "opacity:0" }, root);
    for (i = 0; i < n; i++) {
      svg("circle", { cx: xAt(i), cy: yAt(values[i]), r: 4, style: "fill:" + colorVar + ";stroke:var(--surface-1);stroke-width:2" }, root);
      (function (idx) {
        var hit = svg("circle", { cx: xAt(idx), cy: yAt(values[idx]), r: 13, style: "fill:transparent;cursor:pointer" }, root);
        hit.addEventListener("pointermove", function (ev) {
          crosshair.setAttribute("x1", xAt(idx)); crosshair.setAttribute("x2", xAt(idx)); crosshair.style.opacity = "1";
          showTooltip(ev.clientX, ev.clientY, '<div class="t-title">' + years[idx] + "</div>" + ttRow("valor", formatValue(values[idx]), colorVar));
        });
        hit.addEventListener("pointerleave", function () { crosshair.style.opacity = "0"; hideTooltip(); });
      })(i);
    }
  }

  // -------------------------------------------------- multi-series line chart
  function drawMultiLineChart(container, years, series, formatValue, legendContainer) {
    // series: [{name, colorVar, values:[...]}]
    clear(container);
    if (legendContainer) clear(legendContainer);
    var W = 900, H = 240, ML = 60, MR = 14, MT = 14, MB = 26;
    var plotW = W - ML - MR, plotH = H - MT - MB;
    var root = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, container);
    if (!years.length) { el("div", { class: "empty-msg", html: "Sem dados para o recorte selecionado." }, container); return; }

    var maxV = 0;
    series.forEach(function (s) { maxV = Math.max(maxV, Math.max.apply(null, s.values.concat([0]))); });
    maxV = maxV * 1.15 || 1;
    var n = years.length;
    function xAt(i) { return n === 1 ? ML + plotW / 2 : ML + (plotW * i) / (n - 1); }
    function yAt(v) { return MT + plotH - (plotH * v) / maxV; }

    for (var s = 0; s <= 4; s++) {
      var v = (maxV * s) / 4, y = yAt(v);
      svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, class: s === 0 ? "baseline" : "gridline" }, root);
      svg("text", { x: ML - 8, y: y + 3, "text-anchor": "end", class: "axis-label" }, root).textContent = formatValue(v);
    }
    var labelEvery = Math.ceil(n / 10) || 1;
    for (var i = 0; i < n; i++) {
      if (i % labelEvery === 0 || i === n - 1) svg("text", { x: xAt(i), y: H - 6, "text-anchor": "middle", class: "axis-label" }, root).textContent = years[i];
    }

    series.forEach(function (ser) {
      var d = "";
      for (var i = 0; i < n; i++) d += (i === 0 ? "M" : "L") + xAt(i) + "," + yAt(ser.values[i]) + " ";
      svg("path", { d: d, style: "fill:none;stroke:" + ser.colorVar + ";stroke-width:2;stroke-linejoin:round;stroke-linecap:round" }, root);
      for (i = 0; i < n; i++) svg("circle", { cx: xAt(i), cy: yAt(ser.values[i]), r: 3.5, style: "fill:" + ser.colorVar + ";stroke:var(--surface-1);stroke-width:2" }, root);
    });

    var crosshair = svg("line", { y1: MT, y2: MT + plotH, class: "gridline", style: "opacity:0" }, root);
    for (i = 0; i < n; i++) {
      (function (idx) {
        var hit = svg("rect", { x: xAt(idx) - (plotW / n) / 2, y: MT, width: plotW / n, height: plotH, style: "fill:transparent;cursor:pointer" }, root);
        hit.addEventListener("pointermove", function (ev) {
          crosshair.setAttribute("x1", xAt(idx)); crosshair.setAttribute("x2", xAt(idx)); crosshair.style.opacity = "1";
          var rows = series.map(function (ser) { return ttRow(ser.name, formatValue(ser.values[idx]), ser.colorVar); }).join("");
          showTooltip(ev.clientX, ev.clientY, '<div class="t-title">' + years[idx] + "</div>" + rows);
        });
        hit.addEventListener("pointerleave", function () { crosshair.style.opacity = "0"; hideTooltip(); });
      })(i);
    }

    if (legendContainer) {
      series.forEach(function (s) {
        var item = el("div", { class: "legend-item" }, legendContainer);
        el("span", { class: "legend-swatch", style: "background:" + s.colorVar }, item);
        el("span", {}, item).textContent = s.name;
      });
    }
  }

  // ---------------------------------------------------------------- horizontal bar chart
  function drawHBarChart(container, items, colorVar, formatValue) {
    clear(container);
    if (!items.length) { el("div", { class: "empty-msg", html: "Sem dados para o recorte selecionado." }, container); return; }
    var W = 560, rowH = 26, barH = 16, ML = 168, MR = 74, MT = 6, MB = 6;
    var n = items.length, H = MT + MB + n * rowH;
    var root = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, container);
    var maxV = Math.max.apply(null, items.map(function (d) { return d.value; }).concat([0])) || 1;
    var plotW = W - ML - MR;

    for (var i = 0; i < n; i++) {
      var y = MT + i * rowH;
      var barW = Math.max(1, (plotW * items[i].value) / maxV);
      var labelText = items[i].label;
      var label = svg("text", { x: ML - 10, y: y + barH / 2 + 4, "text-anchor": "end", class: "bar-label" }, root);
      label.textContent = labelText.length > 24 ? labelText.slice(0, 23) + "…" : labelText;
      el("title", {}, label).textContent = labelText;
      svg("rect", { x: ML, y: y, width: barW, height: barH, rx: 4, style: "fill:" + colorVar }, root);
      var valLabel = svg("text", { x: ML + barW + 8, y: y + barH / 2 + 4, class: "bar-label" }, root);
      valLabel.textContent = formatValue(items[i].value);
      (function (idx, yy, bw) {
        var hit = svg("rect", { x: ML, y: yy, width: Math.max(bw, plotW), height: barH, style: "fill:transparent;cursor:pointer" }, root);
        hit.addEventListener("pointermove", function (ev) {
          showTooltip(ev.clientX, ev.clientY, '<div class="t-title">' + esc(items[idx].label) + "</div>" + ttRow("valor", formatValue(items[idx].value), colorVar));
        });
        hit.addEventListener("pointerleave", hideTooltip);
      })(i, y, barW);
    }
  }

  // ---------------------------------------------------------------- diverging horizontal bar
  function drawDivergingBarChart(container, items, formatValue) {
    // items: [{label, value}] — value can be negative
    clear(container);
    if (!items.length) { el("div", { class: "empty-msg", html: "Sem dados para o recorte selecionado." }, container); return; }
    var W = 640, rowH = 26, barH = 16, ML = 190, MR = 64, MT = 6, MB = 6;
    var n = items.length, H = MT + MB + n * rowH;
    var root = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, container);
    var maxAbs = Math.max.apply(null, items.map(function (d) { return Math.abs(d.value); }).concat([1]));
    var plotW = W - ML - MR;
    var x0 = ML + plotW / 2;
    var scale = (plotW / 2) / maxAbs;

    svg("line", { x1: x0, x2: x0, y1: MT, y2: MT + n * rowH, class: "baseline" }, root);

    for (var i = 0; i < n; i++) {
      var y = MT + i * rowH;
      var v = items[i].value;
      var isPos = v >= 0;
      var w = Math.max(1, Math.abs(v) * scale);
      var x = isPos ? x0 : x0 - w;
      var color = isPos ? "var(--series-1)" : "var(--diverge-neg)";
      var labelText = items[i].label;
      var label = svg("text", { x: ML - 12, y: y + barH / 2 + 4, "text-anchor": "end", class: "bar-label" }, root);
      label.textContent = labelText.length > 26 ? labelText.slice(0, 25) + "…" : labelText;
      el("title", {}, label).textContent = labelText;
      svg("rect", { x: x, y: y, width: w, height: barH, rx: 4, style: "fill:" + color }, root);
      var valX = isPos ? x + w + 8 : x - 8;
      var valLabel = svg("text", { x: valX, y: y + barH / 2 + 4, "text-anchor": isPos ? "start" : "end", class: "bar-label" }, root);
      valLabel.textContent = formatValue(v);
      (function (idx, yy) {
        var hit = svg("rect", { x: ML, y: yy, width: plotW, height: barH, style: "fill:transparent;cursor:pointer" }, root);
        hit.addEventListener("pointermove", function (ev) {
          showTooltip(ev.clientX, ev.clientY, '<div class="t-title">' + esc(items[idx].label) + "</div>" + ttRow("valor agregado", formatValue(items[idx].value)));
        });
        hit.addEventListener("pointerleave", hideTooltip);
      })(i, y);
    }
  }

  // ---------------------------------------------------------------- 100% stacked column chart
  function drawStackedChart(container, years, series, legendContainer) {
    clear(container);
    if (legendContainer) clear(legendContainer);
    if (!years.length) { el("div", { class: "empty-msg", html: "Sem dados para o recorte selecionado." }, container); return; }
    var W = 900, H = 240, ML = 46, MR = 14, MT = 10, MB = 26;
    var plotW = W - ML - MR, plotH = H - MT - MB;
    var root = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, container);
    var n = years.length;
    var bandW = plotW / n;
    var barW = Math.min(28, bandW * 0.62);
    var gap = 2;

    [0, 0.25, 0.5, 0.75, 1].forEach(function (p) {
      var y = MT + plotH - plotH * p;
      svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, class: p === 0 ? "baseline" : "gridline" }, root);
      svg("text", { x: ML - 8, y: y + 3, "text-anchor": "end", class: "axis-label" }, root).textContent = Math.round(p * 100) + "%";
    });

    var labelEvery = Math.ceil(n / 10) || 1;
    for (var i = 0; i < n; i++) {
      var cx = ML + bandW * i + bandW / 2;
      if (i % labelEvery === 0 || i === n - 1) svg("text", { x: cx, y: H - 6, "text-anchor": "middle", class: "axis-label" }, root).textContent = years[i];
      var total = 0;
      for (var s = 0; s < series.length; s++) total += series[s].values[i];
      var yCursor = MT + plotH;
      var segs = [];
      for (s = 0; s < series.length; s++) {
        var v = series[s].values[i];
        var frac = total > 0 ? v / total : 0;
        var segH = Math.max(0, plotH * frac - gap);
        var yTop = yCursor - plotH * frac + (segH > 0 ? gap / 2 : 0);
        if (segH > 0.4) svg("rect", { x: cx - barW / 2, y: yTop, width: barW, height: segH, rx: 2, style: "fill:" + series[s].colorVar }, root);
        segs.push({ name: series[s].name, value: v, frac: frac, colorVar: series[s].colorVar });
        yCursor -= plotH * frac;
      }
      (function (idx, cxx, segsArr, yr) {
        var hit = svg("rect", { x: cxx - bandW / 2, y: MT, width: bandW, height: plotH, style: "fill:transparent;cursor:pointer" }, root);
        hit.addEventListener("pointermove", function (ev) {
          var rows = segsArr.map(function (sg) { return ttRow(sg.name, fmtPct(sg.frac), sg.colorVar); }).join("");
          showTooltip(ev.clientX, ev.clientY, '<div class="t-title">' + yr + "</div>" + rows);
        });
        hit.addEventListener("pointerleave", hideTooltip);
      })(i, cx, segs, years[i]);
    }

    if (legendContainer) {
      series.forEach(function (s) {
        var item = el("div", { class: "legend-item" }, legendContainer);
        el("span", { class: "legend-swatch", style: "background:" + s.colorVar }, item);
        el("span", {}, item).textContent = s.name;
      });
    }
  }

  function topN(map, key, n) {
    return Array.from(map.entries()).map(function (e) { return { label: e[0], value: e[1][key] }; })
      .sort(function (a, b) { return b.value - a.value; }).slice(0, n);
  }

  // ================================================================
  // Dataset view: filtered explorer, shared by Bruta and Beneficiada
  // ================================================================
  function createDatasetView(prefix, dataset, cols, opts) {
    var state = {
      anoFrom: dataset.anoMin,
      anoTo: dataset.anoMax,
      regioes: new Set(Object.keys(dataset.regioesSet)),
      classes: new Set(dataset.classes),
      substancia: "",
    };

    function ufRegiao(ufI) { return dataset.regiaoByUf[dataset.ufs[ufI]]; }

    function filteredRows() {
      var q = state.substancia.trim().toLowerCase();
      return dataset.rows.filter(function (r) {
        if (r[cols.ANO] < state.anoFrom || r[cols.ANO] > state.anoTo) return false;
        if (!state.regioes.has(ufRegiao(r[cols.UF]))) return false;
        if (!state.classes.has(dataset.classes[r[cols.CL]])) return false;
        if (q && dataset.substancias[r[cols.SB]].toLowerCase().indexOf(q) === -1) return false;
        return true;
      });
    }

    function aggregate(rows) {
      var byAno = new Map(), byUf = new Map(), bySub = new Map(), byClasse = new Map();
      var totQtdRom = 0, totValorVenda = 0, totValorMov = 0, nProdZero = 0;

      rows.forEach(function (r) {
        var ano = r[cols.ANO], uf = dataset.ufs[r[cols.UF]], cl = dataset.classes[r[cols.CL]], sb = dataset.substancias[r[cols.SB]];
        var valorVenda = r[cols.VALOR_VENDA], valorTransf = r[cols.VALOR_TRANSF], valorTransfer = r[cols.VALOR_TRANSFER];
        var qtdRom = cols.QTD_ROM != null ? r[cols.QTD_ROM] : 0;
        var qtdVenda = cols.QTD_VENDA != null ? r[cols.QTD_VENDA] : 0;
        var qtdTransf = cols.QTD_TRANSF != null ? r[cols.QTD_TRANSF] : 0;
        var qtdTransfer = cols.QTD_TRANSFER != null ? r[cols.QTD_TRANSFER] : 0;
        var valorMov = valorVenda + valorTransf + valorTransfer;

        totQtdRom += qtdRom; totValorVenda += valorVenda; totValorMov += valorMov;
        if (cols.QTD_ROM != null && qtdRom <= 0) nProdZero++;

        if (!byAno.has(ano)) byAno.set(ano, { qtdRom: 0, valorVenda: 0, qtdVenda: 0, valorTransf: 0, qtdTransf: 0, valorTransfer: 0, qtdTransfer: 0, valorMov: 0, n: 0 });
        var a = byAno.get(ano);
        a.qtdRom += qtdRom; a.valorVenda += valorVenda; a.qtdVenda += qtdVenda;
        a.valorTransf += valorTransf; a.qtdTransf += qtdTransf; a.valorTransfer += valorTransfer; a.qtdTransfer += qtdTransfer;
        a.valorMov += valorMov; a.n++;

        if (!byUf.has(uf)) byUf.set(uf, { valorVenda: 0, n: 0 });
        var u = byUf.get(uf); u.valorVenda += valorVenda; u.n++;

        if (!bySub.has(sb)) bySub.set(sb, { valorVenda: 0, n: 0 });
        var sbAgg = bySub.get(sb); sbAgg.valorVenda += valorVenda; sbAgg.n++;

        if (!byClasse.has(cl)) byClasse.set(cl, { valorVenda: 0, n: 0 });
        var c = byClasse.get(cl); c.valorVenda += valorVenda; c.n++;
      });

      return {
        n: rows.length, totQtdRom: totQtdRom, totValorVenda: totValorVenda, totValorMov: totValorMov,
        pctProdZero: rows.length ? nProdZero / rows.length : 0,
        byAno: byAno, byUf: byUf, bySub: bySub, byClasse: byClasse,
        nSubstancias: bySub.size, nUfs: byUf.size,
      };
    }

    function renderKpis(agg) {
      var host = byId(prefix + "-kpiRow");
      if (!host) return;
      clear(host);
      var tiles = [{ label: "Registros no recorte", value: fmtInt(agg.n) }];
      if (opts.hasProducao) tiles.push({ label: "Produção bruta (ROM)", value: fmtT(agg.totQtdRom) });
      tiles.push({ label: "Valor de venda", value: fmtBRL(agg.totValorVenda) });
      tiles.push({ label: "Valor movimentado total", value: fmtBRL(agg.totValorMov) });
      tiles.push({ label: "Substâncias no recorte", value: fmtInt(agg.nSubstancias) });
      tiles.push({ label: "UFs no recorte", value: fmtInt(agg.nUfs) });
      tiles.forEach(function (t) {
        var tile = el("div", { class: "kpi-tile" }, host);
        el("div", { class: "label" }, tile).textContent = t.label;
        el("div", { class: "value" }, tile).textContent = t.value;
      });
    }

    function renderDestinoTable(anos, agg) {
      var host = byId(prefix + "-tableDestino");
      if (!host) return;
      clear(host);
      var t = el("table", { class: "data-table" }, host);
      var thead = el("thead", {}, t); var trh = el("tr", {}, thead);
      ["Ano", "Venda", opts.transformLabel, "Transferência", "Base"].forEach(function (h) { el("th", {}, trh).textContent = h; });
      var tbody = el("tbody", {}, t);
      anos.forEach(function (a) {
        var d = agg.byAno.get(a);
        var v1 = opts.destinoUsesQtd ? d.qtdVenda : d.valorVenda;
        var v2 = opts.destinoUsesQtd ? d.qtdTransf : d.valorTransf;
        var v3 = opts.destinoUsesQtd ? d.qtdTransfer : d.valorTransfer;
        var total = v1 + v2 + v3;
        var tr = el("tr", {}, tbody);
        el("td", {}, tr).textContent = a;
        el("td", {}, tr).textContent = total ? fmtPct(v1 / total) : "—";
        el("td", {}, tr).textContent = total ? fmtPct(v2 / total) : "—";
        el("td", {}, tr).textContent = total ? fmtPct(v3 / total) : "—";
        el("td", {}, tr).textContent = opts.destinoUsesQtd ? fmtT(total) : fmtBRL(total);
      });
    }

    function renderSerieTable(anos, agg) {
      var host = byId(prefix + "-tableSerie");
      if (!host) return;
      clear(host);
      var t = el("table", { class: "data-table" }, host);
      var thead = el("thead", {}, t); var trh = el("tr", {}, thead);
      ["Ano", "Produção ROM (t)", "Valor venda (R$)", "Cresc. valor YoY", "Registros"].forEach(function (h) { el("th", {}, trh).textContent = h; });
      var tbody = el("tbody", {}, t);
      var prevValor = null;
      anos.forEach(function (a) {
        var d = agg.byAno.get(a);
        var tr = el("tr", {}, tbody);
        el("td", {}, tr).textContent = a;
        el("td", {}, tr).textContent = fmtT(d.qtdRom);
        el("td", {}, tr).textContent = fmtBRL(d.valorVenda);
        el("td", {}, tr).textContent = prevValor ? fmtPct((d.valorVenda - prevValor) / prevValor) : "—";
        el("td", {}, tr).textContent = fmtInt(d.n);
        prevValor = d.valorVenda;
      });
    }

    function renderAll() {
      var rows = filteredRows();
      var agg = aggregate(rows);
      renderKpis(agg);

      var anos = Array.from(agg.byAno.keys()).sort(function (a, b) { return a - b; });

      if (opts.hasProducao && byId(prefix + "-chartProducao")) {
        drawLineChart(byId(prefix + "-chartProducao"), anos, anos.map(function (a) { return agg.byAno.get(a).qtdRom; }), "var(--series-1)", fmtT);
      }
      if (byId(prefix + "-chartMovimentado")) {
        drawLineChart(byId(prefix + "-chartMovimentado"), anos, anos.map(function (a) { return agg.byAno.get(a).valorMov; }), "var(--series-1)", fmtBRL);
      }
      drawLineChart(byId(prefix + "-chartValor"), anos, anos.map(function (a) { return agg.byAno.get(a).valorVenda; }), "var(--series-1)", fmtBRL);

      drawHBarChart(byId(prefix + "-chartSubstancias"), topN(agg.bySub, "valorVenda", 15), "var(--series-1)", fmtBRL);
      drawHBarChart(byId(prefix + "-chartUf"), topN(agg.byUf, "valorVenda", 15), "var(--series-2)", fmtBRL);
      drawHBarChart(byId(prefix + "-chartClasse"), topN(agg.byClasse, "valorVenda", 8), "var(--series-3)", fmtBRL);

      var destSeries = opts.destinoUsesQtd
        ? [
            { name: "Venda", colorVar: "var(--series-1)", values: anos.map(function (a) { return agg.byAno.get(a).qtdVenda; }) },
            { name: opts.transformLabel, colorVar: "var(--series-2)", values: anos.map(function (a) { return agg.byAno.get(a).qtdTransf; }) },
            { name: "Transferência", colorVar: "var(--series-3)", values: anos.map(function (a) { return agg.byAno.get(a).qtdTransfer; }) },
          ]
        : [
            { name: "Venda", colorVar: "var(--series-1)", values: anos.map(function (a) { return agg.byAno.get(a).valorVenda; }) },
            { name: opts.transformLabel, colorVar: "var(--series-2)", values: anos.map(function (a) { return agg.byAno.get(a).valorTransf; }) },
            { name: "Transferência", colorVar: "var(--series-3)", values: anos.map(function (a) { return agg.byAno.get(a).valorTransfer; }) },
          ];
      drawStackedChart(byId(prefix + "-chartDestino"), anos, destSeries, byId(prefix + "-legendDestino"));

      renderDestinoTable(anos, agg);
      if (opts.hasProducao) renderSerieTable(anos, agg);
    }

    function initControls() {
      var anoFrom = byId(prefix + "-anoFrom"), anoTo = byId(prefix + "-anoTo");
      for (var y = dataset.anoMin; y <= dataset.anoMax; y++) {
        el("option", { value: y, html: y }, anoFrom);
        el("option", { value: y, html: y }, anoTo);
      }
      anoFrom.value = state.anoFrom; anoTo.value = state.anoTo;
      anoFrom.addEventListener("change", function () { state.anoFrom = Math.min(+anoFrom.value, state.anoTo); anoFrom.value = state.anoFrom; renderAll(); });
      anoTo.addEventListener("change", function () { state.anoTo = Math.max(+anoTo.value, state.anoFrom); anoTo.value = state.anoTo; renderAll(); });

      var regiaoChips = byId(prefix + "-regiaoChips");
      Object.keys(dataset.regioesSet).forEach(function (r) {
        var chip = el("div", { class: "chip active", html: r }, regiaoChips);
        chip.addEventListener("click", function () {
          if (state.regioes.has(r)) { if (state.regioes.size > 1) { state.regioes.delete(r); chip.classList.remove("active"); } }
          else { state.regioes.add(r); chip.classList.add("active"); }
          renderAll();
        });
      });

      var classeChips = byId(prefix + "-classeChips");
      dataset.classes.forEach(function (c) {
        var chip = el("div", { class: "chip active", html: c }, classeChips);
        chip.addEventListener("click", function () {
          if (state.classes.has(c)) { if (state.classes.size > 1) { state.classes.delete(c); chip.classList.remove("active"); } }
          else { state.classes.add(c); chip.classList.add("active"); }
          renderAll();
        });
      });

      var search = byId(prefix + "-substanciaSearch");
      var debounceTimer;
      search.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () { state.substancia = search.value; renderAll(); }, 150);
      });

      byId(prefix + "-resetFilters").addEventListener("click", function () {
        state.anoFrom = dataset.anoMin; state.anoTo = dataset.anoMax;
        state.regioes = new Set(Object.keys(dataset.regioesSet));
        state.classes = new Set(dataset.classes);
        state.substancia = "";
        anoFrom.value = state.anoFrom; anoTo.value = state.anoTo; search.value = "";
        Array.prototype.forEach.call(regiaoChips.children, function (c) { c.classList.add("active"); });
        Array.prototype.forEach.call(classeChips.children, function (c) { c.classList.add("active"); });
        renderAll();
      });
    }

    initControls();
    renderAll();
  }

  // ================================================================ init
  function initTableToggles() {
    Array.prototype.forEach.call(document.querySelectorAll(".table-toggle"), function (btn) {
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-target");
        var chartId = btn.getAttribute("data-chart");
        var host = byId(targetId);
        var show = host.style.display === "none";
        host.style.display = show ? "block" : "none";
        btn.textContent = show ? "Ver gráfico" : "Ver tabela";
        if (chartId) byId(chartId).style.display = show ? "none" : "block";
      });
    });
  }

  function initTheme() {
    function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
    function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* no-op */ } }
    var root = document.documentElement;
    var order = ["system", "light", "dark"];
    var saved = safeGet("bateia-theme") || "system";
    function applyTheme(t) {
      if (t === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", t);
      safeSet("bateia-theme", t);
    }
    applyTheme(saved);
    byId("themeToggle").addEventListener("click", function () {
      saved = order[(order.indexOf(saved) + 1) % order.length];
      applyTheme(saved);
    });
  }

  function initCruzamento() {
    var cruz = DATA.cruzamento;
    if (!cruz) return;

    var kpiHost = byId("cruz-kpiRow");
    var maxAdd = cruz.porSubstanciaComparavel.reduce(function (best, r) { return r.valorAgregado > (best ? best.valorAgregado : -Infinity) ? r : best; }, null);
    var tiles = [
      { label: "Substâncias em ambas as bases", value: fmtInt(cruz.resumo.nSubstanciasAmbas) },
      { label: "Substâncias comparáveis (≥5 registros/lado)", value: fmtInt(cruz.resumo.nSubstanciasComparaveis) },
      { label: "Maior valor agregado", value: maxAdd ? maxAdd.substancia : "—" },
      { label: "Fator de agregação (a maior)", value: maxAdd ? fmtX(maxAdd.fatorAgregacao) : "—" },
    ];
    clear(kpiHost);
    tiles.forEach(function (t) {
      var tile = el("div", { class: "kpi-tile" }, kpiHost);
      el("div", { class: "label" }, tile).textContent = t.label;
      el("div", { class: "value" }, tile).textContent = t.value;
    });

    var sorted = cruz.porSubstanciaComparavel.slice().sort(function (a, b) { return b.valorAgregado - a.valorAgregado; });
    var top = sorted.slice(0, 8);
    var bottom = sorted.slice(-5).reverse().filter(function (r) { return top.indexOf(r) === -1; });
    var combined = top.concat(bottom).map(function (r) { return { label: r.substancia, value: r.valorAgregado }; });
    drawDivergingBarChart(byId("cruz-chartAgregado"), combined, fmtBRL);

    var anos = cruz.porAno.map(function (r) { return r.ano; });
    drawMultiLineChart(
      byId("cruz-chartAnual"),
      anos,
      [
        { name: "Produção Bruta", colorVar: "var(--series-1)", values: cruz.porAno.map(function (r) { return r.valorVendaBruta; }) },
        { name: "Produção Beneficiada", colorVar: "var(--series-2)", values: cruz.porAno.map(function (r) { return r.valorVendaBeneficiada; }) },
      ],
      fmtBRL,
      byId("cruz-legendAnual")
    );
  }

  initTableToggles();
  initTheme();

  createDatasetView("bruta", DATA.bruta, { ANO: 0, UF: 1, CL: 2, SB: 3, QTD_ROM: 4, QTD_VENDA: 5, VALOR_VENDA: 6, QTD_TRANSF: 7, VALOR_TRANSF: 8, QTD_TRANSFER: 9, VALOR_TRANSFER: 10 }, {
    hasProducao: true, destinoUsesQtd: true, transformLabel: "Transformação/consumo",
  });

  createDatasetView("ben", DATA.beneficiada, { ANO: 0, UF: 1, CL: 2, SB: 3, QTD_ROM: null, QTD_VENDA: null, VALOR_VENDA: 4, QTD_TRANSF: null, VALOR_TRANSF: 5, QTD_TRANSFER: null, VALOR_TRANSFER: 6 }, {
    hasProducao: false, destinoUsesQtd: false, transformLabel: "Consumo na usina",
  });

  initCruzamento();
})();
