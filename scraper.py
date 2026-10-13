"""
Housing bot: Plaza + Roomspot -> Telegram, with Roomspot auto-apply
===================================================================

What it does, every check:
  1. Reads the public listing pages of Plaza and Roomspot.
  2. Plaza (notify only): sends every new listing in your cities on Telegram.
  3. Roomspot (auto-apply): logs in with your Roomspot account, checks which
     listings in Enschede (incl. the UT campus) / Hengelo match your Roomspot
     preferences (the green house with the heart) and that Roomspot lets you
     apply, then applies in your priority order. No message per listing.
  4. Roomspot: checks your account for offers (a room offered / assigned to
     you) and sends you a Telegram message as soon as one appears or changes.
  5. Daily "still running" message, with how many Roomspot applications were
     sent since the previous one.

How to run it
-------------
    python scraper.py --once                 one check, then exit
    python scraper.py --loop-minutes 9       check every 60 s for 9 minutes (GitHub fast mode)
    python scraper.py                        check forever (own PC / server)
    python scraper.py --test                 send a Telegram test message
    python scraper.py --check-login          log in to Roomspot and report, without applying

Secrets (NEVER put these in this file)
--------------------------------------
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID     from @BotFather / getUpdates
    ROOMSPOT_USERNAME, ROOMSPOT_PASSWORD     your Roomspot login (needed to apply)
    PLAZA_USERNAME, PLAZA_PASSWORD           no longer used (Plaza is notify-only)
On GitHub these are repository Secrets. On your own computer: a .env file.
"""

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

import requests

try:  # .env is only used when running on your own PC / server
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    LOCAL_TZ = None


# ============================================================================
# YOUR SETTINGS  (safe to edit, e.g. with the pencil icon on GitHub)
# ============================================================================

# Only listings in these cities are sent to you / applied for. [] = all cities.
CITIES = ["Enschede"]

# --- Auto-apply (Roomspot) --------------------------------------------------
# Needs ROOMSPOT_USERNAME and ROOMSPOT_PASSWORD secrets. Without them: nothing
# is applied. Which site applies is set per site below ("auto_apply").
AUTO_APPLY = True

# Only apply to listings that match your preferences on that site
# (the green house with the heart). Change your preferences on the website;
# the bot follows them.
ONLY_PREFERENCE_MATCHES = True

# Priority when several listings can be applied for at once:
#   1st: big AND on a high floor,  2nd: high floor,  3rd: everything else.
# Inside each group: bigger first, then higher first.
HIGH_FLOOR_FROM = 6        # "above floor five" = floor 6 and up
BIG_FROM_M2 = 22           # "big" = at least this many m²

# Safety limit: at most this many applications per check. None = no limit.
MAX_APPLICATIONS_PER_CHECK = None

# --- Extra filters (on top of your site preferences) ------------------------
ONLY_TYPES = []            # e.g. ["Studio", "Apartment", "Room"]; [] = all
MAX_RENT = None            # e.g. 900 (total rent per month); None = no limit

# --- Messages ---------------------------------------------------------------
DAILY_HEARTBEAT = True     # one "still running" message per day
HEARTBEAT_HOUR = 9         # around this hour (Amsterdam time)
OFFER_CHECK_MINUTES = 10   # how often to look for offers in your account
WARN_AFTER_FAILURES = 12   # warn after this many failed checks in a row

# Only used when running forever on your own PC / server.
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # seconds


# ============================================================================
# WEBSITES
# ----------------------------------------------------------------------------
# Plaza and Roomspot run on the same platform ("zig365"). Another zig365 site
# only needs a new block here. Other platforms need a new fetch function.
# ============================================================================

ZIG365_HIDDEN_FILTERS = {
    "$and": [
        {"dwellingType.categorie": {"$eq": "woning"}},
        {"rentBuy": {"$eq": "Huur"}},
        {"isExtraAanbod": {"$eq": ""}},
        {"isWoningruil": {"$eq": ""}},
    ]
}

SITES = [
    {
        "key": "plaza",
        "name": "Plaza",
        "emoji": "🏢",
        "enabled": True,
        "type": "zig365",
        "api_url": "https://mosaic-plaza-aanbodapi.zig365.nl/api/v1/actueel-aanbod",
        "site_url": "https://plaza.newnewnew.space",
        "details_path": "/en/availables-places/living-place/details/",
        "auto_apply": False,      # notify only - the bot no longer applies on Plaza
    },
    {
        "key": "roomspot",
        "name": "Roomspot",
        "emoji": "🏠",
        "enabled": True,
        "type": "zig365",
        "api_url": "https://studentenenschede-aanbodapi.zig365.nl/api/v1/actueel-aanbod",
        "site_url": "https://www.roomspot.nl",
        "portal_url": "https://roomspot.nl",   # where the login lives (www redirects)
        "details_path": "/en/housing-offer/to-rent/translate-to-engels-details/",
        # Enschede includes the University of Twente campus (a quarter of Enschede).
        "cities": ["Enschede", "Hengelo"],  # Roomspot only; Plaza uses CITIES
        "auto_apply": True,           # uses ROOMSPOT_USERNAME / ROOMSPOT_PASSWORD
        "login_env": ("ROOMSPOT_USERNAME", "ROOMSPOT_PASSWORD"),
        "notify_listings": False,     # no message for new / applied listings
        "watch_offers": True,         # message when Roomspot offers you something
    },
]


