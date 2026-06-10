Organize a PDF folder into a Zotero taxonomy (Stages 1–2 of the zotero-organizer pipeline).

**Arguments:** `$ARGUMENTS`
Format: `<pdf-folder> <collection-name>`
Example: `~/Papers/Plasmonics Plasmons`

---

## Step 1 — Parse arguments

Split `$ARGUMENTS` to get `<pdf-folder>` and `<collection-name>`. The collection name is the last token; everything before it is the folder path. If either is missing or `<pdf-folder>` does not exist on disk, tell the user and stop.

Set:
- `FOLDER` = resolved absolute path of `<pdf-folder>`
- `COLLECTION` = `<collection-name>`
- `WORKSPACE` = `collections/<COLLECTION>/` relative to the project root

---

## Step 2 — Ensure scan.json exists

Check whether `collections/<COLLECTION>/scan.json` exists.

**If it does not exist**, run the scanner:
```bash
python scripts/scan_pdfs.py "<FOLDER>" --collection "<COLLECTION>" \
    --output "collections/<COLLECTION>/scan.json" --mode scan-only
```
Wait for completion. Report: PDFs found, DOIs resolved, unresolved.

**If it already exists**, read it and report the same summary. Mention that the user can delete `scan.json` and re-run to force a fresh scan if the folder has changed.

---

## Step 3 — Read scan.json

Read `collections/<COLLECTION>/scan.json`. Each entry in `papers` has:
- `doi` — resolved DOI, or null if unresolved
- `doi_source` — `metadata`, `page1`, `ss_search`, or `unresolved`
- `title`, `abstract_snippet` — from Semantic Scholar if resolved
- `parent_dir` — the immediate subfolder the file lives in (`.` for root)
- `fallback_header` — first 300 chars of page-1 text, present when `doi_source` is `unresolved`
- `duplicate_of` — path of the canonical copy if this is a duplicate; skip these entirely

---

## Step 4 — Design the taxonomy

Analyze all non-duplicate papers and design a collection hierarchy. Apply these rules:

### Grouping
- Group by **research theme or methodology**, not by subfolder. The subfolder structure is a hint, not the answer.
- Aim for **3–8 papers per collection**. Merge thin collections; split collections larger than ~15 unless they form a coherent theme.
- Use **at most 3 levels of nesting**: base → parent → child. Prefer flatter structures.

### Naming
- Concise, hyphenated names: `Quantum-Plasmonics`, `Experimental-Techniques`, `Theoretical-Methods`.
- Avoid `Misc`, `Other`, `General`, `Papers`, or anything that could apply to any paper.
- The `base_collection` is the top-level name — use `<COLLECTION>` as-is.

### Tags
- **2–4 tags per paper**: mix topic keywords from the title/abstract, methodology (`review`, `experiment`, `theory`, `simulation`, `computation`), and era (`foundational` for seminal/pre-2000 works, `recent` for post-2020).
- Lowercase, hyphenated: `nonlinear-optics`, `density-functional-theory`.

### Unresolved papers (flagged)
- Use `fallback_header` to infer the topic. Assign to the best-fit collection.
- Keep in the `flagged` section — do not move to `assignments`.
- Set `search_query` to the most informative fragment of `fallback_header` (strip noise, keep meaningful words).

### Books and theses
- If a flagged entry looks like a book, thesis, or technical report (infer from filename or `fallback_header`), move it to `books`.
- Use `type: book`, `type: thesis`, or `type: document`.
- Fill in `title`, `authors`, `year`, and `extra` where inferable; leave blank otherwise.

---

## Step 5 — Write taxonomy.yaml

Write the taxonomy to `collections/<COLLECTION>/taxonomy.yaml` in this exact format:

```yaml
base_collection: "<COLLECTION>"

collections:
  - name: "Parent-Collection"
    parent: null
  - name: "Child-Collection"
    parent: "Parent-Collection"

assignments:
  "rel/path/paper.pdf":
    collection: "Parent-Collection"
    tags: ["tag1", "tag2"]

flagged:
  - file: "rel/path/unresolved.pdf"
    search_query: "meaningful words from fallback_header"
    collection: "Parent-Collection"
    tags: ["tag1"]

books:
  - file: "rel/path/book.pdf"
    type: book
    title: "Title if known"
    authors: [{first: "First", last: "Last"}]
    year: "YYYY"
    extra: {}
    collection: "Parent-Collection"
    tags: []
```

Paths must be relative to `<FOLDER>` (matching the keys in `scan.json`).

---

## Step 6 — Report

After writing the file, tell the user:
- The collection hierarchy (indented tree)
- Papers assigned / flagged / in books
- Any ambiguous assignments where a paper could fit multiple collections
- Next step: run `/zotero-organize $ARGUMENTS` to generate the batch script, dry-run, and upload — or edit `taxonomy.yaml` manually first.
