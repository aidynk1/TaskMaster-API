# Security review

**Date:** 2026-10-21

**Scope:** Application code and project configuration in this repository. This is a static review; no code or configuration was changed as part of the review.

## Checklist

| Requirement | Result | Evidence |
|---|---|---|
| `GET /health` returns `{"status": "ok"}` | Not implemented | `main.py` defines no `/health` route. Add a small unauthenticated health route returning the required JSON. |
| INFO/WARNING/ERROR logs to console and file | Not configured | The application does not configure Python logging, add `StreamHandler`/`FileHandler`, or emit application logs. Uvicorn's default logging is not a substitute for the requested application logging configuration. |
| Secrets stored outside source in `.env` | No `.env` found | There is no `.env` or `.env.example` in the project. `python-dotenv` is present in `requirements.txt`, but the application does not load it. No hardcoded API keys or real credentials were found in the inspected source. |

## Findings

### High — Authentication token is the username, and login returns a fixed placeholder

**Locations:** `main.py:74-77`, `main.py:120`

The authentication dependency treats the bearer token as a username and looks up that username directly. Usernames are not secrets, so anyone who knows a username can construct an accepted bearer value. In addition, login returns the same literal `"******"` for every successful login; that value is not a per-user credential and does not establish a secure authenticated session.

**Recommendation:** Replace this scheme with a cryptographically random, expiring token or a properly signed token with validated claims. Return it only after successful login; verify its signature, expiry, and subject on protected routes. Revoke/rotate credentials as appropriate.

### Medium — Plain HTTP is documented and the container listens on all interfaces

**Locations:** `Dockerfile:17`, `README.md:25,28`

Uvicorn binds to `0.0.0.0`, and the documented Docker command publishes the service on the host without binding it specifically to loopback. The documented URL uses HTTP. If reachable by other machines, credentials and bearer tokens can be observed in transit.

**Recommendation:** For local-only development, publish with `127.0.0.1:8000:8000`. For a network-facing deployment, terminate TLS at a trusted reverse proxy and do not expose the plaintext application port publicly.

### Medium — SQLite database files are tracked by Git

**Locations:** repository root: `taskmaster.db`, `users.db` (both tracked)

Database files committed to a repository may expose personal data, task contents, or password hashes if those records are present. Removing a database from the latest commit does not remove it from Git history.

**Recommendation:** Do not commit runtime databases. Add both filenames to `.gitignore`; if either contains real data, treat it as disclosed, rotate affected credentials where relevant, and remove the data from repository history using the project's approved process.

### Low — No login throttling or password policy is visible

**Locations:** `main.py:89-118`

Registration accepts the supplied password without an explicit length policy, and the login route has no visible rate limiting. Repeated password guesses may be attempted against accounts.

**Recommendation:** Enforce an appropriate password length policy and add rate limiting/lockout protections at the application or trusted gateway layer. Avoid revealing whether a username exists in authentication error messages.

### Low — File logging requirements are unmet

**Locations:** `main.py` (application-wide)

There are no application log calls or configured handlers, so operational failures and security-relevant events are not captured in the requested console and file destinations.

**Recommendation:** Configure a single logger with `StreamHandler` and `FileHandler`, set the intended levels/format, and log relevant events without passwords, bearer tokens, or other secrets. Ensure log files have restricted permissions and a rotation/retention policy.

## Additional notes

- SQL statements found in the inspected routes use SQLite parameter placeholders for user-supplied values; no SQL injection issue was identified in those statements.
- Passwords are stored using `bcrypt.hashpw` and checked using `bcrypt.checkpw` (`main.py:94`, `main.py:117`), which is preferable to storing plaintext passwords.
- `taskmaster.db` is the configured runtime database (`main.py:13`); ensure production database paths and backups are protected and are not served as static files.
