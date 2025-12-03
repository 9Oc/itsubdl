import argparse
import asyncio
import re
import shutil
import unicodedata
from pathlib import Path

import aiohttp
from rich.console import Console

from itsubdl import appletv, pluralize, tmdb
from itsubdl.config_manager import (
    ensure_config_exists,
    get_output_directory,
    update_tmdb_api_key,
    update_output_directory,
)
from itsubdl.subtitle import subdeduper, subhelper
from itsubdl.tmdbmovie import TMDBMovie

console = Console(color_system="truecolor")


def get_alpha_folder(title: str) -> str:
    """
    Returns the alphabetical folder name (A-Z or 0-9) based on the first character of the title.
    Special characters and numbers go into '0-9'.
    """
    SPECIAL_BUCKET = r"1-9+$@.([¡¿!#"
    if not title:
        return SPECIAL_BUCKET

    title = title.lstrip("\ufeff\u200b\u200c\u200d\xa0")
    if not title:
        return SPECIAL_BUCKET
    # get first character
    first_char = title[0].upper()
    # strip accent from first character
    normalized = unicodedata.normalize("NFD", first_char)
    base_char = normalized[0].upper()

    # Check if it's A-Z
    if base_char.isalpha() and 'A' <= base_char <= 'Z':
        return base_char

    return SPECIAL_BUCKET


def create_movie_folder(base_dir: str | Path, title: str, year: str | int, movie_id: str | int) -> Path:
    # sanitize title for filesystem
    safe_title = re.sub(r'[\/\\\:\*\?"<>\|]+', '', title).strip()
    safe_title = TMDBMovie.make_windows_safe_folder(safe_title)

    # get the alphabetical parent folder
    # alpha_folder = get_alpha_folder(title)

    folder_name = f"{safe_title} ({year})"
    if movie_id:
        folder_name += f" [{movie_id}]"
    path = Path(base_dir) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def move_srt_files_to_folder(directory: Path, destination: Path) -> list[Path]:
    """
    Move all .srt files currently in <directory> to <destination>.
    Args:
        directory: Path object or string for source directory
        destination: Path object or string for destination folder
    Returns:
        list of destination paths for moved files
    """
    directory = Path(directory)
    destination = Path(destination)
    moved = []

    if not directory.exists():
        return moved

    srt_files = subhelper.get_subtitle_files(directory, "srt")

    for file_path in srt_files:
        dest_path = destination / file_path.name

        # If destination exists, append a number
        if dest_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            i = 1
            while True:
                new_name = f"{stem}_{i}{suffix}"
                dest_path = destination / new_name
                if not dest_path.exists():
                    break
                i += 1

        shutil.move(str(file_path), str(dest_path))
        moved.append(dest_path)

    return moved


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download subtitles from Apple TV using TMDB data or Apple TV URLs"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="TMDB ID or Apple TV URL to download subtitles for"
    )
    parser.add_argument(
        "--tmdb-api-key",
        help="Update the TMDB API key in config"
    )
    parser.add_argument(
        "--output-dir",
        help="Update the output directory in config"
    )
    return parser.parse_args()


