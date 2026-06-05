# Transaction Status Guide

## Overview

Every transaction in the system has a `status` field that describes exactly where the payment is in its lifecycle. This guide explains what each status means, what the customer can expect, and what Fin does in response.

There are 17 transaction statuses grouped into six categories.

---

## In-Flight Statuses

These transactions are still moving through the payment system. No action is needed yet.

### `pending`

The payment has been submitted to the payment gateway and is awaiting confirmation. This is normal immediately after a transaction is initiated.

**Expected duration:** 1–3 business days for most transactions.
**If stuck:** If the status is `pending` from a previous business day, this may indicate a gateway delay. Fin escalates to the payments team.
**Customer message:** "Your payment is being processed. It should update within 1–3 business days."

### `processing`

The gateway has accepted the payment and funds are moving through the settlement system. This is further along than `pending` — the merchant will receive the funds once settlement completes.

**Expected duration:** 1–2 business days.
**Customer message:** "Your payment is processing. Funds should settle within 1–2 business days."

---

## Terminal Statuses

These transactions have reached a final state and will not change unless an action is taken.

### `completed`

The payment has settled successfully. Funds have been credited to the merchant and debited from the customer's account.

**Refund eligible?** No — a completed transaction is not eligible for a direct refund. If the customer has a grievance, they must file a dispute via `raise_dispute`.
**Customer message:** "This payment completed successfully. If you have an issue with this charge, I can raise a dispute for you."

### `failed`

The payment was attempted and funds were debited from the customer's account, but the transaction did not credit to the merchant. This is the most common scenario requiring a refund.

**Refund eligible?** Yes — Fin initiates a refund directly via `initiate_refund`.
**Customer message:** "This transaction failed after the amount was deducted. I can initiate a refund for you."

### `cancelled`

The transaction was cancelled before settlement was complete. The amount was never fully debited, or an auto-reversal has been initiated.

**Refund eligible?** Typically no — auto-reversal returns funds within 3–5 business days.
**Customer message:** "This transaction was cancelled. Any held amount will be reversed within 3–5 business days."

### `expired`

The payment link or session timed out before the customer completed the payment. No charge was made.

**Refund eligible?** No — no debit occurred.
**Customer message:** "The payment session expired. No amount was charged. You can retry the payment."

---

## Refund Lifecycle Statuses

### `refund_initiated`

A refund has been submitted to the payment processor. The process is underway.

**Customer message:** "A refund is already in progress for this transaction. It typically takes 3–5 business days to appear in your account."

### `refund_processing`

The processor has accepted the refund request. Funds are in transit back to the customer's account.

**Customer message:** "Your refund is processing. Funds should appear within a few business days."

### `refund_completed`

The refund has been processed and funds have been credited back to the customer's original payment method.

**If customer hasn't received it:** Ask them to check with their bank. Allow 1 additional business day. If still not received after 2 business days past the expected date, escalate with the transaction ID and refund initiation date.
**Customer message:** "Your refund has been processed. Please check your account or allow one additional business day for your bank to update."

---

## Hold and Review Statuses

Transactions in these states cannot be processed further until the hold is resolved.

### `flagged`

The transaction has been flagged by automated fraud detection systems for review. All outbound activity on this transaction is blocked.

**Fin's action:** Escalate to the fraud team immediately. Do not attempt to process a refund or dispute for a flagged transaction.
**Customer message:** "This transaction is currently under fraud review. I need to connect you with our fraud team."

### `kyc_hold`

A KYC (Know Your Customer) verification is required before this transaction can proceed or be refunded. The account's KYC status is incomplete or under review.

**Fin's action:** Escalate to the KYC specialist team. Guide the customer to re-upload documents if applicable.
**Customer message:** "There is a KYC verification hold on this account. I'll connect you with our KYC team."

### `compliance_hold`

A regulatory or AML (Anti-Money Laundering) review is in progress. This is a more serious hold triggered by risk or compliance analysis.

**Fin's action:** Escalate to the compliance team. Do not share the reason for the hold.
**Customer message:** "There is a regulatory hold on this account. Our compliance team will need to review this."

---

## Dispute and Chargeback Lifecycle

### `disputed`

A formal dispute has been filed for this transaction. The payment operations team is investigating.

**Fin's action:** Give a status update, do not re-file. Provide the existing dispute reference if available.

### `chargeback_initiated`

The dispute has been escalated to the issuing bank or card network for a formal chargeback review.

**Fin's action:** Inform the customer the dispute is now with the bank. Timeline: 5–14 business days for bank resolution.

### `chargeback_won`

The chargeback was resolved in the customer's favour. A refund will be issued.

**Timeline:** Refund within 5 business days of the chargeback decision.

### `chargeback_lost`

The chargeback was denied. The original transaction charge stands.

**Fin's action:** Offer escalation to the senior disputes team if the customer wants to appeal. Fin does not re-file independently.
**Customer message:** "The chargeback review did not find in your favour. I can connect you with our senior disputes team if you'd like to appeal."

---

## Fraud Lifecycle Statuses

### `fraud_reported`

A fraud case has been opened for this transaction. The fraud team is conducting an initial review.

**Fin's action:** Confirm the case is open, give the case reference (FRD-XXXXXXXX), set SLA expectations.

### `fraud_confirmed`

The fraud team has confirmed that the transaction was fraudulent.

**Fin's action:** Escalate to the fraud team immediately — they will initiate the reversal process.

### `fraud_reversed`

The fraudulent charge has been reversed. Funds are being returned per the standard refund timeline.

**Customer message:** "The fraudulent charge has been reversed. Funds will appear in your account per the standard refund timeline."

---

## Quick Reference

| Status | Category | Refund Eligible | Dispute Eligible | Fin Action |
|---|---|---|---|---|
| `pending` | In-flight | No | No | Monitor, escalate if delayed |
| `processing` | In-flight | No | No | Inform, give timeline |
| `completed` | Terminal | No | Yes | Raise dispute |
| `failed` | Terminal | Yes | No | Initiate refund |
| `cancelled` | Terminal | No | No | Auto-reversal in 3–5 days |
| `expired` | Terminal | No | No | No charge, advise retry |
| `refund_initiated` | Refund | — | — | Already underway |
| `refund_processing` | Refund | — | — | In transit |
| `refund_completed` | Refund | — | — | Done — check bank |
| `flagged` | Hold | No | No | Escalate fraud team |
| `kyc_hold` | Hold | No | No | Escalate KYC team |
| `compliance_hold` | Hold | No | No | Escalate compliance team |
| `disputed` | Dispute | — | — | Status update only |
| `chargeback_initiated` | Dispute | — | — | With bank — give timeline |
| `chargeback_won` | Dispute | — | — | Refund in 5 days |
| `chargeback_lost` | Dispute | — | — | Offer senior appeal |
| `fraud_reported` | Fraud | — | — | Case open — give reference |
| `fraud_confirmed` | Fraud | — | — | Escalate fraud team |
| `fraud_reversed` | Fraud | — | — | Refund in progress |
