import asyncio
import logging
import re
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp
import m3u8
from rapidfuzz import fuzz
from rich import print
from rich.console import Console

from itsubdl.pluralize import pluralize_numbers
from itsubdl.subtitle import subhelper
from itsubdl.tmdbmovie import TMDBMovie

console = Console(color_system="truecolor")
logger = logging.getLogger(__name__)

# HTTP headers for requests
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/100.0.4896.127 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Apple TV API configuration
API_BASE_URL = "https://tv.apple.com/api/uts/v3"
API_BASE_PARAMS = {
    "utscf": "OjAAAAAAAAA~",
    "caller": "web",
    "v": "84",
    "pfm": "web",
}

# match tv.apple.com movie URLs
ATV_URL_REGEX = re.compile(
    r"(?i)(?P<base_url>https?://tv\.apple\.com/"
    r"(?:(?P<country_code>[a-z]{2})/)?"
    r"(?P<media_type>movie|episode|season|show)/"
    r"(?:(?P<media_name>[^/]+)/)?"
    r"(?P<media_id>umc\.cmc\.[a-z\d]{20,34}))"
    r"(?:\?(?P<url_params>.*))?"
)

# map of all regions and their storefront IDs
REGION_STOREFRONT_MAP = {
    "ae": 143481,
    "ag": 143540,
    "ai": 143538,
    "am": 143524,
    "ao": 143564,
    "ar": 143505,
    "at": 143445,
    "au": 143460,
    "az": 143568,
    "bb": 143541,
    "bd": 143490,
    "be": 143446,
    "bg": 143526,
    "bh": 143559,
    "bm": 143542,
    "bn": 143560,
    "bo": 143556,
    "br": 143503,
    "bs": 143539,
    "bw": 143525,
    "by": 143565,
    "bz": 143555,
    "ca": 143455,
    "ch": 143459,
    "ci": 143527,
    "cl": 143483,
    "cn": 143465,
    "co": 143501,
    "cr": 143495,
    "cv": 143580,
    "cy": 143557,
    "cz": 143489,
    "de": 143443,
    "dk": 143458,
    "dm": 143545,
    "do": 143508,
    "dz": 143563,
    "ec": 143509,
    "ee": 143518,
    "eg": 143516,
    "es": 143454,
    "fi": 143447,
    "fj": 143583,
    "fm": 143591,
    "fr": 143442,
    "gb": 143444,
    "gd": 143546,
    "gh": 143573,
    "gm": 143584,
    "gr": 143448,
    "gt": 143504,
    "gw": 143585,
    "gy": 143553,
    "hk": 143463,
    "hn": 143510,
    "hr": 143494,
    "hu": 143482,
    "id": 143476,
    "ie": 143449,
    "il": 143491,
    "in": 143467,
    "is": 143558,
    "it": 143450,
    "jm": 143511,
    "jo": 143528,
    "jp": 143462,
    "ke": 143529,
    "kg": 143586,
    "kh": 143579,
    "kn": 143548,
    "kr": 143466,
    "kw": 143493,
    "ky": 143544,
    "kz": 143517,
    "la": 143587,
    "lb": 143497,
    "lc": 143549,
    "li": 143522,
    "lk": 143486,
    "lt": 143520,
    "lu": 143451,
    "lv": 143519,
    "md": 143523,
    "mg": 143531,
    "mk": 143530,
    "ml": 143532,
    "mn": 143592,
    "mo": 143515,
    "ms": 143547,
    "mt": 143521,
    "mu": 143533,
    "mv": 143488,
    "mx": 143468,
    "my": 143473,
    "mz": 143593,
    "na": 143594,
    "ne": 143534,
    "ng": 143561,
    "ni": 143512,
    "nl": 143452,
    "no": 143457,
    "np": 143484,
    "nz": 143461,
    "om": 143562,
    "pa": 143485,
    "pe": 143507,
    "ph": 143474,
    "pk": 143477,
    "pl": 143478,
    "pt": 143453,
    "py": 143513,
    "qa": 143498,
    "ro": 143487,
    "rs": 143500,
    "ru": 143469,
    "sa": 143479,
    "se": 143456,
    "sg": 143464,
    "si": 143499,
    "sk": 143496,
    "sn": 143535,
    "sr": 143554,
    "sv": 143506,
    "sz": 143602,
    "tc": 143552,
    "th": 143475,
    "tj": 143603,
    "tm": 143604,
    "tn": 143536,
    "tr": 143480,
    "tt": 143551,
    "tw": 143470,
    "tz": 143572,
    "ua": 143492,
    "ug": 143537,
    "us": 143441,
    "uk": 143444,
    "uy": 143514,
    "uz": 143566,
    "vc": 143550,
    "ve": 143502,
    "vg": 143543,
    "vn": 143471,
    "ye": 143571,
    "za": 143472,
    "zw": 143605,
}
REGIONS_TO_ALWAYS_CHECK = [
    "us",
    "gb",
    "ca",
    "cn",
    "de",
    "dk",
    "es",
    "fi",
    "fr",
    "it",
    "jp",
    "kr",
    "nl",
    "ru",
    "sv",
    "tw",
]

