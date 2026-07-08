#!/usr/bin/env python3
"""Generate with_script variant: apply CANDIDATES + PRESTRIP minus 'script'"""

import sys
from pathlib import Path
from collections import defaultdict
from bs4 import BeautifulSoup

# ── Utils (inlined from clean_html_utils.py) ──

def build_selector(parent, child=None):
    if child:
        return f"{parent} > {child}"
    return parent

def remove_elements(soup, candidates):
    removed = defaultdict(int)
    for label, selector in candidates.items():
        for tag in soup.select(selector):
            removed[selector] += 1
            tag.decompose()
    return removed

# ── Input / Output ──

BASE = Path(__file__).resolve().parent
RAW_HTML = BASE / "raw" / "scan.html"
OUT_HTML = BASE / "with_script"
OUT_HTML.mkdir(parents=True, exist_ok=True)

# ── CANDIDATES from 2_clean_html.ipynb ──

CANDIDATES = {
    "Mobile nav menu": build_selector("div.menu-mobile"),
    "Desktop side menu": build_selector("div.menu-w"),
    "Top header bar": build_selector("div.top-bar"),
    "Loading bar": build_selector("div#progress-bar-loading"),
    "Onboarding modal": build_selector("div.onboarding-modal"),
    "Audio notif": build_selector("audio#sound_notif"),
    "Select dropdowns": "select",
}
CANDIDATES.update({
    "Search Bar": "div.mobile-search-header",
    "Side Bar Top": "div.menu-and-user",
    "Side Bar Bottom": "div.menu-w",
    "Chat": "div.sb-main",
    "Recalculate Queue": "div#recalculate_queue",
    "Recalculate Queue V2": "div#recalculate_queue_progress_v2",
    "Modal Info IOS": "div#modal_info_ios",
    "Weird Igtrial Watermark": "div#__ig_wm__",
    "Loading Global": "div.loading-global",
    "Weird Display Type": "div.display-type",
})

# ── PRESTRIP from 4_clean_html_filter.ipynb, MINUS "script" ──

PRESTRIP = [
    "span.select2-container",
    "b[role='presentation']",
    "div.dataTables_scrollHead",
    "div.dataTables_scrollHeadInner",
    "div.dataTables_sizing",
    "div.loading",
    "div.spinner",
    "div.daterangepicker",
    "div.calendar-tooltip",
    "div.clear",
    # "script",  ← intentionally excluded
    "style",
    "input[type='hidden']",
]

# ── Execute ──

html_content = RAW_HTML.read_text(encoding="utf-8", errors="ignore")
soup = BeautifulSoup(html_content, "html.parser")

print(f"HTML size before cleaning: {len(html_content):,} chars")

# Step 1: Apply CANDIDATES (remove chrome)
removed_candidates = remove_elements(soup, CANDIDATES)
print(f"CANDIDATES removed: {sum(removed_candidates.values())} total elements")

# Step 2: Apply PRESTRIP (minus script)
removed_prestrip = defaultdict(int)
for selector in PRESTRIP:
    for tag in soup.select(selector):
        removed_prestrip[selector] += 1
        tag.decompose()
print(f"PRESTRIP removed: {sum(removed_prestrip.values())} total elements")

# Step 3: Remove EXTERNAL <script src="..."> (library refs) but KEEP inline scripts
external_scripts = [t for t in soup.find_all("script") if t.get("src")]
for tag in external_scripts:
    tag.decompose()
print(f"External scripts removed: {len(external_scripts)}")
inline_scripts = soup.find_all("script")
print(f"Inline scripts kept: {len(inline_scripts)}")

# Step 4: Save
out_path = OUT_HTML / "customer_report_scan_with_script.html"
out_path.write_text(soup.prettify(), encoding="utf-8")
out_size = out_path.stat().st_size
print(f"Saved: {out_path} ({out_size:,} chars)")
print("Done!")