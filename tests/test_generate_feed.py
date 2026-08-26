import unittest
import xml.etree.ElementTree as ET

from generate_feed import build_rss, extract_events, looks_like_event_date


SAMPLE_HTML = """
<html><body>
<h3><a href="/historico">Histórico 2025</a></h3>
<h3>11 Sept</h3>
<p><a href="/img.jpg"><img src="/img.jpg" alt="cartel"></a></p>
<p><a href="/evento-1">Encuentros PCA con Germán Bernácer</a></p>
<h3>7-8 Oct</h3>
<p><a href="/imagen"><img src="x" alt="Summit futuro"></a></p>
<p><a href="https://example.org/summit">Alicante Futura Summit 2026</a></p>
<h3>10&amp;15 Abr</h3>
<p><a href="/talleres">Talleres técnicos IA y desarrollo software</a></p>
<h3>29 Ene - 5 Feb</h3>
<p><a href="/letsgrow">Formaciones del programa europeo LETSGROW</a></p>
<h3>Última actualización</h3>
</body></html>
"""


class TestAgendaParser(unittest.TestCase):
    def test_date_formats(self):
        for value in ("11 Sept", "7-8 Oct", "15-23 Jul", "10&15 Abr", "29 Ene - 5 Feb"):
            self.assertTrue(looks_like_event_date(value), value)
        self.assertFalse(looks_like_event_date("Histórico 2025"))

    def test_extract_events_skips_image_links(self):
        events = extract_events(SAMPLE_HTML, "https://pca.ua.es/base/page.html")
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0]["title"], "Encuentros PCA con Germán Bernácer")
        self.assertEqual(events[0]["url"], "https://pca.ua.es/evento-1")
        self.assertEqual(events[1]["url"], "https://example.org/summit")
        self.assertEqual(events[3]["date"], "29 Ene - 5 Feb")

    def test_rss_is_valid_xml_and_has_stable_guids(self):
        events = extract_events(SAMPLE_HTML, "https://pca.ua.es/base/page.html")
        xml_bytes = build_rss(events, "https://pca.ua.es/base/page.html")
        root = ET.fromstring(xml_bytes)
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 4)
        self.assertTrue(items[0].findtext("guid").startswith("urn:sha256:"))
        self.assertIsNone(items[0].find("pubDate"))


if __name__ == "__main__":
    unittest.main()