async def main(input_arg: str | None = None):
    """
    Main entrypoint accepting either an Apple TV URL or a TMDB id.

    - If `input_arg` matches an Apple TV URL, fetch movie title and year via
      `appletv.get_movie_data`, search TMDB to get a full TMDBMovie object,
      then call `appletv.download_subs` with it.
    - Otherwise treat `input_arg` as a TMDB id and use existing TMDB flow.
    """

    args = parse_args()
    # ensure config exists and is properly set up
    ensure_config_exists()
    # handle config update arguments
    if args.tmdb_api_key or args.output_dir:
        if args.tmdb_api_key:
            update_tmdb_api_key(args.tmdb_api_key)
        if args.output_dir:
            update_output_directory(args.output_dir)
        return

    output_dir = Path(get_output_directory())

    if input_arg is None:
        input_arg = args.input
        if input_arg is None:
            console.print("Usage: python itunesdl.py <tmdb_id|appletv_url>")
            return

    # if input is an Apple TV URL, use the Apple TV API to get title/year
    atv_match = appletv.ATV_URL_REGEX.match(input_arg)

    if atv_match:
        # extract country_code and media_id from the URL
        country = (atv_match.groupdict().get("country_code") or "us").lower()
        media_id = atv_match.groupdict().get("media_id")
        storefront_id = appletv.get_storefront_from_region(country)
        async with aiohttp.ClientSession() as session:
            try:
                # appletv.get_movie_data returns a list of playables with name/year
                playables = await appletv.get_movie_data(session, storefront_id, media_id)
            except Exception as e:
                console.print(f"[red][APPLE TV][/red] Error fetching movie data from Apple TV: {e}")
                return

        if not playables:
            console.print(f"[yellow][APPLE TV][/yellow] No iTunes playables found for: [dodger_blue1]{input_arg}[/dodger_blue1]")
            return

        # prefer the first playable
        playable = playables[0]
        title = playable.get("name") or "Unknown"
        year = playable.get("release_date") or None

        with console.status(f"[green][TMDB][/green] Searching TMDB for movie: {title} ({year})",
                            spinner="dots", spinner_style="white", speed=0.9):
            # search TMDB using the title and year from Apple TV
            movie = tmdb.search_tmdb_movie(title, year)
        if not movie:
            console.print(f"[yellow][APPLE TV][/yellow] Could not find TMDB match.")
            console.print(f"[yellow][APPLE TV][/yellow] Using Apple TV metadata: {title} ({year}).")
            # Fall back to minimal movie object
            movie = TMDBMovie(
                id=None,
                imdb_id=None,
                title=title,
                original_title=title,
                alternative_titles=[],
                year=year,
                duration=None,
                regions=list(appletv.REGION_STOREFRONT_MAP.keys()),
                watch_links=[],
            )
        else:
            console.print(
                f"[green][TMDB][/green] Successfully built TMDBMovie object: {movie.title} ({movie.year}) [{movie.id}]")

        atvp_url = input_arg
    else:
        # otherwise, assume TMDB id
        tmdb_id = str(input_arg)
        with console.status(f"[green][TMDB][/green] Requesting TMDB metadata for ID: [sea_green2]{tmdb_id}[/sea_green2]",
                            spinner="dots", spinner_style="white", speed=0.9):
            movie = tmdb.get_tmdbmovie(tmdb_id)
        if not movie:
            console.print(f"[yellow][TMDB] Could not fetch TMDB metadata for ID:[/yellow] [sea_green2]{tmdb_id}[/sea_green2]")
            return

        console.print(f"[green][TMDB][/green] Successfully built TMDBMovie object: {movie.title} ({movie.year}) [{movie.id}]")
        with console.status(f"[green][JUSTWATCH][/green] Searching for Apple TV URL", spinner="dots", spinner_style="white", speed=0.9):
            atvp_url = tmdb.get_appletv_url(movie)
        if not atvp_url:
            console.print(f"[yellow][JUSTWATCH][/yellow] Could not find Apple TV URL for TMDB ID [orange1]{tmdb_id}[/orange1]")
            return
        console.print(f"[green][JUSTWATCH][/green] Found Apple TV URL: [dodger_blue1]{atvp_url}[/dodger_blue1]")

    temp_download_dir = output_dir / "temp"
    temp_download_dir.mkdir(parents=True, exist_ok=True)
    await appletv.download_subs(atvp_url, temp_download_dir, appletv.REGION_STOREFRONT_MAP.keys(), movie)

    vtt_files = subhelper.get_subtitle_files(temp_download_dir, "vtt")
    if len(vtt_files) > 0:
        console.print(f"[green][APPLE TV][/green] Finished downloading [orange1]{len(vtt_files)}[/orange1] subtitle files")
    with console.status(f"[green][CLEANUP][/green] Running cleanup tasks", spinner="dots", spinner_style="white", speed=0.9):
        md5_deduped, fuzzy_deduped, forced_deduped = subdeduper.dedupe(temp_download_dir)
    if len(md5_deduped) > 0:
        console.print(f"[green][CLEANUP][/green] [orange1]{len(md5_deduped)}[/orange1] files MD5 hash deduped")
    if len(fuzzy_deduped) > 0:
        console.print(f"[green][CLEANUP][/green] [orange1]{len(fuzzy_deduped)}[/orange1] files fuzzy deduped")
    if len(forced_deduped) > 0:
        console.print(f"[green][CLEANUP][/green] [orange1]{len(forced_deduped)}[/orange1] forced subtitles deduped")

    srt_files = subhelper.get_subtitle_files(temp_download_dir, "srt")
    if srt_files:
        movie_folder = create_movie_folder(output_dir, movie.title, movie.year, movie.id)

        itunes_folder = movie_folder / "iTunes"
        itunes_folder.mkdir(parents=True, exist_ok=True)

        moved = move_srt_files_to_folder(temp_download_dir, itunes_folder)
        console.print(pluralize.pluralize_numbers(
            f"[green][CLEANUP][/green] Moved [orange1]{len(moved)}[/orange1] file to [dodger_blue1]{itunes_folder}[/dodger_blue1]"))

    shutil.rmtree(temp_download_dir, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(main())


# Synchronous entry point for setuptools console_script
def cli_main() -> None:
    """Console script entry point that runs the async main function."""
    asyncio.run(main())
