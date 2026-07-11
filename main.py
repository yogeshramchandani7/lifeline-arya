"""FastAPI app: operator console + REST API + ConversationRelay WebSocket.

Run:  uv run uvicorn main:app --port 8000 --reload
(with `ngrok http 8000` and PUBLIC_URL set to the ngrok host)
"""
import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import repo
import twilio_client
from agent import CallSession
from db import init_db
from prompts import welcome_greeting

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arya")

app = FastAPI(title="LifeLine — Arya")
STATIC = Path(__file__).parent / "static"
app.mount("/media", StaticFiles(directory=str(STATIC)), name="media")


@app.on_event("startup")
def _startup():
    init_db()


# ---------------- console ----------------
@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


# ---------------- REST API ----------------
@app.get("/api/donors")
def api_donors():
    return repo.list_donors()


@app.get("/api/calls")
def api_calls():
    return repo.list_calls()


@app.get("/api/calls/{call_id}")
def api_call(call_id: int):
    call = repo.get_call(call_id)
    return call or JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/campaigns")
def api_campaigns():
    return repo.list_campaigns()


@app.get("/api/slots")
def api_slots(center: str | None = None, limit: int = 6):
    return repo.get_available_slots(center=center, limit=limit)


@app.get("/api/config")
def api_config():
    """Lets the console enable/disable actions based on which creds are present."""
    return {
        "phone_ready": config.twilio_ready() and bool(config.PUBLIC_URL),
        "browser_voice_ready": config.browser_voice_ready() and bool(config.PUBLIC_URL),
    }


# ---------------- Browser voice (Twilio Voice SDK) ----------------
@app.get("/api/voice-token")
def api_voice_token():
    if not config.browser_voice_ready():
        return JSONResponse({"error": "browser voice not configured"}, status_code=400)
    return {"token": twilio_client.mint_voice_token(), "identity": "operator"}


class BrowserCallReq(BaseModel):
    donor_id: int


@app.post("/api/browser-call")
def api_browser_call(req: BrowserCallReq):
    """Pre-create the call row so the browser can poll its transcript; returns call_id."""
    donor = repo.get_donor(req.donor_id)
    if not donor:
        return JSONResponse({"error": "donor not found"}, status_code=404)
    call_id = repo.create_call(req.donor_id)
    return {"call_id": call_id, "donor": donor}


@app.post("/voice/browser")
async def voice_browser(request: Request):
    """TwiML App Voice URL. Twilio hits this when the browser Device connects;
    returns ConversationRelay TwiML wiring the browser audio to our /ws agent."""
    form = await request.form()
    donor_id = int(form.get("donor_id", 0))
    call_id = int(form.get("call_id", 0))
    ctx = repo.donor_context(donor_id) or {}
    if call_id:
        repo.update_call(call_id, call_sid=form.get("CallSid"))
    twiml = twilio_client.conversation_relay_twiml(donor_id, call_id, welcome_greeting(ctx))
    return PlainTextResponse(twiml, media_type="text/xml")


def _start_call(donor: dict, campaign_id: int | None = None) -> dict:
    """Create a call row, place the Twilio ConversationRelay call, return call info."""
    ctx = repo.donor_context(donor["id"])
    call_id = repo.create_call(donor["id"], campaign_id=campaign_id)
    if not config.twilio_ready() or not config.PUBLIC_URL:
        repo.update_call(call_id, status="failed")
        return {"call_id": call_id, "error": "Twilio/PUBLIC_URL not configured", "donor": donor}
    twiml = twilio_client.conversation_relay_twiml(donor["id"], call_id, welcome_greeting(ctx))
    try:
        sid = twilio_client.place_call(donor["phone"], twiml)
        repo.update_call(call_id, call_sid=sid)
        return {"call_id": call_id, "call_sid": sid, "donor": donor}
    except Exception as e:
        log.exception("place_call failed")
        repo.update_call(call_id, status="failed")
        return {"call_id": call_id, "error": str(e), "donor": donor}


class CallReq(BaseModel):
    donor_id: int


@app.post("/api/call")
def api_call_start(req: CallReq):
    donor = repo.get_donor(req.donor_id)
    if not donor:
        return JSONResponse({"error": "donor not found"}, status_code=404)
    return _start_call(donor)


class CampaignReq(BaseModel):
    blood_type: str
    center: str | None = None


