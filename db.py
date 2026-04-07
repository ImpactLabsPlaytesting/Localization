import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'localization.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS translators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            languages TEXT NOT NULL DEFAULT '',
            google_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            main_tab TEXT NOT NULL DEFAULT 'Sheet1',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            translator_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            tab_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            done_at TIMESTAMP,
            FOREIGN KEY (translator_id) REFERENCES translators(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    conn.close()
