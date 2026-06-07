#!/usr/bin/env python3
"""
Stage 1 — PDF scanner.

Walks a folder, extracts DOIs via the same 4-step chain used by zotero_mcp.py:
  1. PDF metadata dict
  2. Page-1 DOI/arXiv regex
  3. Semantic Scholar title search (skipped with --no-ss)
  4. Unresolved — stores fallback header for manual review

Writes scan.json. Can also be imported by organize.py for incremental scanning.

Usage:
  python scripts/scan_pdfs.py <folder> --collection <Name> [--output <path>] [--no-ss]
"""

import argparse, json, os, re, sys, time
from pathlib import Path

import pypdf
from pyzotero.semantic_scholar import search_papers, SemanticScholarError

_DOI_RE   = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)
SS_DELAY  = 1.5  # seconds between Semantic Scholar calls


def extract_doi(pdf_path: str, use_ss: bool) -> dict:
    """Return a dict with keys: doi, doi_source, title, abstract_snippet, fallback_header."""
    result = {"doi": None, "doi_source": None, "title": "", "abstract_snippet": "", "fallback_header": ""}

    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception as exc:
        result["doi_source"] = "error"
        result["fallback_header"] = str(exc)
        return result

    if reader.is_encrypted:
        result["doi_source"] = "encrypted"
        return result

    # 1. Metadata dict
    try:
        meta = reader.metadata or {}
    except Exception:
        meta = {}
    for key in ("/doi", "/DOI", "/Subject", "/subject"):
        raw = meta.get(key, "") or ""
        m = _DOI_RE.search(raw)
        if m:
            result["doi"] = m.group(0)
            result["doi_source"] = "metadata"
            return result
        a = _ARXIV_RE.search(raw)
        if a:
            result["doi"] = f"10.48550/arXiv.{a.group(1)}"
            result["doi_source"] = "metadata"
            return result

    # 2. Page-1 text
    if not reader.pages:
        result["doi_source"] = "unresolved"
        return result
    try:
        page1 = reader.pages[0].extract_text() or ""
    except Exception:
        page1 = ""

    m = _DOI_RE.search(page1)
    if m:
        result["doi"] = m.group(0)
        result["doi_source"] = "page1"
        return result
    a = _ARXIV_RE.search(page1)
    if a:
        result["doi"] = f"10.48550/arXiv.{a.group(1)}"
        result["doi_source"] = "page1"
        return result

    # 3. Semantic Scholar title search
    if use_ss and page1.strip():
        title_query = " ".join(page1.split())[:150]
        time.sleep(SS_DELAY)
        try:
            results = search_papers(title_query, limit=3)
            for paper in results.get("papers", []):
                doi = paper.get("doi")
                if doi:
                    result["doi"] = doi
                    result["doi_source"] = "ss_search"
                    result["title"] = paper.get("title", "")
                    result["abstract_snippet"] = (paper.get("abstract") or "")[:300]
                    return result
        except SemanticScholarError:
            pass

    # 4. Unresolved
    result["doi_source"] = "unresolved"
    result["fallback_header"] = page1[:300].strip()
    return result


def walk_pdfs(base: Path) -> list[str]:
    """Return sorted relative paths of all PDFs under base."""
    rel_files = []
    for root, _dirs, files in os.walk(base):
        for fname in sorted(files):
            if fname.lower().endswith(".pdf"):
                rel = str(Path(root, fname).relative_to(base))
                rel_files.append(rel)
    return rel_files


def _scan_files(base: Path, rel_files: list[str], use_ss: bool,
                offset: int = 0, total: int | None = None) -> dict[str, dict]:
    """Extract DOI info for a list of relative paths. Returns papers dict."""
    papers = {}
    n = total or len(rel_files)
    for i, rel in enumerate(rel_files, offset + 1):
        abs_path = str(base / rel)
        _parts = Path(rel).parts
        parent_dir = str(Path(*_parts[:-1])) if len(_parts) > 1 else "."
        print(f"  [{i:>3}/{n}] {rel[:70]}", end="", flush=True)
        info = extract_doi(abs_path, use_ss)
        papers[rel] = {
            "doi":              info["doi"],
            "doi_source":       info["doi_source"],
            "title":            info["title"],
            "abstract_snippet": info["abstract_snippet"],
            "fallback_header":  info["fallback_header"],
            "parent_dir":       parent_dir,
            "duplicate_of":     None,
        }
        print(f"  [{info['doi_source'] or '?'}]")
    return papers


def _detect_duplicates(papers: dict[str, dict]) -> None:
    """Mark duplicates in-place. Keeps the most-nested copy (deepest path wins)."""
    doi_groups: dict[str, list[str]] = {}
    for rel, p in papers.items():
        doi = (p["doi"] or "").lower()
        if doi:
            doi_groups.setdefault(doi, []).append(rel)
    for doi, rels in doi_groups.items():
        if len(rels) == 1:
            continue
        canonical = max(rels, key=lambda r: (len(Path(r).parts), r))
        for rel in rels:
            if rel != canonical:
                papers[rel]["duplicate_of"] = canonical
                print(f"  DUPLICATE: {rel}  (kept deeper: {canonical})")


