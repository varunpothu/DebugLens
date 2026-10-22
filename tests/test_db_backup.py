import sqlite3

import pytest

from app.db_backup import backup_database, restore_database


def create_database(path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY, message TEXT NOT NULL)")
        db.execute("INSERT INTO events (message) VALUES (?)", ("synthetic record",))
        db.commit()


def read_messages(path) -> list[str]:
    with sqlite3.connect(path) as db:
        return [row[0] for row in db.execute("SELECT message FROM events ORDER BY event_id")]


def test_backup_and_restore_preserve_data_and_return_integrity_metadata(tmp_path) -> None:
    source = tmp_path / "live.sqlite"
    backup = tmp_path / "backups" / "snapshot.sqlite"
    restored = tmp_path / "restored.sqlite"
    create_database(source)

    backup_result = backup_database(source, backup)
    restore_result = restore_database(backup, restored)

    assert read_messages(source) == ["synthetic record"]
    assert read_messages(backup) == ["synthetic record"]
    assert read_messages(restored) == ["synthetic record"]
    assert backup_result["integrity"] == "ok"
    assert restore_result["integrity"] == "ok"
    assert len(backup_result["sha256"]) == 64
    assert backup.stat().st_mode & 0o777 == 0o600


def test_backup_and_restore_never_overwrite_existing_files(tmp_path) -> None:
    source = tmp_path / "live.sqlite"
    backup = tmp_path / "backup.sqlite"
    existing = tmp_path / "existing.sqlite"
    create_database(source)
    create_database(existing)

    with pytest.raises(FileExistsError):
        backup_database(source, existing)

    backup_database(source, backup)
    with pytest.raises(FileExistsError):
        restore_database(backup, existing)

    assert read_messages(existing) == ["synthetic record"]


def test_restore_rejects_corrupt_backup(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a SQLite database")

    with pytest.raises(sqlite3.DatabaseError):
        restore_database(corrupt, tmp_path / "restored.sqlite")


def test_backup_rejects_missing_source(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        backup_database(tmp_path / "missing.sqlite", tmp_path / "backup.sqlite")
