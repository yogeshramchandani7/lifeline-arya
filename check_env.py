"""Validate .env credentials without leaking secrets. Run: uv run python check_env.py"""
import config, repo, twilio_client


def mask(v, secret=True):
    if not v:
        return "❌ MISSING"
    if secret:
        return f"✅ set (len {len(v)})"
    return f"✅ {v}"


print("=" * 60)
print("CONFIG PRESENCE")
print("=" * 60)
print("OPENAI_API_KEY       ", mask(config.OPENAI_API_KEY))
print("OPENAI_MODEL         ", mask(config.OPENAI_MODEL, secret=False))
print("TWILIO_ACCOUNT_SID   ", mask(config.TWILIO_ACCOUNT_SID, secret=False))
print("TWILIO_AUTH_TOKEN    ", mask(config.TWILIO_AUTH_TOKEN))
print("TWILIO_FROM_NUMBER   ", mask(config.TWILIO_FROM_NUMBER, secret=False))
print("TWILIO_API_KEY_SID   ", mask(config.TWILIO_API_KEY_SID, secret=False))
print("TWILIO_API_KEY_SECRET", mask(config.TWILIO_API_KEY_SECRET))
print("TWIML_APP_SID        ", mask(config.TWIML_APP_SID, secret=False))
print("PUBLIC_URL           ", mask(config.PUBLIC_URL, secret=False))
print("phone_ready:", config.twilio_ready() and bool(config.PUBLIC_URL),
      "| browser_voice_ready:", config.browser_voice_ready() and bool(config.PUBLIC_URL))

print("\n" + "=" * 60)
print("TWILIO — validate account + number (read-only, no calls sent)")
print("=" * 60)
if config.twilio_ready():
    try:
        c = twilio_client.client()
        acct = c.api.v2010.accounts(config.TWILIO_ACCOUNT_SID).fetch()
        print(f"✅ account auth OK — '{acct.friendly_name}' status={acct.status} type={acct.type}")
        nums = c.incoming_phone_numbers.list(limit=20)
        print(f"   owned numbers: {len(nums)}")
        match = None
        for n in nums:
            cap = n.capabilities
            flag = "  <-- FROM_NUMBER" if n.phone_number == config.TWILIO_FROM_NUMBER else ""
            if n.phone_number == config.TWILIO_FROM_NUMBER:
                match = n
            print(f"   {n.phone_number} voice={cap.get('voice')} sms={cap.get('sms')}{flag}")
        if match is None:
            print(f"   ⚠️  TWILIO_FROM_NUMBER {config.TWILIO_FROM_NUMBER} is NOT among owned numbers!")
        elif not (match.capabilities.get('voice') and match.capabilities.get('sms')):
            print("   ⚠️  FROM number missing voice or SMS capability.")
        else:
            print("   ✅ FROM number has voice + SMS.")
        if acct.type == "Trial":
            verified = [v.phone_number for v in c.outgoing_caller_ids.list(limit=20)]
            import os
            demo = os.getenv("DEMO_PHONE", "").strip()
            print(f"   trial verified caller IDs: {verified}")
            if demo and demo not in verified:
                print(f"   ⚠️  DEMO_PHONE {demo} is NOT verified — trial calls to it will fail.")
    except Exception as e:
        print(f"❌ Twilio auth/API failed: {e}")
else:
    print("skipped — Twilio account creds incomplete")

print("\n" + "=" * 60)
print("TWILIO — browser voice token mint (local)")
print("=" * 60)
if config.browser_voice_ready():
    try:
        tok = twilio_client.mint_voice_token()
        print(f"✅ minted Voice access token (len {len(tok)})")
    except Exception as e:
        print(f"❌ token mint failed: {e}")
else:
    print("skipped — API key / TwiML App SID incomplete")
