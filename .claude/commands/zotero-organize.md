Run the full zotero-organizer pipeline end-to-end (Stages 1–3): scan PDFs, build a thematic taxonomy, then create Zotero items and upload to Google Drive.

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

## Step 2 — Ensure scan.json exists (Stage 1)

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

## Step 4 — Design and write the taxonomy (Stage 2)

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
- Set `search_query` to the most informative fragment of `fallback_header`.

### Books and theses
- If a flagged entry looks like a book, thesis, or technical report, move it to `books`.
- Use `type: book`, `type: thesis`, or `type: document`.
- Fill in `title`, `authors`, `year`, and `extra` where inferable.

Write the taxonomy to `collections/<COLLECTION>/taxonomy.yaml`:

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

Show the user the collection hierarchy (indented tree) and a summary of assignments. Ask the user: **"Does this taxonomy look right? Type 'yes' to continue, or describe any changes and I'll update the file before proceeding."** Wait for their response and apply any edits before moving to Stage 3.

---

## Step 5 — Generate the batch script (Stage 3 setup)

Once the user confirms the taxonomy, generate the batch script:

```bash
python scripts/generate_batch.py --mode taxonomy \
    "collections/<COLLECTION>/taxonomy.yaml" \
    "collections/<COLLECTION>/scan.json" \
    --output "collections/<COLLECTION>/batch_run.py"
```

---

## Step 6 — Dry run

Run the dry run and show the full output to the user:

```bash
python "collections/<COLLECTION>/batch_run.py" --dry-run
```

---

## Step 7 — Confirm and execute

Ask the user: **"The dry run is complete. Proceed with the real run? This will create Zotero items and upload PDFs to Google Drive. Type 'yes' to confirm."**

If the user confirms, run:
```bash
python "collections/<COLLECTION>/batch_run.py"
```

Stream the output. When complete, report: items created, uploads succeeded, any errors.

If the user says no, tell them they can run it manually later:
```bash
python collections/<COLLECTION>/batch_run.py
```