CC_CHARACTERISTICS = {
    "public.accessibility.describes-music-and-sound",
    "public.accessibility.transcribes-spoken-dialog",
}


def get_date_from_ts(timestamp) -> datetime:
    """
    Return a datetime object representing the unix timestamp passed in.
    """
    timestamp = timestamp / 1000  # ms -> s
    if timestamp < 0:
        return datetime(1970, 1, 1) + timedelta(seconds=timestamp)
    else:
        return datetime.fromtimestamp(timestamp)


def get_storefront_from_region(region) -> None | int:
    """
    Return the storefront id which matches the region passed in.
    """
    if not region:
        return None
    return REGION_STOREFRONT_MAP.get(region.lower())


async def query_itunes_api_async(session, storefront_id, search_terms):
    """
    Async query the iTunes API with a storefront id and search terms.
    Used to retrieve the tv.apple.com URL for a specific movie.
    """
    semaphore = asyncio.Semaphore(5)
    async with semaphore:
        base_url = "https://uts-api.itunes.apple.com/uts/v3/search"

        params = {
            "caller": "js",
            "locale": "en-US",
            "pfm": "iphone",
            "sf": storefront_id,
            "utscf": "OjAAAAEAAAAAAAQAEAAAAAwADQAjACQAKwA~",
            "utsk": "1fed679534b8ac2::::::b12ef8cda490576",
            "searchTerm": search_terms,
            "searchTermSource": "keyboard",
            "v": "90",
        }

        async with session.get(
            base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            return await response.json()


async def parse_appletv_response_async(
    session, search_terms, storefront_id, tmdb_movie
):
    """
    Returns all candidates found which are possible matches.
    """
    try:
        # query the itunes api
        response = await query_itunes_api_async(session, storefront_id, search_terms)

        # parse json response
        canvas = response.get("data", {}).get("canvas", {})
        shelves = canvas.get("shelves", [])

        candidates = []

        for shelf in shelves:
            items = shelf.get("items", [])
            for item in items:
                if item.get("type") == "Movie":
                    release_timestamp = item.get("releaseDate")
                    if release_timestamp:
                        release_date = get_date_from_ts(release_timestamp)
                        item_year = release_date.year
                        item_duration = item.get("duration") or None

                        # Check if the title and year fuzzy match
                        item_title = TMDBMovie.sanitize(item.get("title", "").lower())
                        titles_to_check = [TMDBMovie.sanitize(tmdb_movie.title.lower())]

                        # special case, if y or & is in the movie title, check for those
                        # characters replaced with 'and' since apple is retarded
                        if " y " in titles_to_check[0] or " & " in titles_to_check[0]:
                            titles_to_check.append(
                                titles_to_check[0]
                                .replace(" y ", " and ")
                                .replace(" & ", " and ")
                            )

                        if (
                            tmdb_movie.original_title
                        ):  # check original title only if it exists
                            titles_to_check.append(
                                TMDBMovie.sanitize(tmdb_movie.original_title.lower())
                            )

                        for (
                            alt_title
                        ) in tmdb_movie.alternative_titles:  # check any alt titles
                            t = alt_title.get("title")
                            if t:
                                titles_to_check.append(TMDBMovie.sanitize(t.lower()))

                        title_fuzzy_similarity = max(
                            fuzz.token_sort_ratio(title, item_title)
                            for title in titles_to_check
                        )

                        # check duration match - both must exist and be within 60 seconds
                        if (
                            tmdb_movie.duration is not None
                            and item_duration is not None
                        ):
                            duration_diff = abs(tmdb_movie.duration - item_duration)
                        else:
                            # if either duration is missing, set a high penalty
                            duration_diff = float("inf")

                        year_diff = abs(item_year - tmdb_movie.year)
                        if not tmdb_movie.regions or len(tmdb_movie.regions) == 0:
                            if (
                                year_diff == 0
                                and title_fuzzy_similarity >= 95
                                and duration_diff <= 120
                            ):
                                candidates.append(
                                    {
                                        "url": item.get("url"),
                                        "similarity": title_fuzzy_similarity,
                                        "year_diff": year_diff,
                                        "duration_diff": duration_diff,
                                    }
                                )
                        else:
                            if year_diff <= 1 and title_fuzzy_similarity > 92:
                                candidates.append(
                                    {
                                        "url": item.get("url"),
                                        "similarity": title_fuzzy_similarity,
                                        "year_diff": year_diff,
                                        "duration_diff": duration_diff,
                                    }
                                )

        # return all candidates
        return candidates

    except Exception as e:
        return []


async def search_with_terms_async(session, search_terms, storefront_id, tmdb_movie):
    """
    Helper to search with specific terms and return result.
    """
    return await parse_appletv_response_async(
        session, search_terms, storefront_id, tmdb_movie
    )


async def get_appletv_url_for_region_async(
    session, region, tmdb_movie, search_terms_list
):
    """
    Search a single region with all search term variations concurrently.
    Returns ALL candidates found across all search terms.
    """
    storefront_id = get_storefront_from_region(region)
    if not storefront_id:
        return []

    # create tasks for all search term variations
    tasks = [
        asyncio.create_task(
            search_with_terms_async(session, terms, storefront_id, tmdb_movie)
        )
        for terms in search_terms_list
    ]

    # wait for all tasks to complete
    results = await asyncio.gather(*tasks)

    # flatten all candidates from all search terms
    all_candidates = []
    for candidate_list in results:
        all_candidates.extend(candidate_list)

    return all_candidates


async def get_appletv_url_async(tmdb_movie):
    """
    Async version: Get the tv.apple.com url using a TMDBMovie object.
    Searches all regions and search term variations concurrently.
    Waits for ALL tasks to complete before selecting the best candidate.
    """
    # get the regions that the movie is available on Apple TV according to tmdb.
    regions = tmdb_movie.regions.copy()
    # add any regions from the pre-defined always check list if they are not present.
    for reg in REGIONS_TO_ALWAYS_CHECK:
        if reg not in regions:
            regions.append(reg)

    # prepare all search term variations
    search_terms_list = [TMDBMovie.sanitize(tmdb_movie.title).lower()]

    # add original title if it exists
    if tmdb_movie.original_title and tmdb_movie.original_title != tmdb_movie.title:
        search_terms_list.append(TMDBMovie.sanitize(tmdb_movie.original_title).lower())

    # add alternative titles if they exist
    for alt_title in tmdb_movie.alternative_titles:
        t = alt_title.get("title")
        if t:
            search_terms_list.append(TMDBMovie.sanitize(t.lower()))

    # add 'and' variations if needed
    if " y " in tmdb_movie.title or " & " in tmdb_movie.title:
        search_terms_list.append(
            TMDBMovie.sanitize(
                tmdb_movie.title.replace(" y ", " and ").replace(" & ", " and ")
            ).lower()
        )
    if " y " in tmdb_movie.original_title or " & " in tmdb_movie.original_title:
        search_terms_list.append(
            TMDBMovie.sanitize(
                tmdb_movie.original_title.replace(" y ", " and ").replace(
                    " & ", " and "
                )
            ).lower()
        )

    async with aiohttp.ClientSession() as session:
        # create tasks for all regions
        tasks = [
            asyncio.create_task(
                get_appletv_url_for_region_async(
                    session, region, tmdb_movie, search_terms_list
                )
            )
            for region in regions
        ]

        # wait for ALL tasks to complete
        all_results = await asyncio.gather(*tasks)

        # flatten all candidates from all regions into a master list
        master_candidates = []
        for candidate_list in all_results:
            master_candidates.extend(candidate_list)

        # if we have candidates, sort them and return the best one
        if master_candidates:
            master_candidates.sort(
                key=lambda x: (-x["similarity"], x["year_diff"], x["duration_diff"])
            )
            return master_candidates[0]["url"]

    return None


def get_appletv_url(tmdb_movie):
    """
    Synchronous wrapper for backward compatibility.
    Handles both sync and async contexts.
    """
    try:
        # check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # we're in an async context, need to run in a thread pool
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, get_appletv_url_async(tmdb_movie))
            return future.result()
    except RuntimeError:
        # no event loop running, create a new one
        return asyncio.run(get_appletv_url_async(tmdb_movie))


