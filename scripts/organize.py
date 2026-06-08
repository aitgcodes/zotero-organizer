#!/usr/bin/env python3
"""
Interactive pipeline orchestrator — runs all three stages in sequence.

All generated files are written to a workspace directory inside the project:
  <ORGANIZE_HOME>/collections/<collection>/

Usage:
  python scripts/organize.py [folder] [--collection NAME] [options]

Flags (all optional — guided prompts fill in the rest):
  --mode scaffold|auto|taxonomy  skip the Stage 2 prompt
  --no-ss                        skip Semantic Scholar DOI search
  --full-scan                    force a complete rescan even if scan.json exists
  --skip-scan                    skip Stage 1 entirely
  --dry-run                      stop after dry-run validation
  --workspace <path>             override the default workspace location
"""

import argparse, datetime, json, os, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))


def _home() -> Path:
    env = os.environ.get("ORGANIZE_HOME")
    if env:
        return Path(env).resolve()
    return SCRIPTS.parent.resolve()


def run(cmd) -> int:
    sys.stdout.flush()
    return subprocess.run(cmd).returncode


def ask(prompt, default=""):
    try:
        ans = input(prompt).strip()
    except EOFError:
        ans = ""
    return ans or default


def sep(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}", flush=True)


def _mtime_str(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _scan_summary(scan: dict) -> str:
    papers = scan.get("papers", {})
    n = len(papers)
    active = sum(1 for p in papers.values() if not p.get("removed"))
    return f"{active} files" + (f" ({n - active} removed)" if n != active else "")


def write_taxonomy_patch(new_rels: list[str], scan: dict, workspace: Path) -> Path:
    """Write a taxonomy_patch.yaml containing only the new/unplaced files."""
    import yaml
    from generate_batch import _collections_from_dirs

    papers = scan["papers"]
    dirs = {papers[r]["parent_dir"] for r in new_rels if papers[r]["parent_dir"] != "."}
    _, dir_to_leaf = _collections_from_dirs(dirs) if dirs else ([], {})
    root_coll = next(iter(dir_to_leaf.values()), scan["collection_name"])

    assignments, flagged = {}, []
    for rel in new_rels:
        p = papers.get(rel, {})
        if p.get("duplicate_of"):
            continue
        pd = p.get("parent_dir", ".")
        coll = dir_to_leaf.get(pd, root_coll) if pd != "." else root_coll
        if p.get("doi"):
            assignments[rel] = {"collection": coll, "tags": []}
        else:
            flagged.append({
                "file": rel,
                "search_query": " ".join((p.get("fallback_header") or "")[:150].split()),
                "collection": coll,
                "tags": [],
            })

    patch = {
        "assignments": assignments,
        "flagged": flagged,
        "books": [],
    }
    out = workspace / "taxonomy_patch.yaml"
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(patch, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Organize a PDF folder into Zotero end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folder", nargs="?", help="PDF folder path")
    parser.add_argument("--collection", help="Top-level Zotero collection name")
    parser.add_argument("--no-ss", action="store_true",
                        help="Skip Semantic Scholar DOI search in Stage 1")
    parser.add_argument("--mode", choices=["scaffold", "auto", "taxonomy"],
                        help="Stage 2 mode — skips the interactive prompt")
    parser.add_argument("--full-scan", action="store_true",
                        help="Force a complete rescan even if scan.json exists")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip Stage 1 entirely (use existing scan.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only; do not touch Zotero or Drive")
    parser.add_argument("--workspace",
                        help="Override default workspace path")
    args = parser.parse_args()

    # ── Resolve folder and collection name ────────────────────────────────────
    folder = args.folder or ask("PDF folder path: ")
    if not folder:
        sys.exit("Error: folder path required.")
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Error: '{folder}' is not a directory.")

    collection = args.collection or ask("Collection name: ")
    if not collection:
        sys.exit("Error: collection name required.")

    # ── Workspace ─────────────────────────────────────────────────────────────
    if args.workspace:
        workspace = Path(args.workspace).expanduser().resolve()
    else:
        workspace = _home() / "collections" / collection
    workspace.mkdir(parents=True, exist_ok=True)

    scan_json     = workspace / "scan.json"
    taxonomy_yaml = workspace / "taxonomy.yaml"
    batch_py      = workspace / "batch_run.py"
    state_file    = workspace / "state.json"

    print(f"\n  PDF folder : {folder}")
    print(f"  Collection : {collection}")
    print(f"  Workspace  : {workspace}")

    # ── Stage 1: Scan ─────────────────────────────────────────────────────────
    if args.skip_scan:
        if not scan_json.exists():
            sys.exit(f"Error: --skip-scan set but {scan_json} does not exist.")
        print(f"\nSkipping scan — using existing {scan_json.name}")
        scan = json.loads(scan_json.read_text())
        added, removed = [], []

    elif args.full_scan or not scan_json.exists():
        sep("Stage 1 — Full scan")
        cmd = [sys.executable, str(SCRIPTS / "scan_pdfs.py"),
               str(folder), "--collection", collection,
               "--output", str(scan_json), "--mode", "scan-only"]
        if args.no_ss:
            cmd.append("--no-ss")
        if run(cmd) != 0:
            sys.exit("Stage 1 failed.")
        scan = json.loads(scan_json.read_text())
        added, removed = [], []

    else:
        # Incremental scan
        from scan_pdfs import incremental_scan, walk_pdfs
        existing = json.loads(scan_json.read_text())
        known    = set(existing["papers"].keys())
        current  = set(walk_pdfs(folder))
        n_added  = len(current - known)
        n_removed = len(known - current)

        if n_added == 0 and n_removed == 0:
            print(f"\nScan up to date ({_scan_summary(existing)}) — skipping.")
            scan, added, removed = existing, [], []
        else:
            sep("Stage 1 — Scan")
            print(f"\nFound existing scan.json ({_mtime_str(scan_json)}, {_scan_summary(existing)}).")
            if n_added or n_removed:
                print(f"  {n_added} new PDF(s) detected, {n_removed} removed.")
            choice = ask(
                "  [1] Scan new files only (incremental)  [2] Full rescan  [3] Skip\n"
                "  Choice [1]: ", "1"
            )
            if choice == "3":
                scan, added, removed = existing, [], []
                print("Skipping scan.")
            elif choice == "2":
                sep("Stage 1 — Full scan")
                cmd = [sys.executable, str(SCRIPTS / "scan_pdfs.py"),
                       str(folder), "--collection", collection,
                       "--output", str(scan_json), "--mode", "scan-only"]
                if args.no_ss:
                    cmd.append("--no-ss")
                if run(cmd) != 0:
                    sys.exit("Stage 1 failed.")
                scan = json.loads(scan_json.read_text())
                added, removed = [], []
            else:
                sep("Stage 1 — Incremental scan")
                scan, added, removed = incremental_scan(folder, existing, not args.no_ss, current=current)
                scan_json.write_text(json.dumps(scan, indent=2, ensure_ascii=False))
                n_res = sum(1 for r in added if scan["papers"][r].get("doi"))
                print(f"\nScan updated. +{len(added)} files ({n_res} resolved, "
                      f"{len(added)-n_res} unresolved), -{len(removed)} removed.")

    # ── Stage 2: Generate ─────────────────────────────────────────────────────
    sep("Stage 2 — Generate batch script")

    # If incremental scan found new files and taxonomy exists → patch, then exit
    if added and taxonomy_yaml.exists():
        patch_path = write_taxonomy_patch(added, scan, workspace)
        print(f"\n{len(added)} new paper(s) → {patch_path.name}")
        print("Review and merge into taxonomy.yaml, then re-run this command.")
        return

    mode = args.mode

    if taxonomy_yaml.exists() and not mode:
        print(f"\nFound existing taxonomy.yaml (last edited {_mtime_str(taxonomy_yaml)}).")
        choice = ask(
            "  [1] Use existing taxonomy  [2] Regenerate scaffold  [3] Auto-generate\n"
            "  Choice [1]: ", "1"
        )
        if choice == "2":
            mode = "scaffold"
        elif choice == "3":
            mode = "auto"
        else:
            mode = "taxonomy"

    if not mode:
        print("\nChoose how to build the collection structure:")
        print("  [1] Scaffold — generate taxonomy.yaml, edit manually        <-- default")
        print("  [2] Auto     — use subfolder names directly, no editing")
        print("  [3] LLM/Claude — use taxonomy.yaml edited with Claude or another LLM")
        print("      ⚠  Requires Claude Desktop (MCP server) or a separate LLM session")
        choice = ask("  Choice [1]: ", "1")
        if choice == "2":
            mode = "auto"
        elif choice == "3":
            mode = "taxonomy"
        else:
            mode = "scaffold"

    if mode == "scaffold":
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "scaffold", str(scan_json),
                "--output", str(taxonomy_yaml)]) != 0:
            sys.exit("Scaffold generation failed.")
        print(f"\ntaxonomy.yaml written → {taxonomy_yaml}")
        print("\nEdit it in your preferred editor, then re-run:")
        print(f"  python scripts/organize.py {folder} --collection {collection}")
        return

    elif mode == "taxonomy":
        if not taxonomy_yaml.exists():
            print("\nNo taxonomy.yaml found.")
            print("Generate a scaffold first:")
            print(f"  python scripts/organize.py {folder} --collection {collection} --mode scaffold")
            print("Then edit it (optionally with Claude), and re-run with --mode taxonomy.")
            return
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "taxonomy", str(taxonomy_yaml), str(scan_json),
                "--output", str(batch_py)]) != 0:
            sys.exit("Batch generation from taxonomy failed.")

    else:  # auto
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "auto", str(scan_json),
                "--output", str(batch_py)]) != 0:
            sys.exit("Auto batch generation failed.")

    if not batch_py.exists():
        sys.exit("Stage 2 failed — batch script not generated.")

    # ── Stage 3: Dry run ──────────────────────────────────────────────────────
    sep("Stage 3 — Dry run validation")
    run([sys.executable, str(batch_py), "--dry-run"])

    if args.dry_run:
        print("\n--dry-run set. Stopping here.")
        print(f"To run for real:  python {batch_py}")
        return

    # ── Stage 3: Real run ─────────────────────────────────────────────────────
    print()
    confirm = ask(
        "Run for real? This will create Zotero items and upload to Drive. [y/N] ", "n"
    )
    if confirm.lower() != "y":
        print(f"Aborted. Run manually:  python {batch_py}")
        return

    if state_file.exists():
        import json as _json
        _state = _json.loads(state_file.read_text())
        _done = sum(1 for v in _state.get("papers", {}).values() if v.get("done"))
        if _done > 0:
            print(f"\n  Resuming: {_done} paper(s) already done — state preserved.")
        else:
            state_file.unlink()

    sep("Stage 3 — Running batch")
    run([sys.executable, str(batch_py)])


if __name__ == "__main__":
    main()
