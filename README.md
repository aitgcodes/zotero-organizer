# zotero-organizer

Organize local PDF folders into Zotero collections with Google Drive links — works
entirely from the command line, no Claude required. Claude Desktop integration is
available as an optional enhancement.

## Components

| Component | File | Needs Claude? | What it does |
|-----------|------|--------------|--------------|
| CLI pipeline | `scripts/` | No | Scan PDFs → build taxonomy → batch-create Zotero items + Drive upload |
| MCP server | `zotero_mcp.py` | Yes (Claude Desktop) | Same workflow, driven interactively from Claude |

---

## CLI pipeline (no Claude required)

### Prerequisites

- Python 3.10+
- [rclone](https://rclone.org/install/) — `brew install rclone` on macOS
- A [Zotero](https://www.zotero.org) account with API access
- A Google account with Google Drive access

### Install

**Option A — conda (recommended):**

Includes all CLI deps plus the `mcp` package needed if you also want the MCP server.
Version-pinned for reproducibility.

```bash
conda env create -f environment.yml
conda activate claudotero
```

**Option B — pip into any Python environment:**

Installs only the four CLI dependencies — no `mcp` package.
Works with a plain venv, an existing conda env, or `conda install --file requirements.txt`.

```bash
pip install -r requirements.txt
```

### Configure credentials

```bash
cp .env.template .env
```

Fill in `.env`:

| Variable | Description |
|----------|-------------|
| `ZOTERO_USER_ID` | Numeric Zotero user ID (Settings → Feeds/API on zotero.org) |
| `ZOTERO_API_KEY` | Zotero API key with Read/Write access |
| `GOOGLE_DRIVE_FOLDER_ID` | ID from the Drive folder URL: `.../folders/<ID>` |
| `RCLONE_REMOTE` | rclone remote name configured for Google Drive (e.g. `gdrive`) |

### Zotero setup

1. Log in to [zotero.org](https://www.zotero.org) → **Settings → Feeds/API**.
2. Note your **User ID** (numeric, shown at the top).
3. Click **Create new private key**, enable **Read/Write** access, copy the key.

### Google Drive / rclone setup

1. In Google Drive, open the folder you want to use. Copy the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/<FOLDER_ID>
   ```

2. Configure rclone:
   ```bash
   rclone config
   ```
   - Choose **`n`** (new remote), name it `gdrive`
   - Storage type: `drive`
   - Leave client_id / client_secret blank
   - Scope: `1` (full access)
   - Use auto config: `y` — a browser window opens to authenticate

3. Test:
   ```bash
   rclone ls gdrive: --drive-root-folder-id=<FOLDER_ID>
   ```

---

### Running the pipeline

#### Stage 1 — Scan PDFs

Walks the folder, extracts DOIs via a 4-step fallback chain (PDF metadata → page-1
regex → Semantic Scholar title search → raw header text), detects duplicates by DOI,
and writes `scan.json`.

```bash
python scripts/scan_pdfs.py /path/to/pdfs --collection "Plasmons"
```

Flags:
- `--no-ss` — skip Semantic Scholar title search (faster, offline)
- `--mode [auto|scaffold|scan-only]` — skip the interactive prompt after scanning

After scanning, if subdirectories are found you will be prompted to choose a generation
mode (or pass `--mode` to skip the prompt).

#### Stage 2 — Build taxonomy

**Option A: use subfolder structure directly (auto)**

Collections mirror the immediate subdirectory names. No human input needed.

```bash
python scripts/generate_batch.py --mode auto scan.json --output /tmp/batch_run.py
```

**Option B: review and edit a taxonomy scaffold (recommended for new collections)**

```bash
# Generate editable taxonomy.yaml pre-filled from subfolder structure:
python scripts/generate_batch.py --mode scaffold scan.json

# Edit taxonomy.yaml — rearrange collections, add tags, handle flagged/unresolved files.

# Generate batch script from the edited taxonomy:
python scripts/generate_batch.py --mode taxonomy taxonomy.yaml scan.json \
    --output /tmp/batch_run.py
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
  "SubfolderA/paper.pdf":
    collection: "Quantum-Plasmonics"
    tags: ["review", "2024"]

flagged:          # DOI could not be resolved automatically
  - file: "SubfolderB/mystery.pdf"
    search_query: "Plasmon resonance nanoparticle ..."
    collection: "Quantum-Plasmonics"
    tags: []

books:            # non-journal items without DOIs
  - file: "Books/textbook.pdf"
    type: book    # book | thesis | document
    title: "Nanoplasmonics"
    authors: [{first: "Stefan", last: "Maier"}]
    year: "2007"
    extra: {publisher: "Springer"}
    collection: "Books-Notes"
    tags: []
```

Drive folder paths are built automatically from the collection hierarchy:
`Hydrodynamic-Modeling` with parent `Quantum-Plasmonics` under `Plasmons` →
`Plasmons/Quantum-Plasmonics/Hydrodynamic-Modeling/`.

#### Stage 3 — Run the batch

```bash
# Validate first (no Zotero or Drive changes, ~1s):
python /tmp/batch_run.py --dry-run

# Full run — create Zotero collections + items + Drive upload + URL attachment:
python /tmp/batch_run.py

# Drive upload only — Zotero items already exist, just upload and attach links:
python /tmp/batch_run.py --mode drive-only
```

The batch runner is resumable: progress is saved to `/tmp/<CollectionName>_batch_state.json`.
Interrupted runs pick up where they left off.

---

## Optional: Claude integration

### Stage 2 with Claude

After Stage 1, hand `taxonomy.yaml` (generated with `--mode scaffold`) to Claude for
thematic grouping suggestions. Claude can reorganize collections, propose tags, and
identify related papers — then you save the edited YAML and run Stage 3.

This is entirely optional. The `auto` and `scaffold` modes in Stage 2 produce
ready-to-run batch scripts without Claude.

### MCP server (Claude Desktop)

`zotero_mcp.py` exposes the same Zotero/Drive workflow as callable tools within
Claude Desktop, enabling an interactive per-PDF workflow:

**Additional requirement:** [Claude Desktop](https://claude.ai/download)

**Install:** use the conda environment (includes `mcp`):
```bash
conda env create -f environment.yml
conda activate claudotero
```

**Configure Claude Desktop** — add to the config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "zotero": {
      "command": "/path/to/conda/envs/claudotero/bin/python",
      "args": ["/path/to/zotero-organizer/zotero_mcp.py"],
      "env": {
        "ZOTERO_USER_ID": "your_numeric_user_id",
        "ZOTERO_API_KEY": "your_api_key",
        "GOOGLE_DRIVE_FOLDER_ID": "your_folder_id",
        "RCLONE_REMOTE": "gdrive"
      }
    }
  }
}
```

Find the Python path with: `conda activate claudotero && which python`

Restart Claude Desktop after saving. The MCP server tools will appear in your Claude
conversation as callable functions.

**MCP tools:**

| Tool | Description |
|------|-------------|
| `extract_doi_from_local_pdf` | Extract DOI from a local PDF (metadata → page-1 regex → SS title search → fallback) |
| `create_collection` | Create a Zotero collection; `parent_key` for nested collections |
| `add_item_by_doi` | Resolve DOI via Semantic Scholar, create Zotero item, add to collection |
| `upload_pdf_to_drive` | Upload PDF to Drive via rclone; `collection_path` sets subfolder hierarchy |
| `add_url_attachment` | Attach a URL (e.g. Drive link) to an existing Zotero item |
| `get_drive_folder_id` | Return configured `GOOGLE_DRIVE_FOLDER_ID` |
| `get_collection_structure` | Return sub-collections and items of a collection key |
| `add_tags_to_item` | Add tags to an existing Zotero item |
