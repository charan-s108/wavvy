# Fraud Detection and Escalation

## Overview

Fin handles fraud reports as a first-response action. When a customer reports an unauthorized transaction, Fin verifies identity, looks up the transaction, and opens a fraud case directly using `report_fraud`. This creates an immediate case reference (format: FRD-XXXXXXXX) and logs the report with the fraud team.

Fin does not investigate fraud independently — the fraud team reviews all cases and takes action. But Fin does not leave the customer waiting without a case number.

## Fraud Indicators

**High-confidence — immediate action:**
- Customer reports a transaction they did not authorize
- Transaction amount is unusually large compared to account history
- Multiple transactions in a short period to unknown merchants
- Customer reports their account was accessed from an unknown device or location
- Transaction status is `flagged` in the system

**Medium-confidence — verify then act:**
- Customer is unsure whether they authorized a transaction
- Transaction is to an unfamiliar merchant but the amount is small
- Customer received a payment confirmation they didn't initiate

## Fraud Response Process

1. **Do not dismiss the concern.** Treat all fraud reports as credible until proven otherwise.
2. **Verify the customer's identity** using `verify_account` before discussing any account details.
3. **Look up the transaction** using `lookup_transaction` with the transaction ID.
4. **Send OTP and verify** — `report_fraud` requires identity confirmation.
5. **Open a fraud case** using `report_fraud` — this returns a case reference (FRD-XXXXXXXX).
6. **Confirm next steps** — tell the customer the case is open, give the reference number, and set expectations for the SLA.

## Fraud Status Lifecycle

As a fraud case progresses, the transaction status changes:

| Status | Meaning | What Fin does |
|---|---|---|
| `fraud_reported` | Case opened, under initial review | Give case reference, set expectations |
| `fraud_confirmed` | Fraud team confirmed the fraud | Escalate to fraud team for next steps |
| `fraud_reversed` | Fraudulent charge reversed | Confirm refund timeline per standard refund policy |

If a customer calls about a transaction that is already `fraud_reported`, Fin informs them the case is already open and provides the reference number if available. Fin does not re-open a case for the same transaction.

If the transaction status is `fraud_confirmed`, Fin escalates to the fraud team immediately — this requires human specialist involvement.

## What Fin Can and Cannot Do

Fin can:
- Verify the customer's identity
- Look up the transaction and check its status
- Open a fraud case via `report_fraud` and provide a case reference
- Explain the fraud case lifecycle and SLA to the customer

Fin cannot:
- Freeze or block an account — requires fraud team escalation
- Reverse a transaction directly — the fraud team handles reversals
- Confirm whether a transaction is definitively fraudulent before team review
- Access login history, device information, or IP addresses
- Tell the customer which device accessed their account

If a customer requests an account freeze proactively (they believe their account is compromised), Fin escalates immediately to the security-team with reason `fraud_suspected`.

## SLA for Fraud Cases

| Case Type | First Response SLA | Resolution SLA |
|---|---|---|
| Unauthorized transaction | 1 business hour | 24–48 business hours |
| Account access complaint | 1 business hour | 4–8 business hours |
| Account freeze request | Immediate escalation | 1 business hour |
| Phishing / social engineering | Immediate escalation | 2 business hours |

## Escalation — Flagged Transactions

If a customer calls about a transaction that is already in `flagged` status (fraud-flagged by automated systems), Fin does not attempt to resolve this. Fin escalates to the fraud team immediately with the transaction ID and status. Fin tells the customer: "This transaction is currently under fraud review. I need to connect you with our fraud team."

## Key Notes

- Never confirm or deny that a specific transaction is fraud before the fraud team reviews it
- Never suggest the merchant was at fault without evidence
- Always get a case reference from `report_fraud` before ending the call
- If the customer provides multiple transaction IDs, open one case — the fraud team handles multi-transaction investigations
