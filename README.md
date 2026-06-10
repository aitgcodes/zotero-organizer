# zotero-organizer

Organize local PDF folders into Zotero collections with Google Drive links — entirely
from the command line. No Claude required; Claude Desktop integration is available as
an optional enhancement.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Full user manual** (step-by-step installation, usage guide, troubleshooting):
> [docs/manual.md](docs/manual.md)

---

## Platform support

**Mac and Linux** users can follow this guide directly.

**Windows** users should run everything inside
[WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows Subsystem for
Linux — recommended, since your local PDF folders remain accessible) or Docker.
Native Windows is not supported: rclone's authentication flow and the shell environment
assumed by this tool are Unix-based.

---

## Before you begin

You need accounts and credentials from two services before installing anything.
Collect them now and keep them somewhere safe — a password manager or a private text
file — because you will enter them into the setup wizard.

### Zotero

1. Create a free account at [zotero.org](https://www.zotero.org) if you don't have one.
2. Log in → **Settings → Feeds/API**.
3. Note your **User ID** — the numeric value shown at the top of that page.
4. Click **Create new private key**, tick **Read/Write** access for your library,
   and copy the key before closing the page.

### Google Drive

A personal Google account or an institutional Google Workspace account both work.

1. Open [Google Drive](https://drive.google.com) and create (or navigate to) the
   folder where uploaded PDFs should live.
2. Copy the **folder ID** from the URL:
   ```
   https://drive.google.com/drive/folders/<FOLDER_ID>
   ```
   Everything after `/folders/` is your folder ID.

---

## Quick installation

For users who already have rclone configured and both sets of credentials ready:

```bash
git clone https://github.com/aitgcodes/zotero-organizer.git
cd zotero-organizer
pip install -r requirements.txt      # or use conda — see Detailed installation
python scripts/setup.py              # enter your credentials when prompted
python scripts/organize.py /path/to/pdfs --collection "MyCollection"
```

First time? Follow the [Detailed installation](#detailed-installation) below.

---

## Detailed installation

### 1. Install Python dependencies

Python 3.10 or later is required (`python --version` to check).

**Option A — conda (recommended; also enables the optional MCP server):**
```bash
conda env create -f environment.yml
conda activate claudotero
```

**Option B — pip into any existing environment:**
```bash
pip install -r requirements.txt
```

### 2. Install and configure rclone

[rclone](https://rclone.org) handles uploads to Google Drive.

**Install:**
```bash
# macOS
brew install rclone

# Debian / Ubuntu
sudo apt install rclone
# or via the official installer:
curl https://rclone.org/install.sh | sudo bash
```

**Create a Google Drive remote:**
```bash
rclone config
```

At the prompts:
- Choose **`n`** — new remote
- Name: `gdrive` (or any name you prefer; you will enter it during setup)
- Storage type: `drive`
- `client_id` and `client_secret`: leave blank (press Enter)
- Scope: **`1`** — full access
- Use auto config: **`y`** — a browser window opens to authenticate your Google account

**Test the connection** (replace `<FOLDER_ID>` with your Drive folder ID):
```bash
rclone ls gdrive: --drive-root-folder-id=<FOLDER_ID>
```
An empty result with no error means rclone can reach the folder.

### 3. Clone the repository

```bash
git clone https://github.com/aitgcodes/zotero-organizer.git
cd zotero-organizer
```

### 4. Run the setup wizard

```bash
python scripts/setup.py
```

The wizard prompts for each value; press Enter to accept the default shown in brackets.

| Prompt | What to enter |
|--------|---------------|
| `ORGANIZE_HOME` | Press Enter — defaults to the project folder |
| `ZOTERO_USER_ID` | Your numeric Zotero user ID |
| `ZOTERO_API_KEY` | Your Zotero API key (input is hidden) |
| `GOOGLE_DRIVE_FOLDER_ID` | The folder ID from the Drive URL |
| `RCLONE_REMOTE` | Your rclone remote name (default: `gdrive`) |

After entry the wizard validates connectivity to Zotero and Google Drive and prints a
summary. Re-run `setup.py` at any time to update a single value.

---

## Usage guide

### Your first collection

```bash
python scripts/organize.py /path/to/your/pdfs --collection "Plasmons"
```

The tool runs three stages in sequence, prompting before each transition.
Your PDF folder is never modified.

**Stage 1 — Scan**
Walks the folder recursively, extracts DOIs via a four-step fallback (PDF metadata →
page-1 text → Semantic Scholar title search → raw header), detects duplicates, and
writes `collections/Plasmons/scan.json`.

**Stage 2 — Build collection structure**

| Choice | What happens |
|--------|-------------|
| `[1] Scaffold` | Writes `taxonomy.yaml` — review and edit it, then re-run |
| `[2] Auto` | Uses subfolder names as collection names directly — no editing |
| `[3] LLM/Claude` | Same as scaffold, intended for Claude or another LLM to suggest organization |

The scaffold option is recommended for first-time use: it gives you a reviewable
file before anything is written to Zotero or Drive.

**Stage 3 — Dry run → real run**
Prints exactly what would be created and uploaded. Confirm to proceed. Progress is
saved to `state.json`; an interrupted run resumes from where it left off.

### Editing taxonomy.yaml

Open `collections/Plasmons/taxonomy.yaml` in any text editor:

```yaml
base_collection: "Plasmons"

collections:
  - name: "Quantum-Plasmonics"
    parent: null
  - name: "Hydrodynamic-Modeling"
    parent: "Quantum-Plasmonics"    # creates a nested sub-collection

assignments:
  "SubfolderA/paper.pdf":
    collection: "Quantum-Plasmonics"
    tags: ["review", "2024"]

flagged:                            # PDFs whose DOI could not be resolved
  - file: "SubfolderB/mystery.pdf"
    search_query: "Plasmon resonance nanoparticle ..."
    collection: "Quantum-Plasmonics"
    tags: []

books:                              # non-journal items (books, theses, documents)
  - file: "Books/textbook.pdf"
    type: book                      # book | thesis | document
    title: "Nanoplasmonics"
    authors: [{first: "Stefan", last: "Maier"}]
    year: "2007"
    extra: {publisher: "Springer"}
    collection: "Books-Notes"
    tags: []
```

For `flagged` entries, search Semantic Scholar using the `search_query` text, then
either add the correct DOI to `scan.json` or move the entry into `assignments`.

### Re-running when new PDFs are added

Run the same command again:
```bash
python scripts/organize.py /path/to/your/pdfs --collection "Plasmons"
```

New files are detected automatically. A `taxonomy_patch.yaml` is written containing
only the additions. Merge the patch into your main `taxonomy.yaml`, then re-run.

### Drive conflict handling

If the Drive folder already has content from a previous run, the batch pauses:

```
⚠  Drive folder 'Plasmons/' already contains 3 item(s).

  [1] Merge    — add new files, skip existing  <-- default
  [2] Overwrite — replace existing files
  [3] New folder — upload to 'Plasmons_20260610/' instead
  [4] Abort
```

### Command flags

| Flag | Effect |
|------|--------|
| `--mode scaffold\|auto\|taxonomy` | Skip the Stage 2 prompt |
| `--no-ss` | Skip Semantic Scholar search (faster, works offline) |
| `--full-scan` | Force a complete rescan even if scan.json exists |
| `--skip-scan` | Skip Stage 1 entirely |
| `--dry-run` | Stop after dry-run validation |
| `--workspace <path>` | Override the default workspace location |

### Workspace layout

```
zotero-organizer/
  collections/
    Plasmons/
      scan.json            ← Stage 1 output; updated incrementally on re-runs
      taxonomy.yaml        ← edit this to customise collections and tags
      taxonomy_patch.yaml  ← new files found on re-scan; merge into taxonomy.yaml
      batch_run.py         ← generated runner script
      state.json           ← progress tracker; delete to start fresh
```

---

## Advanced: running stages individually

The underlying scripts can be called directly when you need more control.

**Stage 1 — Scan:**
```bash
python scripts/scan_pdfs.py /path/to/pdfs --collection "Plasmons" \
    --output collections/Plasmons/scan.json [--no-ss]
```

**Stage 2 — Build taxonomy:**
```bash
# Scaffold:
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

**Stage 3 — Run the batch:**
```bash
python collections/Plasmons/batch_run.py --dry-run          # validate only
python collections/Plasmons/batch_run.py                    # full run
python collections/Plasmons/batch_run.py --mode drive-only  # Drive upload only
```

---

## Optional: Claude Desktop integration

### Using Claude to suggest taxonomy

After Stage 1, share `taxonomy.yaml` with Claude and ask it to suggest thematic
groupings, collection names, and tags. Save the edited file and re-run; choose
option `[1]` (use existing taxonomy) at the Stage 2 prompt.

### MCP server

`zotero_mcp.py` exposes the full workflow as callable tools inside Claude Desktop,
enabling an interactive per-PDF workflow.

**Additional requirement:** [Claude Desktop](https://claude.ai/download) and the
conda environment (which includes `mcp`).

**Configure** — add to Claude Desktop's config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

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

Restart Claude Desktop after saving.

**Available tools:**

| Tool | Description |
|------|-------------|
| `extract_doi_from_local_pdf` | Extract DOI from a local PDF |
| `create_collection` | Create a Zotero collection (with optional parent) |
| `add_item_by_doi` | Resolve DOI via Semantic Scholar, create Zotero item |
| `upload_pdf_to_drive` | Upload PDF to Drive via rclone |
| `add_url_attachment` | Attach a Drive URL to a Zotero item |
| `get_drive_folder_id` | Return the configured Drive folder ID |
| `get_collection_structure` | List sub-collections and items of a collection |
| `add_tags_to_item` | Add tags to an existing Zotero item |
