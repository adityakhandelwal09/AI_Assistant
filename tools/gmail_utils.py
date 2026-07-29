import re
import html
import unicodedata
from bs4 import BeautifulSoup


USEFUL_URL_DOMAINS = {
    "calendar.google.com",
    "docs.google.com",
    "drive.google.com",
    "meet.google.com",
    "teams.microsoft.com",
    "zoom.us",
    "www.zoom.us",
    "forms.gle",
    "docs.google.com",
    "notion.so",
    "www.notion.so",
}

USEFUL_URL_PATH_HINTS = (
    "/meet/",
    "/document/",
    "/spreadsheets/",
    "/presentation/",
    "/file/",
    "/calendar/",
    "/j/",
    "/wc/",
    "/join",
    "/invitation",
    "/event",
)

def strip_signature_and_disclaimers(email_text):
    """
    Removes common email signatures, disclaimers, and footer boilerplate.
    """
    # Common signature delimiters
    signature_markers = [
        r"--\s*\n",  # standard email signature delimiter "-- "
        r"Sent from my iPhone",
        r"Sent from my Android",
        r"Get Outlook for",
        r"This email and any attachments",
        r"CONFIDENTIALITY NOTICE",
        r"This message contains confidential",
        r"For your security and privacy, please do not reply to this email",
        r"To stop receiving account service communications by email",
        r"Fidelity Brokerage Services LLC",
        r"EMAIL REF#",
        r"All rights reserved",
    ]
    
    text = email_text
    for marker in signature_markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]  #cut off everything from the marker onward
    
    return text.strip()

def compact_url(url):
    """Reduce a URL to a shorter, readable form when possible."""
    match = re.match(r"https?://([^/\s<>)\]]+)(/[^\s<>)\]]*)?", url)
    if not match:
        return url

    domain = match.group(1)
    path = (match.group(2) or "").rstrip("/")

    if path and len(path) <= 32:
        return f"{domain}{path}"

    return domain

def is_useful_url(url):
    """Return True for URLs that are likely useful in retrieval."""
    match = re.match(r"https?://([^/\s<>)\]]+)(/[^\s<>)\]]*)?", url)
    if not match:
        return False

    domain = match.group(1).lower()
    path = (match.group(2) or "").lower()

    if domain in USEFUL_URL_DOMAINS:
        return True

    return any(hint in path for hint in USEFUL_URL_PATH_HINTS)

def normalize_url_token(url):
    """Keep a URL only if it passes the usefulness filter."""
    if is_useful_url(url):
        return compact_url(url)
    return ""

def normalize_email_text(email_text):
    """Normalize email text by removing invisible junk, duplicates, and noise."""
    if not email_text:
        return ""

    text = unicodedata.normalize("NFKC", email_text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\u034f\u200b-\u200f\u2060\ufeff]", "", text)
    text = re.sub(r"\n\s*\(R\)\s*\n", " (R) ", text)
    text = re.sub(r"\(R\)(?=[A-Za-z])", "(R) ", text)
    text = re.sub(r"https?://[^\s<>)\]]+", lambda match: normalize_url_token(match.group(0)), text)
    text = re.sub(r"\s{2,}", " ", text)

    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]

    collapsed_lines = []
    previous_line = None
    for line in lines:
        if not line:
            continue

        if line == previous_line:
            continue

        line = re.sub(r"\s{2,}", " ", line).strip()
        if not line:
            continue

        collapsed_lines.append(line)
        previous_line = line

    return "\n".join(collapsed_lines).strip()

def html_to_clean_text(html_content):
    # Converts HTML email content to readable text while preserving useful links.
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove non-content elements entirely.
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    # Keep visible anchor text and only preserve useful link targets.
    for anchor in soup.find_all("a"):
        anchor_text = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "")

        if href and is_useful_url(href):
            if anchor_text and anchor_text.lower() not in {href.lower(), "here", "click here"}:
                replacement = f"{anchor_text} ({compact_url(href)})"
            else:
                replacement = compact_url(href)
        else:
            replacement = anchor_text

        anchor.replace_with(replacement)
    
    text = soup.get_text(separator="\n", strip=True)
    return normalize_email_text(text)

def looks_like_html(text):
    """Check if text contains HTML markup, regardless of its declared MIME type"""
    html_indicators = re.search(
        r"</?\s*(?:html|head|body|div|table|tr|td|style|script|meta|a|p|br|span|sup|sub|img|ul|ol|li|strong|em|blockquote)\b",
        text,
        re.IGNORECASE,
    )
    return html_indicators is not None