# ============================================================================
# Below here is the machinery. You shouldn't need to change it.
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"


def env(name):
    return os.getenv(name, "").strip()


TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")


def site_login(site):
    """(username, password) for a site, from its own secrets."""
    user_var, pass_var = site.get("login_env") or ("", "")
    return env(user_var), env(pass_var)


SECRETS = [TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID] + [
    v for s in SITES for v in site_login(s)]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

ALLOCATION_LABELS = {
    "reactiedatum": "First come, first served ⚡",
    "cooptation": "Housemates choose (cooptation)",
    "hospiteren": "Housemates choose (cooptation)",
    "loting": "Lottery",
    "inschrijfduur": "Longest registered wins",
}


def now_local():
    return datetime.now(LOCAL_TZ) if LOCAL_TZ else datetime.now()


def log(msg):
    # GitHub logs of public repos are public: never log secrets or personal data.
    print(f"[{now_local():%H:%M:%S}] {redact(msg)}", flush=True)


def redact(text):
    text = str(text)
    for secret in SECRETS:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def _first(*values):
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _id(obj):
    return str(obj.get("id")) if isinstance(obj, dict) and obj.get("id") is not None else None


# ---------------------------------------------------------------- fetching --

def fetch_zig365(site):
    items, page, limit = [], 0, 60
    while True:
        params = {"limit": limit, "locale": "en_GB", "page": page,
                  "sort": "+reactionData.aangepasteTotaleHuurprijs"}
        payload = {"hidden-filters": ZIG365_HIDDEN_FILTERS}
        if site.get("filters"):
            payload["filters"] = site["filters"]
        headers = {"User-Agent": UA, "Accept": "application/json",
                   "Content-Type": "application/json",
                   "Origin": site["site_url"], "Referer": site["site_url"] + "/"}
        r = requests.post(site["api_url"], params=params, json=payload,
                          headers=headers, timeout=30)
        r.raise_for_status()
        batch = r.json().get("data") or []
        items.extend(batch)
        if len(batch) < limit or page >= 4:
            break
        page += 1

    listings, ids = [], set()
    for item in items:
        try:
            listing = parse_zig365_item(item, site)
        except Exception as e:
            log(f"  could not read a {site['name']} listing: {e}")
            continue
        if listing and listing["id"] not in ids:
            ids.add(listing["id"])
            listings.append(listing)
    return listings


