# Refund Policy

## Eligibility

Fin can initiate refunds directly using the `initiate_refund` tool. A refund may be initiated when:

1. A payment was debited but the transaction did not complete — **status must be `failed`**
2. A duplicate charge resulted in one `failed` transaction alongside a `completed` one
3. An unauthorized charge was made and the transaction status is `failed`

Refunds are **not initiated by Fin** for:
- Transactions with status `completed` — these require a formal dispute via `raise_dispute`
- Transactions with status `refund_initiated` or `refund_processing` — already in progress
- Transactions with status `refund_completed` — already processed
- Transactions with status `flagged` — fraud review required first
- Transactions with status `kyc_hold` — KYC must be resolved first
- Transactions older than 90 days — requires manager approval

## Status-Based Response Rules

Before initiating a refund, Fin checks the transaction status and responds accordingly:

| Transaction Status | Fin's Action |
|---|---|
| `failed` | Initiate refund (eligible) |
| `refund_initiated` | Refund already underway — give 3–5 business day timeline |
| `refund_processing` | Refund in transit — give timeline, no re-initiation |
| `refund_completed` | Refund processed — ask customer to check their account or bank |
| `completed` | Not eligible for refund — offer to raise a dispute instead |
| `flagged` | Fraud review required — escalate to fraud team immediately |
| `kyc_hold` | Account KYC hold — escalate to KYC team |
| `compliance_hold` | Regulatory hold — escalate to compliance team |

## Session Idempotency

Fin will not initiate the same refund twice in one call. If a refund has already been opened in the current session, Fin confirms the case ID and timeline without re-initiating.

## High-Value Transactions

Transactions at or above ₹50,000 are not refunded directly by Fin. Fin escalates these to the senior-support team regardless of eligibility.

## Refund Timelines

Processing times begin from the day the refund is initiated, not the day the customer reports the issue.

| Refund Method | Processing Time |
|---|---|
| Wallet / app balance | Same business day |
| Debit card | 3–5 business days |
| Credit card | 5–7 business days |
| Bank account (NEFT) | 3–7 business days |
| International card | 7–10 business days |

## Initiating a Refund (Process)

1. Verify the customer's identity (`verify_account`)
2. Look up the transaction (`lookup_transaction`)
3. Confirm the transaction status is `failed`
4. Send OTP and verify (`send_otp` → `verify_otp`)
5. Initiate the refund (`initiate_refund`)
6. Confirm the refund case ID and expected timeline to the customer

Fin provides a refund case reference on successful initiation. The customer should retain this for follow-up.

## Refund Dispute — Refund Not Received

If a customer says their refund has not arrived after the stated timeline:

1. Check the transaction status — confirm it shows `refund_completed`
2. Confirm the refund destination matches the customer's registered payment method
3. If `refund_completed` but not received: ask the customer to allow 1 additional business day and contact their bank — processing delays are on the bank side, not Fin's
4. If more than 2 business days past the expected date and still not received: escalate with the transaction ID, refund initiation date, and refund case ID

## Key Notes

- Never promise same-day refunds unless the payment method is a wallet/app balance and it has been explicitly confirmed
- Always confirm the customer's registered payment method before stating the refund timeline
- If the transaction status shows `failed` but the customer says no amount was deducted, explain that no debit occurred and no refund is needed — this is a declined transaction, not a failed debit
