#!/usr/bin/env python3
"""Zotero MCP Server — exposes Zotero write operations as MCP tools."""

import asyncio
import json
import os
import re
import shutil

from dotenv import load_dotenv

load_dotenv()  # loads .env if present; does not override vars already in the environment

import mcp.types as types
import pypdf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pyzotero import zotero
from pyzotero.semantic_scholar import (
    PaperNotFoundError,
    SemanticScholarError,
    get_paper,
    search_papers,
)

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def _init_zotero() -> zotero.Zotero:
    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    missing = [
        name
        for name, val in [("ZOTERO_USER_ID", user_id), ("ZOTERO_API_KEY", api_key)]
        if not val
    ]
    if missing:
        raise ValueError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Export them before starting the server."
        )
    return zotero.Zotero(user_id, "user", api_key)


zot = _init_zotero()
server = Server("zotero-organize")

DRIVE_FOLDER_ID: str = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
RCLONE_BIN: str = (
    os.environ.get("RCLONE_PATH")
    or shutil.which("rclone")
    or "/opt/homebrew/bin/rclone"
)

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS: list[types.Tool] = [
    types.Tool(
        name="create_collection",
        description=(
            "Check whether a top-level Zotero collection with the given name already exists. "
            "If it does, returns JSON with 'status': 'exists' and the existing 'key' and 'name' — "
            "prompt the user whether to append to it or create a new collection. "
            "If it does not exist, creates it and returns 'status': 'created' with the new 'key'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name for the collection."},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="extract_doi_from_local_pdf",
        description=(
            "Extract a DOI from a local PDF file by checking its internal metadata "
            "first, then scanning the first page only. Never reads beyond page 1. "
            "If an arXiv ID (e.g. 'arXiv:2301.00001') is found in the metadata or "
            "first page, returns the canonical arXiv DOI (10.48550/arXiv.XXXX.XXXXX) "
            "directly without searching for a published version. "
            "If no DOI or arXiv ID is found, performs a Semantic Scholar title search "
            "using the first-page text and returns the DOI of the top match. "
            "If all methods fail, returns JSON with 'status': 'unresolved', "
            "'file_path', and 'fallback_header_text'. Collect all unresolved files "
            "and report them to the user at the end of a batch run."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="add_item_by_doi",
        description=(
            "Resolve a DOI via Semantic Scholar, create the corresponding Zotero item, "
            "and place it in the specified collection. Before inserting, checks whether "
            "an item with the same DOI already exists in the collection. If a duplicate "
            "is found, returns JSON with 'status': 'duplicate' and the existing 'item_key' "
            "instead of creating a second copy."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "doi": {
                    "type": "string",
                    "description": "DOI string (e.g. '10.1000/xyz123').",
                },
                "collection_key": {
                    "type": "string",
                    "description": "Key of the target Zotero collection.",
                },
            },
            "required": ["doi", "collection_key"],
        },
    ),
    types.Tool(
        name="get_drive_folder_id",
        description=(
            "Return the Google Drive folder ID configured in the server's environment "
            "(GOOGLE_DRIVE_FOLDER_ID). Use this before uploading a PDF to Drive so you "
            "know which folder to target."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="upload_pdf_to_drive",
        description=(
            "Upload a local PDF file to the configured Google Drive folder using rclone. "
            "Returns a JSON object with 'url' (shareable link) and 'name'. "
            "Use the returned 'url' with add_url_attachment to link the file to a Zotero item."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the local PDF file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    types.Tool(
        name="add_url_attachment",
        description=(
            "Attach a URL (e.g. a Google Drive share link) to an existing Zotero item. "
            "The link syncs to the Zotero web library and is accessible from any machine."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "item_key": {
                    "type": "string",
                    "description": "Key of the parent Zotero item (returned by add_item_by_doi).",
                },
                "url": {
                    "type": "string",
                    "description": "Full URL to attach (e.g. a Google Drive web-view link).",
                },
                "title": {
                    "type": "string",
                    "description": "Display title for the attachment (e.g. the PDF filename).",
                },
            },
            "required": ["item_key", "url", "title"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return _TOOLS


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    args = arguments or {}
    try:
        if name == "create_collection":
            return await _create_collection(args["name"])
        if name == "extract_doi_from_local_pdf":
            return await _extract_doi_from_local_pdf(args["file_path"])
        if name == "get_drive_folder_id":
            return await _get_drive_folder_id()
        if name == "add_item_by_doi":
            return await _add_item_by_doi(args["doi"], args["collection_key"])
        if name == "upload_pdf_to_drive":
            return await _upload_pdf_to_drive(args["file_path"])
        if name == "add_url_attachment":
            return await _add_url_attachment(
                args["item_key"], args["url"], args["title"]
            )
        return [types.TextContent(type="text", text=f"Unknown tool: {name!r}")]
    except KeyError as exc:
        return [types.TextContent(type="text", text=f"Missing required argument: {exc}")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_first_item(result: dict) -> dict | None:
    """Return the first item from a Zotero batch-write response, or None on failure.

    pyzotero may return successful as a list (newer versions) or a dict keyed by
    string indices ("0", "1", …); handle both defensively.
    """
    successful = result.get("successful")
    if not successful:
        return None
    if isinstance(successful, list):
        return successful[0] if successful else None
    return next(iter(successful.values()), None)


def _build_item_template(paper: dict, doi: str) -> dict:
    """Map a normalised Semantic Scholar paper dict to a Zotero journalArticle template."""
    template = zot.item_template("journalArticle")

    template["title"] = paper.get("title") or ""
    template["abstractNote"] = paper.get("abstract") or ""
    template["publicationTitle"] = paper.get("venue") or ""
    template["DOI"] = doi
    template["url"] = f"https://doi.org/{doi}"

    # Prefer the full publication date string; fall back to year integer.
    pub_date = paper.get("publicationDate") or paper.get("year")
    template["date"] = str(pub_date) if pub_date else ""

    creators: list[dict] = []
    for author in paper.get("authors") or []:
        raw_name = (author.get("name") or "").strip()
        if not raw_name:
            continue
        parts = raw_name.rsplit(" ", 1)
        if len(parts) == 2:
            creators.append(
                {"creatorType": "author", "firstName": parts[0], "lastName": parts[1]}
            )
        else:
            creators.append({"creatorType": "author", "name": raw_name})
    template["creators"] = creators

    return template


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _create_collection(name: str) -> list[types.TextContent]:
    # Check whether a collection with this name already exists.
    try:
        existing = zot.collections()
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Zotero API error fetching collections: {exc}")]

    name_lower = name.strip().lower()
    for coll in existing:
        if coll["data"]["name"].strip().lower() == name_lower:
            payload = json.dumps(
                {"status": "exists", "key": coll["key"], "name": coll["data"]["name"]}
            )
            return [types.TextContent(type="text", text=payload)]

    # Collection does not exist — create it.
    try:
        result = zot.create_collections([{"name": name, "parentCollection": ""}])
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Zotero API error: {exc}")]

    item = _extract_first_item(result)
    if not item:
        failed = result.get("failed", {})
        return [
            types.TextContent(
                type="text",
                text=f"Collection creation rejected by Zotero: {failed}",
            )
        ]

    payload = json.dumps({"status": "created", "key": item["key"], "name": name})
    return [types.TextContent(type="text", text=payload)]


async def _add_item_by_doi(doi: str, collection_key: str) -> list[types.TextContent]:
    # 1. Check for a duplicate — scan existing collection items for a matching DOI.
    try:
        all_items = zot.everything(zot.collection_items(collection_key))
        doi_lower = doi.strip().lower()
        for existing in all_items:
            if existing["data"].get("DOI", "").strip().lower() == doi_lower:
                payload = json.dumps(
                    {"status": "duplicate", "item_key": existing["key"], "doi": doi}
                )
                return [types.TextContent(type="text", text=payload)]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Zotero API error checking duplicates: {exc}")]

    # 2. Resolve DOI via Semantic Scholar (pyzotero built-in wrapper).
    try:
        paper = get_paper(doi, id_type="doi")
    except PaperNotFoundError:
        return [
            types.TextContent(
                type="text",
                text=f"DOI '{doi}' was not found in Semantic Scholar.",
            )
        ]
    except SemanticScholarError as exc:
        return [types.TextContent(type="text", text=f"Semantic Scholar API error: {exc}")]

    if not paper:
        return [
            types.TextContent(
                type="text", text=f"No metadata returned for DOI '{doi}'."
            )
        ]

    # 2. Build the item payload and create it in Zotero.
    try:
        template = _build_item_template(paper, doi)
        result = zot.create_items([template])
    except Exception as exc:
        return [
            types.TextContent(
                type="text", text=f"Error creating Zotero item for DOI '{doi}': {exc}"
            )
        ]

    item = _extract_first_item(result)
    if not item:
        failed = result.get("failed", {})
        return [
            types.TextContent(
                type="text",
                text=f"Zotero rejected the item for DOI '{doi}': {failed}",
            )
        ]

    item_key: str = item["key"]

    # 3. Add the created item to the target collection.
    # addto_collection requires the full item dict (including version) returned by
    # create_items, so we pass item directly rather than making a second round-trip.
    try:
        zot.addto_collection(collection_key, item)
    except Exception as exc:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"Item '{item_key}' was created but could not be added to "
                    f"collection '{collection_key}': {exc}"
                ),
            )
        ]

    payload = json.dumps(
        {"status": "added", "item_key": item_key, "collection_key": collection_key}
    )
    return [types.TextContent(type="text", text=payload)]


async def _get_drive_folder_id() -> list[types.TextContent]:
    if not DRIVE_FOLDER_ID:
        return [
            types.TextContent(
                type="text",
                text="GOOGLE_DRIVE_FOLDER_ID is not set in the server environment.",
            )
        ]
    return [types.TextContent(type="text", text=DRIVE_FOLDER_ID)]


async def _add_url_attachment(
    item_key: str, url: str, title: str
) -> list[types.TextContent]:
    try:
        attachment = zot.item_template("attachment", "linked_url")
        attachment["title"] = title
        attachment["url"] = url
        attachment["parentItem"] = item_key
        zot.create_items([attachment])
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Failed to attach URL: {exc}")]
    return [
        types.TextContent(
            type="text",
            text=f"URL attachment '{title}' added to item '{item_key}'.",
        )
    ]


async def _upload_pdf_to_drive(file_path: str) -> list[types.TextContent]:
    rclone_remote = os.environ.get("RCLONE_REMOTE")
    if not rclone_remote:
        return [types.TextContent(type="text", text="RCLONE_REMOTE is not set (e.g. 'gdrive').")]
    if not DRIVE_FOLDER_ID:
        return [types.TextContent(type="text", text="GOOGLE_DRIVE_FOLDER_ID is not set.")]
    if not os.path.isfile(file_path):
        return [types.TextContent(type="text", text=f"File not found: '{file_path}'")]
    if not os.path.isfile(RCLONE_BIN):
        return [
            types.TextContent(
                type="text",
                text=f"rclone not found at '{RCLONE_BIN}'. Install it or set RCLONE_PATH.",
            )
        ]

    file_name = os.path.basename(file_path)
    local_dir = os.path.basename(os.path.dirname(os.path.abspath(file_path)))
    dest = f"{rclone_remote}:{local_dir}"
    root_flag = f"--drive-root-folder-id={DRIVE_FOLDER_ID}"

    upload = await asyncio.create_subprocess_exec(
        RCLONE_BIN, "copy", file_path, dest,
        root_flag,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await upload.communicate()
    if upload.returncode != 0:
        return [types.TextContent(type="text", text=f"rclone copy failed: {stderr.decode().strip()}")]

    link_proc = await asyncio.create_subprocess_exec(
        RCLONE_BIN, "link", f"{dest}/{file_name}",
        root_flag,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await link_proc.communicate()
    if link_proc.returncode != 0:
        return [types.TextContent(type="text", text=f"rclone link failed: {stderr.decode().strip()}")]

    url = stdout.decode().strip()
    payload = json.dumps({"url": url, "name": file_name, "subfolder": local_dir})
    return [types.TextContent(type="text", text=payload)]


async def _extract_doi_from_local_pdf(file_path: str) -> list[types.TextContent]:
    try:
        reader = pypdf.PdfReader(file_path)
    except FileNotFoundError:
        return [types.TextContent(type="text", text=f"File not found: '{file_path}'")]
    except pypdf.errors.PdfReadError as exc:
        return [types.TextContent(type="text", text=f"Cannot read PDF '{file_path}': {exc}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Error opening '{file_path}': {exc}")]

    if reader.is_encrypted:
        return [
            types.TextContent(
                type="text",
                text=f"PDF '{file_path}' is encrypted and cannot be read without a password.",
            )
        ]

    # 1. Check internal metadata dictionary first.
    # Encrypted PDFs raise FileNotDecryptedError on metadata access; skip gracefully.
    try:
        meta = reader.metadata or {}
    except Exception:
        meta = {}
    for key in ("/doi", "/DOI", "/Subject", "/subject"):
        raw = meta.get(key, "") or ""
        match = _DOI_RE.search(raw)
        if match:
            return [types.TextContent(type="text", text=match.group(0))]
        arxiv = _ARXIV_RE.search(raw)
        if arxiv:
            return [types.TextContent(type="text", text=f"10.48550/arXiv.{arxiv.group(1)}")]

    # 2. Fall back to first page text only — no subsequent pages are read.
    if not reader.pages:
        return [types.TextContent(type="text", text="PDF has no pages.")]

    try:
        first_page_text = reader.pages[0].extract_text() or ""
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Could not extract text from page 1: {exc}")]

    match = _DOI_RE.search(first_page_text)
    if match:
        return [types.TextContent(type="text", text=match.group(0))]

    arxiv = _ARXIV_RE.search(first_page_text)
    if arxiv:
        return [types.TextContent(type="text", text=f"10.48550/arXiv.{arxiv.group(1)}")]

    # 3. No DOI on page 1 — attempt a Semantic Scholar title search.
    # Collapse newlines so the query reads as a natural phrase, then trim to
    # ~150 chars (enough for a distinctive title without over-constraining).
    title_query = " ".join(first_page_text.split())[:150]
    try:
        results = search_papers(title_query, limit=3)
        for paper in results.get("papers", []):
            doi = paper.get("doi")
            if doi:
                return [types.TextContent(type="text", text=doi)]
    except SemanticScholarError:
        pass  # rate-limit or API error — fall through to header snippet

    # 4. Last resort — return the first 2,000 characters of page 1 so Claude
    # can identify the title and abstract for a downstream metadata search.
    header_snippet = first_page_text[:2000].strip()
    payload = json.dumps(
        {"status": "unresolved", "file_path": file_path, "fallback_header_text": header_snippet},
        ensure_ascii=False,
    )
    return [types.TextContent(type="text", text=payload)]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
