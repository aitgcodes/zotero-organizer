#!/usr/bin/env python3
"""
First-time setup wizard — writes .env and creates collections/ directory.

Run once after cloning:
  python scripts/setup.py

Re-run at any time to update individual variables.
"""

import getpass, json, os, re, shutil, subprocess, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ENV_FILE     = PROJECT_ROOT / ".env"
COLLECTIONS  = PROJECT_ROOT / "collections"

VARS = [
    ("ORGANIZE_HOME",          str(PROJECT_ROOT), False,
     "Project root (where collections/ will live)"),
    ("ZOTERO_USER_ID",         "",                False,
     "Numeric Zotero user ID  (zotero.org → Settings → Feeds/API)"),
    ("ZOTERO_API_KEY",         "",                True,
     "Zotero API key with Read/Write access"),
    ("GOOGLE_DRIVE_FOLDER_ID", "",                False,
     "Drive folder ID from the URL: drive.google.com/drive/folders/<ID>"),
    ("RCLONE_REMOTE",          "gdrive",          False,
     "rclone remote name configured for Google Drive"),
]


def load_env() -> dict[str, str]:
    """Parse existing .env into a dict."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([A-Z_]+)\s*=\s*(.*)$', line)
        if m:
            env[m.group(1)] = m.group(2).strip('"').strip("'")
    return env


def write_env(values: dict[str, str]) -> None:
    lines = []
    for key, val in values.items():
        lines.append(f'{key}={val}')
    ENV_FILE.write_text("\n".join(lines) + "\n")


def prompt(label: str, default: str, secret: bool) -> str:
    display = f"[{'*' * min(len(default), 8) if secret and default else default or 'required'}]"
    prompt_str = f"  {label}\n  {display}: "
    try:
        if secret:
            val = getpass.getpass(prompt_str)
        else:
            val = input(prompt_str).strip()
    except EOFError:
        val = ""
    return val or default


def check_rclone(remote: str) -> bool:
    if not shutil.which("rclone"):
        print("  ✗ rclone not found in PATH. Install from https://rclone.org/install/")
        return False
    result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True)
    remotes = [r.rstrip(":") for r in result.stdout.splitlines()]
    if remote in remotes:
        print(f"  ✓ rclone remote '{remote}' found")
        return True
    print(f"  ✗ rclone remote '{remote}' not configured.")
    print(f"    Run: rclone config  (create a remote named '{remote}')")
    return False


def check_zotero(user_id: str, api_key: str) -> bool:
    try:
        from pyzotero import zotero
        zot = zotero.Zotero(user_id, "user", api_key)
        zot.collections()
        print("  ✓ Zotero API credentials valid")
        return True
    except Exception as e:
        print(f"  ✗ Zotero API check failed: {e}")
        return False


def check_drive(remote: str, folder_id: str) -> bool:
    if not shutil.which("rclone"):
        return False
    result = subprocess.run(
        ["rclone", "lsf", f"{remote}:", f"--drive-root-folder-id={folder_id}", "--max-depth=1"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        print("  ✓ Google Drive folder accessible")
        return True
    print(f"  ✗ Drive folder check failed: {result.stderr.strip()}")
    return False


def main():
    print("=" * 60)
    print("  Zotero Organizer — first-time setup")
    print("=" * 60)

    existing = load_env()
    values: dict[str, str] = {}

    print("\nPress Enter to accept the value shown in brackets.\n")
    for key, default, secret, description in VARS:
        current = existing.get(key, default)
        print(f"{description}")
        val = prompt(key, current, secret)
        if not val and not default:
            print(f"  ⚠  {key} is required. You can re-run setup.py to set it later.")
        values[key] = val

    # Write .env
    write_env(values)
    print(f"\n.env written → {ENV_FILE}")

    # Create collections/
    COLLECTIONS.mkdir(exist_ok=True)
    gitkeep = COLLECTIONS / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    print(f"collections/ ready → {COLLECTIONS}")

    # Validation
    print("\n--- Validating configuration ---")

    all_ok = True

    rclone_ok = check_rclone(values.get("RCLONE_REMOTE", "gdrive"))
    all_ok = all_ok and rclone_ok

    uid = values.get("ZOTERO_USER_ID", "")
    key = values.get("ZOTERO_API_KEY", "")
    if uid and key:
        zotero_ok = check_zotero(uid, key)
        all_ok = all_ok and zotero_ok
    else:
        print("  ⚠  Skipping Zotero check (credentials not set)")
        all_ok = False

    fid = values.get("GOOGLE_DRIVE_FOLDER_ID", "")
    remote = values.get("RCLONE_REMOTE", "gdrive")
    if fid and rclone_ok:
        drive_ok = check_drive(remote, fid)
        all_ok = all_ok and drive_ok
    else:
        print("  ⚠  Skipping Drive check (folder ID not set or rclone unavailable)")

    # Summary
    print("\n" + ("=" * 60))
    if all_ok:
        print("  Setup complete. Next step:")
    else:
        print("  Setup done with warnings — fix the issues above, then:")
    print(f"\n  python scripts/organize.py <pdf-folder> --collection <name>")
    print("=" * 60)


if __name__ == "__main__":
    main()
