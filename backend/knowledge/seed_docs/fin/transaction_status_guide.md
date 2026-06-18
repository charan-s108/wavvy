# Transaction Status Guide

## Pending and processing payments — in-flight transactions

A pending transaction means the payment has been submitted to the payment gateway and is waiting for confirmation. This is normal immediately after a transaction is initiated. Pending payments typically update within one to three business days. If a transaction has been in pending status since a previous business day, it may indicate a gateway delay and Fin escalates to the payments team. Fin tells the customer: "Your payment is being processed. It should update within one to three business days."

A processing transaction means the gateway has accepted the payment and funds are moving through the settlement system. This is further along than pending — the merchant will receive the funds once settlement completes. Processing typically resolves within one to two business days. Fin tells the customer: "Your payment is processing. Funds should settle within one to two business days."

## Completed, failed, cancelled, and expired transactions

A completed transaction means the payment settled successfully. Funds have been credited to the merchant and debited from the customer's account. Completed transactions are not eligible for a direct refund. If the customer has a grievance about a completed charge, they must file a dispute. Fin says: "This payment completed successfully. If you have an issue with this charge, I can raise a dispute for you."

A failed transaction means the payment was attempted and funds were debited from the customer's account, but the transaction did not credit to the merchant. Failed transactions are the most common scenario requiring a refund. Fin can initiate a refund directly. Fin says: "This transaction failed after the amount was deducted. I can initiate a refund for you."

A cancelled transaction means the transaction was cancelled before settlement was complete. The amount was either never fully debited, or an automatic reversal has been initiated. Cancelled transactions are generally not eligible for a refund because auto-reversal returns the funds within three to five business days. Fin says: "This transaction was cancelled. Any held amount will be reversed within three to five business days."

An expired transaction means the payment link or session timed out before the customer completed the payment. No charge was made on an expired transaction. Fin says: "The payment session expired. No amount was charged. You can retry the payment."

## Refund statuses — when a refund is already in progress

A refund initiated status means a refund has been submitted to the payment processor and is underway. Fin tells the customer: "A refund is already in progress. It typically takes three to five business days to appear in your account."

A refund processing status means the processor accepted the refund and funds are in transit back to the customer. Fin says: "Your refund is processing. Funds should appear within a few business days."

A refund completed status means the refund has been processed and funds have been credited back to the customer's original payment method. If the customer says they have not received the refund, Fin asks them to check with their bank and allows one additional business day. If the refund still has not appeared more than two business days past the expected date, Fin escalates with the transaction ID, refund initiation date, and refund case ID. Fin says: "Your refund has been processed. Please check your account or allow one additional business day for your bank to update."

## Flagged, KYC hold, and compliance hold — blocked transactions

A flagged transaction has been flagged by automated fraud detection and all activity on the transaction is blocked. Fin does not attempt to process a refund or dispute for a flagged transaction. Fin escalates to the fraud team immediately. Fin says: "This transaction is currently under fraud review. I need to connect you with our fraud team."

A KYC hold status means a KYC identity verification is required before the transaction can proceed or be refunded. The account's identity verification is incomplete or under review. Fin escalates to the KYC specialist team and guides the customer to re-upload documents if applicable. Fin says: "There is a KYC verification hold on this account. I will connect you with our KYC team."

A compliance hold status means a regulatory or Anti-Money Laundering review is in progress. This is a more serious hold triggered by risk or compliance analysis. Fin escalates to the compliance team and does not share the reason for the hold. Fin says: "There is a regulatory hold on this account. Our compliance team will need to review this."

## Disputed and chargeback statuses — what happens after filing a dispute

A disputed status means a formal dispute has been filed and the payment operations team is investigating. Fin gives a status update and does not re-file a duplicate dispute. Fin provides the existing dispute reference number if available.

A chargeback initiated status means the dispute has been escalated to the issuing bank or card network for a formal review. The timeline for bank resolution is five to fourteen business days. Fin informs the customer the dispute is now with the bank.

A chargeback won status means the chargeback was resolved in the customer's favour. A refund will be issued within five business days of the chargeback decision.

A chargeback lost status means the chargeback was denied and the original charge stands. Fin offers escalation to the senior disputes team if the customer wants to appeal. Fin says: "The chargeback review did not find in your favour. I can connect you with our senior disputes team if you would like to appeal."

## Fraud case statuses — fraud report and reversal lifecycle

A fraud reported status means a fraud case has been opened and the fraud team is conducting an initial review. Fin confirms the case is open, provides the case reference number in the format FRD followed by eight digits, and sets SLA expectations.

A fraud confirmed status means the fraud team has confirmed the transaction was fraudulent. Fin escalates to the fraud team immediately because they initiate the reversal process.

A fraud reversed status means the fraudulent charge has been reversed and funds are being returned. Fin says: "The fraudulent charge has been reversed. Funds will appear in your account per the standard refund timeline."

## Which statuses allow refunds and which require disputes

Failed transactions are eligible for a direct refund initiated by Fin. Completed transactions are not eligible for a refund but are eligible for a dispute. Cancelled and expired transactions are neither refund nor dispute eligible because no permanent debit occurred or auto-reversal is handling it. Pending and processing transactions are not yet eligible for either — the customer waits for final status. Flagged, KYC hold, and compliance hold transactions cannot be refunded or disputed until the hold is resolved. Refund initiated, refund processing, and refund completed mean a refund is already underway. Disputed and chargeback statuses mean a dispute is already in progress. Fraud reported, fraud confirmed, and fraud reversed are handled through the fraud case process, not through standard refunds or disputes.
