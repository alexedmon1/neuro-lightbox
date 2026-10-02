// Render every page of a built gallery in jsdom and print what a reader sees.
//
//   node tests/js/snapshot.cjs <gallery-dir>
//
// Visits each route the app offers — overview, every nav item, every analysis
// under every source (and "Compare All"), source and study-design pages, the
// localization pages, a few searches — and opens what the app renders lazily
// (each table, each domain pill, each subject). Prints, per route, the page title,
// breadcrumb, source selector and content, one tag per line so two snapshots diff
// as pages. The sidebar is printed once.
//
// Used to check that a change to app.js leaves a gallery's pages as they were
// (tests/test_app_dom.py). Needs jsdom: `npm install --prefix tests/js`.

"use strict";

const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const gallery = path.resolve(process.argv[2] || ".");
let html = fs.readFileSync(path.join(gallery, "index.html"), "utf8");
// Inline the local scripts so the page runs from an http origin (localStorage
// is unavailable to file:// pages in jsdom).
html = html.replace(/<script src="([^"?]+)(\?[^"]*)?"><\/script>/g, (_, src) =>
  "<script>" + fs.readFileSync(path.join(gallery, src), "utf8").replace(/<\/script/g, "<\\/script") + "</script>");

const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://gallery.test/index.html",
                              pretendToBeVisual: true });
const { window } = dom;
const doc = window.document;
const out = [];

function tidy(s) {
  return (s || "").replace(/>\s*</g, ">\n<").trim();
}

function settle() {
  return new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function go(hash) {
  if (window.location.hash === hash) window.location.hash = "#/__reset__";
  await settle();
  window.location.hash = hash;
  await settle();
}

function clickAll(selector, root) {
  (root || doc).querySelectorAll(selector).forEach((el) => el.dispatchEvent(
    new window.MouseEvent("click", { bubbles: true })));
}

function snap(label) {
  out.push("=== " + label);
  out.push("title: " + doc.title);
  out.push("crumb: " + tidy(doc.getElementById("breadcrumb").innerHTML));
  const sel = doc.getElementById("source-selector").innerHTML;
  if (sel) out.push("source: " + tidy(sel));
  out.push(tidy(doc.getElementById("figures-section").innerHTML));
}

async function visit(hash) {
  await go(hash);
  // Domain pages fill each pill lazily. Tables render on toggle; each is opened
  // on its analysis page only, which shows every table the domain pages do.
  clickAll(".pill");
  if (hash.indexOf("#/analytics/") === 0) clickAll(".table-toggle");
  snap(hash);
  // Subject pages show one subject at a time.
  const chips = doc.querySelectorAll(".subject-chip");
  chips.forEach((chip) => {
    chip.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    out.push("--- subject " + chip.getAttribute("data-sub"));
    out.push(tidy(doc.getElementById("subject-meta").innerHTML));
    out.push(tidy(doc.getElementById("subject-figures").innerHTML));
  });
}

async function main() {
  await new Promise((resolve) => {
    if (doc.readyState === "complete") resolve();
    else window.addEventListener("load", resolve);
  });
  await settle();
  out.push("=== sidebar");
  out.push(tidy(doc.getElementById("sidebar-nav").innerHTML));

  const M = window.MANIFEST;
  const routes = ["#/overview"];
  doc.querySelectorAll("#sidebar-nav a.nav-item").forEach((a) => routes.push(a.getAttribute("href")));
  // Sources with analytics data: the others (localization pipelines) appear in
  // M.sources but no link leads to an analytics page for them.
  const hasData = (src) => Object.values(M.paradigms).some((analyses) =>
    Object.values(analyses).some((a) => (a.figures[src] || []).length || (a.tables[src] || []).length));
  const sources = M.sources.filter(hasData);
  for (const src of sources) {
    routes.push("#/analytics/" + encodeURIComponent(src));
    for (const paradigm of Object.keys(M.paradigms)) {
      routes.push("#/analytics/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm));
      for (const analysis of Object.keys(M.paradigms[paradigm])) {
        routes.push("#/analytics/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm) +
                    "/" + encodeURIComponent(analysis));
      }
    }
  }
  if (sources.length > 1) {
    for (const paradigm of Object.keys(M.paradigms)) {
      for (const analysis of Object.keys(M.paradigms[paradigm])) {
        routes.push("#/analytics/__compare__/" + encodeURIComponent(paradigm) + "/" +
                    encodeURIComponent(analysis));
      }
    }
  }
  routes.push("#/localization");
  for (const q of ["alpha", "psd", "rescue", "motor", "outlier", "qc", "sub-90", "nbs", "gm"]) {
    routes.push("#/search/" + encodeURIComponent(q));
  }
  const seen = new Set();
  for (const r of routes) {
    if (seen.has(r)) continue;
    seen.add(r);
    await visit(r);
  }
  process.stdout.write(out.join("\n") + "\n");
  window.close();
}

main().catch((err) => { console.error(err); process.exit(1); });
