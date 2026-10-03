"""Sign in with Google or Microsoft (OpenID Connect).

Turned on by setting environment variables (see docs/install.md):
  Google:    OPENPMS_GOOGLE_CLIENT_ID, OPENPMS_GOOGLE_CLIENT_SECRET,
             optionally OPENPMS_GOOGLE_DOMAIN (only accept that Workspace domain)
  Microsoft: OPENPMS_MICROSOFT_CLIENT_ID, OPENPMS_MICROSOFT_CLIENT_SECRET,
             OPENPMS_MICROSOFT_TENANT_ID (your directory's tenant ID; required)

Single sign-on only signs in people who are already in Open PMS and active:
their verified email must match a person's email. It never creates people.

The flow is the authorisation code flow with PKCE, a random state and a
nonce. The ID token comes straight from the provider's token endpoint over
HTTPS, so (as the OpenID Connect spec allows) its issuer is trusted from the
TLS connection; its audience, issuer, expiry, nonce and tenant are checked.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

from flask import Blueprint, abort, current_app, flash, g, redirect, request, session, url_for

from . import auth, db

bp = Blueprint("sso", __name__, url_prefix="/login/sso")

CLOCK_SKEW = 120  # seconds


def _env(name):
    return (os.environ.get(name) or "").strip()


def providers():
    """Configured providers: {name: settings}."""
    out = {}
    if _env("OPENPMS_GOOGLE_CLIENT_ID") and _env("OPENPMS_GOOGLE_CLIENT_SECRET"):
        out["google"] = dict(
            label="Google", client_id=_env("OPENPMS_GOOGLE_CLIENT_ID"),
            client_secret=_env("OPENPMS_GOOGLE_CLIENT_SECRET"),
            authorize="https://accounts.google.com/o/oauth2/v2/auth",
            token="https://oauth2.googleapis.com/token",
            issuers=("https://accounts.google.com", "accounts.google.com"),
            domain=_env("OPENPMS_GOOGLE_DOMAIN").lower())
    tenant = _env("OPENPMS_MICROSOFT_TENANT_ID")
    if _env("OPENPMS_MICROSOFT_CLIENT_ID") and _env("OPENPMS_MICROSOFT_CLIENT_SECRET") and tenant:
        if tenant.lower() in ("common", "organizations", "consumers"):
            raise RuntimeError("OPENPMS_MICROSOFT_TENANT_ID must be your directory's tenant ID, not "
                               f"'{tenant}', so only accounts from your organisation can sign in.")
        base = f"https://login.microsoftonline.com/{tenant}"
        out["microsoft"] = dict(
            label="Microsoft", client_id=_env("OPENPMS_MICROSOFT_CLIENT_ID"),
            client_secret=_env("OPENPMS_MICROSOFT_CLIENT_SECRET"),
            authorize=f"{base}/oauth2/v2.0/authorize", token=f"{base}/oauth2/v2.0/token",
            issuers=(f"{base}/v2.0",), tenant=tenant)
    return out


def enabled():
    """[(name, label)] for the sign-in page."""
    return [(name, p["label"]) for name, p in providers().items()]


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(id_token):
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None


def _post_form(url, fields):
    """POST a form to the provider's token endpoint and return the JSON."""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https URLs above)
        return json.loads(resp.read())


@bp.route("/<name>", methods=["POST"])
def start(name):
    p = providers().get(name)
    if p is None:
        abort(404)
    verifier = secrets.token_urlsafe(48)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session["sso"] = dict(provider=name, state=state, nonce=nonce, verifier=verifier,
                          org=(request.form.get("org") or "").strip().lower(),
                          next=request.form.get("next") or "", started=int(time.time()))
    params = dict(client_id=p["client_id"], response_type="code", scope="openid email profile",
                  redirect_uri=url_for("sso.callback", name=name, _external=True), state=state, nonce=nonce,
                  code_challenge=_b64url(hashlib.sha256(verifier.encode()).digest()), code_challenge_method="S256",
                  prompt="select_account")
    if p.get("domain"):
        params["hd"] = p["domain"]
    return redirect(f"{p['authorize']}?{urllib.parse.urlencode(params)}")


def _fail(message):
    session.pop("sso", None)
    flash(message, "error")
    return redirect(url_for("auth.login"))


def verified_email(p, claims, nonce, now=None):
    """The email address the provider vouches for, or None."""
    now = now or time.time()
    if not claims:
        return None
    if claims.get("iss") not in p["issuers"]:
        return None
    aud = claims.get("aud")
    if aud != p["client_id"] and not (isinstance(aud, list) and p["client_id"] in aud):
        return None
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now - CLOCK_SKEW:
        return None
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        return None
    if "tenant" in p:  # Microsoft: only accounts from your own directory
        if claims.get("tid") != p["tenant"]:
            return None
        email = claims.get("email") or claims.get("preferred_username")
    else:  # Google: only addresses Google has verified
        if claims.get("email_verified") is not True:
            return None
        email = claims.get("email")
        if p.get("domain") and claims.get("hd", "").lower() != p["domain"]:
            return None
    return email.strip().lower() if isinstance(email, str) and "@" in email else None


@bp.route("/<name>/callback")
def callback(name):
    p = providers().get(name)
    pending = session.get("sso")
    if p is None or not pending or pending.get("provider") != name:
        abort(404)
    if request.args.get("error"):
        return _fail("Sign-in was cancelled or refused. Try again, or sign in another way.")
    if not hmac.compare_digest(request.args.get("state", ""), pending["state"]) or \
            time.time() - pending["started"] > 600:
        return _fail("That sign-in link has expired. Try again.")
    try:
        tokens = _post_form(p["token"], dict(
            grant_type="authorization_code", code=request.args.get("code", ""), client_id=p["client_id"],
            client_secret=p["client_secret"], code_verifier=pending["verifier"],
            redirect_uri=url_for("sso.callback", name=name, _external=True)))
    except Exception as exc:  # network or provider error
        current_app.logger.warning("%s sign-in failed at the token step: %s", p["label"], exc)
        return _fail(f"{p['label']} sign-in didn't work. Try again, or sign in another way.")
    email = verified_email(p, _claims(tokens.get("id_token", "")), pending["nonce"])
    if not email:
        return _fail(f"{p['label']} didn't confirm an email address Open PMS can use.")
    org_id = auth.find_org(g.conn, pending["org"])
    person = db.Repo(g.conn, org_id).get("people", email) if org_id else None
    if not person or not person["active"]:
        return _fail(f"{email} isn't set up in Open PMS{' for that organisation' if auth.multi_org(g.conn) else ''}. "
                     "Ask an admin to add you.")
    acc = g.conn.execute("SELECT * FROM accounts WHERE org_id = ? AND email = ?", (org_id, email)).fetchone()
    if acc is None:
        g.conn.execute("INSERT INTO accounts (org_id, email, created_at) VALUES (?, ?, ?)",
                       (org_id, email, db.iso(db.utcnow())))
        acc = g.conn.execute("SELECT * FROM accounts WHERE org_id = ? AND email = ?", (org_id, email)).fetchone()
    target = pending["next"]
    auth.start_session(acc)
    return redirect(auth._safe_next(target))
