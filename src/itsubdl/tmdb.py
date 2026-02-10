import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from rich import print
from simplejustwatchapi.justwatch import details, search

from itsubdl.config_manager import get_tmdb_api_key
from itsubdl.tmdbmovie import TMDBMovie

# match tv.apple.com movie URLs
ATV_URL_REGEX = re.compile(
    r"(?i)(?P<base_url>https?://tv\.apple\.com/"
    r"(?:(?P<country_code>[a-z]{2})/)?"
    r"(?P<media_type>movie|episode|season|show)/"
    r"(?:(?P<media_name>[^/]+)/)?"
    r"(?P<media_id>umc\.cmc\.[a-z\d]{20,34}))"
    r"(?:\?(?P<url_params>.*))?"
)


def search_tmdb_movie(title: str, year: int | None = None) -> TMDBMovie | None:
    """
    Search TMDB by title and year to find the best matching movie.
    Returns a full TMDBMovie object if a good match is found.
    """
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": get_tmdb_api_key(),
        "query": title,
    }
    if year:
        params["year"] = year

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])

        if not results:
            return None

        # use the first result as the best match
        best_match = results[0]
        movie_id = best_match.get("id")

        if not movie_id:
            return None

        # fetch full movie details using the matched id
        return get_tmdbmovie(str(movie_id))

    except Exception as e:
        print(f"[red][TMDB][/red] Error searching for movie: {e}")
        return None


def get_tmdbmovie(movie_id: str) -> TMDBMovie | None:
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    alternative_titles_url = f"https://api.themoviedb.org/3/movie/{movie_id}/alternative_titles"
    params = {"api_key": get_tmdb_api_key()}

    def fetch_with_retry(url, params, timeout=5, retries=1):
        """Fetch URL with retry"""
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, params=params, timeout=timeout)
                r.raise_for_status()
                return r
             except Exception:
                 if attempt == retries:
                     raise

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_main = executor.submit(fetch_with_retry, url, params)
            future_alt = executor.submit(fetch_with_retry, alternative_titles_url, params)

            # Get results
            r_main = future_main.result()
            r_alt = future_alt.result()

        # get main movie info
        j = r_main.json()

        imdb_id = j.get("imdb_id") or None
        title = j.get("title") or None
        original_title = j.get("original_title") or None
        duration = j.get("runtime") or None
        if duration:
            duration = duration * 60  # convert duration to seconds

        # Extract year from release date
        release_date = j.get("release_date") or j.get("first_air_date") or None
        year = None
        if release_date:
            match = re.match(r"(\d{4})", release_date)
            if match:
                year = int(match.group(1))

        # Get alternative titles
        j = r_alt.json()

        alternative_titles = []

        for t in j.get("titles", []):
            alt_title = t.get("title")
            if not alt_title:
                continue

            region = t.get("iso_3166_1").lower()
            alternative_titles.append(
                {
                    "region": region,
                    "title": alt_title,
                }
            )
        regions = get_apple_tv_regions(movie_id)
        # move us, gb, ca to the front
        priority = ["us", "gb", "ca", "au"]
        sorted_regions = {}

        # reorder dictionary based on priority
        for p in priority:
            for k, v in regions.items():
                if k.lower() == p and k not in sorted_regions:
                    sorted_regions[k] = v

        # then, add the rest
        for k, v in regions.items():
            if k not in sorted_regions:
                sorted_regions[k] = v

        return TMDBMovie(
            id=movie_id,
            imdb_id=imdb_id,
            title=title,
            original_title=original_title,
            alternative_titles=alternative_titles,
            year=year,
            duration=duration,
            regions=list(sorted_regions.keys()),
            watch_links=list(sorted_regions.values()),
        )

    except Exception:
        return None


