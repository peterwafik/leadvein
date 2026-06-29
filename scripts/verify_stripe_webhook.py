"""Real-signature Stripe webhook verification against a RUNNING LeadVault server.

Unlike the unit tests (which monkeypatch construct_event), this signs a genuine
`checkout.session.completed` payload with HMAC-SHA256 exactly as Stripe does, so the
server's real `stripe.Webhook.construct_event` signature verification runs. Proves:
  1. a validly-signed event credits the buyer exactly once,
  2. a duplicate delivery (replay) does NOT double-credit,
  3. a bad signature is rejected with 400 (no credit).

Usage (server must be running with STRIPE_WEBHOOK_SECRET set, same value as $STRIPE_WEBHOOK_SECRET here):
  python scripts/verify_stripe_webhook.py <BASE_URL> <SQLITE_DB_PATH>
"""
import sys
import os
import time
import hmac
import hashlib
import json
import urllib.request
import urllib.error

from sqlmodel import Session, create_engine, select

from app.core.db import BuyerAccount, User

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8092"
DB = sys.argv[2]
SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

engine = create_engine(f"sqlite:///{DB}", connect_args={"check_same_thread": False})


def balance(baid):
    with Session(engine) as s:
        return s.get(BuyerAccount, baid).credits


with Session(engine) as s:
    u = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
    baid = u.buyer_account_id

start = balance(baid)


def sign(payload: bytes, ts: int) -> str:
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def post(payload: bytes, sig_header: str) -> int:
    req = urllib.request.Request(BASE + "/stripe/webhook", data=payload, method="POST",
                                 headers={"Stripe-Signature": sig_header,
                                          "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


event = {"id": "evt_verify", "type": "checkout.session.completed",
         "data": {"object": {"id": "cs_verify_real_1", "amount_total": 2900,
                             "currency": "gbp",
                             "metadata": {"buyer_account_id": str(baid),
                                          "pack_key": "pack_100", "credits": "100"}}}}
payload = json.dumps(event).encode()
ts = int(time.time())
good_hdr = sign(payload, ts)

c1 = post(payload, good_hdr)                          # validly-signed delivery
c2 = post(payload, good_hdr)                          # duplicate delivery (replay)
c_bad = post(payload, f"t={ts},v1=deadbeefbad")      # forged signature

end = balance(baid)

print(f"buyer_account_id={baid}  credits {start} -> {end}  (delta {end - start})")
print(f"validly-signed delivery : HTTP {c1}   (expect 200)")
print(f"duplicate replay        : HTTP {c2}   (expect 200, no extra credit)")
print(f"forged signature        : HTTP {c_bad}   (expect 400)")
ok = (c1 == 200 and c2 == 200 and c_bad == 400 and (end - start) == 100)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