@app.post("/api/campaign")
def api_campaign(req: CampaignReq):
    cohort = repo.eligible_donors(req.blood_type, center=req.center)
    if not cohort:
        return JSONResponse({"error": f"No eligible {req.blood_type} donors found."}, status_code=400)
    campaign_id = repo.create_campaign(req.blood_type, req.center, len(cohort))
    # Demo scope: place ONE real call — to the first eligible donor.
    first = cohort[0]
    result = _start_call(first, campaign_id=campaign_id)
    repo.increment_campaign_called(campaign_id)
    return {
        "campaign_id": campaign_id,
        "blood_type": req.blood_type,
        "selected": cohort,
        "calling": first,
        "call": result,
    }


# ---------------- ConversationRelay WebSocket ----------------
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    params = websocket.query_params
    donor_id = int(params.get("donor_id", 0))
    call_id = int(params.get("call_id", 0))

    call_row = repo.get_call(call_id)
    call_sid = call_row["call_sid"] if call_row else None
    session = CallSession(call_id=call_id, donor_id=donor_id, call_sid=call_sid)

    repo.update_call(call_id, status="in_progress")
    # persist the greeting Twilio speaks so the console transcript shows it
    repo.append_transcript(call_id, "assistant", welcome_greeting(session.ctx))
    log.info("WS open: call_id=%s donor_id=%s", call_id, donor_id)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "setup":
                if msg.get("callSid"):
                    session.call_sid = msg["callSid"]
                    repo.update_call(call_id, call_sid=msg["callSid"])

            elif mtype == "prompt":
                user_text = (msg.get("voicePrompt") or "").strip()
                if not user_text:
                    continue
                repo.append_transcript(call_id, "user", user_text)
                reply = await asyncio.to_thread(session.handle_user, user_text)
                if reply:
                    repo.append_transcript(call_id, "assistant", reply)
                    await websocket.send_text(json.dumps({"type": "text", "token": reply, "last": True}))

                if session.ended:
                    await _end(websocket, session)
                    break

            elif mtype == "interrupt":
                # donor barged in; ConversationRelay handles TTS cutoff. Nothing to do.
                pass

            elif mtype == "error":
                log.warning("CR error: %s", msg.get("description"))

    except WebSocketDisconnect:
        log.info("WS disconnect: call_id=%s", call_id)
    except Exception:
        log.exception("WS error: call_id=%s", call_id)
    finally:
        session.finalize()
        log.info("WS closed: call_id=%s disposition=%s outcome=%s",
                 call_id, session.disposition, session.outcome)


async def _end(websocket: WebSocket, session: CallSession) -> None:
    """Terminate the call: live-transfer via Twilio, or hang up via CR end."""
    if session.end_kind == "transfer" and session.transfer_number and session.call_sid:
        # brief pause so the handoff line finishes speaking, then redirect
        await asyncio.sleep(2.5)
        try:
            await asyncio.to_thread(twilio_client.transfer_call, session.call_sid, session.transfer_number)
        except Exception:
            log.exception("transfer failed")
    else:
        try:
            await websocket.send_text(json.dumps({"type": "end"}))
        except Exception:
            pass


# ---------------- Web Speech browser voice (no Twilio) ----------------
@app.websocket("/ws/webspeech")
async def ws_webspeech(websocket: WebSocket):
    """Twilio-free browser voice: the page does STT/TTS with the Web Speech API
    and exchanges plain text with Arya's brain here.
    Client -> {type:'user', text}; Server -> {type:'say', text} / {type:'end'}."""
    await websocket.accept()
    params = websocket.query_params
    donor_id = int(params.get("donor_id", 0))
    call_id = int(params.get("call_id", 0))
    session = CallSession(call_id=call_id, donor_id=donor_id, call_sid=None)

    repo.update_call(call_id, status="in_progress")
    greeting = welcome_greeting(session.ctx)
    repo.append_transcript(call_id, "assistant", greeting)
    await websocket.send_text(json.dumps({"type": "say", "text": greeting}))
    log.info("WebSpeech WS open: call_id=%s donor_id=%s", call_id, donor_id)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "user":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                repo.append_transcript(call_id, "user", text)
                reply = await asyncio.to_thread(session.handle_user, text)
                if reply:
                    repo.append_transcript(call_id, "assistant", reply)
                    await websocket.send_text(json.dumps({"type": "say", "text": reply}))
                if session.ended:
                    await websocket.send_text(json.dumps({"type": "end"}))
                    break
    except WebSocketDisconnect:
        log.info("WebSpeech WS disconnect: call_id=%s", call_id)
    except Exception:
        log.exception("WebSpeech WS error: call_id=%s", call_id)
    finally:
        session.finalize()
        log.info("WebSpeech WS closed: call_id=%s disposition=%s", call_id, session.disposition)
