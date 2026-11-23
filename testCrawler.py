"""Testy jednostkowe dla crawlera Wikipedii.

Zakładamy, że testowany plik nazywa się `crawler.py` i leży obok tego pliku.
Jeśli nazywa się inaczej, zmień linię `import crawler` poniżej.

Uruchomienie:
    pip install pytest beautifulsoup4 requests ratelimit
    pytest -v test_crawler.py
"""
import types
from unittest import mock

import pytest

import crawler


def make_response(html):
    return types.SimpleNamespace(text=html)


def page(content_html, title="Tytuł strony"):
    return (
        f"<html><head><title>{title}</title></head><body>"
        f'<div id="mw-content-text">{content_html}</div>'
        "</body></html>"
    )


# --------------------------------------------------------------------------
# GetLinksAndTextFromSite
# --------------------------------------------------------------------------
class TestGetLinksAndTextFromSite:
    def test_returns_title_text_and_links(self):
        html = page(
            '<p>Ala ma <a href="https://pl.wikipedia.org/wiki/Kot">kota</a></p>',
            title="Test – Wikipedia",
        )

        links, text, title = crawler.GetLinksAndTextFromSite(make_response(html))

        assert title == "Test – Wikipedia"
        assert text == "Ala ma kota"
        assert links == {"https://pl.wikipedia.org/wiki/Kot"}

    def test_links_are_unique(self):
        html = page(
            '<a href="https://pl.wikipedia.org/wiki/A">1</a>'
            '<a href="https://pl.wikipedia.org/wiki/A">2</a>'
        )

        links, _, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert links == {"https://pl.wikipedia.org/wiki/A"}

    def test_external_links_are_skipped(self):
        html = page('<a href="https://example.com/wiki/A">obce</a>')

        links, _, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert links == set()

    def test_relative_links_are_skipped(self):
        # Dokumentuje obecne zachowanie: warunek 'pl.wikipedia.org' in href
        # odrzuca linki względne ("/wiki/..."), a to one dominują w HTML-u Wikipedii.
        html = page('<a href="/wiki/Warszawa">Warszawa</a>')

        links, _, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert links == set()

    @pytest.mark.parametrize(
        "suffix",
        [
            "#Przypisy",
            "~user",
            "plik.jpg",
            "plik.JPG",
            "plik.png",
            "plik.PNG",
            "Specjalna:Szukaj",
            "?action=edit",
            "&oldid=1",
        ],
    )
    def test_links_with_forbidden_substrings_are_skipped(self, suffix):
        html = page(f'<a href="https://pl.wikipedia.org/wiki/{suffix}">x</a>')

        links, _, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert links == set()

    def test_anchor_without_href_is_ignored(self):
        html = page('<a name="kotwica">bez href</a>')

        links, _, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert links == set()

    def test_script_style_and_edit_section_are_removed_from_text(self):
        html = page(
            "<p>Treść</p>"
            "<script>alert('x')</script>"
            "<style>.a{color:red}</style>"
            '<span class="mw-editsection">[edytuj]</span>'
        )

        _, text, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert "Treść" in text
        assert "alert" not in text
        assert "color" not in text
        assert "edytuj" not in text

    def test_technical_blocks_are_removed(self):
        html = page(
            "<p>Treść</p>"
            '<div class="navbox">NAWIGACJA</div>'
            '<div class="printfooter">STOPKA</div>'
            '<div class="catlinks">KATEGORIE</div>'
            '<ol class="references"><li>REF</li></ol>'
            '<div class="reflist">REFLIST</div>'
        )

        _, text, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert text == "Treść"

    @pytest.mark.parametrize(
        "section_id", ["Przypisy", "Linki_zewnętrzne", "Bibliografia", "Zobacz_też"]
    )
    def test_unwanted_sections_are_removed(self, section_id):
        html = page(
            "<p>Treść główna</p>"
            f'<h2><span id="{section_id}">{section_id}</span></h2>'
            '<ul><li><a href="https://pl.wikipedia.org/wiki/Ukryty">ukryty</a></li></ul>'
            "<p>tekst sekcji końcowej</p>"
        )

        links, text, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert "Treść główna" in text
        assert "tekst sekcji końcowej" not in text
        assert section_id.replace("_", " ") not in text
        assert links == set()

    def test_section_removal_stops_at_next_h2(self):
        html = page(
            "<p>Początek</p>"
            '<h2><span id="Przypisy">Przypisy</span></h2>'
            "<ol><li>przypis</li></ol>"
            '<h2><span id="Inna">Inna sekcja</span></h2>'
            '<p>Zostaje <a href="https://pl.wikipedia.org/wiki/Zostaje">link</a></p>'
        )

        links, text, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert "przypis" not in text
        assert "Inna sekcja" in text
        assert "Zostaje" in text
        assert links == {"https://pl.wikipedia.org/wiki/Zostaje"}

    def test_content_outside_mw_content_text_is_ignored(self):
        html = (
            "<html><head><title>T</title></head><body>"
            "<p>Poza treścią</p>"
            '<div id="mw-content-text"><p>W treści</p></div>'
            "</body></html>"
        )

        _, text, _ = crawler.GetLinksAndTextFromSite(make_response(html))

        assert text == "W treści"

    def test_missing_content_container_raises(self):
        # Dokumentuje obecne zachowanie: brak #mw-content-text kończy się
        # AttributeError (content is None), a nie np. pustym wynikiem.
        html = "<html><head><title>T</title></head><body><p>x</p></body></html>"

        with pytest.raises(AttributeError):
            crawler.GetLinksAndTextFromSite(make_response(html))