def parse_zig365_item(item, site):
    listing_id = str(item.get("id") or "").strip()
    if not listing_id:
        return None
    address = " ".join(str(p).strip() for p in
                       (item.get("street"), item.get("houseNumber"), item.get("houseNumberAddition"))
                       if p not in (None, "")).strip()
    city = item.get("city")
    city = city.get("name") if isinstance(city, dict) else city
    city = _first(city, item.get("gemeenteGeoLocatieNaam")) or ""

    def num(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    total_rent = num(_first(item.get("totalRent"), item.get("netRent")))
    net_rent = num(_first(item.get("netRent"), item.get("totalRent")))
    area = num(item.get("areaDwelling"))

    dwelling = item.get("dwellingType") if isinstance(item.get("dwellingType"), dict) else {}
    floor = item.get("floor") if isinstance(item.get("floor"), dict) else {}
    kind = item.get("woningsoort") if isinstance(item.get("woningsoort"), dict) else {}
    model = item.get("model") if isinstance(item.get("model"), dict) else {}
    model_code = ((model.get("modelCategorie") or {}).get("code")
                  or (item.get("toewijzingModelCategorie") or {}).get("code") or "")
    floor_no = floor.get("verdieping")
    try:
        floor_no = int(floor_no) if floor_no is not None else None
    except (TypeError, ValueError):
        floor_no = None

    picture = ""
    pics = item.get("pictures") or []
    if pics and isinstance(pics[0], dict):
        picture = _first(pics[0].get("uri"), pics[0].get("url")) or ""
    if picture and not picture.startswith(("http://", "https://")):
        picture = site["site_url"] + picture

    return {
        "id": listing_id,
        "site": site["key"],
        "address": address or "(address not shown)",
        "city": city,
        "place": f"{item.get('postalcode') or ''} {city}".strip(),
        "rent": total_rent,
        "net_rent": net_rent,
        "area": area,
        "type": (_first(dwelling.get("localizedName"), dwelling.get("name")) or "").strip(),
        "floor": (_first(floor.get("localizedName"), floor.get("name")) or "").strip(),
        "floor_no": floor_no,
        "kind": (kind.get("localizedNaam") or "").strip(),
        "allocation": ALLOCATION_LABELS.get(model_code, model_code),
        "link": site["site_url"] + site["details_path"] + str(item.get("urlKey") or listing_id),
        "image": picture,
        # "independent" = a place of your own, not a room in a shared house.
        # "rent_allowance" is False only when the site says "No rent benefit".
        "independent": item.get("isZelfstandig") in (1, "1", True),
        "rent_allowance": item.get("huurtoeslagMogelijk") not in (0, "0"),
        # used for the Plaza preference match (never stored)
        "_match": {
            "regios": _id(item.get("regio")),
            "municipalities": _id(item.get("municipality")),
            "cities": _id(item.get("city")),
            "quarters": _id(item.get("quarter")),
            "dwellingtypes": _id(dwelling),
            "woningsoorten": _id(kind),
            "modelCategories": _id(item.get("toewijzingModelCategorie")) or _id(model.get("modelCategorie")),
            "sleepingrooms": _id(item.get("sleepingRoom")),
            "doelgroepen": [_id(d) for d in (item.get("doelgroepen") or []) if _id(d)],
            "newlyBuild": item.get("newlyBuild"),
        },
    }


FETCHERS = {"zig365": fetch_zig365}


# ------------------------------------------------------------------ filters --

def in_my_cities(listing):
    # A site can set its own "cities" list; otherwise CITIES above is used.
    cities = CITIES
    for s in SITES:
        if s["key"] == listing["site"]:
            cities = s.get("cities", CITIES)
            break
    return not cities or listing["city"].strip().lower() in {c.strip().lower() for c in cities}


def passes_extra_filters(listing):
    if ONLY_TYPES and listing["type"].lower() not in {t.strip().lower() for t in ONLY_TYPES}:
        return False
    if MAX_RENT is not None and listing["rent"] is not None and listing["rent"] > MAX_RENT:
        return False
    return True


def matches_preferences(listing, profile):
    """Same check as the site's green house icon, using your search profile there."""
    if not profile:
        return False
    m = listing["_match"]
    for key in ("regios", "municipalities", "cities", "quarters", "dwellingtypes",
                "woningsoorten", "modelCategories", "sleepingrooms"):
        wanted = {str(x) for x in (profile.get(key) or [])}
        if wanted and m.get(key) not in wanted:
            return False
    wanted = {str(x) for x in (profile.get("doelgroepen") or [])}
    if wanted and not wanted.intersection(m.get("doelgroepen") or []):
        return False
    rent = listing["net_rent"]
    lo, hi = profile.get("minimumRentalPrice"), profile.get("maximumRentalPrice")
    if rent is not None:
        if lo not in (None, "") and rent < float(lo):
            return False
        if hi not in (None, "") and rent > float(hi):
            return False
    nieuwbouw = profile.get("nieuwbouw")
    if nieuwbouw not in (None, "") and bool(int(nieuwbouw)) != bool(m.get("newlyBuild")):
        return False
    return True


def priority(listing):
    """Lower = apply first."""
    high = listing["floor_no"] is not None and listing["floor_no"] >= HIGH_FLOOR_FROM
    big = listing["area"] is not None and listing["area"] >= BIG_FROM_M2
    group = 0 if (high and big) else 1 if high else 2
    return (group, -(listing["area"] or 0), -(listing["floor_no"] or 0))


PRIORITY_LABELS = {0: "big + high floor", 1: "high floor", 2: "other"}


# ------------------------------------------------------------ site login --
# Plaza and Roomspot share the same login / apply protocol (zig365).

class PlazaError(Exception):
    pass


class PlazaClient:
    """Does what your browser does on a zig365 site (Roomspot, Plaza), with your own login."""

    def __init__(self, portal_url, username, password, name="Plaza"):
        self.name = name
        self.portal = portal_url.rstrip("/")
        self.username, self.password = username, password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                               "X-Requested-With": "XMLHttpRequest",
                               "Origin": self.portal, "Referer": self.portal + "/"})
        self.logged_in = False
        self.login_time = 0
        self.form = None

    def _json(self, r):
        try:
            return r.json()
        except ValueError:
            raise PlazaError(f"unexpected answer from {self.name} (HTTP {r.status_code})")

    def login(self):
        r = self.s.post(self.portal + "/portal/proxy/frontend/api/v1/oauth/token",
                        json={"grant_type": "password", "client_id": "wzp",
                              "username": self.username, "password": self.password},
                        timeout=30)
        body = self._json(r)
        err = body.get("error") if isinstance(body, dict) else None
        if err == "invalid_grant":
            raise PlazaError(f"{self.name} says the username or password is wrong")
        if err == "mfa_required":
            raise PlazaError(f"your {self.name} account uses two-step verification, "
                             "which the bot can't do")
        if r.status_code >= 400 or err:
            raise PlazaError(f"login failed (HTTP {r.status_code}, {err or 'no details'})")
        token = body.get("access_token") if isinstance(body, dict) else None
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        r = self.s.post(self.portal + "/portal/account/frontend/loginbyservice/format/json",
                        timeout=30)
        if r.status_code >= 400:
            raise PlazaError(f"starting the {self.name} session failed (HTTP {r.status_code})")
        acc = self._json(self.s.get(self.portal + "/portal/account/frontend/getaccount/format/json",
                                    timeout=30))
        if not (isinstance(acc, dict) and acc.get("account")):
            raise PlazaError(f"logged in, but {self.name} doesn't show your account")
        self.logged_in = True
        self.login_time = time.time()
        self.form = None

    def ensure_login(self):
        if not self.logged_in or time.time() - self.login_time > 20 * 60:
            self.s.headers.pop("Authorization", None)
            self.s.cookies.clear()
            self.login()

    def preferences(self):
        body = self._json(self.s.get(
            self.portal + "/portal/registration/frontend/getzoekprofielforapi/format/json", timeout=30))
        return (body or {}).get("result") or {}

    def offers(self):
        """Everything assigned / offered to you (the "offers" page on the site)."""
        body = self._json(self.s.get(
            self.portal + "/portal/registration/frontend/getassigneddwellings/format/json", timeout=30))
        result = (body or {}).get("result") if isinstance(body, dict) else None
        if result is None:
            if isinstance(body, dict) and "result" in body:
                return []
            raise PlazaError(f"unexpected offers answer from {self.name}")
        if isinstance(result, dict):   # some versions wrap the list
            result = next((v for v in result.values() if isinstance(v, list)), [])
        return result if isinstance(result, list) else []

    def reaction_status(self, ids):
        """Per listing: can you apply, and have you already applied?"""
        data = [("objectId[]", i) for i in ids]
        body = self._json(self.s.post(
            self.portal + "/portal/object/frontend/getreagerendata/format/json", data=data, timeout=30))
        return (body or {}).get("reagerenData") or {}

    def _form_fields(self):
        if not self.form:
            body = self._json(self.s.get(
                self.portal + "/portal/core/frontend/getformsubmitonlyconfiguration/format/json", timeout=30))
            form = (body or {}).get("form") or {}
            h = ((form.get("elements") or {}).get("__hash__") or {}).get("initialData")
            if not h:
                raise PlazaError(f"couldn't get {self.name}'s apply form")
            self.form = {"__id__": form.get("id") or "Portal_Form_SubmitOnly", "__hash__": h}
        return dict(self.form)

    def apply(self, reaction_url):
        """reaction_url looks like '?add=11791&dwellingID=17017' (from reaction_status)."""
        data = self._form_fields()
        data.update(dict(parse_qsl(reaction_url.lstrip("?"))))
        if "add" not in data:
            raise PlazaError("this listing has no apply option")
        body = self._json(self.s.post(
            self.portal + "/portal/object/frontend/react/format/json", data=data, timeout=30))
        if isinstance(body, dict) and body.get("formHash"):
            self.form["__hash__"] = body["formHash"]
        ok = isinstance(body, dict) and body.get("success") is True
        messages = []
        for m in (body.get("messages") or []) if isinstance(body, dict) else []:
            messages.append(m.get("text") or m.get("message") or str(m) if isinstance(m, dict) else str(m))
        position = None
        if isinstance(body, dict):
            rd = body.get("reactionData") or {}
            position = _first(body.get("positie"), rd.get("positie"), rd.get("voorlopigePositie"))
        return ok, "; ".join(messages)[:300], position


