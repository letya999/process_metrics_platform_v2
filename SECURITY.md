# Security Policy

## Supported Versions

Only the latest release of the Process Metrics Platform is currently supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.0   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take the security of this project seriously. If you find a security vulnerability, please do NOT open a public issue.

Instead, please report it privately:
1. Open a **GitHub Security Advisory** through the repository.
2. Provide a clear description of the vulnerability, reproduction steps, and potential impact.

### Response Timeline

- **Acknowledgement**: We will acknowledge your report within 48 hours.
- **Triage**: We will investigate and confirm the vulnerability within 7 days.
- **Remediation**: We aim to release a fix within 30 days of confirmation.
- **Public Disclosure**: A public advisory will be published only after a fix is released.

## What NOT to do

- **No Public Disclosure**: Do not disclose vulnerabilities publicly (e.g., via GitHub issues, social media, or blogs) before we have had a chance to fix them.
- **Responsible Testing**: Only perform security testing on instances you own and control. Do not test against any production systems or cloud services.

## Operational Security Baseline

For internal/closed-network deployments, we recommend at minimum:

- Set `ADMIN_AUTH_SECRET` (or `SECRET_KEY`) explicitly; do not rely on defaults.
- Keep `ADMIN_AUTH_TTL_MINUTES` reasonably short (default `120`).
- Use `ADMIN_TOKENS_INVALID_BEFORE` to revoke all existing admin tokens after incidents.
- Keep `INTEGRATION_ALLOWED_URL_SCHEMES=https`.
- Configure `INTEGRATION_ALLOWED_HOST_PATTERNS` when you know allowed providers/domains.
- Keep `INTEGRATION_ALLOW_LOCALHOST=false` unless a localhost integration is explicitly required.
