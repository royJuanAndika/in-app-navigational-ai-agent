#!/usr/bin/env node

/**
 * Generate a browser-ready highlight helper from an NKG JSON output.
 *
 * Usage:
 *   node validate/generate_highlight_js.js data/nkg_chunked_output/customer_dashboard.nkg.json
 *
 * Output:
 *   - a deduplicated list of element ids
 *   - a paste-ready JavaScript helper that highlights matching DOM elements
 */

const fs = require('fs');
const path = require('path');

function readJson(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  return JSON.parse(raw);
}

function collectElementIds(nkg) {
  const elements = Array.isArray(nkg?.nkg?.elements) ? nkg.nkg.elements : Array.isArray(nkg?.elements) ? nkg.elements : [];
  const items = [];
  const seen = new Set();

  for (const el of elements) {
    const id = typeof el?.id === 'string' ? el.id.trim() : '';
    const selector = typeof el?.selector === 'string' ? el.selector.trim() : '';
    const type = typeof el?.type === 'string' ? el.type.trim() : '';
    const desc = typeof el?.desc === 'string' ? el.desc.trim() : '';
    if (!id || seen.has(id)) continue;
    seen.add(id);
    items.push({ id, selector, type, desc });
  }

  return items;
}

function normalizeHighlightItem(item) {
  if (typeof item === 'string') {
    return { id: item.trim(), selector: '', type: '', desc: '' };
  }

  if (!item || typeof item !== 'object') {
    return { id: '', selector: '', type: '', desc: '' };
  }

  return {
    id: typeof item.id === 'string' ? item.id.trim() : '',
    selector: typeof item.selector === 'string' ? item.selector.trim() : '',
    type: typeof item.type === 'string' ? item.type.trim() : '',
    desc: typeof item.desc === 'string' ? item.desc.trim() : '',
  };
}

