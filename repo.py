"""Repository layer — the ONLY module that touches SQLite.

In production these functions would call the blood bank's Donor CRM / scheduling
system; here they hit the local `lifeline.db`. Agent code depends on this
interface, not on SQL, so the real integration is a swap of this file.
"""
import json
from datetime import datetime, date, timedelta

from db import connect
from config import ELIGIBILITY_DAYS


# ---------- date helpers ----------

def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def eligible_since(last_donation_date: str | None) -> date | None:
    d = _parse_date(last_donation_date)
    if d is None:
        return None
    return d + timedelta(days=ELIGIBILITY_DAYS)


def is_eligible(last_donation_date: str | None) -> bool:
    es = eligible_since(last_donation_date)
    return es is None or es <= date.today()


def human_date(iso: str | None) -> str:
    d = _parse_date(iso)
    return d.strftime("%A, %B %-d, %Y") if d else "an unknown date"


def human_datetime(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%A, %B %-d at %-I:%M %p")


# ---------- donors ----------

def get_donor(donor_id: int) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM donors WHERE id = ?", (donor_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_donors() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM donors ORDER BY id").fetchall()
    conn.close()
    return [_donor_view(dict(r)) for r in rows]


def eligible_donors(blood_type: str, center: str | None = None) -> list[dict]:
    """Donors of a blood type who can be recruited: eligible, consented, active."""
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM donors WHERE blood_type = ? AND contact_consent = 1 AND status = 'active'",
        (blood_type,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if not is_eligible(d["last_donation_date"]):
            continue
        if center and d.get("preferred_center") and d["preferred_center"] != center:
            continue
        out.append(_donor_view(d))
    return out


def _donor_view(d: dict) -> dict:
    """Adds computed fields used by the UI + prompt."""
    es = eligible_since(d["last_donation_date"])
    d = dict(d)
    d["eligible_since"] = es.isoformat() if es else None
    d["eligible_now"] = is_eligible(d["last_donation_date"])
    d["contact_consent"] = bool(d["contact_consent"])
    return d


def donor_context(donor_id: int) -> dict | None:
    d = get_donor(donor_id)
    if not d:
        return None
    d = _donor_view(d)
    d["eligible_since_human"] = human_date(d["eligible_since"]) if d["eligible_since"] else "your last visit"
    d["last_donation_human"] = human_date(d["last_donation_date"]) if d["last_donation_date"] else "no prior donation on record"
    return d


def update_consent(donor_id: int, consent: bool) -> None:
    conn = connect()
    conn.execute("UPDATE donors SET contact_consent = ? WHERE id = ?", (1 if consent else 0, donor_id))
    conn.commit()
    conn.close()


# ---------- slots + appointments ----------

def get_available_slots(center: str | None = None, limit: int = 6) -> list[dict]:
    conn = connect()
    now = datetime.now().isoformat()
    q = "SELECT * FROM slots WHERE status = 'open' AND starts_at > ?"
    args: list = [now]
    if center:
        q += " AND center = ?"
        args.append(center)
    q += " ORDER BY starts_at LIMIT ?"
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return [{**dict(r), "starts_at_human": human_datetime(r["starts_at"])} for r in rows]


def book_appointment(donor_id: int, slot_id: int) -> dict | None:
    conn = connect()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot or slot["status"] != "open":
        conn.close()
        return None
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO appointments (donor_id, slot_id, created_at, confirmation_sent) VALUES (?,?,?,0)",
        (donor_id, slot_id, now),
    )
    appt_id = cur.lastrowid
    booked = slot["booked_count"] + 1
    status = "full" if booked >= slot["capacity"] else "open"
    conn.execute("UPDATE slots SET booked_count = ?, status = ? WHERE id = ?", (booked, status, slot_id))
    conn.commit()
    conn.close()
    return {
        "appointment_id": appt_id,
        "slot_id": slot_id,
        "center": slot["center"],
        "starts_at": slot["starts_at"],
        "starts_at_human": human_datetime(slot["starts_at"]),
    }


def mark_confirmation_sent(appointment_id: int) -> None:
    conn = connect()
    conn.execute("UPDATE appointments SET confirmation_sent = 1 WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()


# ---------- campaigns ----------

def create_campaign(blood_type: str, center: str | None, selected_count: int) -> int:
    conn = connect()
    cur = conn.execute(
        "INSERT INTO campaigns (blood_type, center, created_at, selected_count, called_count) VALUES (?,?,?,?,0)",
        (blood_type, center, datetime.now().isoformat(), selected_count),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def increment_campaign_called(campaign_id: int) -> None:
    conn = connect()
    conn.execute("UPDATE campaigns SET called_count = called_count + 1 WHERE id = ?", (campaign_id,))
    conn.commit()
    conn.close()


def list_campaigns() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM campaigns ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- calls ----------

def create_call(donor_id: int, campaign_id: int | None = None, call_sid: str | None = None) -> int:
    conn = connect()
    cur = conn.execute(
        "INSERT INTO calls (donor_id, campaign_id, call_sid, transcript, flags, status, created_at) "
        "VALUES (?,?,?,'[]','{}','dialing',?)",
        (donor_id, campaign_id, call_sid, datetime.now().isoformat()),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_call(call_id: int) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["transcript"] = json.loads(d.get("transcript") or "[]")
    d["flags"] = json.loads(d.get("flags") or "{}")
    return d


def get_call_by_sid(call_sid: str) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM calls WHERE call_sid = ?", (call_sid,)).fetchone()
    conn.close()
    if not row:
        return None
    return get_call(row["id"])


def list_calls() -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT c.*, d.name AS donor_name, d.blood_type FROM calls c "
        "JOIN donors d ON d.id = c.donor_id ORDER BY c.id DESC"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["transcript"] = json.loads(d.get("transcript") or "[]")
        d["flags"] = json.loads(d.get("flags") or "{}")
        out.append(d)
    return out


def append_transcript(call_id: int, role: str, text: str) -> None:
    conn = connect()
    row = conn.execute("SELECT transcript FROM calls WHERE id = ?", (call_id,)).fetchone()
    if not row:
        conn.close()
        return
    turns = json.loads(row["transcript"] or "[]")
    turns.append({"role": role, "text": text, "ts": datetime.now().isoformat()})
    conn.execute("UPDATE calls SET transcript = ? WHERE id = ?", (json.dumps(turns), call_id))
    conn.commit()
    conn.close()


def update_call(call_id: int, **fields) -> None:
    if not fields:
        return
    if "flags" in fields and isinstance(fields["flags"], (dict, list)):
        fields["flags"] = json.dumps(fields["flags"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = connect()
    conn.execute(f"UPDATE calls SET {cols} WHERE id = ?", (*fields.values(), call_id))
    conn.commit()
    conn.close()


def merge_flags(call_id: int, new: dict) -> None:
    conn = connect()
    row = conn.execute("SELECT flags FROM calls WHERE id = ?", (call_id,)).fetchone()
    flags = json.loads(row["flags"] or "{}") if row else {}
    flags.update(new)
    conn.execute("UPDATE calls SET flags = ? WHERE id = ?", (json.dumps(flags), call_id))
    conn.commit()
    conn.close()
