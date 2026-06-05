"""
One-time setup: registers a LiveKit SIP dispatch rule that routes inbound SIP/PSTN
calls to rooms with the prefix "sip-call-" and fires a webhook to our backend.

Run ONCE after claiming your free US phone number in the LiveKit Cloud dashboard:
  LiveKit Cloud → SIP → Inbound → "Get a phone number" (free, no credit card needed)

Usage:
  cd backend
  python scripts/setup_sip.py

Prerequisites:
  - LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in .env
  - PUBLIC_BACKEND_URL in .env (e.g. https://your-project.railway.app)
    For local dev: use ngrok → `ngrok http 8000` and set PUBLIC_BACKEND_URL=https://<id>.ngrok.io

What this creates:
  - SIP dispatch rule: all inbound calls → rooms prefixed "sip-call-<uuid>"
  - Webhook on room_started → POST {PUBLIC_BACKEND_URL}/api/livekit/sip-inbound
"""
import asyncio
import sys
import os

# Add parent directory so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import livekit.api as lk_api
from livekit.protocol import sip as lk_sip
from config import settings


async def main() -> None:
    if not settings.livekit_url or not settings.livekit_api_key:
        print("ERROR: LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set in .env")
        sys.exit(1)

    if not settings.public_backend_url or settings.public_backend_url == "http://localhost:8000":
        print(
            "WARNING: PUBLIC_BACKEND_URL is still localhost — LiveKit can't reach it.\n"
            "  For local dev, start ngrok:  ngrok http 8000\n"
            "  Then set PUBLIC_BACKEND_URL=https://<id>.ngrok.io in backend/.env\n"
            "  and re-run this script.\n"
        )

    webhook_url = f"{settings.public_backend_url}/api/livekit/sip-inbound"
    print(f"LiveKit URL     : {settings.livekit_url}")
    print(f"Webhook target  : {webhook_url}")

    lk = lk_api.LiveKitAPI(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )

    try:
        # List existing dispatch rules so we don't create duplicates
        existing = await lk.sip.list_sip_dispatch_rule(
            lk_sip.ListSIPDispatchRuleRequest()
        )
        for rule in existing.items:
            if hasattr(rule, "name") and rule.name == "wavvy-inbound":
                print(f"Dispatch rule 'wavvy-inbound' already exists (id={rule.sip_dispatch_rule_id}). Skipping creation.")
                return

        # Create dispatch rule: route all inbound SIP calls to unique rooms with prefix "sip-call-"
        # SIPDispatchRuleIndividual creates a new room per caller (each call gets its own room).
        resp = await lk.sip.create_sip_dispatch_rule(
            lk_sip.CreateSIPDispatchRuleRequest(
                name="wavvy-inbound",
                rule=lk_sip.SIPDispatchRule(
                    dispatch_rule_individual=lk_sip.SIPDispatchRuleIndividual(
                        room_prefix="sip-call-",
                    ),
                ),
                # trunk_ids: leave empty to apply to ALL inbound trunks on this project
                # Add your trunk ID here if you want to restrict to a specific number:
                # trunk_ids=["ST_xxxxxxxxxxxx"],
            )
        )
        print(f"Dispatch rule created: id={resp.sip_dispatch_rule_id} name={resp.name}")
        print()
        print("Next steps:")
        print(f"  1. Make sure your backend is reachable at: {webhook_url}")
        print("  2. In LiveKit Cloud dashboard → SIP → Webhooks, add the URL above")
        print("     and select the 'room_started' event.")
        print("  3. Call your free US number — the Wavvy agent should answer within 3s.")
    finally:
        await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
