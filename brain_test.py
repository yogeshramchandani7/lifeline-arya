"""Drive a scripted recruitment conversation through Arya's brain (real GPT-4.1).
Also checks Voice-resource access. Run: uv run python brain_test.py"""
import config, repo
from twilio.rest import Client
from agent import CallSession

print("=== Twilio Voice resource access ===")
try:
    c = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    calls = c.calls.list(limit=1)
    print(f"✅ calls.list OK ({len(calls)} items) — Voice resource reachable")
except Exception as e:
    print(f"❌ calls.list FAIL -> {e}")

print("\n=== Arya brain test (live GPT-4.1) ===")
# fresh call row on donor 1
call_id = repo.create_call(donor_id=1)
s = CallSession(call_id=call_id, donor_id=1, call_sid="CAbraintest")
print("Arya (greeting):", s.messages[1]["content"])

donor_turns = [
    "Yes, this is Alex speaking.",
    "Sure, I have a couple of minutes.",
    "Yes, I'd be happy to come donate this week.",
    "The first available time works great for me.",
    "No, that's all. Thank you!",
]
for turn in donor_turns:
    print(f"\nDonor: {turn}")
    reply = s.handle_user(turn)
    print(f"Arya:  {reply}")
    if s.ended:
        print("[call ended by agent]")
        break

s.finalize()
final = repo.get_call(call_id)
print("\n=== RESULT ===")
print("outcome:    ", final["outcome"])
print("disposition:", final["disposition"])
print("flags:      ", final["flags"])
print("transcript turns:", len(final["transcript"]))
