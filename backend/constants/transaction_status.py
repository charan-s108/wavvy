# Transaction status constants — single source of truth for all status strings.
# Used in wavvy_tools.py (status pre-checks), seed.py (test data), and
# workflow/definitions.py (routing keys).

# ── Terminal / final states ───────────────────────────────────────────────────
FAILED             = "failed"             # deducted but not credited — refund eligible
COMPLETED          = "completed"          # successfully settled — disputes-team path
CANCELLED          = "cancelled"          # cancelled before settlement — auto-reversal
EXPIRED            = "expired"            # payment link/session timed out

# ── In-flight states ──────────────────────────────────────────────────────────
PENDING            = "pending"            # submitted to gateway, awaiting confirmation
PROCESSING         = "processing"         # gateway accepted, settlement in progress

# ── Refund lifecycle ──────────────────────────────────────────────────────────
REFUND_INITIATED   = "refund_initiated"   # refund case opened
REFUND_PROCESSING  = "refund_processing"  # refund debit instruction sent to bank
REFUND_COMPLETED   = "refund_completed"   # funds credited back to customer

# ── Hold / review states ──────────────────────────────────────────────────────
FLAGGED            = "flagged"            # fraud-flagged — fraud-team path
KYC_HOLD           = "kyc_hold"           # KYC verification pending — kyc-team path
COMPLIANCE_HOLD    = "compliance_hold"    # regulatory / AML hold — compliance-team path

# ── Dispute / chargeback lifecycle ────────────────────────────────────────────
DISPUTED           = "disputed"           # customer filed a dispute
CHARGEBACK_INITIATED = "chargeback_initiated"  # chargeback raised with bank/card network
CHARGEBACK_WON     = "chargeback_won"     # chargeback resolved in customer's favour
CHARGEBACK_LOST    = "chargeback_lost"    # chargeback denied

# ── Fraud states ──────────────────────────────────────────────────────────────
FRAUD_REPORTED     = "fraud_reported"     # customer reported unauthorized transaction
FRAUD_CONFIRMED    = "fraud_confirmed"    # fraud team confirmed the fraud
FRAUD_REVERSED     = "fraud_reversed"     # fraudulent charge reversed
