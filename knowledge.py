"""Domain knowledge injected into Arya's system prompt (grounding)."""

KNOWLEDGE_BASE = """\
BLOOD DONATION KNOWLEDGE (ground your answers in this; do not invent beyond it):

Eligibility:
- Whole blood can be donated once every 56 days (8 weeks).
- General requirements: at least 17 years old, at least 110 lbs, and feeling well on the day.
- If a donor mentions recent illness, a new medication, recent travel, or feeling unwell, they may need
  to wait — do not book; offer to have a coordinator follow up.

Why blood type matters:
- O-negative is the universal donor type: it can be given to anyone, so hospitals rely on it most for
  emergencies, trauma, and newborns. It is almost always in short supply.
- O-positive is the most common type and the most transfused overall.
- AB plasma is the universal plasma type.
- Shortages hit O-negative and O-positive hardest.

Pre-donation guidance (only standard, non-medical advice):
- Drink plenty of water and stay well hydrated.
- Eat a good meal beforehand, including iron-rich foods (red meat, beans, spinach).
- Bring a photo ID.
- Get a good night's sleep.

The donation itself is quick (about 8-10 minutes of actual donation) and is performed by trained staff.
"""
