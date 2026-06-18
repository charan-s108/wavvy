# Account Security

## When an account gets locked and the three types of account locks

An account is automatically locked when three or more consecutive failed login attempts are detected, when a suspicious login from an unrecognized device or location is flagged, when the fraud team places a security hold, or when the customer manually requests a lock. When locked, all transactions and logins are blocked until the account is unlocked through a verified channel. There are three types of locks and Fin handles each differently.

A standard lock from failed logins is triggered by three or more consecutive failed login attempts and is the most common case. Fin can unlock this directly using unlock_account after verifying identity with OTP. The process is: verify identity, send and verify OTP, unlock the account, then advise the customer to reset their password through the app.

A fraud lock is triggered when the fraud team places a security hold due to suspected or confirmed fraudulent activity. Fin cannot unlock a fraud-locked account. Fin escalates immediately to the security team and tells the customer: "Your account has a security hold placed by our fraud team. I need to connect you with a specialist."

A compliance hold is triggered by a regulatory or Anti-Money Laundering review. Fin cannot unlock a compliance-held account. Fin escalates to the compliance team and tells the customer: "There is a regulatory hold on your account. Our compliance team will need to review this with you." Fin does not share details about what triggered the compliance hold.

When Fin calls unlock_account, the system automatically identifies the lock type. A standard lock allows the unlock to proceed. A fraud lock result causes Fin to escalate to the security team — this is a terminal action. A compliance hold result causes Fin to escalate to the compliance team — also terminal. If Fin cannot determine the lock type, Fin escalates by default.

## OTP not arriving — what to do when OTP is not coming to phone or email

OTP is required to authorize sensitive account actions: unlocking an account, initiating a refund, raising a dispute, and reporting fraud. If a customer is not receiving their OTP, Fin first asks them to check their spam or junk folder for email OTPs. Fin then confirms the registered phone number is correct. Fin suggests waiting ten seconds and requesting a new OTP to account for the cooldown between resends. If the issue persists after three attempts, Fin escalates to the security team.

OTP codes are valid for five minutes from the time they are sent. There is a ten-second cooldown between resend requests. A customer can request a maximum of five OTP resends per session. A maximum of three wrong OTP attempts are allowed before escalation is triggered. If the OTP has expired, Fin offers to resend immediately. If the resend limit of five has been reached, Fin escalates to the identity specialist team. If the customer enters three incorrect OTP codes, Fin escalates to the identity specialist team automatically — this cannot be overridden.

## Password reset and two-factor authentication setup

If the customer forgot their password, a password reset link is sent to the registered email address by clicking Forgot Password on the login screen. The link expires after thirty minutes. The new password must be at least eight characters with at least one number and one special character. If the customer cannot access their registered email, Fin escalates to the security team for alternate identity verification.

Two-factor authentication is enabled by default for all accounts. Supported methods are SMS OTP to the registered phone number, email OTP to the registered email address, and authenticator apps such as Google Authenticator or Authy. Two-factor authentication cannot be disabled without identity verification — any request to disable it must go through the security team.

Active sessions can be viewed and ended from Settings, then Security, then Active Sessions. Mobile app sessions expire after thirty minutes of inactivity. Web app sessions expire after sixty minutes of inactivity. All sessions expire absolutely after seven days. If a customer reports an unknown active session, Fin treats this as a security incident and escalates immediately to the security team with the reason fraud suspected.

## What Fin can and cannot do and when to escalate for security issues

Fin can unlock a standard-locked account directly using unlock_account after OTP verification. Fin can guide the customer through the self-service password reset process. Fin can explain two-factor authentication setup and troubleshooting. Fin can confirm whether an account is locked and what type of lock it is.

Fin cannot unlock accounts with fraud locks or compliance holds. Fin cannot reset passwords directly. Fin cannot disable two-factor authentication. Fin cannot access session logs, device information, or IP addresses. Fin cannot verify alternate identity documents.

Fin escalates immediately when the account has a fraud lock or compliance hold, when the customer cannot access both their registered email and registered phone, when the customer reports a session they did not start, when the customer believes their account has been compromised, when the customer enters three incorrect OTP codes, and when the customer requests a manual identity review.
