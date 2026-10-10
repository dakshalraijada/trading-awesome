"""Offline content policy: URL hygiene and text rules.

These checks need no network access, so they run on every entry in CI and on
every submission before anything is fetched.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")

SHORTENER_HOSTS = {
    "bit.ly", "bitly.com", "buff.ly", "cutt.ly", "goo.gl", "is.gd", "linktr.ee",
    "lnkd.in", "ow.ly", "rb.gy", "rebrand.ly", "shorturl.at", "t.co", "t.ly",
    "tiny.cc", "tinyurl.com", "trib.al", "v.gd", "s.id", "short.io", "bl.ink",
}

# Query parameters that carry tracking, affiliate or referral identifiers.
TRACKING_PARAM_RE = re.compile(
    r"^(utm_\w+|ref|ref_?id|ref_?code|referral(_?code)?|referrer|aff(_?id)?|affiliate(_?id)?|"
    r"via|invite(_?code)?|inviter(_?id)?|partner(_?id)?|promo(_?code)?|coupon|fbclid|gclid|"
    r"dclid|msclkid|yclid|twclid|ttclid|mc_cid|mc_eid|_hsenc|_hsmi|irclickid|clickid|subid|"
    r"campaign(_?id)?)$",
    re.IGNORECASE,
)
REFERRAL_PATH_RE = re.compile(r"/(ref|referral|referrals|invite|aff|affiliate|affiliates|join/[A-Za-z0-9]{4,})(/|$)", re.I)

# Bidirectional overrides and zero-width characters can disguise text or URLs.
HIDDEN_CHARS_RE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")

PROMO_WORDS_RE = re.compile(
    r"\b(best|#1|number one|leading|revolutionary|guaranteed|guarantee|risk[- ]free|100x|"
    r"ultimate|world'?s first|game[- ]chang\w*|cutting[- ]edge|unmatched|unrivall?ed|"
    r"unbeatable|insane|moon|lambo|passive income|get rich)\b",
    re.IGNORECASE,
)

# Multi-label public suffixes we care about; anything else uses the last two labels.
MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "co.jp", "co.kr",
    "com.br", "com.cn", "com.hk", "com.sg", "co.in", "co.nz", "com.tr", "com.mx",
    "co.za", "com.tw",
}
# Hosting suffixes where every subdomain belongs to a different owner, plus umbrella
# foundations whose subdomains are separate projects.
PRIVATE_SUFFIXES = {
    "github.io", "gitbook.io", "readthedocs.io", "vercel.app", "netlify.app",
    "pages.dev", "herokuapp.com", "web.app", "firebaseapp.com", "substack.com",
    "notion.site", "webflow.io", "framer.website", "apache.org",
}
# Hosts where the owner/project lives in the path rather than in the hostname.
CODE_HOSTS = {"github.com", "gitlab.com", "bitbucket.org", "huggingface.co", "codeberg.org"}


def registrable_domain(host: str) -> str:
    host = host.lower().rstrip(".")
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in MULTI_LABEL_SUFFIXES or last_two in PRIVATE_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def identity_key(url: str) -> str:
    """Key used to detect duplicate listings: domain, or owner/repo on code hosts."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    domain = registrable_domain(host)
    if domain in CODE_HOSTS:
        segments = [s for s in parts.path.split("/") if s][:2]
        return f"{domain}/{'/'.join(segments).lower()}"
    return domain


def url_problems(url: str) -> list[str]:
    """Return policy violations for a single URL (empty list when it is fine)."""
    problems: list[str] = []
    if HIDDEN_CHARS_RE.search(url):
        return ["contains hidden or bidirectional Unicode characters"]
    if any(ch.isspace() for ch in url):
        return ["contains whitespace"]
    parts = urlsplit(url)
    if parts.scheme != "https":
        problems.append("must use https://")
    host = parts.hostname or ""
    if not host:
        return problems + ["has no hostname"]
    if parts.username or parts.password:
        problems.append("must not contain credentials")
    if parts.port not in (None, 443):
        problems.append("must not use a custom port")
    if not host.isascii() or any(label.startswith("xn--") for label in host.split(".")):
        problems.append("internationalized (punycode) hostnames are not accepted")
    try:
        ipaddress.ip_address(host)
        problems.append("must use a hostname, not an IP address")
    except ValueError:
        pass
    if "." not in host:
        problems.append("hostname must be a public domain")
    if registrable_domain(host) in SHORTENER_HOSTS or host in SHORTENER_HOSTS:
        problems.append("URL shorteners are not accepted; use the final destination URL")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if TRACKING_PARAM_RE.match(key):
            problems.append(f"remove the tracking/referral parameter `{key}`")
    if REFERRAL_PATH_RE.search(parts.path):
        problems.append("referral or invite links are not accepted")
    return problems


def links_in(text: str) -> list[tuple[str, str]]:
    return LINK_RE.findall(text or "")


def text_problems(text: str, *, allow_links: bool, max_length: int | None = None) -> list[str]:
    """Structural rules for any text that ends up in a README table cell."""
    problems: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["must not be empty"]
    if HIDDEN_CHARS_RE.search(text):
        problems.append("contains hidden or bidirectional Unicode characters")
    if "\n" in text or "\r" in text:
        problems.append("must be a single line")
    if "|" in text:
        problems.append("must not contain the `|` character (it breaks the table)")
    if re.search(r"<[a-zA-Z/!]", text):
        problems.append("must not contain HTML")
    if "![" in text:
        problems.append("must not contain images")
    if text.count("[") != text.count("]") or text.count("(") != text.count(")"):
        problems.append("has unbalanced brackets")
    links = links_in(text)
    if links and not allow_links:
        problems.append("must not contain links (they are added from the dedicated URL fields)")
    for label, target in links:
        if not label.strip():
            problems.append(f"link to {target} has empty text")
        for problem in url_problems(target):
            problems.append(f"link {target} {problem}")
    if re.search(r"(?<!\()https?://", LINK_RE.sub("", text)):
        problems.append("contains a bare URL; use [text](url)")
    if max_length is not None and len(text) > max_length:
        problems.append(f"is {len(text)} characters long (maximum {max_length})")
    return problems


def style_problems(description: str) -> list[str]:
    """Editorial rules applied to new or changed descriptions."""
    problems: list[str] = []
    if not description.rstrip().endswith("."):
        problems.append("description must be one sentence ending with a period")
    match = PROMO_WORDS_RE.search(description)
    if match:
        problems.append(f"description uses promotional wording (`{match.group(0)}`); keep it factual")
    if re.search(r"[!?]", description):
        problems.append("description must not contain `!` or `?`")
    if sum(1 for ch in description if ch.isupper()) > max(12, len(description) // 3):
        problems.append("description uses too many capital letters")
    return problems