async def check_head_success(session, url):
    """Check if a HEAD request to the URL is successful."""
    try:
        async with session.head(
            url, headers=DEFAULT_HEADERS, allow_redirects=True
        ) as resp:
            return resp.status < 400
    except Exception:
        return False


async def fetch_json(session, url, params=None):
    """Fetch JSON data from a URL."""
    try:
        async with session.get(url, params=params, headers=DEFAULT_HEADERS) as resp:
            logger.debug(f"[fetch_json] {url[:80]}... -> HTTP {resp.status}")
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        logger.debug(f"[fetch_json] Error fetching {url[:80]}...: {str(e)}")
        raise


async def fetch_text(session, url):
    """Fetch text data from a URL."""
    try:
        async with session.get(url, headers=DEFAULT_HEADERS) as resp:
            logger.debug(f"[fetch_text] {url[:80]}... -> HTTP {resp.status}")
            resp.raise_for_status()
            return await resp.text()
    except Exception as e:
        logger.debug(f"[fetch_text] Error fetching {url[:80]}...: {str(e)}")
        raise


async def fetch_binary(session, url):
    """Fetch binary data from a URL."""
    async with session.get(url, headers=DEFAULT_HEADERS) as resp:
        resp.raise_for_status()
        return await resp.read()


async def fetch_binary_with_retry(session, url, max_retries=2, retry_delay=1.0):
    """Fetch binary data with retry logic using alternative CDNs."""
    cdns = ["vod-ak-amt", "vod-ap-amt", "vod-fa-amt"]

    for attempt in range(max_retries + 1):  # +1 to include initial attempt
        try:
            current_url = url
            if attempt > 0:
                # cycle through alternative CDNs
                # this prevents failure to download subtitles from a specific ID
                # if one or more of the CDNs fails
                current_url = url.replace(cdns[0], cdns[attempt % len(cdns)])

            return await fetch_binary(session, current_url)
        except Exception as e:
            if attempt == max_retries:
                raise
            wait_time = retry_delay * (2**attempt)
            await asyncio.sleep(wait_time)


