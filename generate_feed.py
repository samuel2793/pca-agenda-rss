#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import mimetypes
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCE_URL = os.getenv(
    "PCA_AGENDA_URL",
    "https://pca.ua.es/es/agenda/2025/agenda-2026.html",
)
EVENT_YEAR = int(os.getenv("PCA_AGENDA_YEAR", "2026"))
FEED_TITLE = os.getenv("RSS_TITLE", "Agenda PCA Alicante 2026")
FEED_DESCRIPTION = os.getenv(
    "RSS_DESCRIPTION",
    "Eventos publicados en la Agenda 2026 del Parque Científico de Alicante.",
)
FEED_URL = os.getenv("RSS_FEED_URL", "").strip()

MEDIA_NS = "http://search.yahoo.com/mrss/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

MONTH_RE = re.compile(
    r"\b(?:ene(?:ro)?|feb(?:rero)?|mar(?:zo)?|abr(?:il)?|may(?:o)?|jun(?:io)?|"
    r"jul(?:io)?|ago(?:sto)?|sep(?:t(?:iembre)?)?|sept(?:iembre)?|oct(?:ubre)?|"
    r"nov(?:iembre)?|dic(?:iembre)?)\b",
    re.IGNORECASE,
)
DATE_START_RE = re.compile(r"^\s*\d{1,2}\b")
HEADING_NAMES = {"h2", "h3", "h4"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def looks_like_event_date(text: str) -> bool:
    text = normalize_space(text)
    return bool(DATE_START_RE.search(text) and MONTH_RE.search(text))


def fetch_source(url: str) -> bytes:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": (
                "pca-agenda-rss/1.1 (+GitHub Pages RSS generator; "
                "contact via repository issues)"
            )
        }
    )
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _image_url_from_tag(tag: Tag, source_url: str) -> str | None:
    """Return a usable image URL from an <img> tag, if present."""
    for attr in ("src", "data-src", "data-lazy-src", "data-original"):
        value = (tag.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return urljoin(source_url, value)

    srcset = (tag.get("srcset") or "").strip()
    if srcset:
        # Pick the last candidate, which is commonly the largest one.
        candidates = [part.strip().split()[0] for part in srcset.split(",") if part.strip()]
        if candidates:
            return urljoin(source_url, candidates[-1])
    return None


def _looks_like_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _event_data_after_heading(heading: Tag, source_url: str) -> dict[str, str] | None:
    """Find event link and its preceding image, stopping at the next heading."""
    image_url: str | None = None
    node = heading.find_next()

    while node is not None:
        if isinstance(node, Tag):
            if node is not heading and node.name in HEADING_NAMES:
                return None

            if node.name == "img" and image_url is None:
                image_url = _image_url_from_tag(node, source_url)

            if node.name == "a":
                href = (node.get("href") or "").strip()
                title = normalize_space(node.get_text(" ", strip=True))

                # Some PCA images are wrapped in a link pointing directly to the image.
                if image_url is None and href:
                    nested_img = node.find("img")
                    if nested_img is not None:
                        image_url = _image_url_from_tag(nested_img, source_url)
                    elif _looks_like_image_url(urljoin(source_url, href)) and not title:
                        image_url = urljoin(source_url, href)

                # Image-only anchors have no text and are intentionally skipped as event links.
                if href and title and not title.lower().startswith("histórico"):
                    event = {"title": title, "url": urljoin(source_url, href)}
                    if image_url:
                        event["image"] = image_url
                    return event

        node = node.find_next()
    return None


def extract_events(document: str | bytes, source_url: str = SOURCE_URL) -> list[dict[str, str]]:
    soup = BeautifulSoup(document, "html.parser")
    events: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for heading in soup.find_all(list(HEADING_NAMES)):
        date_text = normalize_space(heading.get_text(" ", strip=True))
        if not looks_like_event_date(date_text):
            continue

        found = _event_data_after_heading(heading, source_url)
        if not found:
            continue

        title = found["title"]
        url = found["url"]
        key = (date_text.casefold(), title.casefold(), url)
        if key in seen:
            continue
        seen.add(key)

        event = {"date": date_text, "title": title, "url": url}
        if found.get("image"):
            event["image"] = found["image"]
        events.append(event)

    return events


def stable_guid(event: dict[str, str]) -> str:
    raw = f"{EVENT_YEAR}\n{event['date']}\n{event['title']}\n{event['url']}".encode("utf-8")
    return "urn:sha256:" + hashlib.sha256(raw).hexdigest()


def image_mime_type(url: str) -> str:
    guessed, _ = mimetypes.guess_type(urlparse(url).path)
    return guessed or "image/jpeg"


def event_html(event: dict[str, str]) -> str:
    title = html_lib.escape(event["title"], quote=True)
    url = html_lib.escape(event["url"], quote=True)
    date = html_lib.escape(event["date"], quote=True)
    parts: list[str] = []

    image = event.get("image")
    if image:
        image_escaped = html_lib.escape(image, quote=True)
        parts.append(
            f'<p><a href="{url}"><img src="{image_escaped}" alt="{title}" '
            'style="max-width:100%;height:auto"></a></p>'
        )

    parts.append(f"<p><strong>Fecha del evento:</strong> {date} de {EVENT_YEAR}.</p>")
    parts.append(f'<p><a href="{url}">Ver evento en la web del PCA</a></p>')
    return "".join(parts)


def indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "
        for child in element:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    if level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def build_rss(events: list[dict[str, str]], source_url: str = SOURCE_URL) -> bytes:
    if not events:
        raise ValueError("No se encontraron eventos; se cancela para no publicar un feed vacío.")

    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("media", MEDIA_NS)
    ET.register_namespace("content", CONTENT_NS)

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = source_url
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "language").text = "es-es"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    if FEED_URL:
        ET.SubElement(
            channel,
            "{http://www.w3.org/2005/Atom}link",
            {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
        )

    for event in events:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = event["title"]
        ET.SubElement(item, "link").text = event["url"]
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = stable_guid(event)

        html_content = event_html(event)
        ET.SubElement(item, "description").text = html_content
        ET.SubElement(item, f"{{{CONTENT_NS}}}encoded").text = html_content

        image = event.get("image")
        if image:
            media_type = image_mime_type(image)
            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}content",
                {"url": image, "medium": "image", "type": media_type},
            )
            ET.SubElement(item, f"{{{MEDIA_NS}}}thumbnail", {"url": image})

        ET.SubElement(item, "category").text = "Agenda PCA"
        source = ET.SubElement(item, "source", {"url": source_url})
        source.text = "Agenda PCA 2026"

    indent_xml(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def build_index(event_count: int, image_count: int, source_url: str = SOURCE_URL) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source = html_lib.escape(source_url, quote=True)
    return f"""<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>{html_lib.escape(FEED_TITLE)}</title>
  <link rel=\"alternate\" type=\"application/rss+xml\" title=\"{html_lib.escape(FEED_TITLE)}\" href=\"feed.xml\">
  <style>
    body {{ font: 16px/1.55 system-ui, sans-serif; max-width: 760px; margin: 4rem auto; padding: 0 1.25rem; }}
    code {{ background: #f3f4f6; padding: .15rem .35rem; border-radius: .3rem; }}
  </style>
</head>
<body>
  <h1>{html_lib.escape(FEED_TITLE)}</h1>
  <p>Feed RSS generado automáticamente desde la agenda pública del PCA.</p>
  <p><a href=\"feed.xml\">Abrir feed.xml</a> · <a href=\"{source}\">Ver agenda original</a></p>
  <p>Eventos detectados: <strong>{event_count}</strong>. Eventos con imagen: <strong>{image_count}</strong>.</p>
  <p>Última generación: <code>{generated}</code>.</p>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un RSS 2.0 a partir de la Agenda PCA 2026.")
    parser.add_argument("--url", default=SOURCE_URL, help="URL de la agenda fuente")
    parser.add_argument("--output", default="site/feed.xml", help="Ruta de salida del RSS")
    parser.add_argument("--index", default="site/index.html", help="Ruta de la página índice")
    args = parser.parse_args()

    document = fetch_source(args.url)
    events = extract_events(document, args.url)
    if not events:
        raise SystemExit("ERROR: no se detectaron eventos; no se desplegará un feed vacío.")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_rss(events, args.url))

    image_count = sum(1 for event in events if event.get("image"))
    index_path = Path(args.index)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(build_index(len(events), image_count, args.url), encoding="utf-8")
    (index_path.parent / ".nojekyll").touch()

    print(f"OK: {len(events)} eventos ({image_count} con imagen) -> {output_path}")
    for event in events[:5]:
        suffix = f" | imagen: {event['image']}" if event.get("image") else " | sin imagen"
        print(f" - {event['date']}: {event['title']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