_clients = {}


def site_client(site):
    if site["key"] not in _clients:
        user, password = site_login(site)
        _clients[site["key"]] = PlazaClient(site.get("portal_url") or site["site_url"],
                                            user, password, site["name"])
    return _clients[site["key"]]


def auto_apply_enabled(site):
    return bool(AUTO_APPLY and site.get("auto_apply") and all(site_login(site)))


# ----------------------------------------------------------------- telegram --

def telegram(method, **data):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        log("  Telegram is not configured")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = dict(data, chat_id=TELEGRAM_CHAT_ID)
    for _ in range(3):
        try:
            r = requests.post(url, data=data, timeout=30)
            body = r.json()
        except Exception as e:
            log(f"  Telegram request failed: {type(e).__name__}")
            time.sleep(2)
            continue
        if body.get("ok"):
            return True
        if r.status_code == 429:
            time.sleep(min(int((body.get("parameters") or {}).get("retry_after", 5)), 60))
            continue
        log(f"  Telegram error: {body.get('description', r.status_code)}")
        return False
    return False


def fmt_rent(rent):
    return f"€{rent:,.2f}" if rent is not None else "price not shown"


def listing_message(listing, site, headline, status=None):
    e = html.escape
    lines = [f"{site['emoji']} <b>{e(headline)}</b>", f"<b>{e(listing['address'])}</b>"]
    if listing["place"]:
        lines.append(e(listing["place"]))
    facts = [f"💶 {fmt_rent(listing['rent'])} /month"]
    if listing["area"]:
        facts.append(f"📐 {listing['area']:g} m²")
    lines.append("   ".join(facts))
    kind = " · ".join(x for x in (listing["type"], listing["kind"], listing["floor"]) if x)
    if kind:
        lines.append(f"🏷 {e(kind)}")
    if listing["allocation"]:
        lines.append(f"📋 {e(listing['allocation'])}")
    if status:
        lines.append(f"\n{status}")
    lines.append(f'\n<a href="{e(listing["link"])}">Open listing →</a>')
    return "\n".join(lines)