async def get_configuration_data(session, storefront_id):
    """Get Apple TV API configuration data for a storefront."""
    url = f"{API_BASE_URL}/configurations"
    params = API_BASE_PARAMS.copy()
    params["sf"] = storefront_id
    data = await fetch_json(session, url, params)
    return data["data"]


async def get_request_params(session, storefront_id):
    """Get request parameters for API calls."""
    config = await get_configuration_data(session, storefront_id)

    request_params = config["applicationProps"]["requiredParamsMap"]["Default"]
    default_locale = config["applicationProps"]["storefront"]["defaultLocale"]
    available_locales = config["applicationProps"]["storefront"]["localesSupported"]

    # Prefer en_US, fall back to en_GB or default
    locale = default_locale
    for pref in ["en_US", "en_GB"]:
        if pref in available_locales:
            locale = pref
            break

    request_params["sf"] = storefront_id
    request_params["locale"] = locale.replace("_", "-")

    return request_params


async def get_movie_data(session, storefront_id, movie_id):
    """Fetch movie data from Apple TV API."""
    logger.debug(
        f"[get_movie_data] Fetching data for movie_id={movie_id}, storefront_id={storefront_id}"
    )

    request_params = await get_request_params(session, storefront_id)
    url = f"{API_BASE_URL}/movies/{movie_id}"

    logger.debug(f"[get_movie_data] API URL: {url}")
    logger.debug(f"[get_movie_data] Request params: {request_params}")

    data = await fetch_json(session, url, request_params)
    response_data = data.get("data", {})

    logger.debug(f"[get_movie_data] API response keys: {list(response_data.keys())}")

    # extract iTunes playables
    playables = response_data.get("playables", {}).values()
    itunes_playables = []

    logger.debug(f"[get_movie_data] Found {len(list(playables))} playables in response")

    playables = response_data.get(
        "playables", {}
    ).values()  # Re-get since we consumed the iterator
    for playable in playables:
        if playable.get("channelId") != "tvs.sbd.9001":  # iTunes channel
            logger.debug(
                f"[get_movie_data] Skipping non-iTunes channel: {playable.get('channelId')}"
            )
            continue

        logger.debug(f"[get_movie_data] Processing iTunes playable")
        itunes_data = playable.get("itunesMediaApiData", {})
        # extract playlists from offers
        playlists = []
        if offers := itunes_data.get("offers"):
            logger.debug(f"[get_movie_data] Found {len(offers)} offers")
            for offer in offers:
                if hls_url := offer.get("hlsUrl"):
                    if hls_url not in playlists:
                        playlists.append(hls_url)
                        logger.debug(
                            f"[get_movie_data] Added HLS URL: {hls_url[:80]}..."
                        )

        if playlists:
            logger.debug(
                f"[get_movie_data] Checking {len(playlists)} playlist URLs for validity"
            )
            tasks = [check_head_success(session, hls_url) for hls_url in playlists]
            results = await asyncio.gather(*tasks)
            valid_playlists = [url for url, ok in zip(playlists, results) if ok]
            logger.debug(f"[get_movie_data] {len(valid_playlists)} playlists are valid")

            if valid_playlists:
                itunes_playables.append(
                    {
                        "name": playable.get("canonicalMetadata", {}).get(
                            "movieTitle", "Unknown"
                        ),
                        "release_date": get_date_from_ts(
                            playable.get("canonicalMetadata", {}).get("releaseDate")
                        ).year,
                        "playlists": valid_playlists,
                    }
                )

    logger.debug(f"[get_movie_data] Returning {len(itunes_playables)} iTunes playables")
    return itunes_playables