def incremental_scan(base: Path, existing: dict, use_ss: bool) -> tuple[dict, list[str], list[str]]:
    """
    Diff the PDF folder against an existing scan dict.

    Returns:
        (updated_scan, added_rels, removed_rels)
    added_rels  — files in folder but not in existing scan
    removed_rels — files in existing scan but no longer on disk (flagged, not deleted)
    """
    known   = set(existing["papers"].keys())
    current = set(walk_pdfs(base))
    added   = sorted(current - known)
    removed = sorted(known - current)

    papers = dict(existing["papers"])

    for rel in removed:
        papers[rel]["removed"] = True
        print(f"  REMOVED: {rel}")

    if added:
        print(f"Scanning {len(added)} new file(s)...")
        if use_ss:
            print(f"  Semantic Scholar title-search enabled (throttled at {SS_DELAY}s/call).")
        new_papers = _scan_files(base, added, use_ss,
                                 offset=len(known), total=len(known) + len(added))
        papers.update(new_papers)
        _detect_duplicates(papers)

    updated = {**existing, "papers": papers}
    return updated, added, removed


def detect_subdirs(base: Path, rel_files: list[str]) -> list[str]:
    """Return unique immediate subdirectory names that contain PDFs."""
    subdirs = set()
    for rel in rel_files:
        parts = Path(rel).parts
        if len(parts) > 1:
            subdirs.add(parts[0])
    return sorted(subdirs)


def prompt_mode(subdirs: list[str]) -> str:
    """Ask user which generation mode to use after scanning. Returns 'auto', 'scaffold', or 'scan-only'."""
    print(f"\nDetected subfolder structure: {', '.join(subdirs)}/")
    print("Options:")
    print("  [1] Use subfolder structure as collections directly  (auto)")
    print("  [2] Generate editable taxonomy.yaml scaffold         (scaffold)  <-- default")
    print("  [3] Output scan.json only")
    try:
        choice = input("Choice [2]: ").strip()
    except EOFError:
        choice = "2"
    if choice == "1":
        return "auto"
    if choice == "3":
        return "scan-only"
    return "scaffold"


def main():
    parser = argparse.ArgumentParser(description="Scan a PDF folder and extract DOIs.")
    parser.add_argument("folder", help="Root folder containing PDFs")
    parser.add_argument("--collection", required=True, help="Top-level Zotero collection name")
    parser.add_argument("--output", help="Path for scan.json (default: <folder>/scan.json)")
    parser.add_argument("--no-ss", action="store_true", help="Skip Semantic Scholar title search")
    parser.add_argument("--mode", choices=["auto", "scaffold", "scan-only"],
                        help="Generation mode after scan (skips prompt if provided)")
    args = parser.parse_args()

    base = Path(args.folder).resolve()
    if not base.is_dir():
        sys.exit(f"Error: '{base}' is not a directory.")

    output_path = Path(args.output) if args.output else base / "scan.json"
    use_ss = not args.no_ss

    rel_files = walk_pdfs(base)
    if not rel_files:
        sys.exit(f"No PDF files found in '{base}'.")

    print(f"Found {len(rel_files)} PDF files. Extracting DOIs...")
    if use_ss:
        print(f"  Semantic Scholar title-search enabled (throttled at {SS_DELAY}s/call).")
    else:
        print("  Semantic Scholar title-search disabled (--no-ss).")

    papers = _scan_files(base, rel_files, use_ss)
    _detect_duplicates(papers)

    scan = {
        "base":            str(base),
        "collection_name": args.collection,
        "papers":          papers,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scan, f, indent=2, ensure_ascii=False)
    print(f"\nScan complete. {len(papers)} files → {output_path}")

    n_resolved   = sum(1 for p in papers.values() if p["doi"] and not p["duplicate_of"])
    n_unresolved = sum(1 for p in papers.values() if not p["doi"] and not p["duplicate_of"])
    n_dupes      = sum(1 for p in papers.values() if p["duplicate_of"])
    print(f"  Resolved: {n_resolved}  |  Unresolved: {n_unresolved}  |  Duplicates: {n_dupes}")

    subdirs = detect_subdirs(base, rel_files)
    if args.mode:
        mode = args.mode
    elif subdirs:
        mode = prompt_mode(subdirs)
    else:
        print("\nNo subdirectories found. Run generate_batch.py --mode scaffold manually.")
        mode = "scan-only"

    if mode in ("auto", "scaffold"):
        generate_script = Path(__file__).parent / "generate_batch.py"
        import subprocess, sys as _sys
        cmd = [
            _sys.executable, str(generate_script),
            "--mode", mode,
            str(output_path),
        ]
        print(f"\nRunning: {' '.join(cmd)}")
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
