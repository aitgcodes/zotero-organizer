#!/usr/bin/env python3
"""
Interactive pipeline orchestrator — runs all three stages in sequence.

Usage:
  python scripts/organize.py [folder] [--collection NAME]
                             [--no-ss] [--mode scaffold|auto|taxonomy]
                             [--dry-run] [--skip-scan]

Stages:
  1  scan_pdfs.py       Extract DOIs, write scan.json
  2  generate_batch.py  Build taxonomy scaffold or batch script
  3  batch_run.py       Create Zotero collections, upload to Drive
"""

import argparse, os, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).parent


def run(cmd):
    result = subprocess.run(cmd)
    return result.returncode


def ask(prompt, default=""):
    try:
        answer = input(prompt).strip()
    except EOFError:
        answer = ""
    return answer or default


def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Organize a PDF folder into Zotero end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folder", nargs="?", help="PDF folder path")
    parser.add_argument("--collection", help="Top-level Zotero collection name")
    parser.add_argument("--no-ss", action="store_true",
                        help="Skip Semantic Scholar DOI search")
    parser.add_argument("--mode", choices=["scaffold", "auto", "taxonomy"],
                        help="Stage 2 mode — skips the interactive prompt")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only; do not touch Zotero or Drive")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip Stage 1 and use existing scan.json")
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

    scan_json    = folder / "scan.json"
    taxonomy_yaml = folder / "taxonomy.yaml"
    batch_py     = Path(f"/tmp/{collection}_batch.py")
    state_file   = Path(f"/tmp/{collection}_batch_state.json")

    # ── Stage 1: Scan ─────────────────────────────────────────────────────────
    if args.skip_scan:
        if not scan_json.exists():
            sys.exit(f"Error: --skip-scan set but {scan_json} does not exist.")
        print(f"Skipping scan — using {scan_json}")
    else:
        sep("Stage 1 — Scan PDFs")
        cmd = [sys.executable, str(SCRIPTS / "scan_pdfs.py"),
               str(folder), "--collection", collection, "--mode", "scan-only"]
        if args.no_ss:
            cmd.append("--no-ss")
        if run(cmd) != 0:
            sys.exit("Stage 1 failed.")

    # ── Stage 2: Generate ─────────────────────────────────────────────────────
    sep("Stage 2 — Generate batch script")

    mode = args.mode
    if not mode:
        print("\nOptions:")
        print("  [1] Use subfolder structure directly          (auto)")
        print("  [2] Edit a taxonomy scaffold first            (scaffold)  <-- default")
        print("  [3] Use existing taxonomy.yaml               (taxonomy)")
        choice = ask("Choice [2]: ", "2")
        if choice == "1":
            mode = "auto"
        elif choice == "3":
            mode = "taxonomy"
        else:
            mode = "scaffold"

    if mode == "scaffold":
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "scaffold", str(scan_json)]) != 0:
            sys.exit("Scaffold generation failed.")
        print(f"\nTaxonomy written to: {taxonomy_yaml}")
        print("Edit it, then press Enter to continue (Ctrl-C to abort).")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "taxonomy", str(taxonomy_yaml), str(scan_json),
                "--output", str(batch_py)]) != 0:
            sys.exit("Batch generation from taxonomy failed.")

    elif mode == "taxonomy":
        if not taxonomy_yaml.exists():
            sys.exit(f"Error: {taxonomy_yaml} does not exist. Run scaffold mode first.")
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "taxonomy", str(taxonomy_yaml), str(scan_json),
                "--output", str(batch_py)]) != 0:
            sys.exit("Batch generation from taxonomy failed.")

    else:  # auto
        if run([sys.executable, str(SCRIPTS / "generate_batch.py"),
                "--mode", "auto", str(scan_json), "--output", str(batch_py)]) != 0:
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

    # Clear state file so dry-run results don't cause skips
    if state_file.exists():
        state_file.unlink()

    sep("Stage 3 — Running batch")
    run([sys.executable, str(batch_py)])


if __name__ == "__main__":
    main()