async def _fetch_and_parse_playlist(session, url):
    """Fetches a playlist URL and returns a parsed m3u8 object."""
    try:
        text = await fetch_text(session, url)
        return m3u8.loads(text, uri=url)
    except Exception:
        return None


def _is_cc_from_characteristics(characteristics: str | None) -> bool:
    if not characteristics:
        return False
    tokens = {t.strip() for t in characteristics.split(",") if t.strip()}
    # broad match
    if any("public.accessibility" in t for t in tokens):
        return True
    # fallback to narrower set
    return not tokens.isdisjoint(CC_CHARACTERISTICS)


def _extract_subtitle_media(playlist):
    """
    Extracts subtitle information from a parsed m3u8 object.
    Returns a list of subtitles as dicts with keys: url, language, name, forced, cc
    """
    if not playlist or not playlist.media:
        return []

    subtitles = []
    for media in playlist.media:
        if media.type == "SUBTITLES" and media.uri:
            # add relevant data to each subtitle entry
            subtitles.append(
                {
                    "url": media.absolute_uri,
                    "language": media.language or "unknown",
                    "name": media.name or "Unknown",
                    "forced": media.forced == "YES",
                    "cc": _is_cc_from_characteristics(media.characteristics),
                }
            )
    return subtitles


async def find_subtitle_playlists(session, master_playlist_url):
    """Find all unique subtitle playlists in a given master HLS playlist."""
    logger.debug(
        f"[find_subtitle_playlists] Fetching master playlist: {master_playlist_url[:80]}..."
    )

    master_playlist = await _fetch_and_parse_playlist(session, master_playlist_url)
    if not master_playlist:
        logger.debug(f"[find_subtitle_playlists] Failed to parse master playlist")
        return []

    subtitles = _extract_subtitle_media(master_playlist)
    logger.debug(
        f"[find_subtitle_playlists] Found {len(subtitles)} subtitles in master playlist"
    )

    variant_urls = [variant.absolute_uri for variant in master_playlist.playlists]
    logger.debug(
        f"[find_subtitle_playlists] Found {len(variant_urls)} variant playlists"
    )

    variant_playlist_tasks = [
        _fetch_and_parse_playlist(session, url) for url in variant_urls
    ]

    variant_playlists = await asyncio.gather(*variant_playlist_tasks)

    for i, playlist in enumerate(variant_playlists):
        if playlist:
            variant_subs = _extract_subtitle_media(playlist)
            logger.debug(
                f"[find_subtitle_playlists] Variant {i} has {len(variant_subs)} subtitles"
            )
            subtitles.extend(variant_subs)

    seen_urls = set()
    unique_subs = []
    for sub in subtitles:
        if sub["url"] not in seen_urls:
            seen_urls.add(sub["url"])
            unique_subs.append(sub)

    logger.debug(
        f"[find_subtitle_playlists] Total unique subtitles: {len(unique_subs)}"
    )
    return unique_subs


