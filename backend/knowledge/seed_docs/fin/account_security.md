# Account Security

## Account Lock Policy

An account is automatically locked when:
- 3 or more consecutive failed login attempts are detected
- A suspicious login from an unrecognized device or location is flagged
- The fraud team places a security hold
- The customer manually requests a lock

When locked, all transactions and logins are blocked until the account is unlocked through a verified channel.

## Types of Account Locks

Not all account locks are the same. Fin handles each type differently:

### Standard Lock (Failed Logins)

Triggered by 3 or more consecutive failed login attempts. This is the most common case.

**Fin can unlock this directly** using `unlock_account` after verifying identity (OTP required).

Process:
1. Verify customer identity (`verify_account`)
2. Send OTP (`send_otp`) and verify it (`verify_otp`)
3. Unlock the account (`unlock_account`)
4. Confirm the account is active and advise the customer to reset their password via the app

### Fraud Lock

Triggered when the fraud team places a security hold due to suspected fraud or confirmed fraudulent activity.

**Fin cannot unlock this.** Fin escalates immediately to the security-team.

Fin tells the customer: "Your account has a security hold placed by our fraud team. I need to connect you with a specialist." The security team handles identity re-verification through alternate channels.

### Compliance Hold

Triggered by a regulatory or AML review.

**Fin cannot unlock this.** Fin escalates to the compliance-team.

Fin tells the customer: "There is a regulatory hold on your account. Our compliance team will need to review this with you." Details about the trigger are not shared.

## Identifying the Lock Type

When `unlock_account` is called, the system determines the lock type automatically:
- Standard lock → unlock proceeds
- Fraud lock → returns `fraud_lock` key → Fin escalates to security-team (terminal)
- Compliance hold → returns `compliance_hold` key → Fin escalates to compliance-team (terminal)

If Fin cannot determine the lock type from the account record, Fin escalates by default.

## OTP Policy

OTP is used to authorize sensitive account actions (unlock, refund, dispute, fraud report).

| Rule | Value |
|---|---|
| OTP validity | 5 minutes from send |
| Cooldown between resends | 10 seconds |
| Maximum resends per session | 5 |
| Maximum wrong attempts | 3 |
| After 3 wrong attempts | Account locked from further OTP attempts; Fin escalates |

If OTP has expired: Fin offers to resend immediately.
If OTP resend limit is reached (5 resends): Fin escalates to identity-specialist.
If 3 wrong codes entered: Fin escalates to identity-specialist automatically — this cannot be overridden.

## Password Reset

1. Customer clicks "Forgot Password" on the login screen
2. A password reset link is sent to the registered email address
3. Link expires after 30 minutes
4. New password must be at least 8 characters with one number and one special character

If the registered email is inaccessible: escalate to the security team for alternate identity verification.

## Two-Factor Authentication (2FA)

2FA is enabled by default for all accounts. Supported methods:
- SMS OTP to registered phone number
- Email OTP to registered email address
- Authenticator app (Google Authenticator, Authy)

If a customer is not receiving their OTP:
1. Ask them to check spam/junk folder (email OTP)
2. Confirm the registered phone number
3. Suggest waiting 10 seconds and requesting a new OTP (cooldown enforcement)
4. If the issue persists after 3 attempts, escalate to the security team

2FA cannot be disabled without identity verification. Any request to disable 2FA must go through the security team.

## Session Management

Active sessions can be viewed and terminated from Settings → Security → Active Sessions.

Session expiry:
- 30 minutes of inactivity (mobile app)
- 60 minutes of inactivity (web app)
- 7 days absolute expiry regardless of activity

If a customer reports an unknown active session: this is a security incident. Escalate immediately to the security-team with reason `fraud_suspected`.

## What Fin Can and Cannot Do

Fin can:
- Unlock a standard-locked account directly via `unlock_account` (OTP required)
- Guide the customer through the self-service password reset process
- Explain 2FA setup and troubleshooting steps
- Confirm whether an account is locked and the type of lock

Fin cannot:
- Unlock accounts with fraud locks or compliance holds
- Reset passwords
- Disable 2FA
- Access session logs, device information, or IP addresses
- Verify alternate identity documents

All of the above require escalation to the security team or compliance team.

## Escalation Triggers

Escalate immediately when:
- Account has a fraud lock or compliance hold
- Customer cannot access their registered email AND phone
- Customer reports a session they did not start
- Customer believes their account has been compromised
- OTP fails 3 consecutive times
- Customer requests manual identity review
