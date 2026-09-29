# FinVeritas — Threat Model (STRIDE)

## System overview

```
                 ┌─────────────────────────── Trust boundary: server ───────────────────────────┐
 Analyst ──HTTPS/WS──▶ Streamlit app (app.py)                                                    │
 (browser)        │      ├─ auth/        login · MFA · reset · sessions ──────▶ MongoDB Atlas     │
                  │      ├─ ingestion/   PDF / CSV / ticker parsing              users, sessions, │
 Borrower docs ───┼──▶   │               (untrusted content enters here)          rate_limits,     │
 (PDF/CSV)        │      ├─ analysis/    deterministic metrics · LangGraph        password_resets, │
                  │      │               agents                                   audit_log,       │
                  │      └─ security/    guards used by all of the above          file_history     │
                  └──────────────┬──────────────────────┬────────────────────────────────────────┘
                                 ▼                      ▼
                     LLM API (Gemini/OpenAI-compat)   Market data APIs (yfinance, FMP, Alpha Vantage)
                     — third party, sees prompts      — third party, receives ticker symbols
                                 ▲
                     SMTP (Gmail) — delivers reset codes
```

### Assets
| Asset | Why it matters |
|---|---|
| User accounts and sessions | Access to borrower financials and credit memos |
| Borrower financial data and file history | Confidential commercial information |
| Integrity of grades, DSCR and narrative | Lending decisions are made on them |
| Secrets: `JWT_SECRET`, `MONGO_URI`, `LLM_API_KEY`, SMTP password | Compromise of any one leads to full compromise or third-party abuse |
| Audit log | Detection and forensics |

### Actors
- **External attacker**: no account; targets login, reset and registration.
- **Malicious borrower**: supplies documents an analyst uploads. Controls file content, company names and commentary.
- **Malicious or compromised analyst**: authenticated; may try other users' data or admin functions.
- **Network attacker**: on-path between the server and SMTP or APIs.

### Trust boundaries
1. Browser ↔ Streamlit server (all widget input is untrusted)
2. Uploaded file content ↔ parsers (untrusted bytes)
3. App ↔ LLM (prompts carry untrusted text; responses are untrusted output)
4. App ↔ MongoDB / SMTP / market-data APIs

## STRIDE analysis

| # | Category | Threat | Mitigation | Status |
|---|---|---|---|---|
| S1 | Spoofing | Password guessing / credential stuffing | Per-account lockout (5 per 15 min), bcrypt cost 12, password policy, optional TOTP MFA | ✅ |
| S2 | Spoofing | Forged JWT (default secret, `alg=none`, alg confusion) | Fail-closed secret ≥ 32 chars, algorithm pinned to HS256, required claims, server-side session check | ✅ |
| S3 | Spoofing | Reset-code brute force / prediction | CSPRNG, hashed at rest, 5 attempts, single use, 5-min TTL, send throttling | ✅ |
| S4 | Spoofing | Session theft via leaked URL | Token never placed in URL; `?token=` ignored | ✅ |
| S5 | Spoofing | MFA code replay | Last-used time-step stored; conditional update blocks races | ✅ |
| T1 | Tampering | Prompt injection alters the credit narrative | Deterministic numbers, screening, isolation, output grounding check | ⚠️ Mitigated |
| T2 | Tampering | HTML injection in rendered pages (phishing overlay) | `html.escape` on all dynamic values in `unsafe_allow_html` sinks; Streamlit sanitiser blocks scripts | ✅ |
| T3 | Tampering | Parameter injection into third-party API URLs | Ticker allow-list (user and LLM supplied) | ✅ |
| T4 | Tampering | NoSQL operator injection | Query values are always `str` from widgets; no JSON-parsed filters | ✅ (verified) |
| R1 | Repudiation | User denies an action; no record of attacks | Append-only `audit_log` with event, outcome, email, user id, IP, timestamp | ✅ |
| I1 | Info disclosure | Account enumeration | Generic errors, timing equalisation, async email send | ✅ (registration: residual) |
| I2 | Info disclosure | Stack traces / DB errors shown to users | Reference-ID errors, `showErrorDetails = none` | ✅ |
| I3 | Info disclosure | Reset codes intercepted in transit | Full TLS verification on STARTTLS | ✅ |
| I4 | Info disclosure | DB leak exposes secrets | bcrypt password hashes, HMAC'd OTPs, Fernet-encrypted TOTP secrets | ✅ |
| I5 | Info disclosure | Cross-user data access (IDOR) | History queries scoped to the verified token's `user_id` | ✅ (verified) |
| I6 | Info disclosure | LLM exfiltrates data via rendered links/images | Links, images and HTML stripped from output; output escaped | ✅ |
| I7 | Info disclosure | Borrower data sent to a third-party LLM | Only computed facts and short excerpts sent; provider choice is configurable (local LLM supported) | ⚠️ Accepted |
| D1 | Denial of service | Oversized / zip-bomb / many-page uploads | Size, page, row and decompression limits; magic-byte checks | ✅ |
| D2 | Denial of service | Reset-email flooding a victim | 3 sends per email per 15 min | ✅ |
| D3 | Denial of service | Lockout abused to block a legitimate user | Lockout is time-boxed (15 min); dashboard surfaces targeted accounts | ⚠️ Accepted |
| E1 | Elevation | Analyst reaches admin dashboard | Role re-checked in the page itself and read from DB each time; no UI to change roles | ✅ |
| E2 | Elevation | Hijacked session disables MFA | Disabling MFA requires a current TOTP code | ✅ |

## Residual risks and future work

| Risk | Why accepted / next step |
|---|---|
| Registration reveals whether an email exists | Requires email-verified sign-up (send a link, respond identically). Planned. |
| Refresh logs the user out | Secure persistent sessions need an `HttpOnly; Secure; SameSite=Strict` cookie from a reverse proxy (nginx/Caddy) in front of Streamlit. |
| Lockout is per account, not per IP | Add IP-based throttling at the reverse proxy / WAF layer. |
| Pattern-based injection detection misses encoded or non-English payloads | Add an LLM-based classifier or a guard model; keep deterministic numbers as the backstop. |
| No MFA recovery codes | Add one-time recovery codes (hashed) at enrolment. |
| `unsafe_allow_html` is used in ~85 places | Replace ad-hoc f-string HTML with a small escaping template helper; add a lint rule. |
| TLS termination and security headers (CSP, HSTS) | Provided by the deployment's reverse proxy; not configurable in Streamlit itself. |