def send_listing(listing, site, headline, status=None):
    text = listing_message(listing, site, headline, status)
    button = json.dumps({"inline_keyboard": [[{"text": "Open listing", "url": listing["link"]}]]})
    if listing["image"] and telegram("sendPhoto", photo=listing["image"], caption=text[:1024],
                                     parse_mode="HTML", reply_markup=button):
        return True
    return telegram("sendMessage", text=text, parse_mode="HTML",
                    disable_web_page_preview="true", reply_markup=button)


def send_text(text):
    return telegram("sendMessage", text=text, parse_mode="HTML", disable_web_page_preview="true")


# -------------------------------------------------------------------- state --

def load_state(name, default):
    try:
        return json.loads((STATE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:
        log(f"  state file {name}.json unreadable ({e}), starting fresh")
        return default


def save_state(name, data):
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / f"{name}.json"
    new = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != new:
        path.write_text(new, encoding="utf-8")


def trim(ids, online, keep=800):
    """Keep ids still online plus recent history, so the file stays small."""
    ids = list(dict.fromkeys(ids))
    return [i for i in ids if i in online] + [i for i in ids if i not in online][-keep:]


# ------------------------------------------------------------- auto-apply --

def login_or_backoff(site, client, state):
    """Log in (if needed) and return your search profile, or None on failure.
    After a failure, waits longer each time so a wrong password never gets
    your account blocked."""
    name = html.escape(site["name"])
    user_var, pass_var = site.get("login_env") or ("", "")
    if time.time() < state.get("login_retry_after", 0):
        return None
    try:
        client.ensure_login()
        profile = client.preferences()
        if not profile:          # session silently expired? log in again once
            client.logged_in = False
            client.ensure_login()
            profile = client.preferences()
        if not profile:
            raise PlazaError(f"couldn't read your {site['name']} preferences")
    except (PlazaError, requests.RequestException) as e:
        client.logged_in = False
        streak = state["login_fail_streak"] = state.get("login_fail_streak", 0) + 1
        # wait longer after each failure (30 min, 60 min, ... max 6 h) so a wrong
        # password never hammers the site and gets your account blocked
        state["login_retry_after"] = time.time() + min(30 * 60 * streak, 6 * 3600)
        log(f"  {site['name']} login problem ({streak} in a row), next try in {min(30 * streak, 360)} min")
        if streak in (1, 6):
            send_text(f"⚠️ Couldn't log in to {name}, so nothing was applied: "
                      f"{html.escape(redact(e))}.\n"
                      f"Check the {user_var} / {pass_var} secrets. "
                      f"Next try in {min(30 * streak, 360)} minutes.")
        return None
    state.pop("login_retry_after", None)
    if state.get("login_fail_streak", 0) >= 1:
        send_text(f"✅ {name} login works again, auto-apply is back on.")
    state["login_fail_streak"] = 0

    return profile


def run_auto_apply(site, candidates, state, report):
    """Try to apply for candidates. Returns {listing_id: status line} for messages.
    Candidates that couldn't be evaluated (e.g. login problem) stay unevaluated."""
    statuses = {}
    client = site_client(site)
    name = html.escape(site["name"])
    profile = login_or_backoff(site, client, state)
    if profile is None:
        return statuses

    evaluated = state.setdefault("evaluated", [])
    for l in candidates:
        if not passes_extra_filters(l):
            evaluated.append(l["id"])
    candidates = [l for l in candidates if passes_extra_filters(l)]
    if not candidates:
        return statuses

    # Ask the site, logged in, about each listing. Its answer includes
    # "zoekprofielMatch" = the green house with the heart on the website.
    try:
        status = client.reaction_status([l["id"] for l in candidates])
    except (PlazaError, requests.RequestException) as e:
        client.logged_in = False
        log(f"  couldn't read apply status: {type(e).__name__}")
        return statuses
    if not isinstance(status, dict):
        status = {}

    def is_match(l):
        st = status.get(l["id"]) or {}
        if "zoekprofielMatch" in st:
            return bool(st["zoekprofielMatch"])
        return matches_preferences(l, profile)   # fallback: same check, done here

    matching = []
    for l in candidates:
        if ONLY_PREFERENCE_MATCHES and not is_match(l):
            evaluated.append(l["id"])
        else:
            matching.append(l)
    report["matching"] = len(matching)
    if not matching:
        return statuses

    to_apply = []
    for l in matching:
        st = status.get(l["id"]) if isinstance(status, dict) else None
        st = st or {}
        action = st.get("action")
        if action == "remove":
            statuses[l["id"]] = "🏡 Matches your preferences. You already applied."
            evaluated.append(l["id"])
        elif action == "add" and st.get("kanReageren"):
            to_apply.append((l, st.get("url") or ""))
        elif st.get("kanReageren") is False and action not in (None, "login"):
            reason = st.get("redenMagNietReagerenCode") or f"{site['name']} doesn't allow it for your profile"
            statuses[l["id"]] = f"🏡 Matches your preferences, but you can't apply ({html.escape(str(reason))})."
            evaluated.append(l["id"])
        else:
            # No clear answer (e.g. session expired): try again next check.
            client.logged_in = False

    to_apply.sort(key=lambda pair: priority(pair[0]))
    if MAX_APPLICATIONS_PER_CHECK is not None:
        skipped = to_apply[MAX_APPLICATIONS_PER_CHECK:]
        to_apply = to_apply[:MAX_APPLICATIONS_PER_CHECK]
        for l, _ in skipped:
            statuses[l["id"]] = "🏡 Matches, not applied (limit per check reached). Apply yourself if you want it."
            evaluated.append(l["id"])

    for l, url in to_apply:
        label = PRIORITY_LABELS[priority(l)[0]]
        if report.get("dry_run"):
            statuses[l["id"]] = f"🧪 Would apply now (priority: {label})."
            continue
        try:
            ok, msg, position = client.apply(url)
        except (PlazaError, requests.RequestException) as e:
            ok, msg, position = False, redact(e), None
        evaluated.append(l["id"])
        if ok:
            report["applied"] = report.get("applied", 0) + 1
            pos = f" Your place in line: <b>{html.escape(str(position))}</b>." if position else ""
            statuses[l["id"]] = f"✅ <b>Applied automatically</b> (priority: {label}).{pos}"
        else:
            statuses[l["id"]] = (f"❌ Tried to apply but {name} said no"
                                 f"{': ' + html.escape(msg) if msg else ''}. Try it yourself via the link.")
        log(f"  apply attempt: {'ok' if ok else 'failed'}")
    return statuses


# ------------------------------------------------------------------- offers --

OFFER_STATUS_LABELS = {
    "aangeboden": "Offered to you 🎉",
    "interesse": "You showed interest",
    "geaccepteerd": "Accepted",
    "toegewezen": "Assigned to you 🎉",
    "geweigerd": "Declined",
    "vervallen": "Expired",
}


def _offer_info(o, site):
    """Pull the useful bits out of one offer, whatever shape it has."""
    t = o.get("toewijzing") if isinstance(o.get("toewijzing"), dict) else {}
    status = o.get("assignmentStatus") or ((t.get("status") or {}).get("code") if isinstance(t.get("status"), dict) else t.get("status")) or ""
    obj = next((o[k] for k in ("object", "dwelling", "advertentie", "woning") if isinstance(o.get(k), dict)), o)
    city = obj.get("city")
    city = city.get("name") if isinstance(city, dict) else city
    address = " ".join(str(p) for p in (obj.get("street"), obj.get("houseNumber"), obj.get("houseNumberAddition"))
                       if p not in (None, "")).strip()
    key = str(_first(o.get("id"), t.get("id"), obj.get("id"), json.dumps(o, sort_keys=True)[:200]))
    deadline = _first(o.get("lastReactionDate"), o.get("uitersteReactiedatum"), t.get("uitersteReactiedatum"))
    viewing = _first(o.get("bezichtigingsdatum"), o.get("bezichtiging"))
    link = site["site_url"] + site["details_path"] + str(obj.get("urlKey") or obj.get("id") or "") if (obj.get("urlKey") or obj.get("id")) else site["site_url"]
    return {"key": key, "status": str(status), "address": address or "(address not shown)",
            "city": city or "", "deadline": deadline, "viewing": viewing, "link": link}


def check_offers(site, state):
    """Message you when something is offered to you, or its status changes."""
    if time.time() < state.get("offers_next_check", 0):
        return
    state["offers_next_check"] = time.time() + OFFER_CHECK_MINUTES * 60
    client = site_client(site)
    if login_or_backoff(site, client, state) is None:
        return
    try:
        offers = client.offers()
    except (PlazaError, requests.RequestException) as e:
        client.logged_in = False
        log(f"  couldn't read {site['name']} offers: {type(e).__name__}")
        return
    known = state.setdefault("offers", {})
    for o in offers:
        if not isinstance(o, dict):
            continue
        info = _offer_info(o, site)
        if known.get(info["key"]) == info["status"]:
            continue
        e = html.escape
        label = OFFER_STATUS_LABELS.get(info["status"].lower(), info["status"] or "New")
        lines = [f"🔔 <b>{e(site['name'])}: {e(label)}</b>",
                 f"<b>{e(info['address'])}</b>" + (f", {e(info['city'])}" if info["city"] else "")]
        if info["viewing"]:
            lines.append(f"👀 Viewing: {e(str(info['viewing']))}")
        if info["deadline"]:
            lines.append(f"⏰ Respond before: {e(str(info['deadline']))}")
        lines.append(f"\nLog in to {e(site['name'])} to respond. "
                     f'<a href="{e(info["link"])}">Open listing →</a>')
        if send_text("\n".join(lines)):
            known[info["key"]] = info["status"]
    log(f"{site['name']}: {len(offers)} offer(s) in your account")


# --------------------------------------------------------------------- main --

def check_site(site, dry_run=False):
    state = load_state(site["key"], None)
    first_run = state is None
    state = state or {"seen": [], "evaluated": [], "fail_streak": 0}
    seen = set(state.get("seen", []))

    try:
        listings = FETCHERS[site["type"]](site)
    except Exception as e:
        state["fail_streak"] = state.get("fail_streak", 0) + 1
        log(f"{site['name']}: check failed ({type(e).__name__}) - {state['fail_streak']} in a row")
        if state["fail_streak"] == WARN_AFTER_FAILURES:
            send_text(f"⚠️ {html.escape(site['name'])} failed {WARN_AFTER_FAILURES} checks in a row. "
                      f"The site may be down or may have changed.")
        if not first_run:
            save_state(site["key"], state)
        return
    if state.get("fail_streak", 0) >= WARN_AFTER_FAILURES:
        send_text(f"✅ {html.escape(site['name'])} is working again.")
    state["fail_streak"] = 0

    mine = [l for l in listings if in_my_cities(l)]
    # Optional per-site filters: only your own place / rent allowance possible.
    if site.get("only_independent"):
        mine = [l for l in mine if l["independent"]]
    if site.get("only_rent_allowance"):
        mine = [l for l in mine if l["rent_allowance"]]
    new = [l for l in mine if l["id"] not in seen]
    report = {"dry_run": dry_run}
    statuses = {}

    if auto_apply_enabled(site):
        evaluated = set(state.get("evaluated", []))
        candidates = [l for l in mine if l["id"] not in evaluated]
        if candidates:
            statuses = run_auto_apply(site, candidates, state, report)
    log(f"{site['name']}: {len(listings)} online, {len(mine)} in your cities, {len(new)} new"
        + (f", {report.get('applied', 0)} applied" if auto_apply_enabled(site) else ""))

    if first_run and site.get("notify_listings", True):
        lines = [f"👋 Now watching <b>{html.escape(site['name'])}</b>"
                 + (f" ({html.escape(', '.join(CITIES))})" if CITIES else "")
                 + f": {len(mine)} listing(s) online right now."]
        for l in mine[:25]:
            lines.append(f'• <a href="{html.escape(l["link"])}">{html.escape(l["address"])}</a>'
                         f" – {fmt_rent(l['rent'])}" + (f", {html.escape(l['type'])}" if l["type"] else ""))
        lines.append("From now on you get a message for every new one."
                     + (" Auto-apply is ON." if auto_apply_enabled(site) else ""))
        send_text("\n".join(lines))
        seen.update(l["id"] for l in mine)

    # Messages: every new listing, plus anything the bot just applied for.
    if not site.get("notify_listings", True):
        # Silent site: count what happened for the daily message, send nothing now.
        daily = state.setdefault("daily", {"applied": 0, "failed": 0})
        daily["applied"] += sum(1 for st in statuses.values() if st.startswith("✅"))
        daily["failed"] += sum(1 for st in statuses.values() if st.startswith("❌"))
        seen.update(l["id"] for l in mine)
        to_message = {}
    else:
        to_message = {l["id"]: l for l in new} if not first_run else {}
    for lid in (statuses if site.get("notify_listings", True) else {}):
        if statuses[lid].startswith(("✅", "❌", "🧪")) or lid in to_message:
            to_message[lid] = next(l for l in mine if l["id"] == lid)
    for lid, l in sorted(to_message.items(), key=lambda kv: priority(kv[1])):
        st = statuses.get(lid)
        headline = ("Applied on " if st and st.startswith("✅") else "New on ") + site["name"]
        if st and st.startswith("🧪"):
            headline = f"Test: new on {site['name']}"
        if not passes_extra_filters(l) and not st:
            seen.add(lid)
            continue
        if send_listing(l, site, headline, st):
            seen.add(lid)
        time.sleep(1)

    online = {l["id"] for l in listings}
    state["seen"] = trim([i for i in state.get("seen", []) if i in seen] + sorted(seen), online)
    state["evaluated"] = trim(state.get("evaluated", []), online)
    if site.get("watch_offers") and auto_apply_enabled(site) and not dry_run:
        check_offers(site, state)
    save_state(site["key"], state)


def maybe_heartbeat(sites):
    if not DAILY_HEARTBEAT:
        return
    bot = load_state("_bot", {})
    now = now_local()
    today = now.strftime("%Y-%m-%d")
    if now.hour >= HEARTBEAT_HOUR and bot.get("last_heartbeat") != today:
        names = ", ".join(s["name"] for s in sites)
        applying = [s["name"] for s in sites if auto_apply_enabled(s)]
        text = (f"🟢 Still watching {html.escape(names)}. "
                f"Auto-apply: {html.escape(', '.join(applying)) if applying else 'OFF'}.")
        silent = [(s, load_state(s["key"], {})) for s in sites if not s.get("notify_listings", True)]
        for s, st in silent:
            d = st.get("daily") or {}
            text += (f"\n{html.escape(s['name'])} since last message: {d.get('applied', 0)} applied"
                     + (f", {d['failed']} failed (apply by hand?)" if d.get("failed") else "") + ".")
        if send_text(text):
            bot["last_heartbeat"] = today
            save_state("_bot", bot)
            for s, st in silent:
                if st.get("daily"):
                    st["daily"] = {"applied": 0, "failed": 0}
                    save_state(s["key"], st)


def run_once(dry_run=False):
    sites = [s for s in SITES if s.get("enabled", True)]
    for site in sites:
        check_site(site, dry_run=dry_run)
    maybe_heartbeat(sites)


def check_login():
    """Log in and report on Telegram, without applying."""
    site = next(s for s in SITES if s.get("auto_apply"))
    name = html.escape(site["name"])
    user_var, pass_var = site.get("login_env") or ("", "")
    if not all(site_login(site)):
        send_text(f"⚠️ {user_var} / {pass_var} are not set, so auto-apply is off.")
        return False
    client = site_client(site)
    try:
        client.login()
        profile = client.preferences()
        listings = [l for l in fetch_zig365(site) if in_my_cities(l)]
        listings = [l for l in listings if passes_extra_filters(l)]
        status = client.reaction_status([l["id"] for l in listings]) if listings else {}
        status = status if isinstance(status, dict) else {}
        try:
            offers_line = f"Offers in your account right now: {len(client.offers())} (you get a message for each)."
        except (PlazaError, requests.RequestException) as e:
            offers_line = f"⚠️ Couldn't read your offers page: {html.escape(redact(e))}"
        matching = [l for l in listings
                    if (status.get(l["id"]) or {}).get("zoekprofielMatch",
                                                       matches_preferences(l, profile))]
    except (PlazaError, requests.RequestException) as e:
        send_text(f"❌ {name} login test failed: {html.escape(redact(e))}")
        log(f"{site['name']} login test failed")
        return False
    rent = f"€{profile.get('minimumRentalPrice') or 0:g}–{profile.get('maximumRentalPrice') or '∞'}"
    cities = site.get("cities", CITIES)
    lines = [f"✅ Logged in to {name}. Auto-apply is {'ON' if AUTO_APPLY else 'OFF (AUTO_APPLY = False)'}.",
             f"Your {name} preferences: rent {rent}. Change them on the {name} website.",
             f"Cities the bot uses: {html.escape(', '.join(cities) or 'all')}.",
             offers_line,
             f"Listings there matching your preferences right now: {len(matching)}"]
    for l in sorted(matching, key=priority):
        st = status.get(l["id"]) or {}
        what = ("already applied" if st.get("action") == "remove"
                else "would apply" if st.get("kanReageren") else "not allowed to apply")
        lines.append(f'• <a href="{html.escape(l["link"])}">{html.escape(l["address"])}</a> – {what}')
    send_text("\n".join(lines))
    log(f"{site['name']} login test OK")
    return True


def main():
    p = argparse.ArgumentParser(description="Housing bot: Plaza + Roomspot -> Telegram.")
    p.add_argument("--once", action="store_true", help="one check, then exit")
    p.add_argument("--loop-minutes", type=float, default=0, help="keep checking for N minutes")
    p.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="seconds between checks")
    p.add_argument("--test", action="store_true", help="send a Telegram test message")
    p.add_argument("--check-login", action="store_true", help="test the Roomspot login, no applying")
    p.add_argument("--dry-run", action="store_true", help="do everything except actually applying")
    args = p.parse_args()

    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        log("ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (GitHub Secrets or .env file).")
        sys.exit(1)
    if args.test:
        ok = send_text("✅ Your housing bot can reach you. Setup works!")
        log("Test message sent." if ok else "Test message FAILED - check token and chat id.")
        sys.exit(0 if ok else 1)
    if args.check_login:
        sys.exit(0 if check_login() else 1)
    if args.once:
        run_once(dry_run=args.dry_run)
        return

    end = time.time() + args.loop_minutes * 60 if args.loop_minutes else None
    log(f"Checking every {args.interval} s" + (f" for {args.loop_minutes:g} min." if end else " until stopped."))
    while True:
        started = time.time()
        try:
            run_once(dry_run=args.dry_run)
        except Exception as e:
            log(f"Unexpected error: {type(e).__name__}: {e}")
        next_at = started + args.interval
        if end and next_at > end:
            break
        time.sleep(max(0, next_at - time.time()))


if __name__ == "__main__":
    main()
