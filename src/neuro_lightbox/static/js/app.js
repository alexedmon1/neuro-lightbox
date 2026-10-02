/* neuro-lightbox SPA — vanilla JS, fully offline (no fetch needed) */
(function () {
  "use strict";

  const M = window.MANIFEST;
  // The profile's vocabulary — the words, orders and labels this gallery's data
  // is shown in (data/profile.json) — and the page behaviour its script adds
  // (HOOKS, filled through window.LightboxApp once this file has run).
  const V = (window.PROFILE && window.PROFILE.vocabulary) || {};
  const HOOKS = {};
  const PAGE_SIZE = 50;

  /* ── Acronym map for display formatting ── */
  const ACRONYMS = V.acronyms || {};

  /* ── Group label fallbacks for readable contrast display (the study's own
     `groups:` labels come first) ── */
  const GROUP_LABELS = V.group_labels || {};

  /* ── The inputs side (subjects / QC of what the analyses ran on), if any ── */
  const INPUTS = V.inputs || {};
  const INPUT_DATA = (INPUTS.key && M[INPUTS.key]) || {};

  /* ── How the profile's table columns are grouped, labelled and formatted ── */
  const TABLE = V.table || {};

  /* ── State ── */
  let currentSource = null;
  let lightbox = null;

  /* ── Init ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("gallery-title").textContent = M.title || "Gallery";
    document.title = M.title || V.default_title || "Gallery";
    buildSidebar();
    initThemeToggle();
    initSearch();
    initKeyboard();
    window.addEventListener("hashchange", route);
    route();
  });

  /* ── Router ── */
  function route() {
    var hash = location.hash.slice(1) || "/overview";
    var parts = hash.split("/").filter(Boolean);
    highlightNav(hash);

    if (parts[0] === "overview" || parts.length === 0) {
      renderOverview();
    } else if (parts[0] === "search") {
      renderSearch(decodeURIComponent(parts.slice(1).join("/")));
    } else if (INPUTS.route && parts[0] === INPUTS.route) {
      if (parts[1] === "qc") renderQC(parts[2]);
      else if (parts[1] === "subjects") renderSubjects(parts[2]);
      else renderInputsHome();
    } else if (parts[0] === "domain") {
      // #/domain/<source>/<paradigm>/<domain>
      renderDomain(decodeURIComponent(parts[1] || ""),
        decodeURIComponent(parts[2] || ""), decodeURIComponent(parts[3] || ""));
    } else if (parts[0] === "analytics") {
      // #/analytics/<source>/<paradigm>/<analysis>  (single-analysis deep link)
      var src = decodeURIComponent(parts[1] || "");
      if (parts.length >= 4) {
        renderAnalysis(parts[2], parts[3], src);
      } else if (parts.length === 3) {
        renderStudyDesign(parts[2], src);
      } else {
        renderSourceHome(src);
      }
    } else {
      renderOverview();
    }
  }

  /* Sources that actually carry analytics data. The profile's input pipelines
     are a separate namespace from the analytics source(s) (paths.results) and
     have zero figures/tables here, so they're excluded — derived from the data,
     no hardcoded source names. */
  function analyticsSources() {
    return M.sources.filter(function (src) {
      for (var para of Object.keys(M.paradigms)) {
        var analyses = M.paradigms[para];
        for (var aname of Object.keys(analyses)) {
          var ad = analyses[aname];
          if ((ad.figures[src] && ad.figures[src].length) ||
              (ad.tables[src] && ad.tables[src].length)) {
            return true;
          }
        }
      }
      return false;
    });
  }

  /* Analytics breadcrumb — include the source only when more than one exists,
     so a single results source (e.g. "results_treatment") isn't redundant noise. */
  function analyticsCrumbs(src, tail) {
    var base = analyticsSources().length > 1 ? ["Analytics", src] : ["Analytics"];
    return base.concat(tail || []);
  }

  /* ── Domain grouping ──────────────────────────────────────────────────────
     Each analysis carries meta.domain (where it is listed) and meta.supplements
     (the primary it runs *after*, consuming its output). The gallery shows one
     page per (paradigm × domain); a secondary nests right after its primary as a
     sub-tab. Domain order is fixed; unknown domains fall to the end. */
  var DOMAINS = V.domains || {};
  var DOMAIN_ORDER = DOMAINS.order || [];
  // A domain the profile promotes out of its paradigm's domain list into its own
  // study-design heading (e.g. a different acquisition level), and one shown as
  // a sub-group at the end of that heading's section.
  var SECTION_DOMAIN = DOMAINS.section || null;
  var SUBSECTION_DOMAIN = DOMAINS.subsection || null;

  function analysisHasData(ad, src) {
    return (ad.figures[src] && ad.figures[src].length > 0) ||
           (ad.tables[src] && ad.tables[src].length > 0) || !!ad.summary;
  }
  function analysisDomain(ad) {
    return (ad && ad.meta && ad.meta.domain) || "Other";
  }

  // Ordered domain names with ≥1 analysis that has data for src, within paradigm.
  function domainsForParadigm(paradigm, src) {
    var analyses = M.paradigms[paradigm] || {};
    var present = {};
    for (var a of Object.keys(analyses)) {
      if (analysisHasData(analyses[a], src)) present[analysisDomain(analyses[a])] = true;
    }
    return DOMAIN_ORDER.filter(function (d) { return present[d]; })
      .concat(Object.keys(present).filter(function (d) { return DOMAIN_ORDER.indexOf(d) < 0; }));
  }

  // Analyses in a (paradigm, domain) that have data for src — primaries first,
  // each secondary placed immediately after the primary it supplements.
  // The profile's intra-domain analysis order: the standard analysis leads, then
  // the other primary measures. Names are matched by keyword; unknown analyses
  // keep their existing (manifest) order after the ranked ones.
  var ANALYSIS_ORDER = V.analysis_order || [];
  function analysisRank(name) {
    var n = String(name).toLowerCase();
    for (var i = 0; i < ANALYSIS_ORDER.length; i++) {
      if (n.indexOf(ANALYSIS_ORDER[i]) >= 0) return i;
    }
    return ANALYSIS_ORDER.length;
  }

  function domainAnalyses(paradigm, domain, src) {
    var analyses = M.paradigms[paradigm] || {};
    var names = Object.keys(analyses).filter(function (a) {
      return analysisHasData(analyses[a], src) && analysisDomain(analyses[a]) === domain;
    });
    var suppOf = function (a) { return analyses[a].meta && analyses[a].meta.supplements; };
    var prim = names.filter(function (a) { return !suppOf(a); })
      .sort(function (a, b) { return analysisRank(a) - analysisRank(b); });
    var supp = names.filter(function (a) { return suppOf(a); });
    var out = [];
    prim.forEach(function (p) {
      out.push({ name: p, supp: false });
      supp.filter(function (s) { return suppOf(s) === p; })
        .forEach(function (s) { out.push({ name: s, supp: true }); });
    });
    // Orphan secondaries (primary missing / no data) go last.
    supp.filter(function (s) { return prim.indexOf(suppOf(s)) < 0; })
      .forEach(function (s) { out.push({ name: s, supp: true }); });
    return out;
  }

  function domainRoute(src, paradigm, domain) {
    return "/domain/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm) +
      "/" + encodeURIComponent(domain);
  }

  /* ── Paradigm display metadata (optional, from M.paradigm_meta) ──
     Lets a study nest its paradigms under a shared group header and relabel them
     (e.g. resting/vertex → group "Resting" with "ROI-based"/"Vertex-based"). When
     a paradigm has no entry, the nav stays flat and labels fall back to formatName. */
  function paradigmMeta(p) { return (M.paradigm_meta && M.paradigm_meta[p]) || null; }
  function paradigmGroup(p) { var m = paradigmMeta(p); return (m && m.group) || null; }
  function paradigmLabel(p) { var m = paradigmMeta(p); return (m && m.label) || formatName(p); }

  // Display name for an analysis (module meta.display_name overrides the
  // formatted module name), e.g. electrode_comparison → "PSD".
  function analysisLabel(paradigm, name) {
    var a = M.paradigms[paradigm] && M.paradigms[paradigm][name];
    return (a && a.meta && a.meta.display_name) || formatName(name);
  }

  // The study-design label for an analysis header/breadcrumb. The promoted
  // section's analyses read their own design label, not the label of the
  // paradigm they sit in.
  function designLabel(paradigm, analysisName) {
    var ad = M.paradigms[paradigm] && M.paradigms[paradigm][analysisName];
    var d = ad && analysisDomain(ad);
    if (d === SUBSECTION_DOMAIN) return SUBSECTION_DOMAIN;
    if (d === SECTION_DOMAIN) return SECTION_DOMAIN;
    return paradigmLabel(paradigm);
  }

  /* ── Sidebar ── */
  function buildSidebar() {
    var nav = document.getElementById("sidebar-nav");
    var html = "";

    // Overview
    html += '<a class="nav-item" href="#/overview" data-route="/overview">Overview</a>';

    // Inputs — section title (matching Analytics), nested per source
    var locSources = Object.keys(INPUT_DATA);
    if (locSources.length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">' + INPUTS.title + '</div>';
      for (var source of locSources) {
        if (locSources.length > 1) {
          html += '<div class="nav-paradigm">' + escapeHtml(source) + '</div>';
        }
        html += navItem("/" + INPUTS.route + "/subjects/" + source, "Subjects");
        html += navItem("/" + INPUTS.route + "/qc/" + source, "QC");
      }
    }

    // Analytics — grouped by source, then study design (paradigm), then analysis.
    // Only sources with analytics data appear (input-only sources skip).
    var aSources = analyticsSources();
    if (aSources.length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">Analytics</div>';

      for (var si = 0; si < aSources.length; si++) {
        var src = aSources[si];
        // Only show source header when there's more than one analytics source
        if (aSources.length > 1) {
          html += '<div class="nav-paradigm">' + escapeHtml(src) + '</div>';
        }
        // Group paradigms that have data for this source. A paradigm may declare
        // a display group (M.paradigm_meta) so siblings nest under one header
        // (e.g. "Resting" › "ROI-based"/"Vertex-based"); otherwise the nav is flat.
        var lastGroup = null;
        // The promoted section is deferred to the END of its group so it sits after
        // the group's own study designs. Its analyses from EVERY paradigm are merged
        // under ONE heading, with the sub-group domain's analyses at its end.
        var pendingSection = "";     // section nav items (no heading)
        var pendingSub = "";         // sub-group items (own sub-heading)
        function flushSection() {
          if (pendingSection || pendingSub) {
            html += '<div class="nav-study-design">' + escapeHtml(SECTION_DOMAIN) + '</div>' + pendingSection;
            if (pendingSub) {
              html += '<div class="nav-subgroup">' + escapeHtml(SUBSECTION_DOMAIN) + '</div>' +
                '<div class="nav-subgroup-items">' + pendingSub + '</div>';
            }
            pendingSection = ""; pendingSub = "";
          }
        }
        for (var paradigm of Object.keys(M.paradigms)) {
          var analyses = M.paradigms[paradigm];
          var hasData = false;
          for (var aname of Object.keys(analyses)) {
            var adata = analyses[aname];
            if ((adata.figures[src] && adata.figures[src].length > 0) ||
                (adata.tables[src] && adata.tables[src].length > 0)) {
              hasData = true;
              break;
            }
          }
          if (!hasData) continue;

          var grp = paradigmGroup(paradigm);
          if (grp !== lastGroup) {
            flushSection();  // close out the previous group's promoted section first
            if (grp) html += '<div class="nav-paradigm-group">' + escapeHtml(grp) + '</div>';
          }
          lastGroup = grp;  // null for ungrouped → next grouped paradigm re-emits

          html += '<div class="nav-study-design">' + paradigmLabel(paradigm) + '</div>';
          // Group analyses by domain (one nav item per domain → domain page).
          // The promoted domains get their own study-design heading (deferred to the
          // group end), so they are not listed as domains under this paradigm's label.
          var analyticBase = "/analytics/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm) + "/";
          var pdomains = domainsForParadigm(paradigm, src);
          pdomains.forEach(function (domain) {
            if (domain === SECTION_DOMAIN || domain === SUBSECTION_DOMAIN) return;
            html += navItem(domainRoute(src, paradigm, domain), domain);
          });
          // The promoted domains' analyses are deferred and merged across
          // paradigms; the headings are emitted by flushSection at the group's end.
          if (pdomains.indexOf(SECTION_DOMAIN) >= 0) {
            domainAnalyses(paradigm, SECTION_DOMAIN, src).forEach(function (o) {
              pendingSection += navItem(analyticBase + encodeURIComponent(o.name), analysisLabel(paradigm, o.name));
            });
          }
          if (pdomains.indexOf(SUBSECTION_DOMAIN) >= 0) {
            domainAnalyses(paradigm, SUBSECTION_DOMAIN, src).forEach(function (o) {
              pendingSub += navItem(analyticBase + encodeURIComponent(o.name), analysisLabel(paradigm, o.name));
            });
          }
        }
        flushSection();  // emit the final group's promoted section
      }
    }

    nav.innerHTML = html;
  }

  function navItem(route, label) {
    return '<a class="nav-item" href="#' + route + '" data-route="' + route + '">' + label + '</a>';
  }

  function highlightNav(hash) {
    document.querySelectorAll(".nav-item").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-route") === hash.replace("#", ""));
    });
  }

  /* ── Overview ── */
  function renderOverview() {
    setBreadcrumb(["Overview"]);
    clearSourceSelector();
    var s = M.stats;
    var html = '<h2 class="section-header">Overview</h2>';
    html += '<div class="overview-grid">';
    html += statCard(s.total_figures, "Figures");
    html += statCard(s.total_tables, "Tables");
    html += statCard(s.total_summaries, "Summaries");
    html += statCard(s.paradigm_count, "Study Designs");
    var aSources = analyticsSources();
    html += statCard(aSources.length, aSources.length === 1 ? "Source" : "Sources");
    html += "</div>";

    // List by source → paradigm → analysis (only analytics sources)
    for (var si = 0; si < aSources.length; si++) {
      var src = aSources[si];
      var srcEnc = encodeURIComponent(src);
      if (aSources.length > 1) {
        html += '<h2 class="section-header">' + escapeHtml(src) + '</h2>';
      }
      for (var paradigm of Object.keys(M.paradigms)) {
        var domains = domainsForParadigm(paradigm, src);
        if (domains.length === 0) continue;
        html += '<h3 style="margin:12px 0 6px">' + paradigmLabel(paradigm) + '</h3>';
        html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
      }
    }

    setContent(html);
  }

  // <li> rows for each domain in a paradigm (link → domain page, with counts).
  function domainListItems(paradigm, domains, src) {
    var rows = "";
    domains.forEach(function (domain) {
      var das = domainAnalyses(paradigm, domain, src);
      var nf = 0, nt = 0;
      das.forEach(function (o) {
        var ad = M.paradigms[paradigm][o.name];
        nf += (ad.figures[src] || []).length;
        nt += (ad.tables[src] || []).length;
      });
      rows += '<li><a href="#' + domainRoute(src, paradigm, domain) + '">' + escapeHtml(domain) +
        '</a> — ' + das.length + ' analys' + (das.length === 1 ? "is" : "es") +
        ', ' + nf + ' figures, ' + nt + ' tables</li>';
    });
    return rows;
  }

  function statCard(value, label) {
    return '<div class="stat-card"><div class="stat-value">' + value + '</div><div class="stat-label">' + label + '</div></div>';
  }

  /* ── Source Home (list paradigms for a source) ── */
  function renderSourceHome(src) {
    setBreadcrumb(analyticsCrumbs(src));
    clearSourceSelector();
    var srcEnc = encodeURIComponent(src);
    var html = '<h2 class="section-header">' + escapeHtml(src) + '</h2>';

    for (var paradigm of Object.keys(M.paradigms)) {
      var domains = domainsForParadigm(paradigm, src);
      if (domains.length === 0) continue;
      html += '<h3 style="margin:12px 0 6px">' + paradigmLabel(paradigm) + '</h3>';
      html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
    }
    setContent(html);
  }

  /* ── Study Design page (list analyses for a paradigm+source) ── */
  function renderStudyDesign(paradigm, src) {
    var analyses = M.paradigms[paradigm];
    if (!analyses) {
      setContent('<div class="empty-state"><p>Study design not found</p></div>');
      return;
    }
    setBreadcrumb(analyticsCrumbs(src, [paradigmLabel(paradigm)]));
    clearSourceSelector();

    var domains = domainsForParadigm(paradigm, src);
    var html = '<h2 class="section-header">' + paradigmLabel(paradigm) + '</h2>';
    html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
    setContent(html);
  }

  /* ── Analysis Page ── */
  function renderAnalysis(paradigm, analysis, src) {
    var data = (M.paradigms[paradigm] || {})[analysis];
    if (!data) {
      setContent('<div class="empty-state"><p>Analysis not found</p></div>');
      return;
    }

    setBreadcrumb(analyticsCrumbs(src, [designLabel(paradigm, analysis), analysisLabel(paradigm, analysis)]));

    // Source selector (if multiple sources have this analysis)
    var sources = M.sources.filter(function (s) {
      return (data.figures[s] && data.figures[s].length > 0) ||
             (data.tables[s] && data.tables[s].length > 0);
    });

    if (sources.length > 1) {
      renderSourceSelector(sources, src, function (newSrc) {
        location.hash = "#/analytics/" + encodeURIComponent(newSrc) + "/" +
          encodeURIComponent(paradigm) + "/" + encodeURIComponent(analysis);
      });
    } else {
      clearSourceSelector();
    }

    renderAnalysisContent(paradigm, analysis, data, src, sources);
  }

  /* ── What produced these tables ──
     The analysis's provenance.json, as the profile shows it: nothing when the
     profile has no strip for it, or when an older results tree has no record
     (rather than a guess). */
  function provenanceHtml(prov) {
    if (!prov || !HOOKS.provenanceHtml) return "";
    return HOOKS.provenanceHtml(prov);
  }

  function renderAnalysisContent(paradigm, analysis, data, source, allSources) {
    var inner = buildAnalysisInner(paradigm, analysis, data, source, allSources, "a");
    var html = '<h2 class="section-header">' + designLabel(paradigm, analysis) + ' — ' + analysisLabel(paradigm, analysis) + '</h2>' + inner.html;
    setContent(html);
    initLightbox();
    bindTableToggles(inner.tables);
    bindTabs();
    bindMetricTabs();
    bindFigureGroups();
  }

  // Build the Summary/Figures/Tables tab UI for ONE analysis and return
  // {html, tables} — no <h2>, no setContent/bind — so it can be dropped into a
  // standalone analysis page OR a domain-page sub-panel (pill). `idPrefix` keeps
  // table element ids unique when several analyses share one page.
  function buildAnalysisInner(paradigm, analysis, data, source, allSources, idPrefix) {
    idPrefix = idPrefix || "a";
    var sourcesWithFigs = allSources.filter(function (s) { return data.figures[s] && data.figures[s].length > 0; });
    var figs = (data.figures[source] || []);
    var figCount = figs.length;
    var figPanel = "";
    if (sourcesWithFigs.length > 1 && source === "__compare__") {
      figPanel = renderComparisonGrid(data, sourcesWithFigs);
      figCount = sourcesWithFigs.reduce(function (n, s) { return n + data.figures[s].length; }, 0);
    } else if (figs.length > 0) {
      // A profile may lay out a set of its own figures (e.g. tabbed small
      // multiples); larger sets are split into collapsible groups by an adaptive
      // axis; small sets get full-width titled rows.
      var special = HOOKS.figurePanel ? HOOKS.figurePanel(figs) : null;
      if (special) {
        figPanel = special;
      } else {
        // Two-level layouts, tried in the profile's order (e.g. metric-first,
        // then measure-first → figure type). Fall back to single-axis groups,
        // then flat rows.
        var vocab = _contrastVocab();
        var nested = null;
        if (figs.length > 8) {
          for (var ni = 0; ni < NESTED_LAYOUTS.length && !nested; ni++) {
            nested = chooseNestedGrouping(figs, vocab, NESTED_LAYOUTS[ni]);
          }
        }
        if (nested) {
          figPanel = renderNestedMetricFigures(nested);
        } else {
          var groups = figs.length > 8 ? chooseFigureGrouping(figs, vocab) : null;
          figPanel = groups ? renderGroupedFigures(groups) : renderFigureRows(figs);
        }
      }
    }

    var tableSource = data.tables[source] ? source : Object.keys(data.tables)[0];
    var tables = data.tables[tableSource] || [];
    var tablePanel = "";
    if (tables.length > 0) {
      tablePanel = '<div class="tables-section">';
      for (var ti = 0; ti < tables.length; ti++) {
        var tbl = tables[ti];
        var id = idPrefix + "-tbl-" + ti + "-" + tbl.filename.replace(/[^a-z0-9]/gi, "_");
        var displayName = formatTableFilename(tbl.filename);
        tablePanel += '<button class="table-toggle" data-table-idx="' + ti + '" data-table-id="' + id + '">';
        tablePanel += '<span class="arrow">&#9654;</span> ' + displayName;
        tablePanel += "</button>";
        tablePanel += '<div id="' + id + '" class="table-container" style="display:none"></div>';
      }
      tablePanel += "</div>";
    }

    // Concise 'significant results by contrast' digest (generated from tables).
    var summaryPanel = data.summary ? '<div class="summary-content">' + data.summary + '</div>' : "";

    // "About this analysis" — what the test is, what it looks at, how to read it
    // (from the analysis metadata; generic to the analysis type).
    var aboutPanel = (data.meta && data.meta.about)
      ? '<div class="analysis-about"><span class="about-label">About this analysis</span> '
        + escapeHtml(data.meta.about) + '</div>' : "";

    // Natural reading order for viewers: summary, then figures, then tables.
    var tabs = [];
    if (summaryPanel) tabs.push({ id: "summary", label: "Summary", count: null, html: summaryPanel });
    if (figPanel) tabs.push({ id: "figures", label: "Figures", count: figCount, html: figPanel });
    if (tablePanel) tabs.push({ id: "tables", label: "Tables", count: tables.length, html: tablePanel });

    // The profile's glossaries (e.g. metric definitions), on the analyses they
    // apply to.
    var glossaryPanel = glossaryHtml(analysis);

    var html = aboutPanel + provenanceHtml(data.provenance) + glossaryPanel;
    if (tabs.length === 0) {
      html += '<div class="empty-state"><p>No figures, tables, or summary for this analysis.</p></div>';
    } else {
      html += '<div class="tab-bar" role="tablist">';
      tabs.forEach(function (t, i) {
        var badge = t.count != null ? ' <span class="tab-count">' + t.count + "</span>" : "";
        html += '<button class="tab-btn' + (i === 0 ? " active" : "") + '" data-tab="' + t.id + '" role="tab">' +
          t.label + badge + "</button>";
      });
      html += "</div>";
      tabs.forEach(function (t, i) {
        html += '<div class="tab-panel' + (i === 0 ? " active" : "") + '" data-panel="' + t.id + '">' + t.html + "</div>";
      });
    }
    return { html: html, tables: tables };
  }

  /* ── Domain Page (one page per paradigm × domain; secondaries nested) ──
     A domain with a single analysis renders that analysis directly; with several
     it exposes a pill bar (one pill per analysis, secondaries flagged), and each
     pill's Summary/Figures/Tables content is filled in lazily on first view. */
  function renderDomain(src, paradigm, domain) {
    var ordered = domainAnalyses(paradigm, domain, src);
    if (!ordered.length) {
      setContent('<div class="empty-state"><p>Nothing in this domain.</p></div>');
      return;
    }
    // The promoted section is its own study design, so it isn't sub-labelled
    // with the paradigm it sits in; show its group (e.g. "Resting") instead.
    var isSection = (domain === SECTION_DOMAIN);
    var domainSub = isSection ? (paradigmGroup(paradigm) || "") : paradigmLabel(paradigm);
    setBreadcrumb(analyticsCrumbs(src, isSection ? [domain] : [paradigmLabel(paradigm), domain]));
    // Source toggle (e.g. two reconstructions) when more than one analytics
    // source has data in this domain — the same control as the analysis page.
    var domainSources = M.sources.filter(function (s) {
      return ordered.some(function (o) { return analysisHasData(M.paradigms[paradigm][o.name], s); });
    });
    if (domainSources.length > 1) {
      renderSourceSelector(domainSources, src, function (newSrc) {
        location.hash = "#/domain/" + encodeURIComponent(newSrc) + "/" +
          encodeURIComponent(paradigm) + "/" + encodeURIComponent(domain);
      });
    } else {
      clearSourceSelector();
    }

    var html = '<h2 class="section-header">' + escapeHtml(domain) +
      (domainSub ? ' <span class="domain-sub">' + escapeHtml(domainSub) + '</span>' : "") + '</h2>';
    if (ordered.length > 1) {
      html += '<div class="pill-bar" role="tablist">';
      ordered.forEach(function (o, i) {
        var supTip = o.supp ? ' title="Runs after ' +
          escapeHtml(M.paradigms[paradigm][o.name].meta.supplements) + '"' : "";
        var supTag = o.supp ? ' <span class="pill-supp">supplemental</span>' : "";
        html += '<button class="pill' + (i === 0 ? " active" : "") + '" data-pill="' + i + '"' +
          supTip + '>' + analysisLabel(paradigm, o.name) + supTag + "</button>";
      });
      html += "</div>";
    }
    ordered.forEach(function (o, i) {
      html += '<div class="pill-panel' + (i === 0 ? " active" : "") + '" data-pillpanel="' + i + '"></div>';
    });
    setContent(html);

    var rendered = {};
    function fill(i) {
      if (rendered[i]) return;
      rendered[i] = true;
      var o = ordered[i];
      var data = M.paradigms[paradigm][o.name];
      var allSources = M.sources.filter(function (s) {
        return (data.figures[s] && data.figures[s].length > 0) ||
               (data.tables[s] && data.tables[s].length > 0);
      });
      var asrc = analysisHasData(data, src) ? src : (allSources[0] || src);
      var cont = document.querySelector('[data-pillpanel="' + i + '"]');
      var inner = buildAnalysisInner(paradigm, o.name, data, asrc, allSources, "p" + i);
      var desc = (data.meta && data.meta.description)
        ? ' <span class="analysis-desc">' + escapeHtml(data.meta.description) + '</span>' : "";
      cont.innerHTML = (ordered.length > 1
        ? '<h3 class="analysis-sub-header">' + analysisLabel(paradigm, o.name) + desc + '</h3>' : "") + inner.html;
      initLightbox();
      bindTableToggles(inner.tables, cont);
      bindTabs(cont);
      bindMetricTabs(cont);
      bindFigureGroups(cont);
    }
    fill(0);

    document.querySelectorAll(".pill").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var i = parseInt(btn.getAttribute("data-pill"), 10);
        document.querySelectorAll(".pill").forEach(function (b) { b.classList.toggle("active", b === btn); });
        document.querySelectorAll(".pill-panel").forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-pillpanel") === String(i));
        });
        fill(i);
      });
    });
  }

  function bindTabs(root) {
    root = root || document;
    var btns = root.querySelectorAll(".tab-btn");
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-tab");
        root.querySelectorAll(".tab-btn").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        root.querySelectorAll(".tab-panel").forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-panel") === id);
        });
      });
    });
  }

  /* ── Inputs pages (subjects / QC) ── */
  /* Treatment-group helpers (shared by the inputs pages) */
  // Group ids -> readable labels + listing order come from the study YAML
  // (`groups:` / `group_order:`) via the manifest; unknown ids fall back to
  // underscore-to-space formatting in alphabetical order.
  var TX_GROUP_ORDER = (M && M.group_order) || [];
  var TX_GROUP_LABELS = (M && M.group_labels) || {};
  function formatGroup(g) {
    if (!g) return "Unknown";
    return TX_GROUP_LABELS[g] || g.replace(/_/g, " ");
  }
  function groupSubjects(loc) {
    var meta = loc.subject_meta || {};
    var buckets = {};
    for (var key of Object.keys(loc.subjects || {})) {
      var g = (meta[key] && meta[key].group) || "Unknown";
      (buckets[g] = buckets[g] || []).push(key);
    }
    var order = TX_GROUP_ORDER.filter(function (g) { return buckets[g]; })
      .concat(Object.keys(buckets).filter(function (g) { return TX_GROUP_ORDER.indexOf(g) < 0; }));
    return order.map(function (g) { return { group: g, subjects: buckets[g].sort() }; });
  }
  function subjectIsOutlier(loc, key) {
    var m = loc.subject_meta && loc.subject_meta[key];
    return m && m.outliers && m.outliers.length ? m.outliers : null;
  }

  /* What built an input pipeline, as the profile shows it. */
  function inputRunHtml(run) {
    return HOOKS.inputRunHtml ? HOOKS.inputRunHtml(run) : "";
  }

  function renderInputsHome() {
    setBreadcrumb([INPUTS.title]);
    clearSourceSelector();
    var html = '<h2 class="section-header">' + INPUTS.title + '</h2>';
    html += '<p class="page-lead">' + INPUTS.lead + '</p>';
    html += '<div class="loc-cards">';
    for (var source of Object.keys(INPUT_DATA)) {
      var loc = INPUT_DATA[source];
      var nSub = Object.keys(loc.subjects || {}).length;
      var nOut = loc.n_outliers || 0;
      var enc = encodeURIComponent(source);
      html += '<div class="loc-card">';
      html += '<h3>' + escapeHtml(source) + '</h3>';
      html += '<div class="loc-stats"><span>' + nSub + ' subjects</span>';
      html += '<span class="' + (nOut ? "loc-flag" : "") + '">' + nOut + ' outlier' + (nOut === 1 ? "" : "s") + '</span></div>';
      html += '<div class="loc-groups">';
      for (var gb of groupSubjects(loc)) {
        html += '<span class="loc-group-chip">' + escapeHtml(formatGroup(gb.group)) + ' <b>' + gb.subjects.length + '</b></span>';
      }
      html += '</div>';
      html += inputRunHtml(loc.run);
      html += '<div class="loc-links">';
      html += '<a class="btn-link" href="#/' + INPUTS.route + '/subjects/' + enc + '">Browse subjects</a>';
      html += '<a class="btn-link" href="#/' + INPUTS.route + '/qc/' + enc + '">QC dashboard</a>';
      html += '</div></div>';
    }
    html += '</div>';
    setContent(html);
  }

  function renderQC(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = INPUT_DATA[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb([INPUTS.title, source, "QC"]);
    clearSourceSelector();

    var nSub = Object.keys(loc.subjects || {}).length;
    var nOut = loc.n_outliers || 0;
    var html = '<h2 class="section-header">QC — ' + escapeHtml(source) + '</h2>';
    html += '<p class="qc-lead">' + nSub + ' subjects &middot; <span class="' + (nOut ? "loc-flag" : "") + '">' +
      nOut + ' flagged as outlier' + (nOut === 1 ? "" : "s") + '</span>' +
      (INPUTS.outlier_rule ? ' (' + INPUTS.outlier_rule + ')' : '') + '.</p>';

    var figsPanel = (loc.qc_figures && loc.qc_figures.length) ? renderFigureRows(loc.qc_figures) : "";
    var metricsPanel = (loc.qc_metrics && loc.qc_metrics.length) ? renderQCMetricsTable(loc.qc_metrics, loc.subject_meta) : "";
    var reportPanel = loc.qc_report ? '<iframe class="qc-iframe" src="' + loc.qc_report + '"></iframe>' : "";

    var tabs = [];
    if (figsPanel) tabs.push({ id: "figures", label: "Figures", html: figsPanel });
    if (metricsPanel) tabs.push({ id: "metrics", label: "Metrics", html: metricsPanel });
    if (reportPanel) tabs.push({ id: "report", label: "Report", html: reportPanel });

    if (tabs.length === 0) {
      html += '<div class="empty-state"><p>No QC data for this source.</p></div>';
    } else {
      html += '<div class="tab-bar" role="tablist">';
      tabs.forEach(function (t, i) {
        html += '<button class="tab-btn' + (i === 0 ? " active" : "") + '" data-tab="' + t.id + '">' + t.label + '</button>';
      });
      html += '</div>';
      tabs.forEach(function (t, i) {
        html += '<div class="tab-panel' + (i === 0 ? " active" : "") + '" data-panel="' + t.id + '">' + t.html + '</div>';
      });
    }

    setContent(html);
    initLightbox();
    initTableSort();
    bindTabs();
  }

  function renderQCMetricsTable(metrics, subjectMeta) {
    if (!metrics || metrics.length === 0) return "";
    subjectMeta = subjectMeta || {};
    var outlierIds = {};
    for (var k of Object.keys(subjectMeta)) {
      if (subjectMeta[k].outliers && subjectMeta[k].outliers.length) {
        outlierIds[k.replace(/^sub-/, "")] = subjectMeta[k].outliers;
      }
    }
    var headers = Object.keys(metrics[0]);
    var html = '<div class="table-container"><table><thead><tr>';
    for (var h of headers) {
      html += '<th>' + escapeHtml(h) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead><tbody>";
    for (var row of metrics) {
      var flagged = outlierIds[String(row.subject_id)];
      html += "<tr" + (flagged ? ' class="qc-outlier-row" title="Outlier: ' + escapeHtml(flagged.join(", ")) + '"' : "") + ">";
      for (var h of headers) {
        html += '<td>' + escapeHtml(row[h] || "") + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table></div>";
    return html;
  }

  function renderSubjects(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = INPUT_DATA[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb([INPUTS.title, source, "Subjects"]);
    clearSourceSelector();

    var subjectKeys = Object.keys(loc.subjects || {});
    if (subjectKeys.length === 0) {
      setContent('<div class="empty-state"><p>No subject figures found</p></div>');
      return;
    }

    var html = '<h2 class="section-header">Subjects — ' + escapeHtml(source) + '</h2>';
    html += '<div class="subject-browser"><div class="subject-list">';
    for (var gb of groupSubjects(loc)) {
      html += '<div class="subject-group"><div class="subject-group-label">' +
        escapeHtml(formatGroup(gb.group)) + ' <span class="cnt">' + gb.subjects.length + '</span></div>';
      html += '<div class="subject-chips">';
      for (var key of gb.subjects) {
        var sid = key.replace(/^sub-/, "");
        var out = subjectIsOutlier(loc, key);
        html += '<button class="subject-chip' + (out ? " is-outlier" : "") + '" data-sub="' + key + '"' +
          (out ? ' title="Outlier: ' + escapeHtml(out.join(", ")) + '"' : "") + '>' +
          escapeHtml(sid) + (out ? ' <span class="warn">&#9888;</span>' : "") + '</button>';
      }
      html += '</div></div>';
    }
    html += '</div><div class="subject-detail"><div id="subject-meta"></div><div id="subject-figures"></div></div></div>';

    setContent(html);

    var chips = document.querySelectorAll(".subject-chip");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.classList.toggle("active", c === chip); });
        showSubject(loc, chip.getAttribute("data-sub"));
      });
    });
    if (chips.length) {
      chips[0].classList.add("active");
      showSubject(loc, chips[0].getAttribute("data-sub"));
    }
  }

  function showSubject(loc, key) {
    var meta = (loc.subject_meta && loc.subject_meta[key]) || { group: null, outliers: [] };
    var sid = key.replace(/^sub-/, "");
    var bits = '<span class="sm-id">' + escapeHtml(sid) + '</span>';
    if (meta.group) bits += '<span class="sm-group">' + escapeHtml(formatGroup(meta.group)) + '</span>';
    if (meta.outliers && meta.outliers.length) {
      bits += '<span class="sm-out">&#9888; outlier: ' + escapeHtml(meta.outliers.join(", ")) + '</span>';
    }
    document.getElementById("subject-meta").innerHTML = '<div class="subject-meta-bar">' + bits + '</div>';
    document.getElementById("subject-figures").innerHTML = renderFigureRows(loc.subjects[key] || []);
    initLightbox();
  }

  /* ── Search ── */
  function initSearch() {
    var input = document.getElementById("search-input");
    var debounce = null;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        var q = input.value.trim();
        if (q.length >= 2) {
          location.hash = "#/search/" + encodeURIComponent(q);
        } else if (q.length === 0) {
          location.hash = "#/overview";
        }
      }, 300);
    });
  }

  function renderSearch(query) {
    setBreadcrumb(["Search", query]);
    clearSourceSelector();
    var q = query.toLowerCase();
    var results = [];

    var links = [];   // analyses / tables / subjects / QC pages matching the query
    function hit(text) { return text && String(text).toLowerCase().includes(q); }
    function stripHtml(html) { var d = document.createElement("div"); d.innerHTML = html || ""; return d.textContent || ""; }

    for (var paradigm of Object.keys(M.paradigms)) {
      var analyses = M.paradigms[paradigm];
      for (var analysis of Object.keys(analyses)) {
        var data = analyses[analysis];
        var meta = data.meta || {};
        var label = analysisLabel(paradigm, analysis);
        var analysisHit = hit(paradigm) || hit(paradigmLabel(paradigm)) || hit(analysis) ||
          hit(formatName(analysis)) || hit(label) || hit(meta.display_name) ||
          hit(meta.description) || hit(meta.domain) || hit(stripHtml(data.summary));
        var firstSrc = Object.keys(data.figures)[0] || Object.keys(data.tables)[0] || M.sources[0] || "";
        var href = "#/analytics/" + encodeURIComponent(firstSrc) + "/" +
          encodeURIComponent(paradigm) + "/" + encodeURIComponent(analysis);
        if (analysisHit) {
          links.push({ kind: "Analysis", label: label + " (" + paradigmLabel(paradigm) + ")", href: href,
                       sub: meta.description || "" });
        }
        for (var source of Object.keys(data.figures)) {
          var figs = data.figures[source];
          for (var fig of figs) {
            if (analysisHit || hit(fig.filename) || hit(formatFigureTitle(fig.filename))) {
              results.push({ type: "figure", paradigm: paradigm, analysis: analysis, source: source, item: fig });
            }
          }
        }
        for (var tsrc of Object.keys(data.tables)) {
          data.tables[tsrc].forEach(function (t) {
            if (hit(t.filename) || hit(formatTableFilename(t.filename))) {
              links.push({ kind: "Table", label: formatTableFilename(t.filename) + " — " + label,
                           href: href, sub: t.filename });
            }
          });
        }
      }
    }
    for (var locSrc of Object.keys(INPUT_DATA)) {
      var loc = INPUT_DATA[locSrc];
      var encSrc = encodeURIComponent(locSrc);
      if (hit(locSrc) || (INPUTS.search_words || []).some(function (w) { return hit(w); })) {
        links.push({ kind: INPUTS.title, label: locSrc + " — QC dashboard", href: "#/" + INPUTS.route + "/qc/" + encSrc, sub: "" });
      }
      var subjMeta = loc.subject_meta || {};
      for (var subj of Object.keys(loc.subjects || {})) {
        var sm = subjMeta[subj] || {};
        var outl = (sm.outliers || []).join(", ");
        if (hit(subj) || hit(sm.group) || hit(formatGroup(sm.group)) || (outl && hit("outlier")) || hit(outl)) {
          links.push({ kind: "Subject", label: subj + (sm.group ? " · " + formatGroup(sm.group) : ""),
                       href: "#/" + INPUTS.route + "/subjects/" + encSrc,
                       sub: outl ? "outlier: " + outl : locSrc });
        }
      }
    }

    var html = '<h2 class="section-header">Search: "' + escapeHtml(query) + '"</h2>';
    html += '<p class="search-results-header">' + links.length + ' page(s), ' + results.length + ' figure(s)</p>';

    if (links.length > 0) {
      html += '<ul class="search-links">';
      links.slice(0, 200).forEach(function (l) {
        html += '<li><a href="' + l.href + '"><span class="search-kind">' + escapeHtml(l.kind) + '</span> ' +
          escapeHtml(l.label) + '</a>' + (l.sub ? ' <span class="search-sub">' + escapeHtml(l.sub) + '</span>' : "") + '</li>';
      });
      html += '</ul>';
    }
    if (results.length > 0) {
      var figItems = results.map(function (r) { return r.item; });
      html += renderFigureGrid(figItems, PAGE_SIZE);
    }

    setContent(html);
    initLightbox();
  }

  /* ── Figure Grid ── */
  function renderFigureGrid(figs, limit) {
    if (!figs || figs.length === 0) {
      return '<div class="empty-state"><p>No figures</p></div>';
    }
    var show = Math.min(figs.length, limit);
    var html = '<div class="figure-grid">';
    for (var i = 0; i < show; i++) {
      var fig = figs[i];
      html += '<a href="' + fig.path + '" class="glightbox figure-card" data-gallery="gallery">';
      html += '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) + '" loading="lazy">';
      html += '<div class="caption">' + escapeHtml(fig.filename) + '</div>';
      html += "</a>";
    }
    html += "</div>";

    if (figs.length > limit) {
      html += '<button class="show-more-btn" onclick="window._showMore(this)" data-figs=\'' +
        JSON.stringify(figs.slice(limit)).replace(/'/g, "&#39;") +
        "'>Show " + (figs.length - limit) + " more</button>";
    }
    return html;
  }

  function formatFigureTitle(filename) {
    var name = (filename || "").replace(/\.(png|jpe?g|svg|pdf)$/i, "");
    name = name.replace(/^\d+[_-]/, "");   // strip a leading "01_"
    name = name.replace(/__+/g, " — ");    // double underscore = section separator
    name = name.replace(/_/g, " ").trim(); // single underscore = space (hyphens kept)
    // Title-case word initials, fixing known acronyms (ROI, PSD, MVPA, NBS, …).
    name = name.replace(/\S+/g, function (w) {
      var key = w.toLowerCase();
      if (ACRONYMS[key]) return ACRONYMS[key];
      return w.charAt(0).toUpperCase() + w.slice(1);
    });
    name = name.replace(/\bZscore\b/i, "Z-Score");
    // Lead with the distinguishing facet the profile recognises (e.g. its
    // category) when present, dropping the redundant "Effect Size" prefix every
    // analysis figure carries.
    var hit = HOOKS.figureFacet ? HOOKS.figureFacet(name) : null;
    if (hit) {
      var rest = name.replace(hit.re, " ").replace(/\s+/g, " ")
        .replace(/^Effect Size\s*/i, "").trim();
      return rest ? hit.facet + " — " + rest : hit.facet;
    }
    return name;
  }

  // One figure per full-width row with a title — for reading diagnostics inline
  // (vs the thumbnail grid). Full image shown; click opens the lightbox to zoom.
  /* ── Adaptive figure grouping ─────────────────────────────────────────────
     A module can emit 200+ figures; a flat wall is unreadable. We group them by
     the single axis that best organizes THAT module, chosen adaptively from the
     filenames so it works for any study without hardcoding:
       kind (figure-type prefix) → contrast → the profile's token axes in order.
     Rendered as collapsible sections so the page opens as a handful of headers. */
  var FIGURES = V.figures || {};
  // Filename tokens by name (e.g. metric, category), longest-first within each.
  var GROUP_VOCAB = FIGURES.tokens || {};
  var KIND_TOKENS = FIGURES.kind_tokens || [];  // removed to find a figure's kind
  var FIGURE_AXES = FIGURES.axes || [];          // single-axis groupings, in order
  var NESTED_LAYOUTS = FIGURES.nested || [];     // two-level layouts, in order
  var CATEGORY_ORDER = (V.categories && V.categories.order) || [];
  function _escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function _contrastVocab() {
    // Longest-first so "hd_icv_rescue" is matched before any shorter substring.
    return Object.keys((M && M.contrast_labels) || {})
      .map(function (k) { return k.toLowerCase(); })
      .sort(function (a, b) { return b.length - a.length; });
  }
  // Position of `value` in `base` only when it sits on token boundaries
  // (start/end or _ - space), so "pli" doesn't match inside "dwpli". -1 if absent.
  function _tokenHit(base, value) {
    var i = base.indexOf(value);
    while (i !== -1) {
      var b = i === 0 ? "" : base.charAt(i - 1);
      var aPos = i + value.length;
      var a = aPos >= base.length ? "" : base.charAt(aPos);
      var okB = b === "" || b === "_" || b === "-" || b === " ";
      var okA = a === "" || a === "_" || a === "-" || a === " ";
      if (okB && okA) return i;
      i = base.indexOf(value, i + 1);
    }
    return -1;
  }
  function _axisValue(base, values) {           // first (longest) value that hits
    for (var i = 0; i < values.length; i++) {
      if (_tokenHit(base, values[i]) !== -1) return values[i];
    }
    return null;
  }
  function _figBase(fig) {
    return (fig.filename || "").replace(/\.(png|jpe?g|svg|pdf)$/i, "").toLowerCase();
  }
  // Figure "kind" = the descriptive words left after removing every variable
  // token (contrast, and each of the profile's token lists), wherever they sit:
  // e.g. "region_significance_heatmap" from
  // "region_significance_heatmap_disease_effect_relative".
  var _kindVocabCache = null, _kindVocabKey = null;
  function _kindVocab(contrasts) {
    var key = contrasts.join("|");
    if (_kindVocabKey === key) return _kindVocabCache;
    var all = contrasts.slice();
    KIND_TOKENS.forEach(function (name) { all = all.concat(GROUP_VOCAB[name] || []); });
    // Longest-first so a long token is removed before a shorter one inside it.
    all = all.filter(function (v, i) { return all.indexOf(v) === i; })
             .sort(function (a, b) { return b.length - a.length; })
             .map(function (v) { return new RegExp("(^|[_\\-\\s])" + _escapeRe(v) + "(?=$|[_\\-\\s])", "g"); });
    _kindVocabKey = key; _kindVocabCache = all;
    return all;
  }
  function _figKind(base, contrasts) {
    var s = base;
    _kindVocab(contrasts).forEach(function (re) { s = s.replace(re, "$1"); });
    s = s.replace(/[_\-\s]+/g, "_").replace(/^_|_$/g, "");
    return s || base;
  }
  function _kindLabel(kind) { return formatName(kind.replace(/_+/g, " ").trim()); }
  function _categoryOrderKey(base) {
    for (var i = 0; i < CATEGORY_ORDER.length; i++) {
      if (_tokenHit(base, CATEGORY_ORDER[i].toLowerCase().replace(/ /g, "_")) !== -1) return i;
    }
    return 99;
  }
  // Choose the best grouping axis for this figure set; return ordered groups or
  // null (→ render flat). Axes are tried in priority order and the first that
  // partitions the set usefully wins.
  function chooseFigureGrouping(figs, contrasts) {
    var N = figs.length;
    function build(valueOf) {
      var map = {}, order = [];
      figs.forEach(function (f) {
        var v = valueOf(_figBase(f)) || "__other__";
        if (!map[v]) { map[v] = []; order.push(v); }
        map[v].push(f);
      });
      return { map: map, order: order };
    }
    // kind: qualifies when it yields 2–15 balanced groups (no group > 70%).
    var k = build(function (base) { return _figKind(base, contrasts); });
    if (k.order.length >= 2 && k.order.length <= 15) {
      var maxShare = Math.max.apply(null, k.order.map(function (v) { return k.map[v].length; })) / N;
      if (maxShare <= 0.70) {
        return k.order.map(function (v) { return { key: v, label: _kindLabel(v), figs: k.map[v] }; });
      }
    }
    // contrast, then the profile's axes: qualify at ≥2 values covering ≥60% of figures.
    var axes = [
      { valueOf: function (b) { return _axisValue(b, contrasts); },
        label: function (v) { return (M.contrast_labels && M.contrast_labels[v]) || formatName(v); } },
    ].concat(FIGURE_AXES.map(function (ax) {
      var values = GROUP_VOCAB[ax.tokens] || [];
      return { valueOf: function (b) { return _axisValue(b, values); },
               label: ax.label === "metric" ? metricLabel : formatName };
    }));
    for (var ai = 0; ai < axes.length; ai++) {
      var g = build(axes[ai].valueOf);
      var matched = N - (g.map.__other__ ? g.map.__other__.length : 0);
      var distinct = g.order.filter(function (v) { return v !== "__other__"; }).length;
      if (distinct >= 2 && matched >= 0.6 * N) {
        var lab = axes[ai].label;
        var groups = g.order.filter(function (v) { return v !== "__other__"; })
          .map(function (v) { return { key: v, label: lab(v), figs: g.map[v] }; });
        if (g.map.__other__) groups.push({ key: "__other__", label: "Other", figs: g.map.__other__ });
        return groups;
      }
    }
    return null;
  }
  function renderGroupedFigures(groups) {
    var html = '<div class="figure-groups">';
    html += '<div class="fig-group-controls">' +
      '<button type="button" class="fig-toggle-all" data-open="1">Expand all</button>' +
      '<button type="button" class="fig-toggle-all" data-open="0">Collapse all</button></div>';
    groups.forEach(function (g, i) {
      var open = "";  // all figure groups start collapsed (nothing shown until clicked)
      var sorted = g.figs.slice().sort(function (a, b) {
        var ba = _figBase(a), bb = _figBase(b);
        return (_categoryOrderKey(ba) - _categoryOrderKey(bb)) || ba.localeCompare(bb);
      });
      html += '<details class="fig-group"' + open + '>';
      html += '<summary class="fig-group-summary">' + escapeHtml(g.label) +
        ' <span class="fig-group-count">' + g.figs.length + '</span></summary>';
      html += renderFigureRows(sorted);
      html += '</details>';
    });
    html += "</div>";
    return html;
  }
  // Two-level layouts, each from the profile (e.g. connectivity metric → figure
  // type → category, or power measure → figure type → category): the first
  // axis's token lists, its order and its labels. Returns
  // [{metric,label,kinds:[{kind,label,figs}]}] or null when the set isn't
  // shaped that way.
  function chooseNestedGrouping(figs, contrasts, spec) {
    var vocab = [];
    (spec.tokens || []).forEach(function (name) { vocab = vocab.concat(GROUP_VOCAB[name] || []); });
    var order = spec.order || [], labels = spec.labels || {};
    function axisOf(b) { return _axisValue(b, vocab); }
    if (figs.filter(function (f) { return axisOf(_figBase(f)); }).length < 0.5 * figs.length)
      return null;                                     // not keyed on this axis
    var byM = {}, morder = [], kinds = {};
    figs.forEach(function (f) {
      var base = _figBase(f);
      var m = axisOf(base) || "__other__";
      var kind = _figKind(base, contrasts) || "figures";
      kinds[kind] = true;
      if (!byM[m]) { byM[m] = {}; morder.push(m); }
      (byM[m][kind] = byM[m][kind] || []).push(f);
    });
    var distinct = morder.filter(function (m) { return m !== "__other__"; }).length;
    if (distinct < 2 || Object.keys(kinds).length < 2) return null;
    morder.sort(function (a, b) {
      if (a === "__other__") return 1;
      if (b === "__other__") return -1;
      var ia = order.indexOf(a), ib = order.indexOf(b);
      if (ia === -1) ia = 99;
      if (ib === -1) ib = 99;
      return ia - ib || a.localeCompare(b);
    });
    function categorySort(a, b) {
      var ba = _figBase(a), bb = _figBase(b);
      return (_categoryOrderKey(ba) - _categoryOrderKey(bb)) || ba.localeCompare(bb);
    }
    return morder.map(function (m) {
      var kmap = byM[m];
      return {
        metric: m,
        label: m === "__other__" ? "Other" : (labels[m] || formatName(m)),
        kinds: Object.keys(kmap).sort().map(function (k) {
          return { kind: k, label: _kindLabel(k), figs: kmap[k].slice().sort(categorySort) };
        }),
      };
    });
  }
  function renderNestedMetricFigures(nested) {
    var html = '<div class="figure-groups">';
    html += '<div class="fig-group-controls">' +
      '<button type="button" class="fig-toggle-all" data-open="1">Expand all</button>' +
      '<button type="button" class="fig-toggle-all" data-open="0">Collapse all</button></div>';
    nested.forEach(function (mg, i) {
      var open = "";  // all figure groups start collapsed (nothing shown until clicked)
      var count = mg.kinds.reduce(function (n, k) { return n + k.figs.length; }, 0);
      html += '<details class="fig-group"' + open + '>';
      html += '<summary class="fig-group-summary">' + escapeHtml(mg.label) +
        ' <span class="fig-group-count">' + count + '</span></summary>';
      mg.kinds.forEach(function (k) {
        html += '<div class="fig-subgroup-title">' + escapeHtml(k.label) +
          ' <span class="fig-group-count">' + k.figs.length + '</span></div>';
        html += renderFigureRows(k.figs);
      });
      html += '</details>';
    });
    html += "</div>";
    return html;
  }
  function bindFigureGroups(root) {
    (root || document).querySelectorAll(".fig-toggle-all").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var open = btn.getAttribute("data-open") === "1";
        var scope = btn.closest(".figure-groups") || document;
        scope.querySelectorAll("details.fig-group").forEach(function (d) { d.open = open; });
      });
    });
  }

  function renderFigureRows(figs) {
    if (!figs || figs.length === 0) {
      return '<div class="empty-state"><p>No figures</p></div>';
    }
    var html = '<div class="figure-rows">';
    for (var fig of figs) {
      html += '<figure class="figure-row">';
      html += '<figcaption>' + escapeHtml(formatFigureTitle(fig.filename)) + '</figcaption>';
      html += '<a href="' + fig.path + '" class="glightbox" data-gallery="gallery">';
      html += '<img src="' + fig.path + '" alt="' + escapeHtml(fig.filename) + '" loading="lazy">';
      html += '</a></figure>';
    }
    html += "</div>";
    return html;
  }

  /* ── Metric labels: the profile's display forms ── */
  var METRIC_LABELS = V.metric_labels || {};

  function metricLabel(m) { return METRIC_LABELS[m] || formatName(m); }

  /* ── Glossaries: definitions the profile attaches to the analyses they
     apply to (``applies_to`` is a pattern on the analysis name). ── */
  var GLOSSARIES = V.glossaries || [];
  function glossaryHtml(analysis) {
    var html = "";
    GLOSSARIES.forEach(function (g) {
      if (!new RegExp(g.applies_to).test(analysis || "")) return;
      html += '<details class="metric-glossary">';
      html += '<summary class="metric-glossary-summary">' + g.title + '</summary>';
      html += '<dl class="metric-glossary-list">';
      (g.entries || []).forEach(function (m) {
        html += '<dt>' + escapeHtml(m.name) + '</dt>';
        html += '<dd>' + m.def +
          ' <span class="metric-cite">' + escapeHtml(m.cite) + '</span></dd>';
      });
      html += '</dl></details>';
    });
    return html;
  }

  function bindMetricTabs(root) {
    (root || document).querySelectorAll(".metric-tabs").forEach(function (bar) {
      var container = bar.parentNode;
      bar.querySelectorAll(".metric-tab").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-mtab");
          bar.querySelectorAll(".metric-tab").forEach(function (b) { b.classList.toggle("active", b === btn); });
          container.querySelectorAll(".metric-panel").forEach(function (p) {
            p.classList.toggle("active", p.getAttribute("data-mpanel") === id);
          });
        });
      });
    });
  }

  window._showMore = function (btn) {
    try {
      var extra = JSON.parse(btn.getAttribute("data-figs"));
      var grid = btn.previousElementSibling;
      for (var fig of extra) {
        var a = document.createElement("a");
        a.href = fig.path;
        a.className = "glightbox figure-card";
        a.setAttribute("data-gallery", "gallery");
        a.innerHTML = '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) +
          '" loading="lazy"><div class="caption">' + escapeHtml(fig.filename) + '</div>';
        grid.appendChild(a);
      }
      btn.remove();
      initLightbox();
    } catch (e) {
      console.error("Show more error:", e);
    }
  };

  /* ── Comparison Grid ── */
  function renderComparisonGrid(data, sources) {
    var html = '<div class="comparison-grid">';
    for (var source of sources) {
      html += '<div class="comparison-column"><h3>' + escapeHtml(source) + '</h3>';
      html += renderFigureGrid(data.figures[source] || [], PAGE_SIZE);
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  /* ── Source Selector ── */
  function renderSourceSelector(sources, current, onChange) {
    var el = document.getElementById("source-selector");
    var html = "<label>Source: <select id='source-select'>";
    for (var s of sources) {
      var sel = s === current ? " selected" : "";
      html += '<option value="' + escapeHtml(s) + '"' + sel + '>' + escapeHtml(s) + '</option>';
    }
    if (sources.length > 1) {
      html += '<option value="__compare__">Compare All</option>';
    }
    html += "</select></label>";
    el.innerHTML = html;

    document.getElementById("source-select").addEventListener("change", function (e) {
      onChange(e.target.value);
    });
  }

  function clearSourceSelector() {
    document.getElementById("source-selector").innerHTML = "";
  }

  /* ── Tables (inline from manifest — no fetch needed) ── */
  function bindTableToggles(tables, root) {
    (root || document).querySelectorAll(".table-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-table-id");
        var idx = parseInt(btn.getAttribute("data-table-idx"), 10);
        var container = document.getElementById(id);

        if (container.style.display === "none") {
          container.style.display = "block";
          btn.classList.add("expanded");
          if (!container.innerHTML.trim()) {
            renderInlineTable(tables[idx], container);
          }
        } else {
          container.style.display = "none";
          btn.classList.remove("expanded");
        }
      });
    });
  }

  function renderInlineTable(tbl, container) {
    if (!tbl || !tbl.headers || tbl.headers.length === 0) {
      container.innerHTML = "<p style='padding:10px'>Empty table</p>";
      return;
    }

    var headers = tbl.headers;
    var rows = tbl.rows;

    // Determine which columns to hide (diagnostic/model-fit columns)
    var hideCols = computeHiddenColumns(headers);

    // Find grouping columns (pass rows so we only group columns that actually have repeated values)
    var groupCols = findGroupingColumns(headers, rows);
    var visibleCount = hideCols.filter(function (h) { return !h; }).length;

    // Sort rows by grouping columns for clean visual grouping
    if (groupCols.length > 0) {
      rows = rows.slice().sort(function (a, b) {
        for (var gc of groupCols) {
          var va = (a[gc.idx] || "").toString().toLowerCase().replace(/^"|"$/g, "");
          var vb = (b[gc.idx] || "").toString().toLowerCase().replace(/^"|"$/g, "");
          if (va < vb) return -1;
          if (va > vb) return 1;
        }
        return 0;
      });
    }

    // Build table header — hide grouped columns since they appear as sub-headers
    var groupColIndices = groupCols.map(function (gc) { return gc.idx; });
    var html = '<table class="sortable"><thead><tr>';
    for (var ci = 0; ci < headers.length; ci++) {
      if (hideCols[ci] || groupColIndices.indexOf(ci) >= 0) continue;
      html += '<th>' + escapeHtml(formatColumnHeader(headers[ci])) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead>";
    // Tablesort sorts each <tbody> independently and leaves single-row bodies
    // alone, so every group header goes in its own body and each group's data
    // rows in the next one: sorting reorders rows within a group only.
    html += "<tbody>";

    var sigIdx = headers.findIndex(function (h) {
      return h.toLowerCase() === "significant";
    });

    // Count visible, non-grouped columns for colspan
    var dataColCount = 0;
    for (var ci = 0; ci < headers.length; ci++) {
      if (!hideCols[ci] && groupColIndices.indexOf(ci) < 0) dataColCount++;
    }

    // Track current group values for sub-header insertion
    var currentGroups = groupCols.map(function () { return null; });

    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];

      // Insert group sub-headers when values change
      for (var gi = 0; gi < groupCols.length; gi++) {
        var gc = groupCols[gi];
        var val = (row[gc.idx] || "").toString().replace(/^"|"$/g, "");
        if (val !== currentGroups[gi]) {
          currentGroups[gi] = val;
          // Reset child group values when parent changes
          for (var gi2 = gi + 1; gi2 < groupCols.length; gi2++) {
            currentGroups[gi2] = null;
          }
          var formattedVal = gc.formatter(val);
          var level = gi === 0 ? "group-header-primary" : gi === 1 ? "group-header-secondary" : "group-header-tertiary";
          html += '</tbody><tbody class="group-headers"><tr class="' + level + '" data-sort-method="none">' +
            '<td colspan="' + dataColCount + '">' + escapeHtml(gc.label + ": " + formattedVal) +
            '</td></tr></tbody><tbody>';
        }
      }

      var isSig = sigIdx >= 0 && row[sigIdx] && row[sigIdx].toUpperCase() === "TRUE";
      html += '<tr' + (isSig ? ' class="significant"' : '') + '>';
      for (var ci = 0; ci < row.length; ci++) {
        if (hideCols[ci] || groupColIndices.indexOf(ci) >= 0) continue;
        html += '<td>' + formatCellValue(row[ci], headers[ci]) + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    var note = "";
    if (tbl.truncated) {
      note += 'Showing ' + rows.length + ' of ' + tbl.total_rows + ' rows';
    }
    if (tbl.csv) {
      note += (note ? ' &middot; ' : '') + '<a href="' + escapeHtml(tbl.csv) + '" download>Download full CSV</a>';
    }
    if (note) {
      html += '<p class="table-note" style="padding:8px 10px;font-size:12px;color:var(--text-muted)">' + note + '</p>';
    }
    container.innerHTML = html;
    initTableSort(container);
  }

  /**
   * Find columns to use for grouping, in priority order.
   * Returns array of {idx, label, formatter} objects.
   * Supports up to 3 levels: contrast → the profile's grouping columns, in order.
   * Only includes a column if it actually creates multi-row groups
   * within the context of already-chosen parent grouping columns.
   */
  function findGroupingColumns(headers, rows) {
    var lowerHeaders = headers.map(function (h) { return h.toLowerCase().replace(/^"|"$/g, ""); });
    var groups = [];
    var usedIndices = [];
    var totalRows = rows ? rows.length : 0;

    // Helper: check if adding column at idx creates any leaf group with >1 row,
    // given the already-chosen parent grouping columns.
    function columnAddsGrouping(idx) {
      if (!rows || totalRows <= 1) return false;

      // Build composite keys from parent groups + this candidate
      var allIndices = usedIndices.concat([idx]);
      var keyCounts = {};
      for (var r = 0; r < rows.length; r++) {
        var key = allIndices.map(function (i) {
          return (rows[r][i] || "").toString().replace(/^"|"$/g, "");
        }).join("||");
        keyCounts[key] = (keyCounts[key] || 0) + 1;
      }

      // Check if at least some leaf groups have >1 row
      // (i.e., this column doesn't make every group a singleton)
      var multiRowGroups = 0;
      var totalGroups = 0;
      for (var k in keyCounts) {
        totalGroups++;
        if (keyCounts[k] > 1) multiRowGroups++;
      }

      // Also check that this column has fewer unique values than rows
      // within the parent context (it actually groups something)
      var uniqueVals = {};
      for (var r = 0; r < rows.length; r++) {
        var v = (rows[r][idx] || "").toString().replace(/^"|"$/g, "");
        uniqueVals[v] = true;
      }
      var uniqueCount = Object.keys(uniqueVals).length;
      if (uniqueCount >= totalRows) return false;

      // If adding this column makes ALL groups singletons, it's not useful as a grouping column.
      // Keep the column as a regular data column instead.
      return totalGroups < totalRows;
    }

    // Primary: the first of the profile's primary columns present (e.g. the
    // contrast, or a key column).
    var primary = TABLE.primary_group || [];
    var contrastIdx = -1, primarySpec = null;
    for (var pi = 0; pi < primary.length && contrastIdx < 0; pi++) {
      contrastIdx = lowerHeaders.indexOf(primary[pi].column);
      primarySpec = primary[pi];
    }
    if (contrastIdx >= 0 && columnAddsGrouping(contrastIdx)) {
      groups.push({ idx: contrastIdx, label: primarySpec.label, formatter: cellFormatter(primarySpec.format) });
      usedIndices.push(contrastIdx);
    }

    // Ordered list of all possible secondary/tertiary groupings
    var candidates = (TABLE.group_candidates || []).map(function (c) {
      return { names: c.columns, label: c.label, formatter: cellFormatter(c.format) };
    });

    // Add up to 2 more grouping levels from candidates
    for (var cand of candidates) {
      if (groups.length >= 3) break;
      for (var name of cand.names) {
        var idx = lowerHeaders.indexOf(name);
        if (idx >= 0 && usedIndices.indexOf(idx) < 0 && columnAddsGrouping(idx)) {
          groups.push({ idx: idx, label: cand.label, formatter: cand.formatter });
          usedIndices.push(idx);
          break;
        }
      }
    }

    return groups;
  }

  /**
   * Determine which columns to hide for cleaner presentation.
   * Returns an array of booleans (true = hidden).
   */
  function computeHiddenColumns(headers) {
    var lowerHeaders = headers.map(function (h) { return h.toLowerCase().replace(/"/g, ""); });
    var hide = new Array(headers.length).fill(false);

    // Always hide these diagnostic/redundant columns
    var alwaysHide = TABLE.hidden_columns || [];

    for (var i = 0; i < lowerHeaders.length; i++) {
      if (alwaysHide.indexOf(lowerHeaders[i]) >= 0) {
        hide[i] = true;
      }
    }

    return hide;
  }

  /**
   * Format a column header for display.
   */
  function formatColumnHeader(header) {
    // Strip surrounding quotes
    var h = header.replace(/^"|"$/g, "");

    // Special header renames
    var renames = TABLE.header_labels || {};

    var lower = h.toLowerCase();
    if (renames[lower]) return renames[lower];

    // Default: apply formatName
    return formatName(h);
  }

  /**
   * Format a cell value for display.
   */
  function formatCellValue(value, header) {
    if (value === null || value === undefined || value === "") {
      return '<span style="color:var(--text-muted)">—</span>';
    }

    var str = String(value).replace(/^"|"$/g, ""); // strip quotes
    var headerLower = header.toLowerCase().replace(/^"|"$/g, "");

    // Columns the profile formats by kind: contrast, group or measure names,
    // other names, and TRUE / FALSE flags.
    var kind = (TABLE.cell_formats || {})[headerLower];
    if (kind === "flag") {
      var upper = str.toUpperCase();
      if (upper === "TRUE") return '<strong style="color:#4CAF50">Yes</strong>';
      if (upper === "FALSE") return '<span style="color:var(--text-muted)">No</span>';
    } else if (kind) {
      return escapeHtml(cellFormatter(kind)(str));
    }

    // Numeric formatting
    var num = parseFloat(str);
    if (!isNaN(num) && isFinite(num) && str.match(/^-?\d*\.?\d+(?:e[+-]?\d+)?$/i)) {
      return escapeHtml(formatNumber(num, headerLower));
    }

    return escapeHtml(str);
  }

  /** The formatter for a column kind in the profile's table vocabulary. */
  function cellFormatter(kind) {
    if (kind === "contrast") return formatContrast;
    if (kind === "group") return formatGroupName;
    if (kind === "measure") return formatMeasureName;
    return function (v) { return formatName(v); };
  }

  /**
   * Format a contrast string for display: the study's label, else
   * "<group>_vs_<group>" with each group's label.
   */
  function formatContrast(str) {
    if (M && M.contrast_labels && M.contrast_labels[str]) return M.contrast_labels[str];
    var parts = str.split("_vs_");
    if (parts.length === 2) {
      return formatGroupName(parts[0]) + " vs " + formatGroupName(parts[1]);
    }
    return formatName(str);
  }

  /**
   * Format a group name for display.
   */
  function formatGroupName(name) {
    if (TX_GROUP_LABELS[name]) return TX_GROUP_LABELS[name];
    var lower = name.toLowerCase();
    if (GROUP_LABELS[lower]) return GROUP_LABELS[lower];
    return name;
  }

  /**
   * Format measure names like "itc_40hz" → "ITC 40 Hz", "stp_onset" → "STP Onset"
   */
  function formatMeasureName(str) {
    // Split on underscores and format each part
    return str.split("_").map(function (part) {
      var lower = part.toLowerCase();
      if (ACRONYMS[lower]) return ACRONYMS[lower];
      var hzMatch = lower.match(/^(\d+)(hz)$/);
      if (hzMatch) return hzMatch[1] + " Hz";
      return part.charAt(0).toUpperCase() + part.slice(1);
    }).join(" ");
  }

  /**
   * Format a number based on context (header name).
   */
  function formatNumber(num, headerLower) {
    // The profile's rules, first match wins: p-values (3-4 significant digits,
    // scientific notation for very small), statistics and effect sizes (3
    // decimals), estimates (4), degrees of freedom and counts (whole when whole),
    // information criteria (1).
    var rules = TABLE.number_formats || [];
    for (var ri = 0; ri < rules.length; ri++) {
      if (!headerLower.match(new RegExp(rules[ri].match))) continue;
      var f = rules[ri].format;
      if (f === "p") return num < 0.001 ? num.toExponential(2) : num.toFixed(4);
      if (f === "fixed1") return num.toFixed(1);
      if (f === "fixed3") return num.toFixed(3);
      if (f === "fixed4") return num.toFixed(4);
      if (f === "df") return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(1);
      if (f === "count") return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(2);
    }

    // Default: 4 significant figures
    if (Math.abs(num) >= 100) return num.toFixed(1);
    if (Math.abs(num) >= 1) return num.toFixed(3);
    if (Math.abs(num) >= 0.001) return num.toFixed(4);
    return num.toExponential(2);
  }

  /**
   * Format table filename for display.
   * "evoked_omnibus.csv" → "Evoked Omnibus"
   */
  function formatTableFilename(filename) {
    var name = filename.replace(/\.csv$/i, "");
    return formatName(name);
  }

  function initTableSort(root) {
    if (!window.Tablesort) return;
    root = root || document;
    var tables = root.matches && root.matches("table") ? [root] : root.querySelectorAll(".table-container table");
    tables.forEach(function (table) {
      if (table.getAttribute("data-tablesort")) return;  // already bound
      table.setAttribute("data-tablesort", "1");
      new Tablesort(table);
    });
  }

  /* ── Lightbox ── */
  function initLightbox() {
    if (lightbox) { lightbox.destroy(); }
    if (window.GLightbox) {
      lightbox = GLightbox({
        selector: ".glightbox",
        touchNavigation: true,
        loop: true,
        zoomable: true,
        draggable: true,
      });
    }
  }

  /* ── Theme ── */
  function initThemeToggle() {
    var saved = localStorage.getItem("theme");
    if (saved) {
      document.documentElement.setAttribute("data-theme", saved);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      document.documentElement.setAttribute("data-theme", "light");
    }

    document.getElementById("theme-toggle").addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  /* ── Keyboard ── */
  function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
        e.preventDefault();
        document.getElementById("search-input").focus();
      }
      if (e.key === "Escape") {
        document.getElementById("search-input").blur();
      }
    });
  }

  /* ── Helpers ── */
  function setBreadcrumb(parts) {
    var el = document.getElementById("breadcrumb");
    el.innerHTML = parts.map(function (p, i) {
      return (i > 0 ? "<span>&rsaquo;</span>" : "") + escapeHtml(p);
    }).join("");
  }

  function setContent(html) {
    document.getElementById("figures-section").innerHTML = html;
    document.getElementById("tables-section").innerHTML = "";
    document.getElementById("summary-section").innerHTML = "";
  }

  function formatName(slug) {
    return slug
      .replace(/_/g, " ")
      .split(" ")
      .map(function (word) {
        var lower = word.toLowerCase();
        if (ACRONYMS[lower]) return ACRONYMS[lower];
        // Handle "40hz" → "40 Hz", "80hz" → "80 Hz"
        var hzMatch = lower.match(/^(\d+)(hz)$/);
        if (hzMatch) return hzMatch[1] + " Hz";
        return word.charAt(0).toUpperCase() + word.slice(1);
      })
      .join(" ");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ── What a profile's script may use, and where it registers its hooks:
     provenanceHtml(prov), inputRunHtml(run), figureFacet(title) and
     figurePanel(figs) — each optional. ── */
  window.LightboxApp = {
    hooks: HOOKS,
    vocabulary: V,
    escapeHtml: escapeHtml,
    formatName: formatName,
    formatGroup: formatGroup,
    metricLabel: metricLabel,
    renderFigureRows: renderFigureRows,
  };
})();
