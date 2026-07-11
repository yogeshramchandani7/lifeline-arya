"""SQLite schema + connection helper.

Five tables model the blood bank's world:
  donors        -> mocks the Donor CRM / EHR (integration seam)
  slots         -> the bank's appointment availability
  appointments  -> bookings Arya makes
  campaigns     -> one shortage campaign (blood type in demand)
  calls         -> per-call record: transcript, outcome, disposition
"""
import sqlite3
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS donors (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    phone             TEXT NOT NULL,
    dob               TEXT,                -- ISO date, display-only (from hospital system)
    blood_type        TEXT NOT NULL,
    last_donation_date TEXT,               -- ISO date; NULL = never donated
    status            TEXT DEFAULT 'active',
    preferred_center  TEXT,
    contact_consent   INTEGER DEFAULT 1    -- 1 = may contact, 0 = opted out
);

CREATE TABLE IF NOT EXISTS slots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    center        TEXT NOT NULL,
    starts_at     TEXT NOT NULL,           -- ISO datetime
    capacity      INTEGER DEFAULT 1,
    booked_count  INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'open'      -- open | full
);

CREATE TABLE IF NOT EXISTS appointments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id          INTEGER NOT NULL,
    slot_id           INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    confirmation_sent INTEGER DEFAULT 0,
    FOREIGN KEY (donor_id) REFERENCES donors(id),
    FOREIGN KEY (slot_id)  REFERENCES slots(id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    blood_type     TEXT NOT NULL,
    center         TEXT,
    created_at     TEXT NOT NULL,
    selected_count INTEGER DEFAULT 0,
    called_count   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id     INTEGER NOT NULL,
    campaign_id  INTEGER,
    call_sid     TEXT,
    transcript   TEXT DEFAULT '[]',        -- JSON list of {role, text}
    outcome      TEXT,                      -- booked | callback | declined | ineligible | transferred | emergency | no_answer
    flags        TEXT DEFAULT '{}',         -- JSON dict of structured facts
    disposition  TEXT,                      -- red | orange | yellow | green
    callback_at  TEXT,
    status       TEXT DEFAULT 'dialing',    -- dialing | in_progress | done | failed
    created_at   TEXT NOT NULL,
    FOREIGN KEY (donor_id) REFERENCES donors(id)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized schema at {DB_PATH}")
