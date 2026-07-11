# Arya — AI Blood-Donor Recruitment Agent

An outbound voice agent blood banks use to run **shortage-driven recruitment campaigns**. Staff declares
a blood type in shortage; the system selects eligible donors (≥56 days since last donation, consented);
**Arya** calls a donor, personalizes the ask, **books a real appointment from the bank's slot inventory,
and texts an SMS confirmation** — all over a live phone call.

Built for **AI Healthcare Hack NYC**. Twilio-native.

## Stack
- **Telephony:** Twilio **ConversationRelay** (Twilio manages STT/TTS/turn-taking; Deepgram + ElevenLabs)
- **Brain:** OpenAI **GPT-4.1** with tool-calling, over the ConversationRelay WebSocket
- **Backend:** FastAPI (REST + `/ws`), SQLite behind a `repo.py` seam (mocks the Donor CRM / scheduling DB)
- **Console:** single-page two-panel operator console (donor record ↔ live transcript)

```
Console → POST /api/campaign → FastAPI → Twilio calls.create(ConversationRelay wss://…/ws)
Twilio dials donor → WS: donor speech → GPT-4.1 (+ tools: book / SMS / callback / transfer / 911) → spoken reply
every turn persisted → console polls /api/calls/{id} for the live transcript + disposition
```

## Setup (≈5 min)

1. **Install deps**
   ```bash
   uv sync
   ```

2. **Create `.env`** from the template and fill it in:
   ```bash
   cp .env.example .env
   ```
   You need:
   - **Twilio**: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and a **voice + SMS** capable
     `TWILIO_FROM_NUMBER` (console.twilio.com).
   - **OpenAI**: `OPENAI_API_KEY` (platform.openai.com) — model defaults to `gpt-4.1`.
   - **`PUBLIC_URL`**: your ngrok host (set in step 4), e.g. `abcd-1234.ngrok-free.app`.
   - *(optional)* `COORDINATOR_NUMBER`: a second verified number for live transfers.
   - On a Twilio **trial**, verify the phone that will receive the demo call (Console → Verified Caller IDs).

3. **Seed the database** — the FIRST donor uses your verified demo phone:
   ```bash
   DEMO_PHONE="+1XXXXXXXXXX" uv run python seed.py
   ```

4. **Start ngrok** (public URL for ConversationRelay's WebSocket) and put the host in `.env`:
   ```bash
   ngrok http 8000          # copy the https host into PUBLIC_URL (no protocol)
   ```

5. **Run the server**
   ```bash
   uv run uvicorn main:app --port 8000
   ```

6. Open **http://localhost:8000**. Pick a donor on the left; on the **Arya** card choose:
   - **📞 Call** — dials the donor's number (from the record) via ConversationRelay. Your phone rings.
   - **🎙️ Talk on browser** — talk to Arya from the page mic (see browser-voice setup below).

   The live transcript, booking, and red/orange/yellow/green disposition appear on the Arya card.

## Two ways to talk to Arya
1. **🎙️ Talk on browser (no setup, works anywhere):** uses the browser's built-in **Web Speech API**
   (`SpeechRecognition` + `SpeechSynthesis`) for mic-in / voice-out, talking to Arya's GPT-4.1 brain over
   the `/ws/webspeech` WebSocket. **No Twilio account required.** Open the console in **Chrome**, click
   *Talk on browser*, allow the mic, and speak. (Chrome/Edge only — that's where the Web Speech API lives.)
2. **📞 Call (Twilio-native phone call):** places a real outbound call via Twilio **ConversationRelay**
   (Deepgram STT + ElevenLabs TTS, managed by Twilio) to the donor's number. Needs the Twilio account
   creds above + ngrok, and a paid/upgraded Twilio account for the full flow.

*(An optional Twilio Voice-SDK browser path also exists — `/voice/browser` + `mint_voice_token` — which
needs `TWILIO_API_KEY_SID/SECRET` and a `TWIML_APP_SID`; the Web Speech mode above is the zero-setup default.)*

## Demo script to try on the call
- *Happy path:* "Yes, this is Alex." → agree to donate → pick a slot → Arya books it + texts you → **green**.
- *Callback:* "Now's not a good time." → Arya schedules a callback → **yellow**.
- *Escalation:* ask a medical question Arya can't answer → live transfer to coordinator → **orange**.
- *Emergency:* "I'm having chest pain." → Arya tells you to call 911 and ends the call → **red**.

## Files
| File | Role |
|---|---|
| `main.py` | FastAPI app: console, REST API, ConversationRelay `/ws` loop |
| `agent.py` | `CallSession` — GPT-4.1 tool-calling loop + tool implementations |
| `prompts.py` | Recruitment task-list script → system prompt + welcome greeting |
| `knowledge.py` | Donation domain knowledge injected into the prompt |
| `repo.py` | Repository layer (the only SQL) — the swappable integration seam |
| `db.py` / `seed.py` | Schema + demo seed data |
| `twilio_client.py` | ConversationRelay TwiML, outbound call, SMS, live transfer |
| `static/index.html` | Two-panel operator console |
