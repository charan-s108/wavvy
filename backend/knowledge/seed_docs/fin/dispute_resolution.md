# Dispute Resolution

## What is a dispute and when to file one instead of a refund

A dispute, also called a chargeback, is a formal request to reverse a completed transaction. A customer disputes a transaction when they did not receive the product or service, when they were charged the wrong amount, when the same transaction was charged twice and both completed, or when a transaction was unauthorized but it completed rather than being declined or failing. A dispute is different from a refund. Refunds apply to failed transactions where the customer was debited but the merchant was not credited. Disputes apply to completed transactions where the charge went through but the customer has a legitimate grievance about the charge.

Fin can file a dispute directly using raise_dispute when the transaction status is completed. The transaction must be within ninety days of the original transaction date. The transaction value must be above one hundred rupees or two US dollars. The transaction must not already be in disputed status. Fin cannot file a dispute for a failed transaction — use the refund process instead. Fin cannot file a dispute for pending or processing transactions. Fin cannot file a dispute when a refund is already in progress. Fin cannot file a dispute for flagged transactions — the fraud team reviews first. Transactions older than ninety days cannot be disputed directly — Fin escalates to the disputes team for a possible exception.

## How to file a dispute for a completed transaction step by step

Fin follows a specific process for every dispute. First, Fin verifies the customer's identity. Second, Fin looks up the transaction and confirms the status is completed. Third, Fin confirms the dispute reason with the customer. Fourth, Fin sends an OTP and verifies the code. Fifth, Fin files the dispute using raise_dispute, which returns a dispute reference number in the format DSP followed by eight digits. Sixth, Fin confirms the reference number and timeline to the customer.

Common dispute reasons are: item not received meaning the merchant did not deliver the product or service; wrong amount meaning the customer was charged more than the agreed price; duplicate charge meaning the same transaction was charged twice and both completed; unauthorized transaction meaning the customer did not authorize it but it completed; quality issue meaning the product or service was defective, where merchant communication should happen before filing a formal dispute.

For high-value disputes of fifty thousand rupees or above, Fin escalates to the senior disputes team rather than filing directly. Manual review is required for high-value cases.

## Chargeback lifecycle — what happens after a dispute is filed

After a dispute is filed, the transaction status progresses through the chargeback lifecycle. When the status is disputed, a dispute has been filed and the payment operations team is investigating. Fin gives the customer the dispute reference and sets timeline expectations — initial review takes one business day, and final resolution takes three to fourteen business days depending on complexity.

When the status is chargeback initiated, the dispute has been escalated to the bank or card network for a formal review. Fin confirms with the customer that the dispute is now with the bank and the timeline is five to fourteen business days for bank resolution.

When the status is chargeback won, the chargeback was resolved in the customer's favour. A refund will be issued within five business days of the chargeback decision.

When the status is chargeback lost, the chargeback was denied and the original transaction charge stands. Fin offers escalation to the senior disputes team if the customer wants to appeal. Fin does not re-file independently. Fin tells the customer: "The chargeback review did not find in your favour. I can connect you with our senior disputes team if you would like to appeal."

If a customer calls about a transaction already in disputed or chargeback initiated status, Fin gives a status update and does not re-file. A duplicate dispute cannot be opened on the same transaction. If the dispute window has expired at more than ninety days, Fin cannot file directly — Fin escalates to the disputes team who can evaluate an exception.

## Dispute timelines and what Fin can and cannot do

Dispute submission through Fin is processed the same day. Initial review by the payment team takes one business day. The merchant response window is five to seven business days. Final resolution takes three to fourteen business days. A refund after chargeback won takes five business days.

For gateway timeout failures where the transaction status is failed and the reason is gateway timeout, Fin initiates a refund directly — this is faster than the formal dispute process and does not require filing a chargeback.

Fin can check whether a transaction is eligible for a dispute, file a dispute for eligible completed transactions, provide the dispute reference number, explain the dispute process and timeline, and give status updates for existing disputes. Fin cannot promise a specific outcome on a dispute, access merchant records or communications, approve or reject a dispute decision, or file a dispute for non-completed transactions.
