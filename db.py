"""Couche de données SQLite pour Qorb Santé.

Un seul fichier (qorb.db), aucune installation requise.
"""
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("QORB_DB", "qorb.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                center TEXT,
                patient_ref TEXT,
                age INTEGER,
                sex TEXT,
                complaint TEXT,
                history TEXT,
                vitals TEXT,
                image BLOB,
                image_mime TEXT,
                analysis TEXT,
                score INTEGER,
                level TEXT,
                status TEXT DEFAULT 'En attente',
                reply TEXT,
                replied_at TEXT,
                consent INTEGER DEFAULT 0
            )
            """
        )


def add_case(center, patient_ref, age, sex, complaint, history, vitals,
             image, image_mime, analysis, consent):
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO cases (created_at, center, patient_ref, age, sex,
                complaint, history, vitals, image, image_mime, analysis,
                score, level, consent)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                center, patient_ref, age, sex, complaint, history,
                json.dumps(vitals, ensure_ascii=False),
                image, image_mime,
                json.dumps(analysis, ensure_ascii=False),
                analysis["score"], analysis["level"], int(consent),
            ),
        )
        return cur.lastrowid


def _row_to_dict(row):
    d = dict(row)
    d["vitals"] = json.loads(d["vitals"]) if d.get("vitals") else {}
    d["analysis"] = json.loads(d["analysis"]) if d.get("analysis") else {}
    return d


def list_cases(status=None):
    """Retourne les cas, les plus urgents d'abord."""
    q = "SELECT * FROM cases"
    args = ()
    if status:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY score DESC, created_at ASC"
    with _conn() as c:
        return [_row_to_dict(r) for r in c.execute(q, args).fetchall()]


def get_case(case_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return _row_to_dict(r) if r else None


def answer_case(case_id, reply):
    with _conn() as c:
        c.execute(
            "UPDATE cases SET reply = ?, replied_at = ?, status = 'Répondu' WHERE id = ?",
            (reply, datetime.now().isoformat(timespec="seconds"), case_id),
        )


def stats():
    cases = list_cases()
    total = len(cases)
    answered = [c for c in cases if c["status"] == "Répondu"]
    by_level = {}
    for c in cases:
        by_level[c["level"]] = by_level.get(c["level"], 0) + 1
    delays = []
    for c in answered:
        try:
            d = datetime.fromisoformat(c["replied_at"]) - datetime.fromisoformat(c["created_at"])
            delays.append(d.total_seconds() / 60)
        except Exception:
            pass
    return {
        "total": total,
        "pending": total - len(answered),
        "answered": len(answered),
        "by_level": by_level,
        "avg_delay_min": (sum(delays) / len(delays)) if delays else None,
    }
