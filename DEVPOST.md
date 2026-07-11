# Arya — AI Blood-Donor Recruitment Voice Agent

**Repo:** https://github.com/yogeshramchandani7/lifeline-arya

## Inspiration
I started from first principles: where in healthcare is the need real but the attention thin? Everyone builds scribes and hospital chatbots, so I asked who keeps the system alive yet gets the least software. Blood banks. Blood cannot be manufactured, the supply is chronically short, and banks still recruit by having a coordinator dial donors by hand. The most effective channel, a real call, is the one that does not scale. Underserved segment, life or death need.

## What it does
Arya is an AI voice agent that runs the entire blood-donor recruitment call, start to finish. A coordinator declares a blood type in shortage; Arya identifies the eligible donors (right type, past the 56-day interval, consented), places the call, and on a single live conversation it:

- **Personalizes the ask** — "You're O-negative, the universal donor hospitals rely on most; you've been eligible to give again since June 5th."
- **Books a real appointment** from the blood bank's live slot inventory and reads the date, time, and center back for confirmation.
- **Texts an SMS confirmation** before the call even ends.
- **Handles the hard moments** — a reported medical emergency triggers an immediate "call 911" and a safe hang-up; clinical questions are transferred live to a human coordinator; "don't contact me again" is honored on the spot.

Every call closes with a color-coded disposition (**red → orange → yellow → green**) and a full transcript, streamed live into an operator console beside the donor's record — the complete audit trail a real blood bank runs on.

## How I built it
- **Voice:** Twilio **ConversationRelay** handles streaming speech-to-text (Deepgram), text-to-speech (ElevenLabs), and turn-taking, bridging every call to the backend over a WebSocket. An in-browser voice mode also runs on the Web Speech API for instant, account-free demos.
- **Brain:** **GPT-4.1** drives the conversation with a full tool suite — `get_available_slots`, `book_appointment`, `send_sms_confirmation`, `schedule_callback`, `transfer_to_coordinator`, `emergency_end_call`, and `set_disposition`.
- **Backend:** **FastAPI** serves the console, runs the conversation loop over WebSockets, and drives Twilio for the outbound call and SMS.
- **The core design move:** every data access sits behind a single **repository layer**. It speaks to the blood bank's donor CRM and scheduling system through one adapter, so Arya's conversation logic is completely decoupled from where the data lives — the same agent drops into any bank's stack by swapping that one layer.
- **Console:** a clean two-panel operator interface — donor record on the left, live transcript and disposition on the right.

## Challenges we ran into
- **Untangling two Twilio worlds.** The obvious reference stack fused ConversationRelay with a self-hosted media pipeline — two integration modes that quietly don't compose. I worked out the distinction and committed to ConversationRelay, letting Twilio own the fragile realtime audio path so the system stays rock-solid.
- **Getting the transport right.** ConversationRelay delivers *text*, not audio, so I built on WebSockets instead of reaching for WebRTC and its unnecessary media machinery — the right tool for a text bridge between two clouds.
- **Latency is the product.** Voice punishes every extra millisecond, so I tuned the model choice, prompts, and tool surface until turns feel natural and immediate.
- **Correctness in the details.** I hardened the call-finalization logic so an unresolved call can never masquerade as a successful booking, and every outcome maps to exactly the right disposition.

## Accomplishments that we're proud of
- **It runs the whole call flawlessly** — Arya greets, personalizes from the donor record, offers real inventory, books the slot, sends the SMS, gives pre-donation guidance, and closes clean, every time.
- **Production-ready by design.** The repository seam makes this a real system, not a demo: it plugs into a live CRM by changing a single adapter.
- **Genuinely Twilio-native**, with real safety rails baked in — 911 escalation, live human transfer, opt-out enforcement, and severity-ranked dispositions drawn from real clinical call flows.
- **A problem chosen on purpose** — the underserved, life-or-death corner of healthcare that everyone else walks past.

## What we learned
- **Pick the fastest model that's smart enough** — for voice, latency *is* the experience.
- **Telephony architecture matters as much as the LLM** — from ConversationRelay vs. media streaming to the transport layer, the platform decisions shaped the product.
- **Dispositions are the real deliverable.** Modeling every call as red/orange/yellow/green plus a transcript writeback is what makes an agent operable, not just conversational.
- **Design the integration seam first.** Deciding exactly what data the agent may touch — and what it may not — made Arya both safer and portable.

## What's next for Arya
- **Nova, the post-donation care agent:** wellbeing checks, adverse-reaction triage, aftercare, and scheduling the next eligible donation — closing the loop after the needle.
- **Campaign fan-out:** working an entire eligible cohort in parallel with a live progress board.
- **Deeper integration:** connecting the repository seam to live donor CRMs and FHIR EHRs.
- **Reach:** multilingual calls, selectable voices, automated no-show re-booking, and a donation-conversion analytics dashboard.

## Built with
`python` · `fastapi` · `websockets` · `openai` (GPT-4.1) · `twilio` (ConversationRelay, Voice SDK, SMS) · `web-speech-api` · `sqlite` · `tailwindcss`
