from pathlib import Path
from collections import defaultdict
from bs4 import BeautifulSoup
import pandas as pd
import json
import hashlib
import re
from datetime import datetime

def load_and_cache_html_soups(html_files):
    """Pre-parse all HTML files once and cache them in memory.
    
    This is essential for performance — if you need to run multiple operations
    (audit, preview, variance diagnostic) against the same HTML files, parse them
    once and reuse the BeautifulSoup objects instead of re-parsing each file
    for every selector or operation.
    
    Returns:
        dict: {Path(file): BeautifulSoup}
    
    Example:
        soup_cache = load_and_cache_html_soups(html_files)
        df_audit = audit_selectors(html_files, CANDIDATES, soup_cache=soup_cache)
        df_preview = preview_removals(html_files, CANDIDATES, soup_cache=soup_cache)
    """
    cache = {}
    for f in html_files:
        try:
            html_content = f.read_text(encoding="utf-8", errors="ignore")
            cache[f] = BeautifulSoup(html_content, "html.parser")
        except Exception as e:
            print(f"⚠ Warning: Failed to parse {f.name}: {e}")
    return cache

def build_selector(parent, child=None):
    """Build CSS selector from parent and optional child.
    Args:
        parent (str): Parent selector (e.g., 'div.menu-mobile')
        child (str): Optional child selector (e.g., 'button')
                    If provided, returns 'parent > child' (direct child)
    Returns:
        str: CSS selector string
    Examples:
        build_selector('div.menu-mobile')           → 'div.menu-mobile'
        build_selector('div.menu-mobile', 'button') → 'div.menu-mobile > button'
    """
    if child:
        return f"{parent} > {child}"
    return parent

def audit_selectors(html_files, candidates, soup_cache=None):
    """Audit selectors across HTML files. Returns DataFrame with coverage info.
    
    Args:
        html_files: list of Path objects
        candidates: dict {label: selector}
        soup_cache: (optional) dict {Path: BeautifulSoup} from load_and_cache_html_soups()
                   If provided, uses cached soups (MUCH faster). If None, parses on-the-fly.
    """
    total = len(html_files)
    rows = []
    for label, selector in candidates.items():
        count = 0
        file_hits = []
        for f in html_files:
            # Use cached soup if available; otherwise parse on-the-fly
            if soup_cache is not None:
                soup = soup_cache.get(f)
                if soup is None:
                    continue
            else:
                soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
            
            if soup.select_one(selector):
                count += 1
                file_hits.append(f.name)
        rows.append({
            "label": label,
            "selector": selector,
            "count": count,
            "total": total,
            "coverage": f"{count}/{total}",
            "all_pages": count == total,
        })
    return pd.DataFrame(rows)

