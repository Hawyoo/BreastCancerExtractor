import sqlite3

from app.db import SCHEMA, connect


def test_regular_connection_does_not_refresh_all_derived_observations(tmp_path, monkeypatch):
    database = tmp_path / "catalog.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA)

    calls = []
    monkeypatch.setattr("app.db.refresh_derived_observations", lambda connection: calls.append(connection))

    with connect(database) as connection:
        connection.execute("SELECT COUNT(*) FROM patients").fetchone()

    assert calls == []
