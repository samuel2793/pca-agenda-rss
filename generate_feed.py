#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
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

MONTH_RE = re.compile(
    r"\b(?:ene(?:ro)?|feb(?:rero)?|mar(?:zo)?|abr(?:il)?|may(?:o)?|jun(?:io)?|"
    r"jul(?:io)?|ago(?:sto)?|sep(?:t(?:iembre)?)?|sept(?:iembre)?|oct(?:ubre)?|"
    r"nov(?:iembre)?|dic(?:iembre)?)\b",
    re.IGNORECASE,
)
DATE_START_RE = re.compile(r"^\s*\d{1,2}\b")
HEADING_NAMES = {"h2", "h3", "h4"}


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
                "pca-agenda-rss/1.0 (+GitHub Pages RSS generator; "
                "contact via repository issues)"
            )
        }
    )
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _next_event_link(heading: Tag, source_url: str) -> tuple[str, str] | None:
    """Find the first meaningful anchor after a date heading, before the next heading."""
    node = heading.find_next()
    while node is not None:
        if isinstance(node, Tag):
            if node is not heading and node.name in HEADING_NAMES:
                return None
            if node.name == "a":
                href = (node.get("href") or "").strip()
                title = normalize_space(node.get_text(" ", strip=True))
                # Image-only anchors have no textual content via get_text(), so they are skipped.
                if href and title and not title.lower().startswith("histórico"):
                    return title, urljoin(source_url, href)
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

        found = _next_event_link(heading, source_url)
        if not found:
            continue

        title, url = found
        key = (date_text.casefold(), title.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": date_text, "title": title, "url": url})

    return events


def stable_guid(event: dict[str, str]) -> str:
    raw = f"{EVENT_YEAR}\n{event['date']}\n{event['title']}\n{event['url']}".encode("utf-8")
    return "urn:sha256:" + hashlib.sha256(raw).hexdigest()


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
        ET.SubElement(item, "description").text = (
            f"Fecha del evento: {event['date']} de {EVENT_YEAR}. "
            "Fuente: Agenda PCA."
        )
        ET.SubElement(item, "category").text = "Agenda PCA"
        source = ET.SubElement(item, "source", {"url": source_url})
        source.text = "Agenda PCA 2026"

    indent_xml(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def build_index(event_count: int, source_url: str = SOURCE_URL) -> str:
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
  <p>Eventos detectados: <strong>{event_count}</strong>.</p>
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

    index_path = Path(args.index)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(build_index(len(events), args.url), encoding="utf-8")
    (index_path.parent / ".nojekyll").touch()

    print(f"OK: {len(events)} eventos -> {output_path}")
    for event in events[:5]:
        print(f" - {event['date']}: {event['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
