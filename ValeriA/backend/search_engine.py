"""
Interroge le moteur de recherche (SearXNG par defaut) puis recupere
le contenu des pages trouvees EN PARALLELE, avec repli automatique sur
le snippet si le scraping d'une page echoue. Inclut un cache court pour
eviter de re-chercher/re-scraper une question quasi identique posee
juste apres.
"""
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_CACHE: dict[str, tuple[float, list]] = {}
_CACHE_TTL_SECONDS = 180  # 3 minutes


def _cache_key(query: str, settings: dict) -> str:
    return "|".join([
        query.strip().lower(),
        settings.get("searxng_url", ""),
        str(settings.get("num_sources", "")),
        settings.get("scrape_mode", ""),
        settings.get("search_category", "general"),
    ])


def query_search_engine(query: str, base_url: str, num_results: int, category: str = "general") -> list[dict]:
    """Interroge SearXNG (ou tout moteur compatible format=json) et renvoie
    une liste de resultats bruts {title, url, snippet}."""
    try:
        params = {"q": query, "format": "json"}
        if category and category != "general":
            params["categories"] = category
        resp = requests.get(
            base_url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Impossible d'interroger le moteur de recherche : {e}")

    results = []
    for r in data.get("results", [])[:num_results]:
        results.append(
            {
                "title": r.get("title") or r.get("url", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "") or "",
            }
        )
    return results


def scrape_page(url: str, timeout: int, max_chars: int) -> str | None:
    """Recupere et nettoie le texte d'une page. Renvoie None en cas d'echec."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())  # normalise les espaces
        if not text:
            return None
        return text[:max_chars]
    except Exception:
        return None


def _scrape_one(r: dict, scrape_mode: str, timeout: int, max_chars: int) -> dict:
    title, url, snippet = r["title"], r["url"], r["snippet"]

    if scrape_mode == "snippet_only":
        return {"title": title, "url": url, "content": snippet, "method": "snippet"}

    scraped = scrape_page(url, timeout, max_chars)

    if scraped:
        return {"title": title, "url": url, "content": scraped, "method": "scraped"}
    elif scrape_mode == "hybrid":
        if snippet:
            return {"title": title, "url": url, "content": snippet, "method": "snippet"}
        return {"title": title, "url": url, "content": "", "method": "failed"}
    else:  # full_scrape strict, pas de fallback
        return {"title": title, "url": url, "content": "", "method": "failed"}


def build_search_context(query: str, settings: dict, use_cache: bool = True) -> list[dict]:
    """
    Retourne une liste de sources enrichies :
    {title, url, content, method: 'scraped' | 'snippet' | 'failed'}

    Le scraping des pages se fait EN PARALLELE (jusqu'a 8 threads) pour
    reduire fortement le temps d'attente par rapport a un scraping
    sequentiel. Un cache memoire de 3 minutes evite de refaire tout le
    travail si la meme question (ou une tres proche) est reposee juste
    apres.
    """
    if use_cache:
        key = _cache_key(query, settings)
        cached = _CACHE.get(key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

    base_url = settings.get("searxng_url", "http://localhost:8081/search")
    num_results = int(settings.get("num_sources", 10))
    scrape_mode = settings.get("scrape_mode", "hybrid")
    timeout = int(settings.get("scrape_timeout", 8))
    max_chars = int(settings.get("max_chars_per_page", 4000))
    category = settings.get("search_category", "general")

    raw_results = query_search_engine(query, base_url, num_results, category)

    if scrape_mode == "snippet_only":
        enriched = [_scrape_one(r, scrape_mode, timeout, max_chars) for r in raw_results]
    else:
        enriched = [None] * len(raw_results)
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(raw_results)))) as executor:
            future_to_idx = {
                executor.submit(_scrape_one, r, scrape_mode, timeout, max_chars): i
                for i, r in enumerate(raw_results)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                enriched[idx] = future.result()

    if use_cache:
        _CACHE[_cache_key(query, settings)] = (time.time(), enriched)

    return enriched