# --------------------------------------------------------------------------
# FetchPage
# --------------------------------------------------------------------------
class TestFetchPage:
    def test_returns_response_and_uses_timeout(self):
        fake_session = mock.Mock()
        fake_response = mock.Mock()
        fake_session.get.return_value = fake_response

        with mock.patch.object(crawler, "session", fake_session, create=True):
            result = crawler.FetchPage("https://pl.wikipedia.org/wiki/A")

        assert result is fake_response
        fake_session.get.assert_called_once_with(
            "https://pl.wikipedia.org/wiki/A", timeout=15
        )
        fake_response.raise_for_status.assert_called_once()

    def test_http_error_is_propagated(self):
        fake_session = mock.Mock()
        fake_response = mock.Mock()
        fake_response.raise_for_status.side_effect = crawler.requests.HTTPError("404")
        fake_session.get.return_value = fake_response

        with mock.patch.object(crawler, "session", fake_session, create=True):
            with pytest.raises(crawler.requests.HTTPError):
                crawler.FetchPage("https://pl.wikipedia.org/wiki/Brak")


# --------------------------------------------------------------------------
# CrawlWikipedia
# --------------------------------------------------------------------------
START = "https://pl.wikipedia.org/wiki/Start"
A = "https://pl.wikipedia.org/wiki/A"
B = "https://pl.wikipedia.org/wiki/B"
C = "https://pl.wikipedia.org/wiki/C"


@pytest.fixture
def fake_web():
    """Podmienia FetchPage, GetLinksAndTextFromSite i robots.txt.

    Zwraca słownik `graph`: url -> (zbiór linków, tekst, tytuł) oraz
    listę `fetched` z kolejnością pobrań.
    """
    graph = {}
    fetched = []

    def fake_fetch(link):
        fetched.append(link)
        return link  # "odpowiedzią" jest sam adres

    def fake_parse(response):
        return graph[response]

    rp = mock.Mock()
    rp.can_fetch.return_value = True

    with mock.patch.object(crawler, "FetchPage", side_effect=fake_fetch), \
         mock.patch.object(crawler, "GetLinksAndTextFromSite", side_effect=fake_parse), \
         mock.patch.object(crawler, "rp", rp, create=True):
        yield types.SimpleNamespace(graph=graph, fetched=fetched, rp=rp)


