# Security review

**Date:** 2026-10-21

**Scope:** Application code and project configuration in this repository. This is a static review; no code or configuration was changed as part of the review.

## Checklist

| Requirement | Result | Evidence |
|---|---|---|
| `GET /health` returns `{"status": "ok"}` | Implemented after the initial review | `/health` now returns the required JSON without authentication. |
| INFO/WARNING/ERROR logs to console and file | Implemented after the initial review | The `taskmaster` logger writes INFO and higher to a console handler and a rotating file handler. |
| Secrets stored outside source in `.env` | Implemented after the initial review | `.env` is ignored by Git; `.env.example` documents required configuration. The local signing secret is not committed. |

## Findings

### High — Authentication token was the username, and login returned a fixed placeholder

**Locations:** `main.py:74-77`, `main.py:120`

The initial implementation treated the bearer token as a username and returned the username as the login token. Usernames are not secrets, so anyone who knew a username could construct an accepted bearer value.

**Status:** The current implementation issues an HMAC-SHA256-signed token with an expiry, validates its signature and subject on protected routes, and requires `AUTH_TOKEN_SECRET` from the environment. Existing tokens from the former scheme are no longer accepted.

### Medium — Network deployment still needs TLS

**Locations:** `Dockerfile:17`, `README.md` Docker instructions

Uvicorn listens on all container interfaces. The documented Docker command now publishes only on host loopback, which is suitable for local development. If the container is exposed directly to a network, credentials and bearer tokens would be sent over plain HTTP.

**Recommendation:** Keep the documented loopback-only binding for local use. For a network-facing deployment, terminate TLS at a trusted reverse proxy and do not expose the plaintext application port publicly.

### Medium — SQLite database files are tracked by Git

**Locations:** repository root: `taskmaster.db`, `users.db` (were tracked at the time of the initial review)

Database files committed to a repository may expose personal data, task contents, or password hashes if those records are present. Removing a database from the latest commit does not remove it from Git history.

**Recommendation / status:** Both files are now excluded by `.gitignore` and untracked in the current changes. Their copies remain in earlier Git history; if they contain real data, treat it as disclosed, rotate affected credentials where relevant, and remove the data from repository history using the project's approved process.

### Low — No login throttling or password policy is visible

**Locations:** `main.py:89-118`

Registration accepts the supplied password without an explicit length policy, and the login route has no visible rate limiting. Repeated password guesses may be attempted against accounts.

**Recommendation:** Enforce an appropriate password length policy and add rate limiting/lockout protections at the application or trusted gateway layer. Avoid revealing whether a username exists in authentication error messages.

### Low — File logging requirements were unmet at initial review

**Locations:** `main.py` (application-wide)

The initial version had no application log calls or configured handlers. The current changes add console and rotating file handlers, INFO logs for successful actions, WARNING logs for rejected requests, and ERROR-level exception logging for unhandled errors.

**Remaining recommendation:** The application logger uses a rotating file handler and logs messages without passwords or bearer tokens. For production, also ensure log files have restricted permissions and the configured retention policy meets operational requirements.

## Additional notes

- SQL statements found in the inspected routes use SQLite parameter placeholders for user-supplied values; no SQL injection issue was identified in those statements.
- Passwords are stored using `bcrypt.hashpw` and checked using `bcrypt.checkpw` (`main.py:94`, `main.py:117`), which is preferable to storing plaintext passwords.
- `taskmaster.db` is the configured runtime database (`main.py:13`); ensure production database paths and backups are protected and are not served as static files.
