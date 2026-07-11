"""Seed realistic demo data.

The FIRST donor is the one we actually call in the demo, so its phone comes from
the DEMO_PHONE env var (your Twilio-verified number). Everyone else is fabricated.

Run:  uv run python seed.py
"""
import os
from datetime import datetime, timedelta, date

from db import connect, init_db

DEMO_PHONE = os.getenv("DEMO_PHONE", "+10000000000")
CENTERS = ["Downtown Donor Center", "Riverside Donor Center"]


def _iso(d: date) -> str:
    return d.isoformat()


def seed() -> None:
    init_db()
    conn = connect()
    cur = conn.cursor()

    # Wipe existing rows (idempotent reseed) and reset AUTOINCREMENT so ids are
    # stable (donors 1..5) on every reseed.
    for t in ("appointments", "calls", "campaigns", "slots", "donors"):
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM sqlite_sequence")

    today = date.today()

    # --- Donors --- (donor #1 = the verified demo phone; O-negative + eligible)
    donors = [
        # name, phone, dob, blood_type, last_donation (days ago or None), center, consent
        ("Alex Morgan",   DEMO_PHONE,      "1991-03-14", "O-negative", 92,  CENTERS[0], 1),
        ("Priya Sharma",  "+14155550123",  "1988-07-22", "O-negative", 120, CENTERS[1], 1),
        ("Jordan Lee",    "+14155550145",  "1995-11-02", "O-positive", 70,  CENTERS[0], 1),
        ("Sam Rivera",    "+14155550178",  "1990-01-30", "O-negative", 18,  CENTERS[0], 1),   # ineligible (recent)
        ("Taylor Brooks", "+14155550199",  "1979-05-09", "A-positive", 200, CENTERS[1], 0),   # opted out
    ]
    for name, phone, dob, bt, ago, center, consent in donors:
        last = _iso(today - timedelta(days=ago)) if ago is not None else None
        cur.execute(
            """INSERT INTO donors (name, phone, dob, blood_type, last_donation_date,
                                   status, preferred_center, contact_consent)
               VALUES (?,?,?,?,?,?,?,?)""",
            (name, phone, dob, bt, last, "active", center, consent),
        )

    # --- Slots --- next 7 days, a few times per center, all open
    times = [(9, 0), (11, 30), (14, 0), (16, 30)]
    for day_offset in range(1, 8):
        d = today + timedelta(days=day_offset)
        for center in CENTERS:
            for hh, mm in times:
                starts = datetime(d.year, d.month, d.day, hh, mm)
                cur.execute(
                    "INSERT INTO slots (center, starts_at, capacity, booked_count, status) VALUES (?,?,?,?,?)",
                    (center, starts.isoformat(), 2, 0, "open"),
                )

    conn.commit()
    n_don = cur.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    n_slot = cur.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
    conn.close()
    print(f"Seeded {n_don} donors and {n_slot} slots.")
    print(f"Demo donor 'Alex Morgan' (O-negative, eligible) -> phone {DEMO_PHONE}")
    if DEMO_PHONE == "+10000000000":
        print("WARNING: DEMO_PHONE not set. Export DEMO_PHONE=+1<your verified number> and reseed.")


if __name__ == "__main__":
    seed()
