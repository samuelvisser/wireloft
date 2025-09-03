from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Optional

from .data import media_profiles as seed_media_profiles
from .data import shows as seed_shows
from .data import episodes as seed_episodes

# Default DB location: project_root\\data\\wireloft.db

def _compute_project_root() -> str:
    # Starting from this file: ...\\server\\backend\\src\\backend\\dblegacy.py
    # Go up 4 levels to reach the repository root
    here = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    return root

PROJECT_ROOT = _compute_project_root()
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "data", "wireloft.db")

print(f"Using project root: {PROJECT_ROOT}")
print(f"Using DB path: {DEFAULT_DB_PATH}")

def connect_db(db_path: Optional[str] = None, require_exists: bool = True) -> sqlite3.Connection:
    path = db_path or os.environ.get("WIRELOFT_DB_PATH") or DEFAULT_DB_PATH
    # Ensure directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if require_exists and not os.path.exists(path):
        raise FileNotFoundError(
            f"Database not found at: {path}. Initialize it with 'backend-api --init-db' or provide --db."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def init_db(db_path: Optional[str] = None) -> None:
    conn = connect_db(db_path, require_exists=False)
    try:
        cur = conn.cursor()
        # Enable foreign keys
        cur.execute("PRAGMA foreign_keys = ON;")

        # shows table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT,
                dw_id TEXT,
                slug TEXT UNIQUE,
                name TEXT,
                description TEXT,
                author TEXT,
                download_media INTEGER DEFAULT 0,
                download_delay_minutes INTEGER DEFAULT 0,
                redownload_delay_minutes INTEGER DEFAULT 0,
                download_days_in_past INTEGER DEFAULT 0,
                delete_older_episodes INTEGER DEFAULT 0,
                title_filter TEXT,
                created_date TEXT NOT NULL,
                modified_date TEXT NOT NULL
            );
            """
        )

        # episodes table (id increments per show; composite PK on (show_id, id))
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER NOT NULL,
                show_id INTEGER NOT NULL,
                uuid TEXT,
                dw_id TEXT,
                slug TEXT,
                title TEXT,
                description TEXT,
                went_live_date TEXT,
                published_date TEXT,
                downloaded_date TEXT,
                redownloaded_date TEXT,
                created_date TEXT NOT NULL,
                modified_date TEXT NOT NULL,
                PRIMARY KEY (show_id, id),
                FOREIGN KEY (show_id) REFERENCES shows(id) ON DELETE CASCADE
            );
            """
        )

        # media_profiles table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS media_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                output_template TEXT,
                preferred_format TEXT,
                download_series_images INTEGER DEFAULT 0,
                created_date TEXT NOT NULL,
                modified_date TEXT NOT NULL
            );
            """
        )

        # settings table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                value TEXT,
                created_date TEXT NOT NULL,
                modified_date TEXT NOT NULL
            );
            """
        )

        conn.commit()
    finally:
        conn.close()

