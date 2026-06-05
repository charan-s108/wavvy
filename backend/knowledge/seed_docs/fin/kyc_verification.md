# KYC Verification — Customer Guidance

## What is KYC?

KYC (Know Your Customer) is a mandatory identity verification process required by financial regulators. All accounts must complete KYC to unlock full transaction limits and services. Without completed KYC, accounts operate in a restricted state with lower transaction limits.

## KYC Levels

| Level | Status | Transaction Limit | Features Available |
|---|---|---|---|
| KYC Pending | Not submitted | ₹10,000 / $200 per month | Basic wallet only |
| KYC Submitted | Under review | Same as pending | Basic wallet only |
| KYC Verified | Fully verified | Full limits | All features |
| KYC Failed | Verification failed | Restricted | Re-verify or escalate |
| KYC Hold | Manual review pending | Restricted | Escalation required |

## Required Documents

**Identity Proof (one required):**
- Aadhaar Card (India)
- PAN Card (India)
- Passport
- Driver's License
- National ID Card

**Address Proof (one required, if different from identity proof):**
- Utility bill (last 3 months)
- Bank statement (last 3 months)
- Aadhaar Card (if current address matches)

**For premium accounts or high-limit transactions:**
- Recent bank statement (last 6 months)
- Employment letter or income proof

## Common KYC Failure Reasons

1. **Document mismatch** — Name on the document does not match the account registration name
2. **Expired document** — ID document has passed its validity date
3. **Poor image quality** — Photo is blurry, cropped, or has glare; all four corners must be visible
4. **Incomplete document** — Not all pages uploaded (passports require both pages)
5. **Address mismatch** — Address on proof does not match the registered address
6. **Duplicate KYC** — Another account already uses the same document

## Re-Verification Process

If a customer's KYC has failed:

1. Inform the customer of the specific failure reason (if available in their account record)
2. Guide them to re-upload documents via the app (Settings → KYC → Re-verify)
3. Re-verification review takes 24–48 business hours
4. If re-verification fails a second time, Fin escalates to the KYC specialist team

## KYC Hold vs. Compliance Hold

These two statuses are different and require different escalation paths:

**KYC Hold (`kyc_hold`)**
KYC documents are under manual review. The account is temporarily restricted pending document verification. Fin escalates to the **KYC specialist team**.
- Typical SLA: 24–48 business hours for review
- Customer can accelerate by re-uploading clearer documents via the app

**Compliance Hold (`compliance_hold`)**
A regulatory or AML (Anti-Money Laundering) review is in progress. This is a more serious hold triggered by transaction pattern analysis or regulatory flags. Fin escalates to the **compliance team**.
- Cannot be resolved by the customer through self-service
- Compliance team reviews all available account data
- Customer should be told: "There is a regulatory hold on your account. Our compliance team will review and contact you directly."
- Do not share details about what triggered the compliance hold
- Typical SLA: 2–5 business days for initial response

## What Fin Can and Cannot Do

Fin can:
- Explain KYC requirements and document types
- Confirm the customer's current KYC status from their account record
- Guide the customer through the app re-verification steps
- Explain what a specific failure reason means in plain language

Fin cannot:
- Approve or override KYC verification
- Access the document images submitted
- Confirm the outcome of a pending review
- Waive KYC requirements
- Resolve a compliance hold (this always requires the compliance team)

## Escalation for KYC Issues

Always escalate to the kyc-team when:
- Customer's status is `kyc_hold` and they need urgent transaction access
- Customer has re-submitted documents twice without approval
- Customer believes the failure reason is incorrect
- Customer's business account requires enhanced due diligence (EDD)

Always escalate to the compliance-team when:
- Transaction status shows `compliance_hold`
- Customer has received a compliance notification and wants to understand it
- A transaction was blocked due to regulatory concerns
