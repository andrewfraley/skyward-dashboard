"""HTTP session for Skyward Qmlativ Family Access.

Qmlativ has no parent-facing API, so this drives the same requests the browser
makes:

1. GET a Family Access page; it redirects to /StudentSTS/Session/Signin.
2. POST the sign-in form to /StudentSTS. The reply is an auto-submitting form
   carrying SessionAuthenticationID/Hash, which is POSTed on to the page.
3. Each page embeds a CSRF token (sessionGuidHash), window ids (p, w) and a
   `browseList[...] = {...}` config per data grid. A grid's rows come from
   POST /Student/{routeModule}/{routeObject}/GetBrowse built from that config.

Note that the site root (/) resets the connection, so never request it.

Cookies can be kept between runs in a file (see `cookie_file`). Skyward sets a
long-lived LoginHistoryIdentifier cookie at sign-in that identifies the device;
throwing it away makes every sign-in look like a new device, which is what
sends the parent a "new sign-in" email. Keeping the session cookie too means a
run soon after the last one doesn't sign in at all.
"""

import hashlib
import http.cookiejar
import json
import logging
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from selectolax.parser import HTMLParser

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"


class SkywardError(Exception):
    pass


class LoginError(SkywardError):
    pass


@dataclass
class Page:
    url: str
    html: str
    csrf: str
    p: str
    w: str
    browses: dict[str, dict] = field(default_factory=dict)

    def browse(self, name: str) -> dict:
        """The config of the grid whose browseName (or id) is `name`."""
        for key, cfg in self.browses.items():
            if key == name or cfg.get("browseName") == name:
                return cfg
        raise SkywardError(f"No browse {name!r} on {self.url}; found {list(self.browses)}")


@dataclass
class Browse:
    """A GetBrowse result: the grid's HTML plus its registerBrowse() metadata."""

    html: str
    meta: dict

    @property
    def fields(self) -> list[str | None]:
        return self.meta.get("columnFieldNames", [])


