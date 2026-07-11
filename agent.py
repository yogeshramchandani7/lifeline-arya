"""Arya's brain: the GPT-4.1 tool-calling loop for one recruitment call.

A CallSession holds the conversation + control state for a single call. The WS
handler feeds it each donor utterance via handle_user() and speaks back the
returned text. Tools mutate the DB (via repo) and Twilio (SMS / transfer) and set
the call's outcome + disposition.
"""
import json

from openai import OpenAI

import config
import repo
import twilio_client
from prompts import build_system_prompt, welcome_greeting

_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# Disposition severity (higher wins)
_SEVERITY = {"green": 1, "yellow": 2, "orange": 3, "red": 4}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_available_slots",
        "description": "Fetch open, upcoming donation appointment slots to offer the donor.",
        "parameters": {"type": "object", "properties": {
            "preferred_center": {"type": "string", "description": "Optional center name to filter by."}
        }},
    }},
    {"type": "function", "function": {
        "name": "book_appointment",
        "description": "Book the donation appointment the donor chose, by slot id (from get_available_slots).",
        "parameters": {"type": "object", "properties": {
            "slot_id": {"type": "integer"}
        }, "required": ["slot_id"]},
    }},
    {"type": "function", "function": {
        "name": "send_sms_confirmation",
        "description": "Text the donor an SMS confirmation of the appointment just booked.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "decline",
        "description": "Record that the donor declined to donate.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}
        }, "required": ["reason"]},
    }},
    {"type": "function", "function": {
        "name": "schedule_callback",
        "description": "Record a callback because now is not a good time or the donor may be temporarily ineligible.",
        "parameters": {"type": "object", "properties": {
            "when": {"type": "string", "description": "When to call back, in the donor's words."}
        }, "required": ["when"]},
    }},
    {"type": "function", "function": {
        "name": "update_consent",
        "description": "Opt the donor out of future automated calls when they ask not to be contacted.",
        "parameters": {"type": "object", "properties": {
            "opt_out": {"type": "boolean"}
        }, "required": ["opt_out"]},
    }},
    {"type": "function", "function": {
        "name": "transfer_to_coordinator",
        "description": "Live-transfer the donor to a human care coordinator for a medical question you cannot answer.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}
        }, "required": ["reason"]},
    }},
    {"type": "function", "function": {
        "name": "emergency_end_call",
        "description": "Use when the donor reports a medical emergency: after telling them to call 911, end the call.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}
        }, "required": ["reason"]},
    }},
    {"type": "function", "function": {
        "name": "end_call",
        "description": "End the call normally once the conversation is complete.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


class CallSession:
    def __init__(self, call_id: int, donor_id: int, call_sid: str | None = None):
        self.call_id = call_id
        self.donor_id = donor_id
        self.call_sid = call_sid
        self.ctx = repo.donor_context(donor_id) or {}

        self.messages = [
            {"role": "system", "content": build_system_prompt(self.ctx)},
            {"role": "assistant", "content": welcome_greeting(self.ctx)},
        ]
        self.last_appointment: dict | None = None
        self.disposition: str | None = None
        self.outcome: str | None = None
        # control signals read by the WS handler after each turn
        self.ended = False
        self.end_kind = "normal"           # normal | emergency | transfer
        self.transfer_number: str | None = None

    # ---------- disposition ----------
    def _set_disposition(self, color: str) -> None:
        if color not in _SEVERITY:
            return
        if self.disposition is None or _SEVERITY[color] > _SEVERITY[self.disposition]:
            self.disposition = color

    # ---------- main turn ----------
    def handle_user(self, text: str) -> str:
        """Append donor speech, run the tool loop, return Arya's spoken reply."""
        self.messages.append({"role": "user", "content": text})
        reply = ""
        for _ in range(6):  # cap tool hops per turn
            try:
                resp = _openai().chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=self.messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.5,
                    max_tokens=220,
                )  # noqa: E501
            except Exception:
                import logging
                logging.getLogger("arya").exception("OpenAI call failed")
                return "Sorry, I didn't quite catch that — could you say it again?"
            msg = resp.choices[0].message
            if msg.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    result = self._dispatch(tc.function.name, tc.function.arguments)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
                continue  # let the model speak after seeing tool results
            reply = (msg.content or "").strip()
            self.messages.append({"role": "assistant", "content": reply})
            break
        return reply

    # ---------- tool dispatch ----------
    def _dispatch(self, name: str, raw_args: str) -> dict:
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
        fn = getattr(self, f"_tool_{name}", None)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(args)
        except Exception as e:  # keep the call alive even if a tool errors
            return {"error": str(e)}

    def _tool_get_available_slots(self, args: dict) -> dict:
        center = args.get("preferred_center") or self.ctx.get("preferred_center")
        slots = repo.get_available_slots(center=center, limit=4)
        return {"slots": [
            {"slot_id": s["id"], "when": s["starts_at_human"], "center": s["center"]} for s in slots
        ]}

    def _tool_book_appointment(self, args: dict) -> dict:
        appt = repo.book_appointment(self.donor_id, int(args["slot_id"]))
        if not appt:
            return {"ok": False, "error": "That slot is no longer available; offer another."}
        self.last_appointment = appt
        self.outcome = "booked"
        self._set_disposition("green")
        repo.update_call(self.call_id, outcome="booked")
        repo.merge_flags(self.call_id, {
            "appointment": {"when": appt["starts_at_human"], "center": appt["center"]}
        })
        return {"ok": True, "when": appt["starts_at_human"], "center": appt["center"]}

    def _tool_send_sms_confirmation(self, args: dict) -> dict:
        if not self.last_appointment:
            return {"ok": False, "error": "No appointment booked yet."}
        appt = self.last_appointment
        body = (
            f"{config.BANK_NAME}: Your blood donation appointment is confirmed for "
            f"{appt['starts_at_human']} at {appt['center']}. Thank you for helping save lives! "
            f"Call us to change or cancel."
        )
        phone = self.ctx.get("phone")
        try:
            twilio_client.send_sms(phone, body)
            repo.mark_confirmation_sent(appt["appointment_id"])
            repo.merge_flags(self.call_id, {"sms_confirmation_sent": True})
            return {"ok": True}
        except Exception as e:
            repo.merge_flags(self.call_id, {"sms_confirmation_sent": False, "sms_error": str(e)})
            return {"ok": False, "error": str(e)}

    def _tool_decline(self, args: dict) -> dict:
        self.outcome = "declined"
        self._set_disposition("yellow")
        repo.update_call(self.call_id, outcome="declined")
        repo.merge_flags(self.call_id, {"decline_reason": args.get("reason", "")})
        return {"ok": True}

    def _tool_schedule_callback(self, args: dict) -> dict:
        self.outcome = "callback"
        self._set_disposition("yellow")
        when = args.get("when", "")
        repo.update_call(self.call_id, outcome="callback", callback_at=when)
        repo.merge_flags(self.call_id, {"callback_when": when})
        return {"ok": True}

    def _tool_update_consent(self, args: dict) -> dict:
        if args.get("opt_out", True):
            repo.update_consent(self.donor_id, False)
            repo.merge_flags(self.call_id, {"opted_out": True})
        return {"ok": True}

    def _tool_transfer_to_coordinator(self, args: dict) -> dict:
        self.outcome = "transferred"
        self._set_disposition("orange")
        repo.update_call(self.call_id, outcome="transferred")
        repo.merge_flags(self.call_id, {"transfer_reason": args.get("reason", "")})
        if config.COORDINATOR_NUMBER and self.call_sid:
            self.ended = True
            self.end_kind = "transfer"
            self.transfer_number = config.COORDINATOR_NUMBER
            return {"ok": True, "transferring": True,
                    "say": "Let me connect you with a care coordinator now. Please hold."}
        # stubbed transfer (no coordinator number configured)
        repo.merge_flags(self.call_id, {"transfer_stubbed": True})
        return {"ok": True, "transferring": False,
                "say": "I'll have a care coordinator call you back shortly about that."}

    def _tool_emergency_end_call(self, args: dict) -> dict:
        self.outcome = "emergency"
        self._set_disposition("red")
        self.ended = True
        self.end_kind = "emergency"
        repo.update_call(self.call_id, outcome="emergency")
        repo.merge_flags(self.call_id, {"emergency_reason": args.get("reason", "")})
        return {"ok": True,
                "say": "This could be serious. Please hang up now and call 911 right away. Take care."}

    def _tool_end_call(self, args: dict) -> dict:
        self.ended = True
        self.end_kind = "normal"
        return {"ok": True}

    # ---------- finalize ----------
    def finalize(self) -> None:
        # Tools set disposition/outcome on decisive events (book→green, decline/
        # callback→yellow, transfer→orange, emergency→red). If none fired, the
        # call ended without resolution → yellow / incomplete (NEVER green/booked).
        if self.disposition is None:
            self.disposition = "yellow"
        if self.outcome is None:
            self.outcome = "incomplete"
        repo.update_call(
            self.call_id,
            status="done",
            disposition=self.disposition,
            outcome=self.outcome,
        )
