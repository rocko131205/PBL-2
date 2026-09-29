# Security

FinVeritas handles confidential borrower financials, so security is treated as a feature:
threat-modelled, tested, and checked in CI.

- **Assessment and fixes:** [docs/security/PENTEST_REPORT.md](docs/security/PENTEST_REPORT.md) (13 findings, CVSS-scored, all remediated)
- **Threat model:** [docs/security/THREAT_MODEL.md](docs/security/THREAT_MODEL.md) (STRIDE, trust boundaries, residual risks)

## Controls at a glance

| Area | Control |
|---|---|
| Passwords | bcrypt (cost 12), server-side policy, common-password block |
| Login | Generic errors, timing equalisation, 5-attempt lockout per 15 min |
| MFA | TOTP (Google/Microsoft Authenticator, Authy), encrypted at rest, replay-protected |
| Sessions | Server-side registry, revocable JWTs (`jti`), 8 h lifetime, 15 min idle timeout, never in URLs |
| Password reset | CSPRNG 6-digit code, HMAC-hashed, 5 attempts, single use, 5 min TTL, send throttling, revokes all sessions |
| Secrets | Fail-closed: the app won't start with a missing or default `JWT_SECRET` |
| Uploads | Size, magic-byte, page, row and zip-bomb limits |
| Output encoding | All dynamic values escaped before HTML rendering |
| LLM | Prompt-injection screening, untrusted-data isolation, output sanitising, numeric grounding check |
| Monitoring | Audit log of all security events; admin Security Dashboard |
| Access control | `analyst` / `admin` roles; roles changed only via `scripts/make_admin.py` |
| Supply chain | `pip-audit` and `gitleaks` in CI, weekly scheduled scan |

## Running the security checks

```sh
pip install -r requirements-dev.txt
pytest tests/security -q                 # 113 security regression tests
bandit -r finveritas app.py scripts -ll -ii
pip-audit -r requirements.txt
python scripts/llm_redteam.py            # live prompt-injection run (needs LLM configured)
```

## Operations

- Generate secrets with `python -c "import secrets; print(secrets.token_hex(32))"`.
- Promote an admin: `python scripts/make_admin.py you@example.com`.
- Deploy behind a reverse proxy that terminates TLS and sets HSTS / CSP headers.
- Rotate `MONGO_URI` credentials, `LLM_API_KEY` and `SMTP_PASS` if they are ever exposed (chat, logs, screenshots, commits).

## Reporting a vulnerability

Please email the maintainer privately rather than opening a public issue. Include steps to reproduce,
and allow reasonable time for a fix before disclosure.
