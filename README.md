# zotero-organizer

An MCP server for Claude Desktop that organizes local PDF files into Zotero collections. Given a PDF, it extracts the DOI, fetches metadata from Semantic Scholar, creates the Zotero item, uploads the PDF to Google Drive, and attaches the Drive link — all as callable tools from within Claude.

## Tools

| Tool | What it does |
|------|-------------|
| `extract_doi_from_local_pdf` | Extracts a DOI from a local PDF (metadata → page-1 regex → Semantic Scholar title search → raw header fallback) |
| `create_collection` | Creates a new top-level Zotero collection, returns its key |
| `add_item_by_doi` | Resolves a DOI via Semantic Scholar and adds the item to a Zotero collection |
| `upload_pdf_to_drive` | Uploads a local PDF to a Google Drive folder via rclone, returns a shareable link |
| `add_url_attachment` | Attaches a URL (e.g. the Drive link) to an existing Zotero item |
| `get_drive_folder_id` | Returns the configured `GOOGLE_DRIVE_FOLDER_ID` |

## Typical workflow

1. `extract_doi_from_local_pdf` → get the DOI
2. `create_collection` (if needed) → create a Zotero collection
3. `add_item_by_doi` → add the paper's metadata to Zotero
4. `upload_pdf_to_drive` → upload the PDF to Drive, get the link
5. `add_url_attachment` → attach the Drive link to the Zotero item

---

## Prerequisites

- [Miniconda or Anaconda](https://docs.conda.io/en/latest/miniconda.html)
- [Claude Desktop](https://claude.ai/download)
- [rclone](https://rclone.org/install/) — `brew install rclone` on macOS
- A [Zotero](https://www.zotero.org) account
- A Google account with Google Drive access

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/aitgcodes/zotero-organizer.git
cd zotero-organizer
```

### 2. Create the conda environment

```bash
conda env create -f environment.yml
conda activate zotero-organizer
```

### 3. Configure credentials

```bash
cp .env.template .env
```

Open `.env` and fill in the values (see the sections below for how to obtain each one).

---

## Zotero setup

1. Log in to [zotero.org](https://www.zotero.org) and go to **Settings → Feeds/API**.
2. Note your **User ID** (numeric, shown at the top of the page).
3. Click **Create new private key**, enable **Read/Write** access to your library, and copy the generated key.
4. Set these in `.env`:
   ```
   ZOTERO_USER_ID=your_numeric_user_id
   ZOTERO_API_KEY=your_api_key
   ```

---

## Google Drive setup

### 1. Find your Drive folder ID

Navigate to the Drive folder you want to use. The folder ID is the last segment of the URL:

```
https://drive.google.com/drive/folders/<FOLDER_ID>
```

Set it in `.env`:
```
GOOGLE_DRIVE_FOLDER_ID=your_folder_id
```

### 2. Configure rclone

Run the interactive setup:

```bash
rclone config
```

When prompted:
- Choose **`n`** (new remote)
- **Name**: `gdrive` (or any name you prefer)
- **Storage type**: `drive`
- **client_id / client_secret**: leave blank (uses rclone's built-in OAuth app)
- **Scope**: `1` (full access)
- **root_folder_id / service_account_file**: leave blank
- **Edit advanced config**: `n`
- **Use auto config**: `y` — a browser window will open; sign in with your Google account
- **Configure as shared drive**: `n`

Test the connection:
```bash
rclone ls gdrive: --drive-root-folder-id=<GOOGLE_DRIVE_FOLDER_ID>
```

Set the remote name in `.env`:
```
RCLONE_REMOTE=gdrive
```

---

## Claude Desktop configuration

Add the following to your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "zotero": {
      "command": "/path/to/conda/envs/zotero-organizer/bin/python",
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

Replace `/path/to/conda/envs/zotero-organizer/bin/python` with the actual path — find it with:
```bash
conda activate zotero-organizer && which python
```

Restart Claude Desktop after saving the config.
