# Payment Failure — Standard Operating Procedure

## Overview

A payment failure occurs when a transaction is initiated but does not complete successfully. The funds may or may not have been debited from the customer's account depending on the failure type and stage of processing.

## Step 1 — Check Payment Status

When a customer reports a payment issue, the first step is to verify the account and look up the transaction status. Fin uses `check_payment_status` when the customer does not have a transaction ID and just wants to know "where is my payment?"

`check_payment_status` checks the live state of the most recent payment and returns one of the following outcomes:

| Result | What it means | Fin's response |
|---|---|---|
| `payment_processing` | Gateway accepted, settlement in progress | Normal — tell customer expected timeline |
| `payment_processing_delayed` | Status has been `pending` since a previous day | Escalate to payments team |
| `payment_settled` | Payment completed successfully | No issue — explain the funds reached merchant |
| `payment_failed_post_debit` | Deducted but not credited | Eligible for refund — proceed to initiate_refund |
| `payment_returned` | Funds returned to source account automatically | Tell customer to check their account |
| `gateway_error` | Gateway error prevented processing | Escalate to payments team |

## Step 2 — Identify Failure Type

### Gateway Timeout

The payment was initiated but the gateway did not receive a confirmation within the allowed window (typically 30 seconds). The amount is often debited but not credited to the merchant.

**Transaction status:** `failed`
**Resolution:** Initiate refund via `initiate_refund`. Refund credited within 3–5 business days (debit card) or same day (wallet).

### Insufficient Funds (NSF)

The transaction was declined because the account did not have sufficient balance.

**Transaction status:** `failed` or `cancelled`
**Resolution:** No debit occurred — advise the customer to ensure sufficient balance and retry. No refund needed.

### Network or Bank Error

The transaction failed due to a transient network issue or error at the issuing bank.

**Transaction status:** `failed`
**Resolution:** Advise the customer to retry. If the error has persisted across multiple attempts or the amount was debited, initiate a refund.

### Card or Account Blocked

The transaction was declined due to a security hold, expired card, or account restriction.

**Transaction status:** `failed` or `flagged`
**Resolution:**
- Expired card: guide customer to update card details in the app
- `flagged` status: escalate to fraud team immediately — Fin does not investigate flagged transactions
- Account lock: use `unlock_account` if it is a standard lock; escalate if fraud lock or compliance hold

### Pending Too Long

The payment is stuck in `pending` status beyond the normal 1–3 business day window.

**Transaction status:** `pending` from a previous day
**Resolution:** Escalate to payments team (`payment_processing_delayed` outcome).

## Transaction Status Reference

| Status | Meaning | Action |
|---|---|---|
| `pending` | Submitted, awaiting gateway confirmation | Check if same-day — if previous day, escalate |
| `processing` | Gateway accepted, settlement in progress | Normal — give timeline |
| `failed` | Deducted but not credited | Eligible for refund |
| `cancelled` | Cancelled before settlement | Auto-reversal within 3–5 business days |
| `expired` | Payment link or session timed out | No charge — advise customer to retry |

## Key Information to Collect

Before initiating a refund or escalating:
1. Transaction ID (format: TXN-XXXX)
2. Transaction amount and date
3. Merchant name
4. Whether the amount was debited from the account
5. If the customer has received any confirmation messages

## Refund Timelines for Payment Failures

| Payment Method | Timeline After Initiation |
|---|---|
| Wallet / app balance | Same business day |
| Debit card | 3–5 business days |
| Credit card | 5–7 business days |
| Bank account (NEFT) | 3–7 business days |
| International card | 7–10 business days |

## High-Value Threshold

Transactions at or above ₹50,000 require escalation to the senior-support team regardless of failure type. Fin does not initiate refunds for high-value transactions without senior approval.

## Escalation Triggers

Escalate to the appropriate team immediately when:
- Transaction status is `flagged` (fraud team)
- Transaction status shows `kyc_hold` or `compliance_hold` (respective teams)
- Amount is ₹50,000 or above (senior-support)
- Customer reports the same issue a second time without resolution
- Customer expresses high frustration or explicitly requests a human agent
