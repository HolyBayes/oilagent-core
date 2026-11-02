import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

from analyst.config import configured_path

_locks = [threading.RLock() for _ in range(64)]


class Sessions:
    def __init__(self):
        self.path = configured_path("SESSION_DB_PATH", "workspace/sessions.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT, ts REAL)"
            )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        return db

    @contextmanager
    def turn(self, session_id=""):
        sid = session_id or str(uuid4())
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", sid):
            raise ValueError("Invalid session_id")
        # Fixed lock striping bounds memory and serializes turns within this process.
        with _locks[hash(sid) % len(_locks)]:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE ts < ?", (time.time() - 86400,))
                row = db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            data = json.loads(row[0]) if row else {"messages": [], "route": {}, "release": None}
            yield sid, data
            with self.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)",
                    (sid, json.dumps(data, ensure_ascii=False), time.time()),
                )
