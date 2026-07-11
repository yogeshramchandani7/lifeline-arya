"""Thin Twilio helpers: place the outbound ConversationRelay call, send SMS,
redirect (live-transfer) an in-progress call, and mint browser Voice SDK tokens."""
from xml.sax.saxutils import quoteattr

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

import config

_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def conversation_relay_twiml(donor_id: int, call_id: int, greeting: str) -> str:
    """Raw TwiML that connects the call to our ConversationRelay WebSocket.

    Kept minimal for reliability: `url` + `welcomeGreeting` only, so Twilio uses
    its managed defaults (Deepgram STT + ElevenLabs TTS). donor_id + call_id ride
    as query params on the wss URL. (To pin Deepgram Flux / a specific ElevenLabs
    voice, add ttsProvider / transcriptionProvider / speechModel attributes.)
    """
    url = f"{config.wss_url()}?donor_id={donor_id}&amp;call_id={call_id}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<ConversationRelay url="{url}" welcomeGreeting={quoteattr(greeting)} '
        'interruptible="true" />'
        "</Connect></Response>"
    )


def place_call(to_number: str, twiml: str) -> str:
    call = client().calls.create(to=to_number, from_=config.TWILIO_FROM_NUMBER, twiml=twiml)
    return call.sid


def send_sms(to_number: str, body: str) -> str:
    msg = client().messages.create(to=to_number, from_=config.TWILIO_FROM_NUMBER, body=body)
    return msg.sid


def transfer_call(call_sid: str, to_number: str) -> None:
    """Redirect the in-progress call to a human coordinator (ends ConversationRelay)."""
    vr = VoiceResponse()
    vr.say("Please hold while I connect you to a care coordinator.")
    vr.dial(to_number)
    client().calls(call_sid).update(twiml=str(vr))


def mint_voice_token(identity: str = "operator") -> str:
    """Access token for the browser Voice SDK ('Talk on browser')."""
    token = AccessToken(
        config.TWILIO_ACCOUNT_SID,
        config.TWILIO_API_KEY_SID,
        config.TWILIO_API_KEY_SECRET,
        identity=identity,
    )
    token.add_grant(VoiceGrant(outgoing_application_sid=config.TWIML_APP_SID, incoming_allow=False))
    return token.to_jwt()
