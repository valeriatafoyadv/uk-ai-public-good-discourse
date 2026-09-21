#!/usr/bin/env python3
"""Phase 6 finalize -- single entry point re-running the analysis chain.

Every step downstream of Round 1 coding is idempotent, so re-running this
script regenerates every output from whatever is currently on disk.

A dated copy of coding/guidebook_draft.yaml is made first (step 1 overwrites
that file, including the hand recoding of BENEFICIARY and MECHANISM).

Steps, in order, continuing past individual failures so one broken step never
blocks the rest:
    1. scripts/06_consolidate.py       (guidebook_draft.yaml, metaphors_report.md)
    2. scripts/06_network_v0.py + re-embed the refreshed intertextual_v0.json
       into analysis/networks/authorship_family_map.html (regex-replaces the
       `const DATA = {...};` object in place; verified with json.loads before
       and after the write)
    3. scripts/11_agency_query.py      (analysis/queries/agency_by_genre.csv)
    4. scripts/07b_queries.py          (analysis/queries/queries.html, 3 charts)

Prints a final step -> ok/failed summary table and exits non-zero if any step
failed (so it's script-able / cron-able without silently swallowing errors).

Usage:
    .venv/bin/python scripts/10_finalize.py
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PYTHON = sys.executable  # the venv interpreter running this script

INTERTEXTUAL_JSON = ROOT / "analysis" / "networks" / "intertextual_v0.json"
AUTHORSHIP_HTML = ROOT / "analysis" / "networks" / "authorship_family_map.html"

DATA_RE = re.compile(r"const DATA = (\{.*?\});\n", re.S)

results = []  # list of (step_name, ok: bool, detail: str)


def log(msg):
    print(f"[10_finalize] {msg}")


def run_step(name, fn):
    log(f"--- {name} " + "-" * max(1, 60 - len(name)))
    t0 = time.time()
    try:
        detail = fn()
        dt = time.time() - t0
        log(f"OK ({dt:.1f}s)")
        results.append((name, True, detail or ""))
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: keep going
        dt = time.time() - t0
        log(f"FAILED ({dt:.1f}s): {exc}")
        results.append((name, False, str(exc)))


def run_script(rel_path, args=None):
    """Run a scripts/<rel_path> with the same interpreter, streaming its
    stdout/stderr, and raise if it exits non-zero."""
    cmd = [PYTHON, str(SCRIPTS / rel_path)] + (args or [])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"{rel_path} exited with code {proc.returncode}")
    return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""


def step_network_and_reembed():
    run_script("06_network_v0.py")

    if not INTERTEXTUAL_JSON.exists():
        raise RuntimeError(f"{INTERTEXTUAL_JSON} was not produced by 06_network_v0.py")
    if not AUTHORSHIP_HTML.exists():
        raise RuntimeError(f"{AUTHORSHIP_HTML} does not exist -- nothing to re-embed into")

    new_data = json.loads(INTERTEXTUAL_JSON.read_text(encoding="utf-8"))
    new_data_str = json.dumps(new_data, indent=1, ensure_ascii=False)

    html = AUTHORSHIP_HTML.read_text(encoding="utf-8")
    m = DATA_RE.search(html)
    if not m:
        raise RuntimeError("could not find 'const DATA = {...};' in authorship_family_map.html")

    # Sanity-check the OLD embedded object also still parses, so a broken
    # re-embed is never blamed on pre-existing corruption.
    json.loads(m.group(1))

    new_html = html[:m.start(1)] + new_data_str + html[m.end(1):]
    AUTHORSHIP_HTML.write_text(new_html, encoding="utf-8")

    # Verify: re-extract from the file we just wrote and confirm it parses
    # and matches what we intended to embed.
    verify_html = AUTHORSHIP_HTML.read_text(encoding="utf-8")
    m2 = DATA_RE.search(verify_html)
    if not m2:
        raise RuntimeError("post-write verification failed: DATA object no longer found")
    verify_obj = json.loads(m2.group(1))
    if len(verify_obj.get("nodes", [])) != len(new_data.get("nodes", [])) or \
       len(verify_obj.get("edges", [])) != len(new_data.get("edges", [])):
        raise RuntimeError("post-write verification failed: node/edge counts do not match")

    return (f"re-embedded {len(new_data['nodes'])} nodes, {len(new_data['edges'])} edges; "
            "json.loads verified")


def backup_guidebook():
    src = ROOT / "coding" / "guidebook_draft.yaml"
    if src.exists():
        dst = src.with_name("guidebook_draft.backup-" + time.strftime("%Y%m%d-%H%M%S") + ".yaml")
        shutil.copy2(src, dst)
        log(f"backed up {src.name} -> {dst.name}")


def main():
    backup_guidebook()
    run_step("1. scripts/06_consolidate.py", lambda: run_script("06_consolidate.py"))
    run_step("2. scripts/06_network_v0.py + re-embed authorship_family_map.html",
              step_network_and_reembed)
    run_step("3. scripts/11_agency_query.py", lambda: run_script("11_agency_query.py"))
    run_step("4. scripts/07b_queries.py", lambda: run_script("07b_queries.py"))

    print("\n" + "=" * 78)
    print("FINALIZE SUMMARY")
    print("=" * 78)
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        status = "OK" if ok else "FAILED"
        print(f"{name.ljust(width)}  {status}" + (f"  -- {detail}" if detail else ""))
    print("=" * 78)

    n_failed = sum(1 for _, ok, _ in results if not ok)
    if n_failed:
        print(f"{n_failed}/{len(results)} step(s) failed -- see log above for details.")
        sys.exit(1)
    else:
        print(f"All {len(results)} steps completed. Coverage banners in individual outputs "
              "still apply if Round 1 coding is not yet at 100% -- check each file's own "
              "STATUS line.")


if __name__ == "__main__":
    main()
