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

### First-time setup

Run the setup wizard once after installing. It prompts for all required credentials,
validates your configuration, and creates the `collections/` workspace directory.

```bash
python scripts/setup.py
```

You will be prompted for:

| Variable | Default | Description |
|----------|---------|-------------|
| `ORGANIZE_HOME` | project root | Where `collections/` lives |
| `ZOTERO_USER_ID` | — | Numeric user ID (zotero.org → Settings → Feeds/API) |
| `ZOTERO_API_KEY` | — | API key with Read/Write access |
| `GOOGLE_DRIVE_FOLDER_ID` | — | ID from the Drive folder URL: `.../folders/<ID>` |
| `RCLONE_REMOTE` | `gdrive` | rclone remote name for Google Drive |

The wizard writes `.env`, validates rclone/Zotero/Drive connectivity, and prints
next-step instructions. Re-run at any time to update individual values.

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

#### Guided mode (recommended)

`organize.py` runs all three stages interactively. It detects the current state of the
collection workspace and prompts only for what it needs.

```bash
python scripts/organize.py /path/to/pdfs --collection "Plasmons"
```

**First run** (no prior state):

```
  PDF folder : /path/to/pdfs
  Collection : Plasmons
  Workspace  : /path/to/zotero-organizer/collections/Plasmons/

============================================================
  Stage 1 — Full scan
============================================================
Found 22 PDF files. Extracting DOIs...
  ...

============================================================
  Stage 2 — Generate batch script
============================================================
Choose how to build the collection structure:
  [1] Scaffold — generate taxonomy.yaml, edit manually        <-- default
  [2] Auto     — use subfolder names directly, no editing
  [3] LLM/Claude — use taxonomy.yaml edited with Claude or another LLM
      ⚠  Requires Claude Desktop (MCP server) or a separate LLM session
  Choice [1]:
```

Choosing **scaffold** writes `collections/Plasmons/taxonomy.yaml` and exits cleanly:
```
taxonomy.yaml written → collections/Plasmons/taxonomy.yaml

Edit it in your preferred editor, then re-run:
  python scripts/organize.py /path/to/pdfs --collection Plasmons
```

**Re-run after editing taxonomy.yaml:**

```
  Found existing scan.json (2026-06-07, 22 files). Scan up to date — skipping.

  Found existing taxonomy.yaml (last edited 2026-06-07).
    [1] Use existing taxonomy            <-- default
    [2] Regenerate scaffold from scratch
    [3] Auto-generate (skip taxonomy)
  Choice [1]:

============================================================
  Stage 3 — Dry run validation
============================================================
=== DRY RUN — no Zotero or Drive changes will be made ===
  ...
=== DONE: 22/22 in 1s ===

Run for real? This will create Zotero items and upload to Drive. [y/N]:
```

**Re-run when new PDFs are added to the folder:**

```
  Found existing scan.json (2026-06-07, 22 files).
  3 new PDFs detected, 0 removed.
    [1] Scan new files only (incremental)  <-- default
    [2] Full rescan
    [3] Skip scan
  Choice [1]:

  3 new papers → collections/Plasmons/taxonomy_patch.yaml
  Review and merge into taxonomy.yaml, then re-run this command.
```

#### Organize flags

| Flag | Effect |
|------|--------|
| `--mode scaffold\|auto\|taxonomy` | Skip the Stage 2 prompt |
| `--no-ss` | Skip Semantic Scholar title search (faster, offline) |
| `--full-scan` | Force complete rescan even if scan.json exists |
| `--skip-scan` | Skip Stage 1 entirely |
| `--dry-run` | Stop after dry-run validation, don't run for real |
| `--workspace <path>` | Override the default workspace location |

#### Workspace layout

All generated files go to `collections/<collection-name>/` inside the project.
**Your PDF folder is never modified.**

```
zotero-organizer/
  collections/
    Plasmons/
      scan.json        ← Stage 1 output; updated incrementally on re-runs
      taxonomy.yaml    ← Stage 2 scaffold; edit this to customise collections
      taxonomy_patch.yaml  ← new files found on re-scan; merge into taxonomy.yaml
      batch_run.py     ← Stage 2 output; self-contained async runner
      state.json       ← Stage 3 progress; allows resuming interrupted runs
```

By default `collections/` is excluded from git (see `.gitignore`). To track taxonomy
files across machines, remove the `collections/` line from `.gitignore`.

---

#### Stage-by-stage (advanced / scripting)

The individual stage scripts can also be used directly when you need more control.

**Stage 1 — Scan**

```bash
python scripts/scan_pdfs.py /path/to/pdfs --collection "Plasmons" \
    --output collections/Plasmons/scan.json [--no-ss]
```

DOI extraction uses a 4-step fallback: PDF metadata → page-1 regex →
Semantic Scholar title search → raw header text. Duplicates are detected by DOI;
the most deeply nested copy is kept as canonical.

**Stage 2 — Build taxonomy**

```bash
# Scaffold from scan.json:
python scripts/generate_batch.py --mode scaffold collections/Plasmons/scan.json \
    --output collections/Plasmons/taxonomy.yaml

# Auto (no editing):
python scripts/generate_batch.py --mode auto collections/Plasmons/scan.json \
    --output collections/Plasmons/batch_run.py

# From edited taxonomy.yaml:
python scripts/generate_batch.py --mode taxonomy \
    collections/Plasmons/taxonomy.yaml collections/Plasmons/scan.json \
    --output collections/Plasmons/batch_run.py
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

Nested collections are built automatically from subfolder structure.
`Hydrodynamic-Modeling` with parent `Quantum-Plasmonics` under `Plasmons` →
Drive path `Plasmons/Quantum-Plasmonics/Hydrodynamic-Modeling/`.

**Stage 3 — Run the batch**

```bash
# Validate (no Zotero or Drive changes, ~1s):
python collections/Plasmons/batch_run.py --dry-run

# Full run — create Zotero collections + items + Drive upload + URL attachment:
python collections/Plasmons/batch_run.py

# Drive upload only — Zotero items already exist:
python collections/Plasmons/batch_run.py --mode drive-only
```

Progress is saved to `collections/Plasmons/state.json`. Interrupted runs resume
from where they left off.

---

## Optional: Claude integration

### Stage 2 with Claude

After Stage 1, hand `taxonomy.yaml` to Claude for thematic grouping suggestions.
Claude can reorganize collections, propose tags, and identify related papers.
Save the edited YAML, then re-run `organize.py` and choose option 1 (use existing taxonomy).

Select option 3 (LLM/Claude) in the Stage 2 prompt to acknowledge this path.
Note: this requires Claude Desktop with the MCP server configured (see below),
or a separate Claude session where you paste the taxonomy content manually.

### MCP server (Claude Desktop)

`zotero_mcp.py` exposes the Zotero/Drive workflow as callable tools within Claude
Desktop, enabling an interactive per-PDF workflow.

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