def seed_db(db_path: Optional[str] = None) -> None:
    """Seed database using the hardcoded data from backend.data.

    This function is idempotent: it checks for existing rows by natural keys (slug/name)
    before inserting to avoid duplicates.
    """
    # Ensure schema exists
    init_db(db_path)

    conn = connect_db(db_path)
    try:
        cur = conn.cursor()
        now = _now_iso()

        # Seed media profiles
        for mp in seed_media_profiles:
            # Check by name
            cur.execute("SELECT id FROM media_profiles WHERE name = ?", (mp["name"],))
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO media_profiles (name, output_template, preferred_format, download_series_images, created_date, modified_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mp.get("name"),
                        mp.get("outputPathTemplate"),
                        mp.get("preferredFormat"),
                        1 if mp.get("downloadSeriesImages") else 0,
                        now,
                        now,
                    ),
                )

        # Seed shows first, build slug -> show_id map
        slug_to_show_id: dict[str, int] = {}
        for s in seed_shows:
            slug = s.get("slug")
            name = s.get("title")
            author = s.get("author")
            description = f"Years: {s.get('years')}" if s.get("years") else None

            # Upsert-like behavior: insert if not exists by slug
            cur.execute("SELECT id FROM shows WHERE slug = ?", (slug,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO shows (uuid, dw_id, slug, name, description, author,
                                       download_media, download_delay_minutes, redownload_delay_minutes,
                                       download_days_in_past, delete_older_episodes, title_filter,
                                       created_date, modified_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        None,  # uuid
                        None,  # dw_id
                        slug,
                        name,
                        description,
                        author,
                        0,     # download_media
                        0,     # download_delay_minutes
                        0,     # redownload_delay_minutes
                        0,     # download_days_in_past
                        0,     # delete_older_episodes
                        None,  # title_filter
                        now,
                        now,
                    ),
                )
                show_id = cur.lastrowid
            else:
                show_id = row["id"]

            slug_to_show_id[slug] = show_id
            sid_key = s.get("id")
            if sid_key is not None:
                try:
                    slug_to_show_id[str(int(sid_key))] = show_id
                except Exception:
                    slug_to_show_id[str(sid_key)] = show_id

        # Detect current episodes table columns (handle legacy schemas gracefully)
        cur.execute("PRAGMA table_info(episodes);")
        episode_cols = {row[1] for row in cur.fetchall()}  # name is at index 1 in pragma output

        # Seed episodes
        for e in seed_episodes:
            show_slug = e.get("show_id")
            show_id = slug_to_show_id.get(show_slug)
            if show_id is None:
                # Skip episodes whose show wasn't created for some reason
                continue

            # Determine per-show incremental id: prefer 'index', fallback to 'id'
            number = e.get("index") if e.get("index") is not None else e.get("id")
            title = e.get("title")
            uuid_v = e.get("uuid")
            dw_id_v = e.get("dw_id")
            slug_v = e.get("slug") or (f"{show_slug}-{number}" if (show_slug is not None and number is not None) else None)
            description_v = e.get("description") if e.get("description") is not None else e.get("status")
            status_v = e.get("status") if e.get("status") is not None else description_v
            went_live_date_v = e.get("went_live_date")
            published_date_v = e.get("published_date")
            downloaded_date_v = e.get("downloaded_date")
            redownloaded_date_v = e.get("redownloaded_date")
            created_date_v = e.get("created_date") or now
            modified_date_v = e.get("modified_date") or now

            if number is None:
                # Cannot seed without a per-show episode number
                continue

            # Check if an episode with same (show_id, id) exists
            cur.execute(
                "SELECT 1 FROM episodes WHERE show_id = ? AND id = ?",
                (show_id, number),
            )
            if cur.fetchone() is None:
                # Build dynamic column list based on actual table schema
                cols = ["id", "show_id", "uuid", "dw_id", "slug", "title"]
                vals = [number, show_id, uuid_v, dw_id_v, slug_v, title]
                if "description" in episode_cols:
                    cols.append("description")
                    vals.append(description_v)
                if "status" in episode_cols:
                    cols.append("status")
                    vals.append(status_v)
                if "went_live_date" in episode_cols:
                    cols.append("went_live_date")
                    vals.append(went_live_date_v)
                if "published_date" in episode_cols:
                    cols.append("published_date")
                    vals.append(published_date_v)
                if "downloaded_date" in episode_cols:
                    cols.append("downloaded_date")
                    vals.append(downloaded_date_v)
                if "redownloaded_date" in episode_cols:
                    cols.append("redownloaded_date")
                    vals.append(redownloaded_date_v)
                if "created_date" in episode_cols:
                    cols.append("created_date")
                    vals.append(created_date_v)
                if "modified_date" in episode_cols:
                    cols.append("modified_date")
                    vals.append(modified_date_v)

                placeholders = ", ".join(["?"] * len(cols))
                collist = ", ".join(cols)
                sql = f"INSERT INTO episodes ({collist}) VALUES ({placeholders})"
                cur.execute(sql, tuple(vals))

        # Seed some default settings if empty
        cur.execute("SELECT COUNT(*) AS c FROM settings")
        if cur.fetchone()[0] == 0:
            defaults = [
                ("download_root", "Download root path", "D:\\Downloads\\DailyWire"),
                ("concurrency", "Concurrent downloads", "2"),
            ]
            for slug, name, value in defaults:
                cur.execute(
                    "INSERT INTO settings (slug, name, value, created_date, modified_date) VALUES (?, ?, ?, ?, ?)",
                    (slug, name, value, now, now),
                )

        conn.commit()
    finally:
        conn.close()