async def download_subtitle_segments(
    session, subtitle_playlist_url, output_path, max_retries=3
):
    """Download all segments from a subtitle playlist and merge them."""
    try:
        text = await fetch_text(session, subtitle_playlist_url)
        playlist = m3u8.loads(text, uri=subtitle_playlist_url)
    except Exception as e:
        print(f"Failed to load subtitle playlist: {subtitle_playlist_url}\n{e}")
        return False

    if not playlist.segments:
        print(f"[yellow][APPLE TV][/yellow] No segments found in playlist")
        return False

    # download all segments concurrently
    tasks = [
        fetch_binary_with_retry(session, segment.absolute_uri, max_retries=max_retries)
        for segment in playlist.segments
    ]

    try:
        segments_data = await asyncio.gather(*tasks)
    except Exception as e:
        # print(f"Failed to download segments: {e}")
        return False

    # merge webvtt segments
    merged_content = merge_webvtt_segments(segments_data)

    # save merged file
    with open(output_path, "wb") as f:
        f.write(merged_content)

    return True


def merge_webvtt_segments(segments) -> bytes:
    """Merge multiple WebVTT segments into one file, removing duplicate headers."""
    if not segments:
        return b""

    merged_lines = []
    first = True

    for segment in segments:
        try:
            text = segment.decode("utf-8")
            lines = text.split("\n")

            if first:
                # keep entire first segment including header
                merged_lines.extend(lines)
                first = False
            else:
                # skip WEBVTT header and X-TIMESTAMP-MAP for subsequent segments
                content_started = False

                for line in lines:
                    stripped = line.strip()

                    # skip header lines
                    if not content_started:
                        if stripped.startswith("WEBVTT"):
                            continue
                        elif stripped.startswith("X-TIMESTAMP-MAP"):
                            continue
                        elif stripped == "":
                            continue
                        else:
                            # found actual content (timestamp or cue)
                            content_started = True

                    if content_started:
                        merged_lines.append(line)

        except Exception:
            print(f"debug: Failed to decode segment: {segment}")
            continue

    cleaned_lines = []
    previous_blank = False

    for line in merged_lines:
        if line.strip() == "":
            if not previous_blank:
                cleaned_lines.append(line)
            previous_blank = True
        else:
            cleaned_lines.append(line)
            previous_blank = False

    return "\n".join(cleaned_lines).encode("utf-8")


