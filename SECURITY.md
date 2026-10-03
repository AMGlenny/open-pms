# Security

Please report security problems privately, not in a public issue. Use GitHub's **Report a vulnerability** button on this repository (Security tab), and we'll reply within a week.

## What Open PMS does to protect your data

- **Passwords:** stored as salted hashes, never in plain text, and at least 12 characters.
- **Invite and reset links:** they work once, expire after 7 days, and only a hash of each is stored.
- **Lockout:** ten failed sign-ins lock an account for 15 minutes.
- **Single sign-on:** Google and Microsoft sign-in use the authorisation code flow with PKCE, a one-time state and a nonce. Open PMS checks the token's issuer, audience, expiry and nonce. It only accepts email addresses Google has verified, and only accounts from your own Microsoft directory. It never creates people: they must already be in Open PMS and active.
- **Forms and sessions:** every form is protected against cross-site request forgery. Session cookies are HttpOnly and SameSite, and Secure once you turn on HTTPS.
- **Browser protections:** a strict Content Security Policy, no framing, and no third-party scripts, fonts or trackers.
- **New installations:** they can only be claimed with the one-time setup code from the server log.
- **Separate organisations:** every row belongs to an organisation and every query is limited to one, so organisations can't see each other's data. Tests try to reach another organisation's records, exports and data links, and must be refused.
- **Exports:** wellbeing, review comments, the audit log and unapproved values are never exported. Spreadsheet formulas in text can't run when an export is opened. Data links are stored only as hashes, can be turned off, and making or turning them off is audited.
- **Backups:** `openpms backup` checks every backup it takes, and files are readable only by the account that runs Open PMS.
- **Wellbeing:** individual answers are only ever shown to the person's recorded line manager, and are never written to the audit log or exports.
- **History:** nothing is deleted, and every change records who, when, the old value and the new value.
