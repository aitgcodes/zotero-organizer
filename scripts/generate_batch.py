#!/usr/bin/env python3
"""
Stage 2/3 bridge — build taxonomy.yaml scaffold or generate a complete batch_run.py.

Modes:
  scaffold   Read scan.json → write taxonomy.yaml pre-filled from subfolder structure.
  auto       Read scan.json → write batch_run.py directly (no taxonomy.yaml needed).
  taxonomy   Read taxonomy.yaml + scan.json → write batch_run.py.

Usage:
  # Scaffold from scan:
  python scripts/generate_batch.py --mode scaffold <scan.json> [--output <taxonomy.yaml>]

  # Auto (no human input):
  python scripts/generate_batch.py --mode auto <scan.json> [--output <batch.py>]

  # From taxonomy:
  python scripts/generate_batch.py --mode taxonomy <taxonomy.yaml> <scan.json> [--output <batch.py>]
"""

import argparse, datetime, json, os, sys
from pathlib import Path

import yaml  # pyyaml
from batch_template import TEMPLATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_scan(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_taxonomy(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _derive_drive_paths(base_collection: str, collections: list[dict]) -> dict[str, str]:
    """Walk the parent chain for each collection and build its full Drive path."""
    parent_of = {c["name"]: c.get("parent") for c in collections}
    paths = {}
    def path_for(name):
        if name in paths:
            return paths[name]
        parent = parent_of.get(name)
        if parent:
            paths[name] = f"{path_for(parent)}/{name}"
        else:
            paths[name] = f"{base_collection}/{name}"
        return paths[name]
    for c in collections:
        path_for(c["name"])
    return paths


def _topo_order(collections: list[dict]) -> list[tuple[str, str | None]]:
    """Return (name, parent_name) in topological order (parents before children)."""
    parent_of = {c["name"]: c.get("parent") for c in collections}
    order = []
    visited = set()
    def visit(name):
        if name in visited:
            return
        p = parent_of.get(name)
        if p:
            visit(p)
        visited.add(name)
        order.append((name, p))
    for c in collections:
        visit(c["name"])
    return order


# ---------------------------------------------------------------------------
# Scaffold mode
# ---------------------------------------------------------------------------

def run_scaffold(scan: dict, output: Path):
    base_collection = scan["collection_name"]
    papers = scan["papers"]

    # Build collection list from unique parent_dir values
    subdirs = sorted({p["parent_dir"] for p in papers.values() if p["parent_dir"] != "."})
    root_dir = "." in {p["parent_dir"] for p in papers.values()}

    collections = [{"name": d, "parent": None} for d in subdirs]
    if root_dir and not subdirs:
        collections = [{"name": base_collection, "parent": None}]

    # Build assignments
    assignments = {}
    flagged = []
    for rel, p in papers.items():
        if p.get("duplicate_of"):
            continue
        coll = p["parent_dir"] if p["parent_dir"] != "." else (subdirs[0] if subdirs else base_collection)
        if p["doi"]:
            assignments[rel] = {
                "collection": coll,
                "tags": [],
            }
        else:
            flagged.append({
                "file": rel,
                "search_query": " ".join(p.get("fallback_header", "")[:150].split()),
                "collection": coll,
                "tags": [],
            })

    taxonomy = {
        "base_collection": base_collection,
        "collections": collections,
        "assignments": assignments,
        "flagged": flagged,
        "books": [],
    }

    with open(output, "w", encoding="utf-8") as f:
        yaml.dump(taxonomy, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"Scaffold written → {output}")
    print(f"  {len(assignments)} assigned  |  {len(flagged)} flagged  |  {len(collections)} collections")
    print(f"\nEdit {output} then run:")
    print(f"  python scripts/generate_batch.py --mode taxonomy {output} <scan.json> --output /tmp/{base_collection}_batch.py")


# ---------------------------------------------------------------------------
# Batch generation (auto + taxonomy modes)
# ---------------------------------------------------------------------------

def build_manifests_from_scan(scan: dict):
    """Auto mode: use parent_dir as collection name."""
    papers_list, flagged_list, books_list = [], [], []
    base_collection = scan["collection_name"]

    for rel, p in scan["papers"].items():
        if p.get("duplicate_of"):
            continue
        coll = p["parent_dir"] if p["parent_dir"] != "." else base_collection
        tags = []
        if p["doi"]:
            papers_list.append((rel, p["doi"], coll, tags))
        else:
            query = " ".join(p.get("fallback_header", "")[:150].split())
            flagged_list.append((rel, query, coll, tags))

    return papers_list, flagged_list, books_list


def build_manifests_from_taxonomy(taxonomy: dict, scan: dict):
    """Taxonomy mode: merge DOIs from scan into taxonomy assignments."""
    papers_list, flagged_list, books_list = [], [], []
    scan_papers = scan["papers"]

    for rel, info in (taxonomy.get("assignments") or {}).items():
        coll = info["collection"]
        tags = info.get("tags") or []
        doi  = (scan_papers.get(rel) or {}).get("doi") or info.get("doi", "")
        if doi:
            papers_list.append((rel, doi, coll, tags))
        else:
            query = " ".join((scan_papers.get(rel, {}).get("fallback_header") or "")[:150].split())
            flagged_list.append((rel, query, coll, tags))

    for item in (taxonomy.get("flagged") or []):
        flagged_list.append((
            item["file"],
            item.get("search_query", ""),
            item["collection"],
            item.get("tags") or [],
        ))

    for b in (taxonomy.get("books") or []):
        authors = b.get("authors") or [{}]
        first = authors[0].get("first", "")
        last  = authors[0].get("last", "")
        books_list.append((
            b["file"],
            b.get("type", "book"),
            b.get("title", ""),
            first, last,
            str(b.get("year", "")),
            b.get("extra") or {},
            b["collection"],
            b.get("tags") or [],
        ))

    return papers_list, flagged_list, books_list


def build_collections_from_scan(scan: dict):
    base_collection = scan["collection_name"]
    subdirs = sorted({p["parent_dir"] for p in scan["papers"].values() if p["parent_dir"] != "."})
    colls = [{"name": d, "parent": None} for d in subdirs]
    return base_collection, colls


def render_batch(
    base: str,
    state_file: str,
    collection_name: str,
    collections: list[dict],
    papers: list, flagged: list, books: list,
    scan_path: str = "",
) -> str:
    env_path         = str(Path(__file__).parent.parent / ".env")
    coll_drive_path  = _derive_drive_paths(collection_name, collections)
    collection_order = _topo_order(collections)

    return TEMPLATE.format(
        generated_at     = datetime.datetime.now().isoformat(timespec="seconds"),
        collection_name  = collection_name,
        scan_path        = scan_path,
        env_path         = env_path,
        base             = base,
        state_file       = state_file,
        global_tag       = collection_name,
        coll_drive_path  = coll_drive_path,
        papers           = papers,
        flagged          = flagged,
        books            = books,
        collection_order = collection_order,
    )


def run_generate(scan: dict, taxonomy: dict | None, output: Path, mode: str):
    base           = scan["base"]
    collection_name = scan["collection_name"]
    state_file     = f"/tmp/{collection_name}_batch_state.json"
    scan_path      = str(output.parent / "scan.json")  # best-effort

    if mode == "auto":
        papers, flagged, books = build_manifests_from_scan(scan)
        _, collections = build_collections_from_scan(scan)
    else:
        papers, flagged, books = build_manifests_from_taxonomy(taxonomy, scan)
        collections = taxonomy.get("collections") or []

    code = render_batch(base, state_file, collection_name, collections,
                        papers, flagged, books, scan_path)

    with open(output, "w", encoding="utf-8") as f:
        f.write(code)
    os.chmod(output, 0o755)
    print(f"Batch script written → {output}")
    print(f"  {len(papers)} papers  |  {len(flagged)} flagged  |  {len(books)} books/notes")
    print(f"\nRun with:")
    print(f"  conda run -n claudotero python {output}")
    print(f"  conda run -n claudotero python {output} --mode drive-only")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate taxonomy scaffold or batch script.")
    parser.add_argument("--mode", choices=["scaffold", "auto", "taxonomy"], required=True)
    parser.add_argument("inputs", nargs="+",
                        help="scaffold/auto: <scan.json> | taxonomy: <taxonomy.yaml> <scan.json>")
    parser.add_argument("--output", "-o", help="Output file path")
    args = parser.parse_args()

    if args.mode == "scaffold":
        if len(args.inputs) != 1:
            sys.exit("scaffold mode requires exactly one argument: <scan.json>")
        scan = load_scan(args.inputs[0])
        out  = Path(args.output) if args.output else Path(scan["base"]) / "taxonomy.yaml"
        run_scaffold(scan, out)

    elif args.mode == "auto":
        if len(args.inputs) != 1:
            sys.exit("auto mode requires exactly one argument: <scan.json>")
        scan = load_scan(args.inputs[0])
        out  = Path(args.output) if args.output else Path(f"/tmp/{scan['collection_name']}_batch.py")
        run_generate(scan, None, out, "auto")

    elif args.mode == "taxonomy":
        if len(args.inputs) != 2:
            sys.exit("taxonomy mode requires two arguments: <taxonomy.yaml> <scan.json>")
        taxonomy = load_taxonomy(args.inputs[0])
        scan     = load_scan(args.inputs[1])
        out      = Path(args.output) if args.output else Path(f"/tmp/{scan['collection_name']}_batch.py")
        run_generate(scan, taxonomy, out, "taxonomy")


if __name__ == "__main__":
    main()
