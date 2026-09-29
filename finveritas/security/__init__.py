"""Security controls for FinVeritas.

- config      — fail-closed secret loading and security constants
- passwords   — server-side password policy
- ratelimit   — brute-force / credential-stuffing throttling (MongoDB-backed)
- audit       — append-only security event log
- sessions    — server-side JWT session registry (revocation on logout / reset)
- mfa         — TOTP two-factor authentication with encrypted secrets
- uploads     — file upload validation (size, magic bytes, page limits)
- llm_guard   — prompt-injection screening and LLM output grounding checks
"""