class SkywardSession:
    """A signed-in Family Access session.

    `cookie_file`, when given, keeps cookies between runs: loaded here (if it
    was saved for the same site and username), saved after signing in and on
    close. It holds a live session, so it belongs in the data directory with
    owner-only permissions, never in the repository.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 30,
        cookie_file: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self.cookie_file = Path(cookie_file) if cookie_file else None
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
            transport=transport,
        )
        self.logged_in = False
        self.sign_ins = 0  # how many times this session had to sign in
        if self.cookie_file:
            load_cookies(self.client.cookies.jar, self.cookie_file, self._owner)

    @property
    def _owner(self) -> str:
        return cookie_owner(self.base_url, self._username)

    def save_cookies(self) -> None:
        if self.cookie_file:
            save_cookies(self.client.cookies.jar, self.cookie_file, self._owner)

    def close(self) -> None:
        try:
            self.save_cookies()
        finally:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- pages --------------------------------------------------------------

    def page(self, path: str) -> Page:
        """Load a Family Access page, signing in first if redirected."""
        r = self.client.get(path)
        r.raise_for_status()
        if "/Session/Signin" in str(r.url):
            r = self._sign_in(r)
        return parse_page(str(r.url), r.text)

    def _sign_in(self, signin: httpx.Response) -> httpx.Response:
        form = HTMLParser(signin.text).css_first("form.signIn")
        if form is None:
            raise LoginError("Sign-in form not found")
        data = _form_fields(form)
        data.update(
            UserName=self._username, Password=self._password, ScreenWidth="1400", ScreenHeight="900"
        )
        r = self.client.post("/StudentSTS", data=data)
        r.raise_for_status()

        handoff = HTMLParser(r.text).css_first("form")
        fields = _form_fields(handoff) if handoff else {}
        if "SessionAuthenticationID" not in fields:
            message = HTMLParser(r.text).css_first(
                ".validation-summary-errors, .field-validation-error"
            )
            raise LoginError(message.text(strip=True) if message else "Sign-in was rejected")
        r = self.client.post(handoff.attributes["action"], data=fields)
        r.raise_for_status()
        if "/Session/Signin" in str(r.url):
            raise LoginError("Still on the sign-in page after authenticating")
        self.logged_in = True
        self.sign_ins += 1
        self.save_cookies()
        return r

    # -- grids --------------------------------------------------------------

    def get_browse(self, page: Page, name: str, **post_data_overrides: str) -> Browse:
        """Fetch the rows of the grid `name` on `page`."""
        cfg = page.browse(name)
        post_data = dict(cfg.get("data") or {})
        post_data.update(post_data_overrides)
        form = {
            "pageModule": cfg["pageModule"],
            "pageObject": cfg["pageObject"],
            "pageScreen": cfg["pageScreen"],
            "pageTab": cfg.get("pageTab", ""),
            "routeModule": cfg["routeModule"],
            "routeObject": cfg["routeObject"],
            "dataModule": cfg["dataModule"],
            "dataObject": cfg["dataObject"],
            "browseName": cfg["browseName"],
            "browseId": cfg["id"],
            "hideIfEmpty": "false",
            "selectMode": "false",
            "isCodeEel": "false",
            "queryParameterData": json.dumps(
                cfg.get("queryParameterData") or {}, separators=(",", ":")
            ),
            "queryParameterDataHash": cfg.get("queryParameterDataHash", ""),
            "requestDataHash": cfg.get("requestDataHash", ""),
            "displayName": cfg.get("displayName", ""),
            "performSearch": "true",
            "getBrowseSearchMode": "Always",
            "detailsPanelType": cfg.get("detailsPanelType", "Row"),
            "headerNumber": str(cfg.get("headerNumber", 3)),
            "dynamicFilterValues": "{}",
            "dynamicFilterHashes": "{}",
            "postData": json.dumps(post_data, separators=(",", ":")),
            "browseType": "Default",
            "returnSearchCondition": "false",
        }
        r = self.client.post(
            f"/Student/{cfg['routeModule']}/{cfg['routeObject']}/GetBrowse",
            params={"w": page.w, "p": page.p},
            data=form,
            headers={
                "X-CSRF-Token": page.csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": page.url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        r.raise_for_status()
        try:
            payload = r.json()
        except ValueError as e:
            raise SkywardError(
                f"GetBrowse {name} returned non-JSON ({r.headers.get('content-type')})"
            ) from e
        match = re.search(r"registerBrowse\((\{.*\})\)", payload.get("script", ""), re.S)
        meta = json.loads(match.group(1)) if match else {}
        return Browse(html=payload.get("html", ""), meta=meta)

    def open_panel(self, page: Page, path: str, cell_attrs: dict[str, str]) -> Page:
        """Open the details panel a grid cell links to, e.g. a grade breakdown.

        `cell_attrs` are the cell's attributes; its data-* values are what the
        browser posts. Panels get a fresh page id (p) but share the window (w)
        and CSRF token of the page they open from.
        """
        data = {
            k[5:]: v
            for k, v in cell_attrs.items()
            if k.startswith("data-") and k != "data-click-action"
        }
        r = self.client.post(
            path,
            params={
                "renderType": "contentOnly",
                "renderInDetailsPanel": "true",
                "w": page.w,
                "p": uuid.uuid4().hex,
            },
            data=data,
            headers={
                "X-CSRF-Token": page.csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": page.url,
            },
        )
        r.raise_for_status()
        return parse_page(str(r.url), r.text, csrf=page.csrf)


# -- cookie persistence -------------------------------------------------------

_COOKIE_FORMAT = 1


def cookie_owner(base_url: str, username: str) -> str:
    """Ties a cookie file to one site and account, without storing the username."""
    return hashlib.sha256(f"{base_url.rstrip('/')}\n{username}".encode()).hexdigest()


def save_cookies(jar: http.cookiejar.CookieJar, path: Path, owner: str) -> None:
    """Write the jar as JSON, atomically and readable by the owner only."""
    cookies = [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "expires": c.expires,
            "secure": c.secure,
            "httponly": c.has_nonstandard_attr("HttpOnly"),
        }
        for c in jar
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"format": _COOKIE_FORMAT, "owner": owner, "cookies": cookies}, f)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_cookies(jar: http.cookiejar.CookieJar, path: Path, owner: str) -> int:
    """Add the file's unexpired cookies to the jar; return how many. A file saved
    for another site or account, or one that can't be read, is ignored."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        log.warning("Ignoring unreadable cookie file %s", path)
        return 0
    if data.get("format") != _COOKIE_FORMAT or data.get("owner") != owner:
        log.info("Cookie file %s is for another site or account; starting fresh", path)
        return 0
    now = time.time()
    loaded = 0
    for c in data.get("cookies", []):
        if c.get("expires") is not None and c["expires"] <= now:
            continue
        domain = c["domain"]
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=domain.startswith("."),
                domain_initial_dot=domain.startswith("."),
                path=c["path"],
                path_specified=True,
                secure=c["secure"],
                expires=c.get("expires"),
                discard=c.get("expires") is None,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": None} if c.get("httponly") else {},
            )
        )
        loaded += 1
    return loaded


