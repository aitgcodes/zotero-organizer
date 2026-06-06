# Claudetoro

## Environment

All components of this project must be implemented and run within the **claudotero** conda environment.

To activate it:
```
conda activate claudotero
```

## Project Overview

A Zotero MCP server (`zotero_mcp.py`) that exposes tools for organizing local PDF files into Zotero collections. Registered in Claude Desktop as the `zotero` MCP server.

## MCP Tools

| Tool | Description |
|------|-------------|
| `create_collection` | Create a new top-level Zotero collection, returns its key |
| `extract_doi_from_local_pdf` | Extract DOI from a local PDF (metadata → page 1 regex → Semantic Scholar title search → fallback header text) |
| `add_item_by_doi` | Resolve a DOI via Semantic Scholar, create the Zotero item, add it to a collection |
| `upload_pdf_to_drive` | Upload a local PDF to Google Drive via rclone, returns a shareable URL |
| `add_url_attachment` | Attach a URL (e.g. Drive link) to an existing Zotero item |
| `get_drive_folder_id` | Return the configured `GOOGLE_DRIVE_FOLDER_ID` |

## Typical Workflow

1. `extract_doi_from_local_pdf` — get the DOI from the PDF
2. `create_collection` (if needed) — create a Zotero collection
3. `add_item_by_doi` — add the paper's metadata to Zotero under that collection
4. `upload_pdf_to_drive` — upload the PDF to Google Drive, get a shareable link
5. `add_url_attachment` — attach the Drive link to the Zotero item

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ZOTERO_USER_ID` | Numeric Zotero user ID |
| `ZOTERO_API_KEY` | Zotero API key (Read/Write) |
| `GOOGLE_DRIVE_FOLDER_ID` | Google Drive folder ID (from the folder URL) |
| `RCLONE_REMOTE` | rclone remote name configured for Google Drive (e.g. `gdrive`) |

## CLI Pipeline (`scripts/`)

A Claude-independent 3-stage pipeline for batch-organising PDF folders into Zotero + Google Drive.
Claude is an optional enhancement for Stage 2 only; all other stages are pure Python.

### Stage 1 — Scan

```bash
python scripts/scan_pdfs.py <folder> --collection <Name> [--no-ss]
```

Walks the folder, extracts DOIs (PDF metadata → page-1 regex → Semantic Scholar title search),
detects duplicates, and writes `<folder>/scan.json`. Prompts for the next mode when subdirectories
are found.

Flags: `--no-ss` skips Semantic Scholar calls; `--mode [auto|scaffold|scan-only]` skips the prompt.

### Stage 2 — Taxonomy

**Scaffold** (pre-fill from subfolder structure, then edit manually or with Claude):
```bash
python scripts/generate_batch.py --mode scaffold <folder>/scan.json \
    --output <folder>/taxonomy.yaml
```

**Auto** (use subfolder structure directly, no YAML needed):
```bash
python scripts/generate_batch.py --mode auto <folder>/scan.json \
    --output /tmp/<Name>_batch.py
```

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
    search_query: "title query for Semantic Scholar"
    collection: "Quantum-Plasmonics"
    tags: []
books:
  - file: "rel/book.pdf"
    type: "book"          # book | thesis | document
    title: "Full title"
    authors: [{first: "First", last: "Last"}]
    year: "2006"
    extra: {publisher: "Springer"}
    collection: "Books-Notes"
    tags: []
```

### Stage 3 — Generate & Run

```bash
# From taxonomy.yaml (after editing or Claude review):
python scripts/generate_batch.py --mode taxonomy \
    <folder>/taxonomy.yaml <folder>/scan.json \
    --output /tmp/<Name>_batch.py

# Run full pipeline (Zotero + Drive):
python /tmp/<Name>_batch.py

# Drive-only (Zotero items already exist, re-upload to Drive):
python /tmp/<Name>_batch.py --mode drive-only
```

The generated `batch_run.py` is self-contained — it embeds all config, manifests,
and the async runner. Resumable via state file at `/tmp/<Name>_batch_state.json`.

### Complete example (Claude-free)

```bash
conda activate claudotero
python scripts/scan_pdfs.py ~/papers/QuantumDots --collection QuantumDots
# edit ~/papers/QuantumDots/taxonomy.yaml
python scripts/generate_batch.py --mode taxonomy \
    ~/papers/QuantumDots/taxonomy.yaml ~/papers/QuantumDots/scan.json \
    --output /tmp/QuantumDots_batch.py
python /tmp/QuantumDots_batch.py
```

## Dependencies

- `pyzotero` — Zotero API client (includes Semantic Scholar integration)
- `pypdf` — PDF reading for DOI extraction
- `pyyaml` — YAML parsing for `taxonomy.yaml`
- `mcp` — MCP server framework
- `rclone` (system) — Google Drive upload; configured with institute Google account via `rclone config`

## Setup Notes

- rclone is installed via Homebrew and configured with the institute Google account
- The Drive folder targeted by `GOOGLE_DRIVE_FOLDER_ID` must be accessible to the authenticated rclone remote
- MCP server config lives in `~/Library/Application Support/Claude/claude_desktop_config.json`
