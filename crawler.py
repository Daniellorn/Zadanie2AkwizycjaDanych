from bs4 import BeautifulSoup
from ratelimit import limits, sleep_and_retry
import requests
import urllib.robotparser
import sys
from collections import deque
import string
import os


USER_AGENT = "MyCrawler Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0"
ROBOT_FILE_URL = "https://pl.wikipedia.org/robots.txt"
START_URL = "https://pl.wikipedia.org/wiki/J%C3%B3zef_Poniatowski"
BASE_URL= "https://pl.wikipedia.org"

SKIP_SUBSTR = ['#', '~', 'jpg', 'JPG', 'png', 'PNG', 'Specjalna', '?', '&']

CALLS_LIMIT = 5
PERIOD_SECONDS = 1

#AI
def GetLinksAndTextFromSite(response):
    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup.select(
        "script, style, nav, footer, header, .mw-editsection"
    ):
        element.decompose()

    content = soup.select_one("#mw-content-text")

    if content:
            # 1. Usuwanie sekcji końcowych (Przypisy, Linki zewnętrzne, Bibliografia, Zobacz też)
            unwanted_sections = ["Przypisy", "Linki_zewnętrzne", "Bibliografia", "Zobacz_też"]
            for section_id in unwanted_sections:
                header = content.find(id=section_id)
                if header:
                    heading_tag = header.find_parent(["h2", "h3", "h4"])
                    if heading_tag:
                        # Usuwamy nagłówek i wszystkie kolejne elementy aż do napotkania kolejnego nagłówka h2
                        for sibling in list(heading_tag.find_next_siblings()):
                            if sibling.name == "h2":
                                break
                            sibling.decompose()
                        heading_tag.decompose()
    
            # 2. Usuwanie dodatkowych bloków technicznych i nawigacyjnych na dole
            for unwanted in content.select(".navbox, .printfooter, .catlinks, .references, .reflist"):
                unwanted.decompose()
            text = content.get_text(separator=" ", strip=True)

    unique_links = set()
    for link in content.find_all('a', href=True):
        href = link.get('href')

        if 'pl.wikipedia.org' not in href:
            continue
        if any(substr in href for substr in SKIP_SUBSTR):
            continue
        unique_links.add(href)

    return unique_links, text, soup.title.string

@sleep_and_retry
@limits(calls=CALLS_LIMIT, period=PERIOD_SECONDS)
def FetchPage(link):
    response = session.get(link, timeout=15)
    response.raise_for_status()
    return response

def CrawlWikipedia(start_url, max_depth):
    visited = set()
    q = deque([(start_url, 0)])

    visited.add(start_url)

    crawled_data = {}

    depth = 0

    while q:
        link, depth = q.popleft()

        if not rp.can_fetch(USER_AGENT, link):
            print("Dostęp zabroniony")
            raise SystemExit

        response = FetchPage(link)

        links, text, title = GetLinksAndTextFromSite(response)

        crawled_data[link] = (title, text)

        print(title)

        if depth < max_depth:
            for link in links:
                if link not in visited:
                    q.append((link, depth + 1))
                    visited.add(link)

    return crawled_data

def SaveToFiles(crawled_data):

    #for i, (title, text) in enumerate(crawled_data.items()):
    for link, (title, text) in crawled_data.items():
        filename = title.replace('–', '').replace(' ', '_') + '.txt'

        with open(os.path.join("Dane", filename), "w", encoding="utf-8") as f:
            f.write(f'Link: {link}\n\n')
            f.write(text)


if __name__ == "__main__":
    session = requests.Session()
    session.headers.update({
        "user-agent": USER_AGENT
    })
    
    response = session.get(ROBOT_FILE_URL, timeout=15)
    response.raise_for_status()

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(response.text.splitlines())


    print("Podaj maksymalną głębokość (maks 5)")
    max_depth = int(input())

    crawler_result = CrawlWikipedia(START_URL, max_depth)
    SaveToFiles(crawler_result)