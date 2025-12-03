# itsubdl
Download subtitles from iTunes using a TMDB ID or Apple TV URL.

### Features
- Downloads subtitles across all regions concurrently for a given title from iTunes.
- Converts downloaded subtitles from WebVTT -> SRT format.
- Removes duplicate subtitle files by both MD5 hash content and fuzzy similarity content.
- Fixes ISO 639-1 language tags.
- Fixes common subtitle content errors with <a href="https://github.com/vevv/subby">subby</a>.
- Supports both Apple TV url's and TMDB movie ID's as input.

## Requirements
- Python 3.10+
- <a href="https://git-scm.com/install/windows">Git</a>

Ensure Git is in your PATH.

## Installation
```
pip install git+https://github.com/9Oc/itsubdl.git
```

Alternatively, clone the repository locally and install from the source:
```
git clone https://github.com/9Oc/itsubdl
cd itsubdl
pip install .
```

## Usage
A TMDB ID or an Apple TV url are both accepted arguments. If using a TMDB ID, `itsubdl` will search for a matching Apple TV url

```
itsubdl <TMDB_ID or Apple TV URL>
```

### Example
Download subtitles for a movie using a TMDB ID:

```
itsubdl 550
```

Download subtitles for a movie using an Apple TV URL:
```
itsubdl https://tv.apple.com/us/movie/example-title/umc.cmc.123456789012345678901234
```

## Configuration
On first run, you will be prompted to enter your TMDB API key and output directory for subtitles.

To update your output directory and/or TMDB API key, these arguments are available:

```
itsubdl --tmdb-api-key <TMDB_API_KEY> --output-dir <OUTPUT_DIRECTORY>
```

You may use the above arguments before attempting your first download to skip the first run prompt.
