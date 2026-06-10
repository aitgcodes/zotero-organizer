# Zotero Organizer — AI Skills

Two AI skills are included to automate the most reasoning-intensive part of the
pipeline: grouping papers into thematic collections and assigning tags. Everything
else (scanning PDFs, uploading to Drive, creating Zotero items) is pure Python and
uses no AI tokens.

## The skills

| Skill | Stages | What it does |
|-------|--------|--------------|
| `zotero-taxonomy` | 1–2 | Scans PDFs (if needed) and writes a thematic `taxonomy.yaml` |
| `zotero-organize` | 1–3 | Everything above, then generates the batch script, dry-runs it, confirms, and executes |

`zotero-taxonomy` is useful when you want to review or edit the taxonomy before
committing to a run. `zotero-organize` takes you all the way through in one session.

## Token usage

AI tokens are consumed only during Stage 2 (taxonomy reasoning). The scan and batch
execution are Python subprocesses — zero tokens. Rough estimates for Stage 2:

| Collection size | Approximate input tokens |
|----------------|--------------------------|
| ~30 papers | 2,000–4,000 |
| ~100 papers | 6,000–12,000 |
| ~300 papers | 18,000–35,000 |

---

## Using with Claude Code

If you cloned this repository, the commands are already available — Claude Code picks
up `.claude/commands/` automatically.

```
/zotero-taxonomy ~/Papers/Plasmonics Plasmons
/zotero-organize ~/Papers/Plasmonics Plasmons
```

To use the skills from a **different project** or across all your projects, copy the
command files:

```bash
# Available in one specific project:
cp .claude/commands/zotero-taxonomy.md /path/to/project/.claude/commands/
cp .claude/commands/zotero-organize.md /path/to/project/.claude/commands/

# Available in all projects (user-level):
cp .claude/commands/zotero-taxonomy.md ~/.claude/commands/
cp .claude/commands/zotero-organize.md ~/.claude/commands/
```

---

## Using with other AI platforms

The skill files in `.claude/commands/` double as standalone prompts. To use them with
ChatGPT, Gemini, Mistral, or any other AI:

**Step 1 — Run the scan manually** (this is the Python part, no AI needed):
```bash
python scripts/scan_pdfs.py /path/to/pdfs --collection "MyCollection" \
    --output collections/MyCollection/scan.json --mode scan-only
```

**Step 2 — Start a new conversation** with your AI and paste the following as the
system prompt (or first message):

> Paste the full contents of `.claude/commands/zotero-taxonomy.md` here.

Then paste the contents of `collections/MyCollection/scan.json` as your next message.

**Step 3 — Save the output** as `collections/MyCollection/taxonomy.yaml`.

**Step 4 — Generate the batch script and run:**
```bash
python scripts/generate_batch.py --mode taxonomy \
    collections/MyCollection/taxonomy.yaml \
    collections/MyCollection/scan.json \
    --output collections/MyCollection/batch_run.py

python collections/MyCollection/batch_run.py --dry-run
python collections/MyCollection/batch_run.py
```

### Tips for other platforms

- If the AI truncates the taxonomy, ask it to continue from where it stopped.
- For large collections (200+ papers), split `scan.json` into batches by `parent_dir`
  and run the taxonomy prompt once per batch, then merge the YAML sections.
- The skill files contain no Claude-specific syntax — they are plain markdown
  instructions that any instruction-following model can follow.
