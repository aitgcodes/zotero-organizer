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

## Dependencies

- `pyzotero` — Zotero API client (includes Semantic Scholar integration)
- `pypdf` — PDF reading for DOI extraction
- `mcp` — MCP server framework
- `rclone` (system) — Google Drive upload; configured with institute Google account via `rclone config`

## Setup Notes

- rclone is installed via Homebrew and configured with the institute Google account
- The Drive folder targeted by `GOOGLE_DRIVE_FOLDER_ID` must be accessible to the authenticated rclone remote
- MCP server config lives in `~/Library/Application Support/Claude/claude_desktop_config.json`