async def get_unique_playlists_from_regions(session, base_url_data, regions):
    """
    Get unique playlists from specified regions.
    If no regions are supplied, check the REGIONS_TO_ALWAYS_CHECK regions.
    """
    if not regions:
        regions = []

    for region in REGIONS_TO_ALWAYS_CHECK:
        if region not in regions:
            regions.append(region)

    logger.debug(f"[get_unique_playlists_from_regions] Checking {len(regions)} regions")

    all_playlists = []
    seen_ids = set()

    # create tasks for all regions
    tasks = []
    for country_code in regions:
        try:
            storefront_id = REGION_STOREFRONT_MAP[country_code]
        except Exception as e:
            logger.debug(
                f"[get_unique_playlists_from_regions] Invalid region: {country_code}"
            )
            continue
        tasks.append(
            get_movie_data_safe(
                session, storefront_id, base_url_data["media_id"], country_code
            )
        )

    logger.debug(
        f"[get_unique_playlists_from_regions] Created {len(tasks)} tasks for regions"
    )

    # fetch all regions concurrently
    with console.status(
        pluralize_numbers(
            f"[green][APPLE TV][/green] Fetching data from {len(regions)} region"
        ),
        spinner="dots",
        spinner_style="white",
        speed=0.9,
    ):
        results = await asyncio.gather(*tasks)
        # process results
        regions_with_data = 0
        for country_code, movies in results:
            if movies:
                regions_with_data += 1
                logger.debug(
                    f"[get_unique_playlists_from_regions] Region {country_code}: {len(movies)} movies found"
                )
                for movie in movies:
                    for playlist_url in movie.get("playlists", []):
                        if not playlist_url:
                            continue
                        parsed = urlparse(playlist_url)
                        params = parse_qs(parsed.query)
                        playlist_id = params.get("id", [None])[0]
                        if playlist_id and playlist_id not in seen_ids:
                            seen_ids.add(playlist_id)
                            all_playlists.append(
                                {
                                    "url": playlist_url,
                                    "region": country_code,
                                    "movie_name": movie.get("name", "Unknown"),
                                    "movie_year": movie.get("release_date", "Unknown"),
                                }
                            )
            else:
                logger.debug(
                    f"[get_unique_playlists_from_regions] Region {country_code}: no data"
                )

    logger.debug(
        f"[get_unique_playlists_from_regions] Found {len(all_playlists)} unique playlists across {regions_with_data} regions"
    )

    console.print(
        pluralize_numbers(
            f"[green][APPLE TV][/green] Found [orange1]{len(all_playlists)}[/orange1] playlist across [orange1]{regions_with_data}[/orange1] region"
        )
    )

    return all_playlists


async def get_movie_data_safe(session, storefront_id, movie_id, country_code):
    """Safely fetch movie data, returning empty list on error."""
    try:
        movies = await get_movie_data(session, storefront_id, movie_id)
        return (country_code, movies)
    except Exception as e:
        logger.debug(
            f"[get_movie_data_safe] Error fetching data for {country_code}: {str(e)}"
        )
        return (country_code, [])


async def process_all_playlists(session, playlists, output_dir, movie):
    if not playlists:
        print("[yellow][APPLE TV][/yellow] No playlists provided to process")
        return

    # get movie name and year
    safe_name = TMDBMovie.sanitize(movie.title).replace(" ", ".")
    safe_name = re.sub(r"\.+", ".", safe_name).strip(
        "."
    )  # collapse multiple . characters into one
    safe_name = TMDBMovie.make_windows_safe(safe_name)
    movie_year = movie.year

    movie_dir = Path(output_dir)
    movie_dir.mkdir(parents=True, exist_ok=True)

    with console.status(
        f"[green][APPLE TV][/green] Extracting subtitles from playlists",
        spinner="dots",
        spinner_style="white",
        speed=0.9,
    ):
        tasks = [
            find_subtitle_playlists(session, playlist["url"]) for playlist in playlists
        ]
        all_subtitles_results = await asyncio.gather(*tasks)

        all_subtitles = []
        for subs in all_subtitles_results:
            for sub in subs:
                # filter duplicate CDNS
                # alternative CDNs will be tried later during download
                # if this one fails
                if "vod-ak-amt" in sub["url"]:
                    all_subtitles.append(sub)

    if all_subtitles:
        with console.status(
            pluralize_numbers(
                f"[green][APPLE TV][/green] Downloading [orange1]{len(all_subtitles)}[/orange1] subtitle from playlists"
            ),
            spinner="dots",
            spinner_style="white",
            speed=0.9,
        ):
            # group by language
            lang_count = {}
            for sub in all_subtitles:
                lang = sub["language"]
                lang_count[lang] = lang_count.get(lang, 0) + 1

            # track used filenames to prevent race conditions
            used_filenames = set()

            # pre-generate all unique filenames before starting async downloads
            subtitle_download_info = []
            for idx, subtitle in enumerate(all_subtitles, 1):
                lang = subtitle["language"]

                # check if this is a forced or cc subtitle
                is_forced = subtitle["forced"]
                is_cc = subtitle["cc"]

                # create base filename with forced/cc tag if needed
                if is_cc:
                    filename = f"{safe_name}.{movie_year}.iT.WEB.{lang}[sdh].vtt"
                elif is_forced:
                    filename = f"{safe_name}.{movie_year}.iT.WEB.{lang}[forced].vtt"
                else:
                    filename = f"{safe_name}.{movie_year}.iT.WEB.{lang}.vtt"

                output_path = movie_dir / filename

                # get a unique filename to prevent naming conflicts
                output_path = subhelper.get_unique_filename(output_path, used_filenames)

                subtitle_download_info.append(
                    {
                        "subtitle": subtitle,
                        "output_path": output_path,
                        "idx": idx,
                        "total": len(all_subtitles),
                    }
                )

            # create download tasks
            download_tasks = [
                download_with_info(session, info["subtitle"], info["output_path"])
                for info in subtitle_download_info
            ]

            # download all subs asynchronously
            results = await asyncio.gather(*download_tasks, return_exceptions=True)

            # count successes
            successes = sum(1 for r in results if r is True)
    else:
        print("[yellow][APPLE TV][/yellow] No subtitles available for download")


