"""Consistent, integrity-checked SQLite backup and restore utilities.

Backups are written to a new file with restrictive permissions. Restore never overwrites an
existing destination; operators must explicitly move the current database aside first.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import get_settings


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if path.is_symlink():
        raise ValueError("Database paths must not be symbolic links.")
    if not path.is_file():
        raise ValueError(f"Database file does not exist: {path}")
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _integrity_check(connection: sqlite3.Connection) -> None:
    result = connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        detail = str(result[0]) if result else "no integrity result"
        raise sqlite3.DatabaseError(f"SQLite integrity check failed: {detail}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(source_path: str | Path, destination_path: str | Path) -> dict[str, Any]:
    """Create a consistent SQLite snapshot without replacing an existing destination."""
    source = Path(source_path)
    destination = Path(destination_path)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("Database paths must not be symbolic links.")
    if not source.is_file():
        raise ValueError(f"Source database does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different files.")
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".debuglens-backup-",
        suffix=".sqlite.tmp",
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        with closing(_readonly_connection(source)) as source_db:
            with closing(sqlite3.connect(temporary)) as destination_db:
                source_db.backup(destination_db, pages=256, sleep=0.01)
                destination_db.commit()
                _integrity_check(destination_db)
        with temporary.open("rb+") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        # Destination was checked above; os.link avoids overwriting a file created in a race.
        os.link(temporary, destination)
        temporary.unlink()
        os.chmod(destination, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "path": str(destination.resolve()),
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "integrity": "ok",
    }


def restore_database(backup_path: str | Path, destination_path: str | Path) -> dict[str, Any]:
    """Restore to a new database path after validating the backup; never overwrite."""
    backup = Path(backup_path)
    with closing(_readonly_connection(backup)) as connection:
        _integrity_check(connection)
    return backup_database(backup, destination_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Integrity-checked DebugLens SQLite backup/restore.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup", help="Create a consistent database snapshot.")
    backup_parser.add_argument("--source", default=get_settings().database_path)
    backup_parser.add_argument("--destination", required=True)
    restore_parser = subparsers.add_parser("restore", help="Restore a backup to a new database path.")
    restore_parser.add_argument("--source", required=True, help="Existing backup SQLite file.")
    restore_parser.add_argument("--destination", required=True, help="New destination; must not exist.")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = backup_database(args.source, args.destination)
        else:
            result = restore_database(args.source, args.destination)
    except (ValueError, FileExistsError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({"operation": args.command, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
