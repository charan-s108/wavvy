# Payment Failure — Standard Operating Procedure

## Checking payment status when a customer reports a problem

A payment failure occurs when a transaction is initiated but does not complete successfully. The customer's account may or may not have been debited depending on the failure type and stage of processing. When a customer reports a payment problem and does not have a transaction ID, Fin verifies the customer's identity and uses check_payment_status to see where the payment is.

If the result is payment processing, the gateway accepted the payment and settlement is in progress — Fin tells the customer the expected timeline. If the result is payment processing delayed, the payment has been in pending status since a previous business day indicating a gateway delay — Fin escalates to the payments team. If the result is payment settled, the payment completed successfully — Fin explains funds have reached the merchant. If the result is payment failed after debit, the amount was debited but not credited to the merchant — the transaction is eligible for a refund and Fin proceeds to initiate one. If the result is payment returned, the funds have been automatically returned to the source account — Fin tells the customer to check their account. If the result is gateway error, a gateway error prevented processing — Fin escalates to the payments team.

## Gateway timeout, insufficient funds, and network error failures

Gateway timeout failure occurs when the payment was initiated but the gateway did not receive confirmation within the allowed window, typically thirty seconds. The amount is often debited but not credited to the merchant. The transaction status will be failed. Fin initiates a refund. Debit card refunds take three to five business days. Wallet refunds are same business day.

Insufficient funds failure occurs when the transaction was declined because the account did not have enough balance. The transaction status will be failed or cancelled. No debit occurred. Fin advises the customer to ensure sufficient balance and retry the payment. No refund is needed.

Network or bank error failure occurs when the transaction failed due to a temporary network issue or error at the issuing bank. The transaction status will be failed. Fin advises the customer to retry. If the error has happened across multiple attempts or the amount was debited, Fin initiates a refund.

## Card blocked, account locked, or payment stuck in pending too long

Card or account blocked failure occurs when the transaction was declined due to a security hold, an expired card, or an account restriction. If the card is expired, Fin guides the customer to update their card details in the app. If the transaction status is flagged, Fin escalates to the fraud team immediately and does not investigate independently. If the account has a standard lock, Fin uses unlock_account to unlock it. If there is a fraud lock or compliance hold, Fin escalates to the respective team.

Payment stuck in pending too long occurs when the payment has been in pending status beyond the normal one to three business day window. Fin escalates to the payments team.

## Refund timelines, high-value escalation, and when to escalate immediately

Before initiating a refund or escalating, Fin collects the transaction ID, the transaction amount and date, the merchant name, whether the amount was actually debited, and whether the customer received any payment confirmation.

Wallet and app balance refunds are credited the same business day. Debit card refunds take three to five business days. Credit card refunds take five to seven business days. Bank account refunds via NEFT take three to seven business days. International card refunds take seven to ten business days.

Transactions at or above fifty thousand rupees require escalation to the senior support team regardless of the failure type. Fin does not initiate refunds for high-value transactions without senior approval.

Fin escalates to the fraud team immediately when the transaction status is flagged. Fin escalates to the respective team when the status is KYC hold or compliance hold. Fin escalates to senior support when the amount is fifty thousand rupees or above. Fin escalates when the customer reports the same issue a second time without resolution. Fin escalates when the customer expresses high frustration or explicitly asks to speak with a human agent.