function buildBrowserHelper(items) {
  return [
    '// Paste this into the web app JS or browser console',
    `const NKG_ELEMENT_ITEMS = ${JSON.stringify(items, null, 2)};`,
    'const NKG_ELEMENT_IDS = NKG_ELEMENT_ITEMS.map((item) => item.id);',
    '',
    'function clearNkgHighlights() {',
    '  document.querySelectorAll("[data-nkg-highlight=\'1\']").forEach((el) => {',
    "    el.style.outline = '';",
    "    el.style.outlineOffset = '';",
    "    el.style.backgroundColor = '';",
    "    el.removeAttribute('data-nkg-highlight');",
    '  });',
    '  const root = document.getElementById("nkg-highlight-root");',
    '  if (root) root.remove();',
    '}',
    '',
    'function ensureNkgHighlightRoot() {',
    '  let root = document.getElementById("nkg-highlight-root");',
    '  if (root) return root;',
    '  root = document.createElement("div");',
    '  root.id = "nkg-highlight-root";',
    '  root.style.position = "fixed";',
    '  root.style.left = "0";',
    '  root.style.top = "0";',
    '  root.style.width = "100vw";',
    '  root.style.height = "100vh";',
    '  root.style.pointerEvents = "none";',
    '  root.style.zIndex = "2147483647";',
    '  document.body.appendChild(root);',
    '  return root;',
    '}',
    '',
    'function positionNkgBadge(el, badge) {',
    '  if (!el || !badge) return;',
    '  const rect = el.getBoundingClientRect();',
    '  badge.style.position = "fixed";',
    '  badge.style.left = `${Math.max(0, Math.round(rect.right))}px`;',
    '  badge.style.top = `${Math.max(0, Math.round(rect.top))}px`;',
    '  badge.style.transform = "translate(-100%, -100%) translate(-8px, -8px)";',
    '}',
    '',
    'function refreshNkgBadges() {',
    '  document.querySelectorAll("[data-nkg-badge=\'1\']").forEach((badge) => {',
    '    const targetId = badge.getAttribute("data-nkg-target-id");',
    '    if (!targetId) return;',
    '    const target = document.getElementById(targetId);',
    '    if (target) positionNkgBadge(target, badge);',
    '  });',
    '}',
    '',
    'function attachNkgBadge(el, label) {',
    '  if (!el) return;',
    '  const root = ensureNkgHighlightRoot();',
    '  const targetId = el.id || label || "NKG";',
    '  const existing = root.querySelector(`[data-nkg-target-id="${CSS.escape(targetId)}"]`);',
    '  if (existing) existing.remove();',
    '',
    '  const badge = document.createElement("span");',
    '  badge.setAttribute("data-nkg-badge", "1");',
    '  badge.setAttribute("data-nkg-target-id", targetId);',
    '  badge.textContent = label;',
    '  badge.style.position = "fixed";',
    '  badge.style.padding = "2px 6px";',
    '  badge.style.borderRadius = "999px";',
    '  badge.style.background = "linear-gradient(135deg, #ff4d4f, #ff7875)";',
    '  badge.style.color = "#fff";',
    '  badge.style.fontSize = "11px";',
    '  badge.style.fontWeight = "700";',
    '  badge.style.lineHeight = "1.2";',
    '  badge.style.boxShadow = "0 2px 8px rgba(0, 0, 0, 0.18)";',
    '  badge.style.pointerEvents = "none";',
    '  badge.style.whiteSpace = "nowrap";',
    '  badge.style.zIndex = "2147483647";',
    '  root.appendChild(badge);',
    '  positionNkgBadge(el, badge);',
    '}',
    '',
    'function findNkgElement(item) {',
    '  if (!item) return null;',
    '  if (typeof item === "string") {',
    '    const byId = document.getElementById(item);',
    '    if (byId) return byId;',
    '    try {',
    '      const bySelector = document.querySelector(`#${CSS.escape(item)}`);',
    '      if (bySelector) return bySelector;',
    '    } catch (err) {',
    '      /* ignore */',
    '    }',
    '    return null;',
    '  }',
    '',
    '  if (item.id) {',
    '    const byId = document.getElementById(item.id);',
    '    if (byId) return byId;',
    '  }',
    '  if (item.selector) {',
    '    try {',
    '      const bySelector = document.querySelector(item.selector);',
    '      if (bySelector) return bySelector;',
    '    } catch (err) {',
    "      console.warn('Invalid selector for NKG item:', item.selector, err);",
    '    }',
    '  }',
    '  return null;',
    '}',
    '',
    'function highlightNkgElement(item, options = {}) {',
    '  item = typeof item === "string" ? { id: item } : item;',
    '  const el = findNkgElement(item);',
    '  if (!el) return false;',
    '',
    '  const outlineColor = options.outlineColor || "#ff4d4f";',
    '  const backgroundColor = options.backgroundColor || "rgba(255, 77, 79, 0.12)";',
    '  const scrollBehavior = options.scrollBehavior || "smooth";',
    '  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 0;',
    '',
    '  el.setAttribute("data-nkg-highlight", "1");',
    '  el.style.outline = "3px solid " + outlineColor;',
    '  el.style.outlineOffset = "2px";',
    '  el.style.backgroundColor = backgroundColor;',
    '  attachNkgBadge(el, item?.id || el.id || "NKG");',
    '  el.scrollIntoView({ behavior: scrollBehavior, block: "center" });',
    '  requestAnimationFrame(refreshNkgBadges);',
    '',
    '  if (timeoutMs > 0) {',
    '    setTimeout(() => {',
    '      const current = item?.id ? document.getElementById(item.id) : el;',
    '      if (!current) return;',
    '      current.style.outline = "";',
    '      current.style.outlineOffset = "";',
    '      current.style.backgroundColor = "";',
    '      const root = document.getElementById("nkg-highlight-root");',
    '      if (root) {',
    '        const badge = Array.from(root.querySelectorAll("[data-nkg-badge=\'1\']")).find((node) => node.getAttribute("data-nkg-target-id") === current.id);',
    '        if (badge) badge.remove();',
    '      }',
    '      current.removeAttribute("data-nkg-highlight");',
    '    }, timeoutMs);',
    '  }',
    '',
    '  return true;',
    '}',
    '',
    'function highlightNkgElements(items = NKG_ELEMENT_ITEMS, options = {}) {',
    '  clearNkgHighlights();',
    '',
    '  const missing = [];',
    '  const found = [];',
    '',
    '  items.forEach((item) => {',
    '    const ok = highlightNkgElement(item, options);',
    '    if (ok) found.push(item.id);',
    '    else missing.push(item);',
    '  });',
    '',
    '  console.log("NKG highlight summary:", { found: found.length, missing: missing.length });',
    '  if (missing.length) {',
    '    console.warn("Elements failed to highlight:");',
    '    console.table(missing.map((item) => ({ id: item.id, selector: item.selector || "", type: item.type || "", desc: item.desc || "" })));',
    '  }',
    '  return { found, missing };',
    '}',
    '',
    'function reportFailedNkgHighlights(items = NKG_ELEMENT_ITEMS) {',
    '  const failed = [];',
    '  items.forEach((item) => {',
    '    if (!findNkgElement(item)) {',
    '      failed.push({',
    '        id: typeof item === "string" ? item : item.id,',
    '        selector: typeof item === "string" ? "" : item.selector || "",',
    '        type: typeof item === "string" ? "" : item.type || "",',
    '        desc: typeof item === "string" ? "" : item.desc || "",',
    '        reason: typeof item === "string" ? "not found by id" : (item.selector ? "not found by id/selector" : "not found by id")',
    '      });',
    '    }',
    '  });',
    '  console.log("Failed highlight candidates:", failed.length);',
    '  if (failed.length) console.table(failed);',
    '  return failed;',
    '}',
    '',
    'window.NKG_ELEMENT_ITEMS = NKG_ELEMENT_ITEMS;',
    'window.NKG_ELEMENT_IDS = NKG_ELEMENT_IDS;',
    'window.clearNkgHighlights = clearNkgHighlights;',
    'window.findNkgElement = findNkgElement;',
    'window.highlightNkgElement = highlightNkgElement;',
    'window.highlightNkgElements = highlightNkgElements;',
    'window.reportFailedNkgHighlights = reportFailedNkgHighlights;',
    '',
    'window.addEventListener("scroll", refreshNkgBadges, true);',
    'window.addEventListener("resize", refreshNkgBadges, true);',
    '',
    'console.log("NKG helper loaded. Use highlightNkgElements(), highlightNkgElement(item), or reportFailedNkgHighlights().");',
  ].join("\n");
}

function main() {
  const input = process.argv[2];
  if (!input) {
    console.error('Usage: node validate/generate_highlight_js.js <path-to-nkg-json>');
    process.exit(1);
  }

  const filePath = path.resolve(process.cwd(), input);
  if (!fs.existsSync(filePath)) {
    console.error(`File not found: ${filePath}`);
    process.exit(1);
  }

  const nkg = readJson(filePath);
  const items = collectElementIds(nkg);

  console.log(`// Source: ${filePath}`);
  console.log(`// Total element ids: ${items.length}`);
  console.log(buildBrowserHelper(items));
}

main();