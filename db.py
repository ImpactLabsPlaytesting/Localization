import os

DATABASE_URL = os.environ.get('DATABASE_URL', '')


def _is_postgres():
    return DATABASE_URL.startswith('postgres')


class DBWrapper:
    def __init__(self, conn, is_pg):
        self._conn = conn
        self._is_pg = is_pg

    def _convert_query(self, query):
        if self._is_pg:
            return query.replace('?', '%s')
        return query

    def execute(self, query, params=None):
        query = self._convert_query(query)
        if self._is_pg:
            cur = self._conn.cursor()
            cur.execute(query, params or ())
            return cur
        else:
            if params:
                return self._conn.execute(query, params)
            return self._conn.execute(query)

    def executescript(self, script):
        self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    if _is_postgres():
        import psycopg2
        import psycopg2.extras
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        return DBWrapper(conn, True)
    else:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), 'localization.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return DBWrapper(conn, False)


def init_db():
    if _is_postgres():
        import psycopg2
        import psycopg2.extras
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS translators (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                languages TEXT NOT NULL DEFAULT '',
                google_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                sheet_id TEXT NOT NULL,
                main_tab TEXT NOT NULL DEFAULT 'Sheet1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                id SERIAL PRIMARY KEY,
                translator_id INTEGER NOT NULL REFERENCES translators(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                language TEXT NOT NULL,
                tab_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                done_at TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS magic_links (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                translator_id INTEGER NOT NULL REFERENCES translators(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
    else:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), 'localization.db')
        conn = sqlite3.connect(db_path)
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
            CREATE TABLE IF NOT EXISTS magic_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                translator_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (translator_id) REFERENCES translators(id) ON DELETE CASCADE
            );
        ''')
        conn.commit()
        conn.close()