def remove_elements_and_save(html_files, candidates, out_dir):
    """Remove elements matching selectors and save cleaned HTML. Returns summary DataFrame."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for f in html_files:
        soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        removed = defaultdict(int)
        for selector in candidates.values():
            for tag in soup.select(selector):
                removed[selector] += 1
                tag.decompose()
        out_path = out_dir / f.name
        out_path.write_text(soup.prettify(), encoding="utf-8")
        summary.append({
            "file": f.name,
            "removed": dict(removed),
            "total_removed": sum(removed.values()),
        })
    return pd.DataFrame(summary)

def lint_and_format_html(folder):
    """Lint and prettify all HTML files in a folder. Returns summary DataFrame."""
    folder = Path(folder)
    html_files = sorted(folder.glob("*.html"))
    format_summary = []
    for f in html_files:
        html_content = f.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_content, "html.parser")
        formatted_html = soup.prettify()
        f.write_text(formatted_html, encoding="utf-8")
        format_summary.append({
            "file": f.name,
            "original_size": len(html_content),
            "formatted_size": len(formatted_html),
        })
    return pd.DataFrame(format_summary)


# Tags considered "NKG-relevant" — if a to-be-removed element contains
# any of these, it may carry navigational/interactive signal worth keeping.
_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea"}


def preview_removals(html_files, candidates, soup_cache=None):
    """For each (selector, file) pair, summarise what would be removed.

    Returns a DataFrame with columns:
        label, selector, file, el_index, tag, id, classes,
        interactive_children, interactive_tags, text_preview, risk

    ``risk`` is either "SAFE" (no interactive children) or "RISKY"
    (contains at least one interactive descendant that may matter for the NKG).
    
    Args:
        soup_cache: (optional) dict {Path: BeautifulSoup} from load_and_cache_html_soups()
                   If provided, uses cached soups (MUCH faster).
    """
    rows = []
    for label, selector in candidates.items():
        for f in html_files:
            # Use cached soup if available; otherwise parse on-the-fly
            if soup_cache is not None:
                soup = soup_cache.get(f)
                if soup is None:
                    continue
            else:
                soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
            
            matches = soup.select(selector)
            for idx, el in enumerate(matches):
                interactive = [t.name for t in el.find_all(_INTERACTIVE_TAGS)]
                rows.append({
                    "label":               label,
                    "selector":            selector,
                    "file":                f.name,
                    "el_index":            idx,
                    "tag":                 el.name,
                    "id":                  el.get("id", ""),
                    "classes":             " ".join(el.get("class", [])),
                    "interactive_children": len(interactive),
                    "interactive_tags":    ", ".join(sorted(set(interactive))) or "—",
                    "text_preview":        el.get_text(separator=" ", strip=True)[:160] or "—",
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["risk"] = df["interactive_children"].apply(lambda n: "RISKY" if n > 0 else "SAFE")
    return df


def risk_summary(df_preview):
    """Aggregate preview_removals output to a per-label risk summary.

    Returns a DataFrame with columns:
        label, files_matched, total_elements, total_interactive, risk

    A selector is flagged RISKY if ANY matched element contains interactive children.
    """
    if df_preview.empty:
        return pd.DataFrame()
    agg = (
        df_preview.groupby("label")
        .agg(
            files_matched    =("file",                "nunique"),
            total_elements   =("el_index",            "count"),
            total_interactive=("interactive_children", "sum"),
            risk             =("risk", lambda x: "RISKY" if (x == "RISKY").any() else "SAFE"),
        )
        .reset_index()
    )
    return agg


def count_elements_per_file(html_files, candidates, soup_cache=None):
    """Count matched elements per (selector, file) pair.

    Useful for diagnosing *why* line-removal is unequal across files — a
    selector that matches 0 elements on some pages but 5+ on others will
    produce high variance.

    Returns a pivot DataFrame (rows=files, columns=selector labels).
    
    Args:
        soup_cache: (optional) dict {Path: BeautifulSoup} from load_and_cache_html_soups()
                   If provided, uses cached soups (MUCH faster).
    """
    rows = []
    for label, selector in candidates.items():
        for f in html_files:
            # Use cached soup if available; otherwise parse on-the-fly
            if soup_cache is not None:
                soup = soup_cache.get(f)
                if soup is None:
                    continue
            else:
                soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
            
            rows.append({
                "label": label,
                "file":  f.name,
                "count": len(soup.select(selector)),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    pivot = df.pivot_table(index="file", columns="label", values="count", fill_value=0)
    pivot.columns.name = None
    # Add a row-total column so outlier files are immediately obvious
    pivot["TOTAL"] = pivot.sum(axis=1)
    return pivot.sort_values("TOTAL", ascending=False)


# ──────────────────────────────────────────────────────────────────────────────
# Defensive One-by-One Review
# ──────────────────────────────────────────────────────────────────────────────

def _queue_stats(items):
    """Return counts of each decision state in the queue."""
    from collections import Counter
    counts = Counter(i["decision"] for i in items)
    return {
        "total":   len(items),
        "pending": counts.get("pending", 0),
        "remove":  counts.get("remove", 0),
        "keep":    counts.get("keep", 0),
    }


def _hl_tag(tok: str, cb: str, ct: str, ca: str, cv: str) -> str:
    """Color a single HTML tag token with inline <span> elements."""
    inner = tok[1:-1]  # strip outer < >
    result = [f'<span style="color:{cb}">&lt;</span>']

    if inner.startswith('/'):
        result.append(f'<span style="color:{cb}">/</span>')
        inner = inner[1:]

    m = re.match(r'([^\s/>=]+)(.*)', inner, re.DOTALL)
    if not m:
        e = inner.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        result.append(e)
        result.append(f'<span style="color:{cb}">&gt;</span>')
        return ''.join(result)

    result.append(f'<span style="color:{ct}">{m.group(1)}</span>')
    rest = m.group(2)

    attr_re = re.compile(
        r'(\s+)([a-zA-Z_:][^\s=/>]*)'
        r'(\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]*))?'
    )
    last = 0
    for am in attr_re.finditer(rest):
        gap = rest[last:am.start()]
        if gap:
            result.append(gap.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        result.append(am.group(1))  # whitespace
        result.append(f'<span style="color:{ca}">{am.group(2)}</span>')
        if am.group(3):
            eq_val = am.group(3)
            eq_pos = eq_val.index('=')
            eq  = eq_val[:eq_pos + 1]
            val = eq_val[eq_pos + 1:]
            val_e = val.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            result.append(f'<span style="color:{cb}">{eq}</span>')
            result.append(f'<span style="color:{cv}">{val_e}</span>')
        last = am.end()

    tail = rest[last:]
    if tail:
        result.append(tail.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    result.append(f'<span style="color:{cb}">&gt;</span>')
    return ''.join(result)


def _highlight_html(raw: str) -> str:
    """Return syntax-highlighted HTML markup for display inside a <pre> block.

    Colours follow VS Code dark-theme conventions:
      - tag names   -> #569cd6 (blue)
      - attr names  -> #9cdcfe (light blue)
      - attr values -> #ce9178 (orange)
      - comments    -> #6a9955 (green)
      - plain text  -> #d4d4d4 (light grey)
    """
    CB = "#808080"  # brackets / punctuation
    CT = "#569cd6"  # tag names
    CA = "#9cdcfe"  # attribute names
    CV = "#ce9178"  # attribute values
    CC = "#6a9955"  # comments
    CN = "#d4d4d4"  # plain text nodes

    out = []
    for tok in re.split(r'(<!--[\s\S]*?-->|<[^>]*>)', raw):
        if not tok:
            continue
        if tok.startswith('<!--'):
            e = tok.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            out.append(f'<span style="color:{CC}">{e}</span>')
        elif tok.startswith('<'):
            out.append(_hl_tag(tok, CB, CT, CA, CV))
        else:
            e = tok.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            out.append(f'<span style="color:{CN}">{e}</span>')
    return ''.join(out)


def _content_fingerprint(html_snippet: str) -> str:
    """Stable hash of an element's HTML content, whitespace-normalised.

    Two elements are considered identical (and will receive the same
    auto-propagated decision) when their fingerprints match.  Whitespace
    is collapsed so that prettify differences between files don't produce
    spurious mismatches.
    """
    normalised = " ".join(html_snippet.split())
    return hashlib.md5(normalised.encode("utf-8")).hexdigest()


def generate_review_queue(html_files, candidates, queue_path, soup_cache=None):
    """Generate (or resume) an element-level review queue persisted as JSON.

    Scans every (selector, file) pair and creates one queue item per matched
    element. If the queue file already exists, previously decided items are
    preserved — only NEW (unseen) items are added as 'pending'.

    Args:
        html_files:  list of Path objects (scraped HTML sources)
        candidates:  dict {label: selector}
        queue_path:  Path or str — where to save/load the JSON queue
        soup_cache:  (optional) dict {Path: BeautifulSoup}

    Returns:
        (Path, dict):  queue file path + stats {"total","pending","remove","keep"}
    """
    queue_path = Path(queue_path)

    # Load any existing decisions so we never overwrite them
    existing: dict[str, dict] = {}
    if queue_path.exists():
        with open(queue_path, "r", encoding="utf-8") as fh:
            old = json.load(fh)
        for item in old.get("items", []):
            # Back-fill content_fp for queues generated before this feature
            if "content_fp" not in item:
                item["content_fp"] = _content_fingerprint(item.get("html_snippet", ""))
            existing[item["queue_id"]] = item
        print(f"↺  Resuming existing queue — {len(existing)} decisions already on disk")

    items = []
    for label, selector in candidates.items():
        for f in html_files:
            if soup_cache is not None:
                soup = soup_cache.get(f)
                if soup is None:
                    continue
            else:
                soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")

            matches = soup.select(selector)
            for idx, el in enumerate(matches):
                qid = f"{label}::{f.name}::{idx}"
                if qid in existing:
                    items.append(existing[qid])   # preserve decision
                else:
                    interactive  = [t.name for t in el.find_all(_INTERACTIVE_TAGS)]
                    html_snippet = el.prettify()
                    items.append({
                        "queue_id":            qid,
                        "label":               label,
                        "selector":            selector,
                        "file":                f.name,
                        "el_index":            idx,
                        "tag":                 el.name,
                        "id_attr":             el.get("id", ""),
                        "classes":             " ".join(el.get("class", [])),
                        "interactive_children": len(interactive),
                        "interactive_tags":    ", ".join(sorted(set(interactive))) or "—",
                        "text_preview":        el.get_text(separator=" ", strip=True)[:300] or "—",
                        "html_snippet":        html_snippet,
                        "content_fp":          _content_fingerprint(html_snippet),
                        "risk":                "RISKY" if interactive else "SAFE",
                        "decision":            "pending",
                    })

    queue = {"generated_at": datetime.now().isoformat(), "total": len(items), "items": items}
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as fh:
        json.dump(queue, fh, indent=2, ensure_ascii=False)

    stats = _queue_stats(items)
    return queue_path, stats


def review_progress(queue_path):
    """Print a concise summary of current queue decisions.

    Args:
        queue_path: Path or str — the JSON queue file
    """
    queue_path = Path(queue_path)
    if not queue_path.exists():
        print("❌ Queue file not found. Run generate_review_queue() first.")
        return None

    with open(queue_path, "r", encoding="utf-8") as fh:
        queue = json.load(fh)

    stats = _queue_stats(queue["items"])
    total   = stats["total"]
    done    = stats["remove"] + stats["keep"]
    pct     = int(done / total * 100) if total else 0
    bar     = "█" * (pct // 5) + "░" * (20 - pct // 5)

    print(f"Progress: [{bar}] {pct}%  ({done}/{total})")
    print(f"  🗑  remove  : {stats['remove']}")
    print(f"  🔒 keep    : {stats['keep']}")
    print(f"  ⏳ pending  : {stats['pending']}")

    # Per-label breakdown
    from collections import defaultdict as dd
    by_label: dict = dd(lambda: {"remove": 0, "keep": 0, "pending": 0})
    for item in queue["items"]:
        by_label[item["label"]][item["decision"]] += 1

    rows = [
        {"label": lbl, **counts}
        for lbl, counts in sorted(by_label.items())
    ]
    import pandas as pd
    df = pd.DataFrame(rows)[["label", "remove", "keep", "pending"]]
    display(df)
    return stats


def interactive_review(queue_path):
    """Interactive element review loop with prev/next navigation and auto-propagation.

    Displays every element one at a time. Navigate freely:

        [r]  remove  — mark for deletion + auto-propagate to identical pending elements
        [k]  keep    — preserve + auto-propagate to identical pending elements
        [s]  skip    — reset to pending (undo a previous r/k, no propagation)
        [p]  prev    — go to previous item (no decision change)
        [n]  next    — go to next item (no decision change)
        [q]  quit    — save progress and exit

    The current decision for each item (REMOVE / KEEP / pending) is shown in the
    header so you always know what you previously decided when revisiting.

    After pressing [r] or [k], the cursor automatically jumps to the next pending
    item.  Use [p] / [n] to freely revisit any element and change your mind.

    Every decision is written to disk IMMEDIATELY after each keypress.

    Args:
        queue_path: Path or str — the JSON queue file from generate_review_queue()
    """
    from IPython.display import display, HTML, clear_output

    queue_path = Path(queue_path)
    if not queue_path.exists():
        print("❌ Queue file not found. Run generate_review_queue() first.")
        return

    with open(queue_path, "r", encoding="utf-8") as fh:
        queue = json.load(fh)

    # Back-fill content_fp for old queue files
    for item in queue["items"]:
        if "content_fp" not in item:
            item["content_fp"] = _content_fingerprint(item.get("html_snippet", ""))

    items = queue["items"]
    total = len(items)

    if total == 0:
        print("Queue is empty. Run generate_review_queue() first.")
        return

    def _save():
        queue["items"] = items
        with open(queue_path, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, indent=2, ensure_ascii=False)

    def _next_pending(from_idx):
        """Return index of next pending item after from_idx, or None."""
        for i in range(from_idx + 1, total):
            if items[i]["decision"] == "pending":
                return i
        # Wrap around from beginning
        for i in range(0, from_idx + 1):
            if items[i]["decision"] == "pending":
                return i
        return None

    # Start at first pending item (or item 0 if all reviewed)
    cursor = 0
    for idx, it in enumerate(items):
        if it["decision"] == "pending":
            cursor = idx
            break

    s = _queue_stats(items)
    print(f"  {total} items  |  remove={s['remove']}  keep={s['keep']}  pending={s['pending']}")
    print("  [r] remove  [k] keep  [s] pending  [p] prev  [n] next  [q] quit\n")

    while True:
        item = items[cursor]
        qid  = item["queue_id"]

        s    = _queue_stats(items)
        done = s["remove"] + s["keep"]
        pct  = int(done / total * 100) if total else 0
        bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)

        # Twin count: OTHER pending items with same fingerprint
        twin_count = sum(
            1 for it in items
            if it["queue_id"] != qid
            and it["content_fp"] == item["content_fp"]
            and it["decision"] == "pending"
        )
        twin_label = (
            f'<span style="color:#f0a030;">⚡ {twin_count} identical pending element(s) will be auto-propagated</span>'
            if twin_count else
            '<span style="color:#555;">no identical pending duplicates</span>'
        )

        risk_color = "#e74c3c" if item["risk"] == "RISKY" else "#2ecc71"
        risk_badge = "🔴 RISKY" if item["risk"] == "RISKY" else "🟢 SAFE"

        cur_dec   = item["decision"]
        dec_style = {
            "remove":  ("✂ REMOVE",  "#e74c3c"),
            "keep":    ("✓ KEEP",    "#2ecc71"),
            "pending": ("⏸ pending", "#888888"),
        }.get(cur_dec, (cur_dec, "#888888"))
        dec_label, dec_color = dec_style

        # Lint and syntax-highlight the HTML snippet
        try:
            linted_soup = BeautifulSoup(item["html_snippet"], "html.parser")
            linted_html = linted_soup.prettify()
        except Exception:
            linted_html = item["html_snippet"]

        highlighted_snippet = _highlight_html(linted_html)

        clear_output(wait=True)
        display(HTML(f"""
        <div style="border:2px solid {risk_color}; border-radius:8px; padding:16px;
                    margin:8px 0; font-family:monospace; background:#1e1e1e; color:#d4d4d4;">
          <div style="margin-bottom:8px; font-size:13px;
                      display:flex; justify-content:space-between; align-items:center;">
            <span>
              <b style="color:#569cd6;">[{cursor + 1}/{total}]</b>
              &nbsp;[{bar}]&nbsp;{pct}%
              &nbsp;&nbsp;{risk_badge}
              &nbsp;&nbsp;<span style="color:#dcdcaa;">pending: {s['pending']}</span>
            </span>
            <span style="background:{dec_color}22; border:1px solid {dec_color};
                         border-radius:4px; padding:2px 10px;
                         color:{dec_color}; font-weight:bold;">
              {dec_label}
            </span>
          </div>
          <table style="border-collapse:collapse; font-size:13px; width:100%;">
            <tr>
              <td style="color:#9cdcfe; padding:2px 8px 2px 0;">label</td>
              <td><b>{item['label']}</b></td>
              <td style="color:#9cdcfe; padding:2px 8px 2px 16px;">file</td>
              <td><b>{item['file']}</b></td>
              <td style="color:#9cdcfe; padding:2px 8px 2px 16px;">el_index</td>
              <td>{item['el_index']}</td>
            </tr>
            <tr>
              <td style="color:#9cdcfe; padding:2px 8px 2px 0;">selector</td>
              <td colspan="3"><code style="color:#ce9178;">{item['selector']}</code></td>
              <td style="color:#9cdcfe; padding:2px 8px 2px 16px;">tag</td>
              <td>&lt;{item['tag']}&gt;</td>
            </tr>
            <tr>
              <td style="color:#9cdcfe; padding:2px 8px 2px 0;">id</td>
              <td>"{item['id_attr']}"</td>
              <td style="color:#9cdcfe; padding:2px 8px 2px 16px;">classes</td>
              <td colspan="3">{item['classes']}</td>
            </tr>
            <tr>
              <td style="color:#9cdcfe; padding:2px 8px 2px 0;">interactive</td>
              <td colspan="5">{item['interactive_children']} child(ren) &nbsp;
                <span style="color:#ce9178;">[{item['interactive_tags']}]</span></td>
            </tr>
          </table>
          <div style="margin-top:8px; color:#9cdcfe;">text preview:</div>
          <div style="color:#ce9178; font-size:12px; margin:4px 0 8px 0;">
            "{item['text_preview'][:250]}"
          </div>
          <div style="margin-top:6px; font-size:12px;">{twin_label}</div>
          <div style="margin-top:12px; color:#9cdcfe; font-size:12px;">HTML snippet ({len(linted_html)} chars):</div>
          <pre style="background:#1e1e1e; padding:10px; border-radius:4px;
                      overflow:auto; max-height:600px; font-size:11px;
                      margin:8px 0; white-space:pre-wrap;">{highlighted_snippet}</pre>
        </div>
        """))

        # Prompt until valid input
        while True:
            try:
                ans = input("  → [r] remove  [k] keep  [s] pending  [p] prev  [n] next  [q] quit: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "q"
                print()
            if ans in ("r", "k", "s", "p", "n", "q"):
                break
            print("  Invalid input. Enter r / k / s / p / n / q")

        # ── Navigation ────────────────────────────────────────────────────────
        if ans == "q":
            _save()
            s = _queue_stats(items)
            print(f"\n  ✓ Progress saved — remove={s['remove']}  keep={s['keep']}  pending={s['pending']}")
            return

        if ans == "p":
            cursor = max(0, cursor - 1)
            continue

        if ans == "n":
            cursor = min(total - 1, cursor + 1)
            continue

        # ── Decision ──────────────────────────────────────────────────────────
        decision_map = {"r": "remove", "k": "keep", "s": "pending"}
        decision     = decision_map[ans]
        item["decision"] = decision

        propagated_to = []

        # Auto-propagate r/k to identical PENDING elements (never overwrites
        # a decision the user already made manually)
        if ans in ("r", "k"):
            for other in items:
                if (other["queue_id"] != qid
                        and other["content_fp"] == item["content_fp"]
                        and other["decision"] == "pending"):
                    other["decision"] = decision
                    propagated_to.append(other["file"])

        _save()

        if propagated_to:
            verb = "remove" if ans == "r" else "keep"
            print(f"  ⚡ Auto-propagated '{verb}' to {len(propagated_to)} identical element(s):")
            for fn in sorted(set(propagated_to)):
                print(f"      {fn}")

        # After a decision, jump to next pending item (if any)
        nxt = _next_pending(cursor)
        if nxt is not None:
            cursor = nxt
        else:
            # All done — stay at current position so user can review freely
            s = _queue_stats(items)
            clear_output(wait=True)
            print(f"  ✓ All {total} elements reviewed!")
            print(f"  remove={s['remove']}  keep={s['keep']}  pending={s['pending']}")
            print("  Use [p] / [n] to revisit any decision, or [q] to quit.")
            # keep looping so user can still navigate / change decisions


def apply_queue_decisions(src_dir, queue_path, out_dir, removed_log_dir=None):
    """Apply all 'remove' decisions from the queue, write cleaned HTML to out_dir.
    
    Also extracts and saves each removed element to a per-file removal log (JSON).

    Elements marked 'keep' or still 'pending' are left untouched.
    Removal is done per-file, in reverse element-index order so that
    decomposing one element never shifts the indices of others.

    Args:
        src_dir:          Path — source HTML directory (scraped_html/)
        queue_path:       Path — the JSON queue file
        out_dir:          Path — output directory (cleaned_html/)
        removed_log_dir:  Path — where to save removal logs (default: data/removed_log/)

    Returns:
        DataFrame with columns: file, elements_removed
    """
    src_dir    = Path(src_dir)
    queue_path = Path(queue_path)
    out_dir    = Path(out_dir)
    if removed_log_dir is None:
        removed_log_dir = Path("../data/removed_log")
    removed_log_dir = Path(removed_log_dir)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    removed_log_dir.mkdir(parents=True, exist_ok=True)

    if not queue_path.exists():
        raise FileNotFoundError(f"Queue file not found: {queue_path}")

    with open(queue_path, "r", encoding="utf-8") as fh:
        queue = json.load(fh)

    s = _queue_stats(queue["items"])
    if s["pending"] > 0:
        print(f"⚠  {s['pending']} item(s) still pending — they will be KEPT.")
        print("   Run interactive_review() to decide on them first.\n")

    # Group 'remove' decisions: {filename → {selector → [(index, label, item_metadata), ...]}}
    to_remove: dict[str, dict[str, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    for item in queue["items"]:
        if item["decision"] == "remove":
            to_remove[item["file"]][item["selector"]].append(
                (item["el_index"], item["label"], item)
            )

    summary = []
    for f in sorted(src_dir.glob("*.html")):
        soup         = BeautifulSoup(f.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        removed_log  = []  # List of removed element records
        removed_count = 0

        if f.name in to_remove:
            for selector, removal_list in to_remove[f.name].items():
                matches = soup.select(selector)
                
                # Sort by index descending, so we remove in reverse order
                removal_list_sorted = sorted(removal_list, key=lambda x: x[0], reverse=True)
                
                for idx, label, item_metadata in removal_list_sorted:
                    if idx < len(matches):
                        matched_el = matches[idx]

                        if matched_el.name == "select":
                            option_nodes = matched_el.find_all("option")
                            to_trim = option_nodes[1:]

                            removed_log.append({
                                "label":      label,
                                "selector":   item_metadata["selector"],
                                "el_index":   idx,
                                "tag":        item_metadata["tag"],
                                "id":         item_metadata["id_attr"],
                                "classes":    item_metadata["classes"],
                                "text_preview": item_metadata["text_preview"],
                                "action":     "trim_select_options_keep_first",
                                "options_removed": len(to_trim),
                                "html":       matched_el.prettify(),
                            })

                            for opt in to_trim:
                                opt.decompose()
                            removed_count += len(to_trim)
                        else:
                            # Record what was removed
                            removed_log.append({
                                "label":      label,
                                "selector":   item_metadata["selector"],
                                "el_index":   idx,
                                "tag":        item_metadata["tag"],
                                "id":         item_metadata["id_attr"],
                                "classes":    item_metadata["classes"],
                                "text_preview": item_metadata["text_preview"],
                                "html":       matched_el.prettify(),
                            })

                            # Remove from DOM
                            matched_el.decompose()
                            removed_count += 1

        # Write cleaned HTML
        (out_dir / f.name).write_text(soup.prettify(), encoding="utf-8")
        
        # Write removal log (only if something was removed)
        if removed_log:
            log_path = removed_log_dir / f"{f.stem}_removed.json"
            with open(log_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "file": f.name,
                        "total_removed": len(removed_log),
                        "removed_elements": removed_log,
                    },
                    fh,
                    indent=2,
                    ensure_ascii=False,
                )
        
        summary.append({"file": f.name, "elements_removed": removed_count})

    print(f"✓ Removal logs saved → {removed_log_dir.resolve()}\n")
    return pd.DataFrame(summary)


def reset_review_queue(queue_path, confirm=True):
    """Delete the review queue and start fresh.

    This wipes all your decisions and resets all items to 'pending'.
    Use this if you want to restart the review process from scratch.

    Args:
        queue_path: Path or str — the JSON queue file to reset
        confirm:    if True, prompts you before deleting (safety measure)

    Returns:
        bool: True if reset succeeded, False if cancelled
    """
    queue_path = Path(queue_path)
    
    if not queue_path.exists():
        print(f"ℹ Queue file does not exist: {queue_path}")
        return False
    
    if confirm:
        size_kb = queue_path.stat().st_size / 1024
        ans = input(f"⚠ Delete {queue_path.name} ({size_kb:.1f} KB) and reset all decisions? [y/n]: ").strip().lower()
        if ans != "y":
            print("Cancelled.")
            return False
    
    queue_path.unlink()
    print(f"✓ Queue deleted. Run generate_review_queue() to create a fresh one.")
    return True