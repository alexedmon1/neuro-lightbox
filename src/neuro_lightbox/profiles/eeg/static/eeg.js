/* The EEG profile's page behaviour for the neuro-lightbox app.
   Loaded after app.js; registers hooks through window.LightboxApp:
   - provenanceHtml: what produced an analysis's tables (source-analytics'
     provenance.json), with Monte Carlo parcel caveats open;
   - inputRunHtml: what source-localization run built a pipeline;
   - figureFacet: lead a figure title with its band (or aperiodic measure);
   - figurePanel: connectivity circos as metric tabs of band rows.
   Moved verbatim from source-lightbox's app.js. */
(function () {
  "use strict";

  var app = window.LightboxApp;
  if (!app) return;
  var M = window.MANIFEST;
  var V = app.vocabulary;
  var escapeHtml = app.escapeHtml;
  var formatName = app.formatName;
  var formatGroup = app.formatGroup;
  var metricLabel = app.metricLabel;
  var renderFigureRows = app.renderFigureRows;

  var BAND_ORDER = (V.categories && V.categories.order) || [];
  var METRIC_ORDER = V.metric_order || [];

  /* ── What produced these tables ──
     source-analytics writes provenance.json beside each analysis's tables
     (v0.8.2+). The Monte Carlo parcel caveats show open, because a parcel the
     montage cannot separate from its neighbour produces an ordinary-looking
     table row and there is otherwise nothing to distinguish it. The rest is
     reference and stays collapsed. Absent for an older results tree, in which
     case nothing is shown rather than a guess. */
  function provenanceHtml(prov) {
    if (!prov) return "";
    var loc = prov.localization || {};
    var html = "";

    var caveats = prov.parcel_caveats || {};
    var names = Object.keys(caveats).sort();
    if (names.length) {
      html += '<div class="analysis-warn"><b>' + names.length
        + (names.length === 1 ? " parcel carries" : " parcels carry")
        + ' a Monte Carlo caveat</b> — '
        + (names.length === 1 ? "its individual value is" : "their individual values are")
        + ' not interpretable on ' + (names.length === 1 ? "its" : "their") + ' own:<ul>';
      for (var n of names) {
        html += "<li><b>" + escapeHtml(n) + "</b> — " + escapeHtml(caveats[n]) + "</li>";
      }
      html += "</ul></div>";
    }

    var bits = [];
    if (loc.description) bits.push(["localization", loc.description]);
    else {
      if (loc.atlas) bits.push(["atlas", loc.atlas]);
      if (loc.inverse_method) bits.push(["inverse", loc.inverse_method]);
      if (loc.source_sampling) {
        bits.push(["sampling", loc.source_sampling === "monte_carlo" ? "Monte Carlo" : "fixed grid"]);
      }
    }
    if (loc.version) bits.push(["source-localization", loc.version]);
    if (prov.source_analytics) bits.push(["source-analytics", prov.source_analytics]);
    if (prov.plugin) bits.push(["plugin", prov.plugin]);
    if (prov.n_subjects != null) {
      var groups = prov.groups || {};
      var gnames = Object.keys(groups).sort();
      var detail = gnames.length
        ? " (" + gnames.map(function (g) { return formatGroup(g) + " " + groups[g]; }).join(", ") + ")"
        : "";
      bits.push(["subjects", prov.n_subjects + detail]);
    }
    if (loc.n_unrecorded) {
      bits.push(["not recorded", loc.n_unrecorded + " subject(s) localized before "
        + "source-localization 0.4.2"]);
    }
    if (prov.written) bits.push(["run", String(prov.written).replace("T", " ").slice(0, 16)]);
    if (!bits.length) return html;

    var lead = loc.description
      || [loc.atlas, loc.inverse_method].filter(Boolean).join(", ")
      || "recorded";
    html += '<details class="analysis-prov"><summary>What produced this — '
      + escapeHtml(lead) + "</summary><dl>";
    for (var b of bits) {
      html += "<dt>" + escapeHtml(b[0]) + "</dt><dd>" + escapeHtml(String(b[1])) + "</dd>";
    }
    html += "</dl></details>";
    return html;
  }

  /* ── What source-localization run built a pipeline ──
     Two galleries can look identical and report different measurements, so the
     settings that decide the numbers are shown rather than left in a YAML file.
     Monte Carlo is called out because it is ROI-only by construction. */
  function runProvenanceHtml(run) {
    if (!run) return '<div class="loc-run loc-run-unknown">Run settings not recorded '
      + '(localized before source-localization 0.4.2)</div>';
    var bits = [];
    if (run.atlas) bits.push(["atlas", run.atlas]);
    if (run.bem) bits.push(["head model", run.bem]);
    if (run.source_space) bits.push(["sources", run.source_space]);
    if (run.inverse) bits.push(["inverse", run.inverse + (run.orientation ? " (" + run.orientation + ")" : "")]);
    bits.push(["sampling", run.sampling === "monte_carlo" ? "Monte Carlo" : "fixed grid"]);

    var html = '<div class="loc-run">';
    for (var b of bits) {
      html += '<span class="loc-run-item"><span class="loc-run-key">' + escapeHtml(b[0])
        + '</span> ' + escapeHtml(String(b[1])) + '</span>';
    }
    html += '</div>';
    if (run.sampling === "monte_carlo") {
      html += '<div class="loc-note">Monte Carlo sampling: the ROI operator is averaged '
        + 'over many source draws, so this pipeline has parcel time series only — no '
        + 'vertex-level output exists for it.</div>';
    }
    if (run.mismatched && run.mismatched.length) {
      html += '<div class="loc-warn">Subjects disagree on: '
        + escapeHtml(run.mismatched.join(", "))
        + '. These were not all localized the same way, so pooling them compares '
        + 'different measurements.</div>';
    }
    if (run.n_unrecorded) {
      html += '<div class="loc-warn">' + run.n_unrecorded + ' subject(s) recorded no run '
        + 'settings, so they cannot be checked against the rest.</div>';
    }
    return html;
  }

  // The facet that distinguishes one figure in a module from the next — band
  // (Delta…), aperiodic measure (exponent/offset), or power type. Surfaced up
  // front so a reader can tell figures apart at a glance instead of hunting the
  // end of the title. Bands come from the vocabulary's category order.
  function _figureFacet(name) {
    // Prefer the band as the lead facet, but mask "Delta Ref" (delta-referenced
    // power) first so it can't false-match the "Delta" band; fall back to a
    // Delta-ref facet only when the figure carries no band (e.g. psd_by_region).
    var dref = /(^|\s)delta\s*ref(\s|$)/i;
    var hasDref = dref.test(name);
    var probe = hasDref ? name.replace(dref, " \u0000 ") : name;
    var measures = ["Exponent", "Offset", "Relative", "Absolute"];
    var facets = BAND_ORDER.concat(measures);  // bands first — prefer the band
    for (var i = 0; i < facets.length; i++) {
      var re = new RegExp("(^|\\s)" + facets[i].replace(/ /g, "\\s") + "(\\s|$)", "i");
      if (re.test(probe)) return { facet: facets[i], re: re };
    }
    if (hasDref) return { facet: "Delta-ref", re: dref };
    return null;
  }

  // A contrast's label from the study; else its name, word by word.
  function circosContrastLabel(name) {
    if (M && M.contrast_labels && M.contrast_labels[name]) return M.contrast_labels[name];
    return name.split("_").map(function (t) {
      return t.toLowerCase() === "vs" ? "vs" : formatName(t);
    }).join(" ");
  }

  function parseCircos(filename) {
    var base = (filename || "").replace(/\.png$/i, "");
    if (base.indexOf("circos__") !== 0) return null;
    var parts = base.slice("circos__".length).split("__");
    if (parts.length < 3) return null;
    return { metric: parts[0], band: parts[1], contrast: parts.slice(2).join("__") };
  }

  function orderBands(bands) {
    return bands.slice().sort(function (a, b) {
      var ia = BAND_ORDER.indexOf(formatName(a)); if (ia < 0) ia = 99;
      var ib = BAND_ORDER.indexOf(formatName(b)); if (ib < 0) ib = 99;
      return ia - ib || a.localeCompare(b);
    });
  }

  function renderCircosFigures(figs) {
    var byMetric = {};
    figs.forEach(function (f) {
      var p = parseCircos(f.filename);
      if (!p) return;
      byMetric[p.metric] = byMetric[p.metric] || {};
      (byMetric[p.metric][p.band] = byMetric[p.metric][p.band] || []).push({ fig: f, contrast: p.contrast });
    });
    var metrics = Object.keys(byMetric);
    if (!metrics.length) return renderFigureRows(figs);
    metrics.sort(function (a, b) {
      var ia = METRIC_ORDER.indexOf(a); if (ia < 0) ia = 99;
      var ib = METRIC_ORDER.indexOf(b); if (ib < 0) ib = 99;
      return ia - ib || a.localeCompare(b);
    });

    var html = '<div class="metric-tabs" role="tablist">';
    metrics.forEach(function (m, i) {
      html += '<button class="metric-tab' + (i === 0 ? " active" : "") + '" data-mtab="' +
        escapeHtml(m) + '">' + escapeHtml(metricLabel(m)) + "</button>";
    });
    html += "</div>";

    metrics.forEach(function (m, i) {
      html += '<div class="metric-panel' + (i === 0 ? " active" : "") + '" data-mpanel="' + escapeHtml(m) + '">';
      orderBands(Object.keys(byMetric[m])).forEach(function (band) {
        html += '<div class="band-block"><h4 class="band-title">' + escapeHtml(formatName(band)) + "</h4>";
        html += '<div class="band-figs">';
        byMetric[m][band].forEach(function (it) {
          html += '<figure class="circos-thumb">' +
            '<a class="glightbox" href="' + it.fig.path + '" data-gallery="gallery">' +
            '<img src="' + it.fig.thumb + '" loading="lazy" alt="' + escapeHtml(it.fig.filename) + '"></a>' +
            '<figcaption>' + escapeHtml(circosContrastLabel(it.contrast)) + "</figcaption></figure>";
        });
        html += "</div></div>";
      });
      html += "</div>";
    });
    return html;
  }

  /* Chord diagrams get the metric-tab layout; any other figure of the module
     (e.g. the NBS component heatmap) is shown above them as rows. */
  function figurePanel(figs) {
    var circos = figs.filter(function (f) { return f.filename.indexOf("circos__") === 0; });
    if (!circos.length) return null;
    var rest = figs.filter(function (f) { return f.filename.indexOf("circos__") !== 0; });
    return (rest.length ? renderFigureRows(rest) : "") + renderCircosFigures(circos);
  }

  app.hooks.provenanceHtml = provenanceHtml;
  app.hooks.inputRunHtml = runProvenanceHtml;
  app.hooks.figureFacet = _figureFacet;
  app.hooks.figurePanel = figurePanel;
})();