class TestCrawlWikipedia:
    def test_depth_zero_crawls_only_start(self, fake_web):
        fake_web.graph[START] = ({A, B}, "tekst start", "Start")

        result = crawler.CrawlWikipedia(START, 0)

        assert result == {START: ("Start", "tekst start")}
        assert fake_web.fetched == [START]

    def test_depth_one_crawls_neighbours(self, fake_web):
        fake_web.graph[START] = ({A, B}, "s", "Start")
        fake_web.graph[A] = ({C}, "a", "A")
        fake_web.graph[B] = (set(), "b", "B")

        result = crawler.CrawlWikipedia(START, 1)

        assert set(result) == {START, A, B}
        assert C not in result  # głębokość 2 -> poza limitem
        assert result[A] == ("A", "a")

    def test_depth_two_reaches_second_level(self, fake_web):
        fake_web.graph[START] = ({A}, "s", "Start")
        fake_web.graph[A] = ({C}, "a", "A")
        fake_web.graph[C] = (set(), "c", "C")

        result = crawler.CrawlWikipedia(START, 2)

        assert set(result) == {START, A, C}

    def test_pages_are_visited_only_once(self, fake_web):
        # cykl: START -> A -> START, oraz A i B wskazują na to samo C
        fake_web.graph[START] = ({A, B}, "s", "Start")
        fake_web.graph[A] = ({START, C}, "a", "A")
        fake_web.graph[B] = ({C}, "b", "B")
        fake_web.graph[C] = ({START}, "c", "C")

        crawler.CrawlWikipedia(START, 5)

        assert len(fake_web.fetched) == len(set(fake_web.fetched))
        assert set(fake_web.fetched) == {START, A, B, C}

    def test_bfs_order(self, fake_web):
        fake_web.graph[START] = ({A}, "s", "Start")
        fake_web.graph[A] = ({B}, "a", "A")
        fake_web.graph[B] = (set(), "b", "B")

        crawler.CrawlWikipedia(START, 5)

        assert fake_web.fetched == [START, A, B]

    def test_robots_txt_disallow_stops_crawler(self, fake_web, capsys):
        fake_web.rp.can_fetch.return_value = False
        fake_web.graph[START] = (set(), "s", "Start")

        with pytest.raises(SystemExit):
            crawler.CrawlWikipedia(START, 1)

        assert fake_web.fetched == []
        assert "Dostęp zabroniony" in capsys.readouterr().out

    def test_robots_checked_with_user_agent(self, fake_web):
        fake_web.graph[START] = (set(), "s", "Start")

        crawler.CrawlWikipedia(START, 0)

        fake_web.rp.can_fetch.assert_called_with(crawler.USER_AGENT, START)

    def test_prints_titles(self, fake_web, capsys):
        fake_web.graph[START] = (set(), "s", "Tytuł startowy")

        crawler.CrawlWikipedia(START, 0)

        assert "Tytuł startowy" in capsys.readouterr().out


# --------------------------------------------------------------------------
# SaveToFiles
# --------------------------------------------------------------------------
class TestSaveToFiles:
    @pytest.fixture
    def workdir(self, tmp_path, monkeypatch):
        (tmp_path / "Dane").mkdir()
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_creates_file_with_link_and_text(self, workdir):
        data = {START: ("Józef Poniatowski", "Treść artykułu")}

        crawler.SaveToFiles(data)

        path = workdir / "Dane" / "Józef_Poniatowski.txt"
        assert path.exists()
        assert path.read_text(encoding="utf-8") == f"Link: {START}\n\nTreść artykułu"

    def test_filename_removes_en_dash_and_replaces_spaces(self, workdir):
        data = {START: ("Józef Poniatowski – Wikipedia, wolna encyklopedia", "x")}

        crawler.SaveToFiles(data)

        expected = "Józef_Poniatowski__Wikipedia,_wolna_encyklopedia.txt"
        assert (workdir / "Dane" / expected).exists()

    def test_saves_multiple_pages(self, workdir):
        data = {A: ("Strona A", "a"), B: ("Strona B", "b")}

        crawler.SaveToFiles(data)

        assert sorted(p.name for p in (workdir / "Dane").iterdir()) == [
            "Strona_A.txt",
            "Strona_B.txt",
        ]

    def test_empty_data_creates_nothing(self, workdir):
        crawler.SaveToFiles({})

        assert list((workdir / "Dane").iterdir()) == []

    def test_missing_output_directory_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # brak katalogu "Dane"

        with pytest.raises(FileNotFoundError):
            crawler.SaveToFiles({A: ("A", "a")})