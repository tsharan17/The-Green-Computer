# Privacy Policy

**Draft, awaiting professional legal review.** This policy describes what The Green Computer stores
and sends as it is built and hosted today.

## 1. Who is responsible

The Green Computer is operated by **T Sharan**, who decides how your data is used. Contact:
{{contact}}.

## 2. What we store

| Data | Why | Where |
|---|---|---|
| Email address, optional display name | Your account and sign-in | Database |
| Password | Sign-in. Stored only as a salted scrypt hash, never in plain text | Database |
| Sessions | Keep you signed in. The cookie holds a random token; only its SHA-256 hash is stored, with the browser's user agent and IP address | Database |
| Optional two-step sign-in secret and recovery codes | Two-step sign-in. The secret is encrypted; recovery codes are stored as hashes | Database |
| Projects, requirements, analyses, plans, measurements and exports | The features you use | Database and file storage |
| Uploaded files (models, datasheets, logs) | Validation and analysis | File storage, inside your workspace |
| Terms acceptance (document, version, time, account id) | A record of what you agreed to | Database |
| Audit log (security-relevant actions, with IP address) and usage counts | Security, abuse prevention and your usage page | Database |

We do not sell your data, show advertising, or use your content to train models.

## 3. Who processes it for us

| Provider | What it does for us | What it receives |
|---|---|---|
| Render | Runs the application | Everything the application handles while serving your requests |
| Neon | Hosts the database, including your uploaded files and exports | The database contents listed above |
| Brevo | Sends confirmation and password-reset email from {{contact}} | Your email address and the message |
| Sentry (only if turned on) | Reports server errors | Error type, route and request id; no request bodies, passwords or tokens |

These providers may process data outside your country. Uploaded documents are treated as data:
instructions written inside a file are never followed, and no AI service is sent your content.

## 4. Cookies and browser storage

One cookie keeps you signed in; it is necessary for the service and is not used for tracking. The
browser also remembers your chosen workspace and display mode locally. There are no analytics or
advertising cookies.

## 5. How long data is kept

Your data is kept until you delete it or your workspace's retention rules remove it. An email address invited to a team workspace is kept until the invitation is answered or cancelled, or the workspace is deleted, and is sent one invitation email. The database
provider's restore history and encrypted backups may keep deleted data for up to 14 days. Security logs are kept while your account
exists.

## 6. Your rights

- **Access and export:** each project has exports with a hashed manifest, and a workspace export.
- **Correct:** edit your name and projects at any time.
- **Delete:** Account → Delete account removes workspaces you own alone, with all their projects and
  files; in shared workspaces your name is removed from records.
- **Ask us:** for anything else, including a copy of your data or an objection, write to
  {{contact}}. Depending on where you live you may also complain to a data-protection authority.

## 7. Security

Passwords are hashed, sessions are HTTP-only cookies with CSRF protection, sign-in and password
reset are rate limited, two-step sign-in is available, connections use TLS, and every project, file
and export is checked against your workspace on the server. No system is perfectly secure.

## 8. Changes

When this policy changes materially, its version changes and you are asked to accept it at your
next sign-in.