# -- parsing helpers ---------------------------------------------------------


def _form_fields(form) -> dict[str, str]:
    return {i.attributes["name"]: i.attributes.get("value") or "" for i in form.css("input[name]")}


def parse_page(url: str, html: str, csrf: str | None = None) -> Page:
    """Parse a full page, or a panel fragment when the parent page's `csrf` is given."""
    query = parse_qs(urlsplit(url).query)
    if csrf is None:
        found = re.search(r"sessionGuidHash='([^']+)'", html)
        if not found:
            raise SkywardError(f"No CSRF token on {url}")
        csrf = found.group(1)
    return Page(
        url=url,
        html=html,
        csrf=csrf,
        p=query.get("p", [""])[0],
        w=query.get("w", [""])[0],
        browses=parse_browse_configs(html),
    )


_BROWSE_START = re.compile(r"browseList\['([^']+)'\]\s*=\s*\{")
_JSON_KEYS = ("data", "queryParameterData")
_SCALAR = re.compile(
    r"""\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|(-?\d+(?:\.\d+)?|true|false|null|undefined))"""
)
_WANTED = (
    "pageModule", "pageObject", "pageScreen", "pageTab", "browseName", "routeModule", "routeObject",
    "dataModule", "dataObject", "queryParameterDataHash", "requestDataHash", "displayName",
    "detailsPanelType", "headerNumber",
)  # fmt: skip


def parse_browse_configs(html: str) -> dict[str, dict]:
    """Pull the fields GetBrowse needs out of each `browseList['id'] = {...}` literal.

    The literals are JavaScript, not JSON (unquoted keys, jQuery calls), so
    rather than parse the whole thing, known keys are located and their values
    decoded: JSON objects for `data`/`queryParameterData`, scalars otherwise.
    """
    configs = {}
    decoder = json.JSONDecoder()
    starts = list(_BROWSE_START.finditer(html))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
        body = html[m.end() : end]
        cfg: dict = {"id": m.group(1)}
        for key in _JSON_KEYS:
            k = re.search(rf"[{{,]\s*{key}\s*:\s*(?=\{{)", body)
            if k:
                try:
                    cfg[key], _ = decoder.raw_decode(body, k.end())
                except ValueError:
                    pass
        for key in _WANTED:
            k = re.search(rf"[{{,]\s*{key}\s*:", body)
            if not k:
                continue
            v = _SCALAR.match(body, k.end())
            if v:
                raw = (
                    v.group(1)
                    if v.group(1) is not None
                    else v.group(2) if v.group(2) is not None else v.group(3)
                )
                cfg[key] = None if raw in ("null", "undefined") else raw
        configs[cfg["id"]] = cfg
    return configs
