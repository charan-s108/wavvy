# Dispute Resolution

## What is a Dispute?

A dispute (also called a chargeback) is a formal request to reverse a completed transaction because:
- The customer did not receive the product or service
- They were charged the wrong amount
- The transaction was duplicated
- The transaction was unauthorized (but the transaction completed — not failed)

A dispute is different from a simple refund. Refunds apply to failed transactions. Disputes apply to completed transactions where the customer has a grievance about the charge.

## Dispute Eligibility

Fin can file a dispute directly using `raise_dispute`. A dispute can be raised when:

- Transaction status is `completed` — **not eligible for any other status**
- Transaction is within 90 days of the transaction date
- Transaction value is above ₹100 or $2 (minimum threshold)
- The transaction has not already been disputed (`disputed` status)

**Not eligible for dispute:**
- `failed` transactions — use `initiate_refund` instead
- `pending` or `processing` transactions — wait for final status
- `refund_initiated` or `refund_completed` — already in process
- `flagged` transactions — escalate to fraud team first
- Transactions older than 90 days — requires escalation to disputes team

## Filing a Dispute (Process)

1. Verify the customer's identity (`verify_account`)
2. Look up the transaction (`lookup_transaction`) — confirm status is `completed`
3. Confirm the dispute reason with the customer
4. Send OTP and verify (`send_otp` → `verify_otp`)
5. File the dispute (`raise_dispute`) — returns a dispute reference (DSP-XXXXXXXX)
6. Confirm the reference number and timeline to the customer

**High-value disputes (≥ ₹50,000):** Fin escalates to the senior-disputes team rather than filing directly. Manual review is required for these cases.

## Dispute Reasons

Common reasons a customer may dispute a completed transaction:

| Reason | Description |
|---|---|
| `item_not_received` | Merchant did not deliver the product or service |
| `wrong_amount` | Customer was charged more than the agreed amount |
| `duplicate_charge` | Same transaction charged twice (both completed) |
| `unauthorized` | Customer did not authorize the transaction (but it completed) |
| `quality_issue` | Product or service was defective (requires merchant communication first) |

## Chargeback Lifecycle

After a dispute is filed, the transaction status progresses through the chargeback lifecycle:

| Status | Meaning | Fin's response |
|---|---|---|
| `disputed` | Dispute filed, investigation in progress | Give reference, set timeline expectations |
| `chargeback_initiated` | Escalated to bank or card network | Confirm it is with the bank |
| `chargeback_won` | Resolved in customer's favour | Confirm refund timeline (5 business days) |
| `chargeback_lost` | Chargeback denied | Explain next steps — escalate to senior disputes team for appeal |

If a customer calls about a transaction already in `disputed` or `chargeback_initiated` status, Fin gives a status update and does not re-file. A duplicate dispute cannot be opened on the same transaction.

If the dispute window has expired (more than 90 days), Fin cannot file directly — Fin escalates to the disputes team who can evaluate an exception.

## Timeline

| Stage | Timeline |
|---|---|
| Dispute submission (via Fin) | Same day |
| Initial review by payment team | 1 business day |
| Merchant response window | 5–7 business days |
| Final resolution | 3–14 business days depending on complexity |
| Refund after chargeback_won | 5 business days |

## Manual Reconciliation for Gateway Failures

For gateway timeout failures (transaction status `failed`, reason `gateway_timeout`), Fin initiates a refund directly via `initiate_refund` — this is faster than the formal dispute process and does not require filing a chargeback.

Manual reconciliation via refund is only available when:
- Transaction status is `failed`
- Customer's account is in good standing (not flagged, kyc_hold, or compliance_hold)
- Transaction is not under any fraud review

## What Fin Can and Cannot Do

Fin can:
- Verify transaction eligibility for a dispute
- File a dispute directly via `raise_dispute` for eligible completed transactions
- Provide the dispute reference number (DSP-XXXXXXXX)
- Explain the dispute process and timeline
- Give status updates for existing disputes

Fin cannot:
- Promise a specific outcome on a dispute
- Access merchant transaction records or communications
- Approve or reject a dispute decision
- File a dispute for non-completed transactions