async def download_with_info(session, subtitle, output_path):
    """Download the given subtitle."""
    success = await download_subtitle_segments(session, subtitle["url"], output_path)
    return success


async def resolve_itunes_to_atv(session, url):
    """
    Given an iTunes URL, follow redirects to get the Apple TV+ URL.
    """
    if "itunes.apple.com" not in url:
        return url  # already a tv.apple.com link

    try:
        async with session.get(url, timeout=10, allow_redirects=True) as resp:
            final_url = str(resp.url)  # the final redirected URL
            return final_url
    except Exception as e:
        print(f"[red][APPLE TV][/red] Failed to resolve iTunes link: {url} -> {e}")
        return None


async def download_subs(appletv_url, output_dir, regions, movie):
    """
    Download all subtitles available from the provided tv.apple.com URL.
    """
    if "itunes.apple.com" in appletv_url:
        async with aiohttp.ClientSession() as tmp_session:
            resolved_url = await resolve_itunes_to_atv(tmp_session, appletv_url)
            if not resolved_url:
                print(
                    f"[red][APPLE TV][/red] Failed to resolve iTunes link: {appletv_url}"
                )
                return False
            appletv_url = resolved_url
    # check if the ATV URL is valid.
    match = ATV_URL_REGEX.match(appletv_url)
    if not match:
        print(
            f"[red][APPLE TV][/red] Invalid Apple TV URL: [dodger_blue1]{appletv_url}[/dodger_blue1]"
        )
        return False

    # check if the provided URL is for a movie
    url_data = match.groupdict()
    media_type = url_data["media_type"]
    media_id = url_data["media_id"]
    if media_type != "movie":
        print(
            f"[red][APPLE TV][/red] Only movies are supported for scraping, (type attempted: [dodger_blue1]{media_type}[/dodger_blue1])"
        )
        return False

    # download the subtitles asyncronously, limit connections so that the pool
    # does not become too large
    connector = aiohttp.TCPConnector(limit=400, limit_per_host=200)
    async with aiohttp.ClientSession(
        connector=connector, headers=DEFAULT_HEADERS
    ) as session:
        try:
            # get unique playlists from all regions
            playlists = await get_unique_playlists_from_regions(
                session, url_data, regions
            )

            # if not playlists:
            if not playlists:
                print(
                    f"[yellow][APPLE TV][/yellow] No .m3u8 playlists found in any region for URL: [dodger_blue1]{appletv_url}[/dodger_blue1]"
                )
                return False

            # Process all playlists and download subtitles
            # await process_all_playlists(session, playlists, output_dir, movie)
            await process_all_playlists(session, playlists, output_dir, movie)

        except Exception as e:
            print(f"[red][APPLE TV][/red] Error while scraping Apple TV: {e}")
            traceback.print_exc()
            return False

    return True
