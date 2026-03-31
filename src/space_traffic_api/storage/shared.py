from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass


@dataclass(slots=True)
class StorageContext:
    db_path: str
    conn: sqlite3.Connection
    lock: threading.Lock
