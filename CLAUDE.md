# Claudetoro — developer reference

## Project layout

| File / folder | Role | Claude needed? |
|---------------|------|---------------|
| `zotero_mcp.py` | MCP server — exposes Zotero tools to Claude Desktop | Yes (Claude Desktop) |
| `scripts/scan_pdfs.py` | Stage 1 — scans a PDF folder, extracts DOIs, writes `scan.json` | No |
| `scripts/generate_batch.py` | Stage 2/3 bridge — builds `taxonomy.yaml` scaffold or generates `batch_run.py` | No (Claude optional for taxonomy editing) |
| `scripts/batch_template.py` | Shared async runner template consumed by `generate_batch.py` | No |
| `requirements.txt` | Minimal CLI deps (`pyzotero`, `pypdf`, `pyyaml`, `python-dotenv`) | — |
| `environment.yml` | Full `claudotero` conda env (CLI deps + `mcp` for MCP server) | — |

## Environment

The `claudotero` conda environment is required for MCP server development (it includes
`mcp`). The CLI pipeline only needs the packages in `requirements.txt`.

```bash
# Full env (MCP + CLI):
conda env create -f environment.yml
conda activate claudotero

# CLI pipeline only (no conda required):
pip install -r requirements.txt
```

## CLI pipeline — stage logic

### Stage 1 — `scripts/scan_pdfs.py`

Walks a folder recursively, extracts DOIs via a 4-step fallback chain:
1. PDF metadata dict (`/doi`, `/DOI`, `/Subject`)
2. Page-1 text regex (`_DOI_RE`, `_ARXIV_RE`)
3. Semantic Scholar title search (skipped with `--no-ss`)
4. Unresolved — stores first 300 chars of page-1 text as `fallback_header`

Detects duplicates by DOI across all files. Writes `scan.json`:
```json
{
  "base": "/abs/path",
  "collection_name": "Plasmons",
  "papers": {
    "rel/file.pdf": {
      "doi": "10.xxx/xxx",
      "doi_source": "metadata|page1|ss_search|unresolved",
      "title": "", "abstract_snippet": "",
      "parent_dir": "PlasmonCatalysis",
      "duplicate_of": null
    }
  }
}
```

If subdirectories are detected, prompts for generation mode (unless `--mode` is passed).

### Stage 2 — `scripts/generate_batch.py`

Three modes:

| Mode | Input | Output | When to use |
|------|-------|--------|-------------|
| `scaffold` | `scan.json` | `taxonomy.yaml` pre-filled from subfolders | Edit manually or hand to Claude |
| `auto` | `scan.json` | `batch_run.py` directly | Subfolder structure is already the desired collection layout |
| `taxonomy` | `taxonomy.yaml` + `scan.json` | `batch_run.py` | After editing/reviewing the scaffold |

`taxonomy.yaml` format:
```yaml
base_collection: "Plasmons"
collections:
  - name: "Quantum-Plasmonics"
    parent: null
  - name: "Hydrodynamic-Modeling"
    parent: "Quantum-Plasmonics"
assignments:
  "rel/file.pdf":
    collection: "Quantum-Plasmonics"
    tags: ["tag1", "tag2"]
flagged:
  - file: "rel/unresolved.pdf"
    search_query: "Semantic Scholar title query"
    collection: "Quantum-Plasmonics"
    tags: []
books:
  - file: "rel/book.pdf"
    type: "book"            # book | thesis | document
    title: "Full title"
    authors: [{first: "First", last: "Last"}]
    year: "2006"
    extra: {publisher: "Springer"}
    collection: "Books-Notes"
    tags: []
```

Drive folder paths are derived from the collection hierarchy:
`Hydrodynamic-Modeling` with parent `Quantum-Plasmonics` under `Plasmons` →
`Plasmons/Quantum-Plasmonics/Hydrodynamic-Modeling`.

### Stage 3 — generated `batch_run.py`

Self-contained async script rendered from `scripts/batch_template.py`. Flags:

| Flag | Effect |
|------|--------|
| *(none)* | Full run: create Zotero collections + items + Drive upload + URL attachment |
| `--dry-run` | Print what would happen; no Zotero or Drive changes (~1s) |
| `--mode drive-only` | Skip Zotero item creation; upload to Drive and attach URL to existing items |

Resumable: progress is tracked in `collections/<Name>/state.json`.

Drive pre-flight check: on the first real run (state empty), `_preflight_drive_check()`
runs `rclone lsf` on the base collection folder. If it already has content the user
is prompted to merge (adds `--ignore-existing` to rclone copy), overwrite, redirect to
a timestamped folder, or abort. Skipped in dry-run and on resume.

Concurrency: up to 5 papers in parallel (`asyncio.Semaphore(5)`); Drive upload and
Semantic Scholar lookup run concurrently per paper via `asyncio.gather`.

## MCP tools

| Tool | Description |
|------|-------------|
| `create_collection` | Create a Zotero collection; optional `parent_key` for nested collections |
| `extract_doi_from_local_pdf` | Extract DOI (metadata → page-1 regex → SS title search → fallback header) |
| `add_item_by_doi` | Resolve DOI via Semantic Scholar, create Zotero item, add to collection |
| `upload_pdf_to_drive` | Upload PDF to Drive via rclone; `collection_path` sets hierarchical subfolder |
| `add_url_attachment` | Attach a URL to an existing Zotero item |
| `get_drive_folder_id` | Return configured `GOOGLE_DRIVE_FOLDER_ID` |
| `get_collection_structure` | Return sub-collections and items of a collection key |
| `add_tags_to_item` | Add tags to an existing Zotero item (deduplicates against existing tags) |

## Environment variables

| Variable | Description |
|----------|-------------|
| `ZOTERO_USER_ID` | Numeric Zotero user ID |
| `ZOTERO_API_KEY` | Zotero API key (Read/Write) |
| `GOOGLE_DRIVE_FOLDER_ID` | Google Drive folder ID (from the folder URL) |
| `RCLONE_REMOTE` | rclone remote name (e.g. `gdrive`) |

## Setup notes

- rclone must be configured with a Google account that has access to the Drive folder
- MCP server config: `~/Library/Application Support/Claude/claude_desktop_config.json`
- The `mcp` package is only needed for `zotero_mcp.py`; the CLI scripts import it nowhere
