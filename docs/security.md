# Security model

What protects users and their data, how it is tested, and what is still open. Report a problem
privately to the maintainers rather than in a public issue.

## Accounts and sessions

- Passwords: scrypt (Python standard library, N=2^14, r=8, p=1, 16-byte salt), at least 10
  characters, a short block-list of common passwords, re-hashed on sign-in when parameters change.
- Sessions and API tokens: 256-bit random tokens; only their SHA-256 is stored. Browser sessions use
  an HttpOnly, SameSite=Lax cookie (Secure in production or over HTTPS). Sessions expire
  (`GC_SESSION_DAYS`); each can be revoked; a password change or reset signs out other sessions.
- Password reset: single-use, one-hour token, stored hashed. The response is identical whether or not
  the address has an account. The reset link appears in the response only outside production and
  only when no mail server is configured (development convenience); otherwise it is emailed.
- Sign-in errors do not reveal whether an account exists; failed sign-ins are audited and rate
  limited per address and per email. Sign-up reveals that an email is taken (a deliberate usability
  trade-off; set `GC_ALLOW_SIGNUP=0` to close sign-up).
- Account deletion requires the password and a typed confirmation; it deletes every workspace the
  user owns alone, with all rows and stored files, and anonymises the user in shared workspaces.

## Cross-site protections

- State-changing requests authenticated by cookie must carry `X-GC-CSRF: 1` (browsers cannot add
  custom headers cross-site without a CORS pre-flight, which the API never grants); sign-in and
  sign-up need it too (login CSRF). Requests whose `Origin` is neither the server nor an allowed
  origin are refused.
- Headers: Content-Security-Policy (`default-src 'self'`, no inline scripts, `object-src 'none'`),
  X-Frame-Options DENY, nosniff, no referrer. Fonts are bundled; the UI loads nothing from third
  parties. User text in reports is HTML-escaped; downloads are served as attachments with sanitised
  file names.

## Tenant isolation

- Every owned row carries `workspace_id`; repository and service functions take the caller's
  workspace and filter by it; objects in another workspace answer 404 so their existence is not
  revealed. Membership is checked for the `X-GC-Workspace` header on every request. Roles: owner,
  editor, viewer (read-only).
- Shared library data (built-in devices, models, committed measurements) has no owner and is
  read-only. Measurements, calibrations, custom devices and uploaded models are private.
- Uploaded files live in a per-workspace folder of the blob store, so deleting a tenant cannot touch
  another's files.

## Untrusted input

- Uploads have size limits (100 MB models, 20 MB other files); pickle/torch archives are refused;
  ONNX is parsed as protobuf without executing anything; YAML uses `safe_load`; PDFs are read as
  text; ELF is read from its section table only.
- Running a model happens only in a separate worker process with a wall-clock limit, one run per
  workspace at a time; ONNX Runtime loads no custom-operator libraries. Arguments are passed without
  a shell.
- The optional AI assistant can only call engine tools; it cannot change hard requirements, and a
  guardrail rejects any number not present in a tool result.

## Audit and usage

Uploads (accepted or refused), analyses, versions, plans, exports, measurement imports, runs,
member changes and account events are recorded with the acting user and address. Usage events
meter analyses, exports, execution seconds and storage.

## Tests that guard this

- `tests/api/test_security.py`: every API operation (from the OpenAPI schema) returns 401 without a
  session except an explicit public list; every state-changing operation returns 403 without the
  CSRF header; cookie flags and headers; escaping and safe file names.
- `tests/api/test_auth_tenancy.py`: cross-tenant access to every owned endpoint returns 404; roles;
  reset and session revocation; deletion removes rows and files.
- `frontend/e2e`: a second account cannot open the first account's project in the browser.

## Known limits

- Rate limits are in memory (one process). Run one worker, or move limits to a shared store before
  scaling out.
- No email verification and no multi-factor authentication yet.
- No malware scanning of uploaded files (they are never executed except ONNX models in the worker).
- The datasheet reader and OCR operate on untrusted PDFs in-process (pypdf); keep the upload limit.