def get_apple_tv_regions(tmdb_id: str) -> dict:
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
    params = {"api_key": get_tmdb_api_key()}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", {})

        found_regions = {}

        for region_code, info in results.items():
            buy_list = info.get("buy", [])
            rent_list = info.get("rent", [])

            for item in buy_list + rent_list:
                if "apple tv" in item.get("provider_name").lower():
                    found_regions[region_code.lower()] = info.get("link")
                    break

        return found_regions
    except Exception as e:
        print(f"[yellow][TMDB][/yellow] Error getting watch/providers for ID [orange1]{tmdb_id}[/orange1]: {e}")
        return {}


def get_justwatch_node_id(movie: TMDBMovie, country: str) -> str | None:
    """
    Search JustWatch for the movie and get its node ID
    Uses title and year to find the correct entry
    """
    if not movie.title:
        return None

    try:
        # search with title and country
        results = search(movie.title, country.upper(), "en", count=100, best_only=False)

        if not results:
            return None

        for entry in results:
            # check TMDB ID and IMDB ID if available
            tmdb_match = entry.tmdb_id == str(movie.id) if entry.tmdb_id else False
            imdb_match = entry.imdb_id == str(movie.imdb_id) if entry.imdb_id else False
            if tmdb_match or imdb_match:
                return entry.entry_id

    except Exception as e:
        print(f"[red][JUSTWATCH][/red] Error searching for movie in {country}: {e}")

    return None


def get_apple_tv_url_from_justwatch(node_id: str, country: str) -> str | None:
    """
    Get Apple TV URL from JustWatch for given node ID and country
    Returns the Apple TV URL if found
    """
    if not node_id or not country:
        return None

    try:
        # get full details for this country which includes offers with URLs
        entry = details(node_id, country.upper(), "en", best_only=True)

        if not entry or not entry.offers:
            return None

        # look through offers for Apple TV
        for offer in entry.offers:
            # check if this is an Apple TV offer
            offer_url = offer.url
            if offer_url and ("tv.apple.com" in offer_url.lower() or "itunes.apple.com" in offer_url.lower()):
                atv_url = offer_url.split("?")[0]
                atv_url_match = ATV_URL_REGEX.match(atv_url)
                if atv_url_match:
                    return atv_url

    except Exception as e:
        print(f"[yellow][JUSTWATCH][/yellow] Error getting details for {country.upper()}: {e}")

    return None


def get_appletv_url(movie: TMDBMovie, max_workers: int = 5) -> str | None:
    """
    Main function to get Apple TV URL for a movie

    1. Search JustWatch in parallel across all regions for node IDs
    2. As each node_id is found, immediately search all regions for Apple TV URL
    3. Stop everything once Apple TV URL is found

    Args:
        movie: TMDBMovie object with regions list
        max_workers: Maximum number of parallel threads (default: 5)
    """
    if movie is None or len(movie.regions) == 0:
        return None

    checked_node_ids = set()

    with ThreadPoolExecutor(max_workers=max_workers) as node_executor:
        # submit all region searches for node_ids
        node_futures = {node_executor.submit(get_justwatch_node_id, movie, region): region for region in movie.regions}

        # process node_id results as they complete
        for node_future in as_completed(node_futures):
            try:
                node_id = node_future.result()
                # skip if no node_id or already checked this one
                if not node_id or node_id in checked_node_ids:
                    continue

                checked_node_ids.add(node_id)

                # search all regions for Apple TV URL with this node_id
                with ThreadPoolExecutor(max_workers=max_workers) as url_executor:
                    url_futures = {
                        url_executor.submit(get_apple_tv_url_from_justwatch, node_id, region): region
                        for region in movie.regions
                    }

                    # check if any region has the Apple TV URL
                    for url_future in as_completed(url_futures):
                        try:
                            apple_tv_url = url_future.result()
                            if apple_tv_url:
                                # apple tv url found
                                for f in url_futures:
                                    f.cancel()
                                for f in node_futures:
                                    f.cancel()
                                return apple_tv_url
                        except Exception as e:
                            region = url_futures[url_future]
                            print(f"[yellow][JUSTWATCH][/yellow] Exception in URL search for {region}: {e}")

            except Exception as e:
                region = node_futures[node_future]
                print(f"[red][JUSTWATCH][/red] Exception in node_id search for {region}: {e}")

    return None
