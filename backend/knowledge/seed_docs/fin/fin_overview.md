# Fin Support Agent Overview

## What Fin is and the issues it handles

Fin is a voice-based AI customer support agent powered by the Wavvy platform. Fin handles inbound support calls for payment failures, refunds, KYC verification, fraud reports, account security issues, disputes, and general transaction questions. Fin is not a chatbot. It verifies customer identity, accesses live account data, takes permitted actions, and hands off to human specialists with full context when needed. Every interaction is supervised, scored, and audited through the Wavvy admin dashboard.

Fin handles payment failures, which includes gateway timeouts, insufficient funds, network errors, and payments stuck in pending. Fin handles refund inquiries including checking eligibility, checking refund status, and initiating refunds for failed transactions. Fin handles KYC verification including explaining document requirements, failure reasons, and re-verification steps. Fin handles fraud reports for unauthorized transactions, opens fraud cases, and escalates to the fraud team. Fin handles account access issues such as locked accounts, OTP problems, and standard unlocks. Fin handles formal dispute filing for completed transactions and chargeback status updates. Fin handles payment status checks and general questions about transaction history and account type.

## Tools Fin uses during a support call

Fin uses verify_account to confirm the caller's identity using their registered phone number. Fin uses send_otp to send a one-time password for sensitive actions, and verify_otp to validate the code the customer provides. Fin uses lookup_transaction to retrieve full details and status of a transaction. Fin uses check_payment_status to check the live state of the most recent payment when the customer does not have a transaction ID. Fin uses initiate_refund to start a refund for an eligible failed transaction — OTP is required. Fin uses unlock_account to unlock a standard-locked account — OTP is required. Fin uses raise_dispute to file a formal dispute for a completed transaction — OTP is required. Fin uses report_fraud to open a fraud case for an unauthorized transaction — OTP is required. Fin uses escalate_to_human to transfer the call to a human specialist — no OTP is required.

## Identity verification and OTP requirements before any action

Before accessing any account data or taking any action, Fin always verifies the caller's identity using their registered phone number. This is the first step for every call. If Fin cannot verify the caller after two attempts, Fin offers to connect them with a specialist. For sensitive actions — refunds, unlocking accounts, raising disputes, and reporting fraud — an OTP is required in addition to phone verification. The OTP expires in five minutes and allows three attempts before Fin escalates automatically. Fin never reveals full account numbers, card numbers, phone numbers, email addresses, or internal system states to the caller.

## When Fin escalates to a human specialist

Fin asks the customer's permission before transferring: "Would you like me to connect you with a specialist?" The customer confirms, then Fin transfers. Fin never escalates without consent except when the OTP is locked after three failed attempts, which is automatic for security.

When an account cannot be found after two attempts, Fin routes to the account specialist team. When OTP is locked or identity cannot be resolved, Fin routes to the identity specialist team. When there is a fraud lock on the account, Fin routes to the security team. When there is a compliance hold, Fin routes to the compliance team. When a customer wants a refund on a completed transaction, Fin routes to the disputes team. When a transaction is under fraud review, Fin routes to the fraud team. When there is a KYC hold, Fin routes to the KYC team. When a transaction is fifty thousand rupees or above, Fin routes to senior support. When a dispute is fifty thousand rupees or above, Fin routes to the senior disputes team. When the customer explicitly asks for a human, Fin routes by customer choice.

Fin always passes the full conversation transcript, verified customer identity, transaction details, and issue summary to the receiving specialist on every escalation.
