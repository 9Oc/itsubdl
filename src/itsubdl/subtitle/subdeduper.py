"""
sub_deduper.py
@author squash

Contains various helper functions to deduplicate subtitle files.
"""
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz
from rich import print
from subby import CommonIssuesFixer
from subby import WebVTTConverter

from itsubdl.subtitle import subhelper
from itsubdl.subtitle.subtitlepatterns import FileName, Tags

SIMILARITY_THRESHOLD = 96
FILE_READ_CHUNK_SIZE = 8192


def compute_md5(file_path: str | Path) -> str:
    """
    Compute MD5 hash of file contents.
    File name and extension are excluded from the hash.
    """
    file_path = Path(file_path)
    md5_hash = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(FILE_READ_CHUNK_SIZE), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def convert_vtt_to_srt(directory: str | Path):
    """Convert all VTT files to SRT format in the given directory."""
    directory = Path(directory)
    converter = WebVTTConverter()
    vtt_files = subhelper.get_subtitle_files(directory, "vtt")

    for vtt in vtt_files:
        output_srt = directory / (vtt.stem + ".srt")
        if output_srt.exists():
            continue

        srt = converter.from_file(vtt)
        srt.save(output_srt)
        vtt.unlink()


def fix_common_issues(directory: str | Path):
    """Run common issues fixer on all SRT files in the specified directory."""
    directory = Path(directory)
    fixer = CommonIssuesFixer()
    srt_files = subhelper.get_subtitle_files(directory, "srt")
    for srt_file in srt_files:
        srt, status = fixer.from_file(srt_file)
        fixed_srt_file = srt_file.with_name(srt_file.stem + "_fix" + srt_file.suffix)
        srt.save(fixed_srt_file)
        srt_file.unlink()
        fixed_srt_file.rename(srt_file)


def remove_forced_subtitles(directory: str | Path) -> list[Path]:
    """Remove all files with 'forced' in their name
       excluding English forced subtitles.
       """
    directory = Path(directory)
    files = subhelper.get_subtitle_files(directory)
    files_to_delete = []

    for file in files:
        file_name_lower = file.name.lower()
        allowed_forced = {"en[forced]", "en-us[forced]", "en-gb[forced]", "en-ca[forced]", "en-au[forced]"}
        if file.is_file() and "[forced]" in file_name_lower and not any(lang in file_name_lower for lang in allowed_forced):
            try:
                files_to_delete.append(file)
                file.unlink()
            except Exception as e:
                pass
    return files_to_delete


def cleanup_filenames(directory: str | Path):
    files = subhelper.get_subtitle_files(directory)

    used_filenames = set()
    for file in files:
        used_filenames.add(str(file))

    # cleanup rules
    rules = list(FileName.CLEANUP_RULES)
    for locale in FileName.SIMPLIFY_LOCALES:
        short = locale[:2]
        rules.append((re.compile(re.escape(locale)), short, 'locale'))

    for file in files:
        original_name = file.name
        new_name = original_name

        # fix "pt" -> "pt-PT"
        if file.stem.lower().endswith("pt") and not file.stem.lower().endswith("pt-pt"):
            new_name = file.stem + "-PT" + file.suffix

        # apply cleanup rules
        for pattern, replacement, _ in rules:
            new_name = pattern.sub(replacement, new_name)

        # try to remove numbered suffix
        new_name = subhelper.strip_numbered_suffix(new_name)

        if new_name == original_name:  # skip renaming if current name is the same as desired name
            continue
        desired_path = file.parent / new_name

        # get a safe unique filename
        final_path = subhelper.get_unique_filename(desired_path, used_filenames)

        # rename
        if final_path != file:
            try:
                old_path_str = str(file)
                file.rename(final_path)
                used_filenames.discard(old_path_str)
            except Exception:
                pass


def count_formatting_tags(text: str) -> int:
    """Count only <i> and {\an8} tags."""
    return len(Tags.TAG_COUNT.findall(text))


def remove_numbered_suffix(file_path: str | Path) -> str:
    """Remove a 1 or 2 numbered suffix from the end of a file name."""
    file_path = Path(file_path)
    if not file_path.exists() or not file_path.suffix == ".srt":
        return str(file_path)
    stripped_file_path = file_path.parent / (subhelper.strip_numbered_suffix(file_path.name))
    if stripped_file_path != file_path and not stripped_file_path.exists():
        file_path.rename(stripped_file_path)
        return str(stripped_file_path)
    return str(file_path)


def get_base_language_tag(path: str | Path) -> str:
    """
    Extracts the base language tag from the end of the subtitle filename.
    Ignores trailing dash + 1-2 numerals before .srt
    Returns only the part before the first dash for grouping.
    Examples:
        Braveheart.1995.iT.WEB.en-US.srt     -> en
        Braveheart.1995.iT.WEB.es-419.srt    -> es
        Braveheart.1995.iT.WEB.en-US-10.srt  -> en
    """
    path = Path(path)
    # remove trailing dash + 1-2 digits
    base = subhelper.strip_numbered_suffix(path.stem)
    parts = base.split('.')
    if not parts:
        return ''
    lang_tag = parts[-1]
    # remove language tag region and any modifier
    lang_tag = lang_tag.split('-')[0]
    lang_tag = lang_tag.split('[')[0]
    return lang_tag


def prefer_fr_fr(path_i: str | Path, path_j: str | Path) -> tuple[Path, Path] | None:
    """
    Return the path to keep and the path to delete if one is fr-FR and the other fr-CA.
    Returns (kept_subtitle, deleted_subtitle), or None if this rule does not apply.
    """
    name_i = Path(path_i).name
    name_j = Path(path_j).name

    if "fr-CA" in name_i and "fr-FR" in name_j:
        return path_j, path_i  # keep FR, delete CA
    elif "fr-FR" in name_i and "fr-CA" in name_j:
        return path_i, path_j  # keep FR, delete CA
    return None


def dedupe_md5(directory: str | Path) -> list[Path]:
    """Remove duplicate files based on MD5 hash, keeping better-named files."""
    directory = Path(directory)
    files = subhelper.get_subtitle_files(directory)
    # sort files, process ones without numbered suffixes first
    sorted_files = sorted(files, key=lambda f: (
        2 if FileName.NUMBERED_SUFFIX.search(f.name) else 1,
        f.name
    ))

    file_content_hashes = {}
    files_to_keep = []
    files_to_delete = []

    for file in sorted_files:
        if not file.is_file():
            continue

        try:
            hash_string = compute_md5(file)

            if hash_string in file_content_hashes:
                existing_file = file_content_hashes[hash_string]

                # special case: prefer fr-FR over fr-CA
                french_preference = prefer_fr_fr(str(existing_file), str(file))
                if french_preference:
                    keep_file, delete_file = french_preference
                    keep_file = Path(keep_file)
                    delete_file = Path(delete_file)

                    delete_file.unlink()
                    files_to_delete.append(delete_file)

                    if delete_file == existing_file:
                        file_content_hashes[hash_string] = file
                        files_to_keep.remove(existing_file)
                        files_to_keep.append(file)
                    continue
                existing_has_suffix = bool(FileName.NUMBERED_SUFFIX.search(existing_file.name))
                current_has_suffix = bool(FileName.NUMBERED_SUFFIX.search(file.name))

                keep_existing = not (existing_has_suffix and not current_has_suffix)

                if keep_existing:
                    files_to_delete.append(file)
                    file.unlink()
                else:
                    files_to_delete.append(existing_file)
                    existing_file.unlink()
                    file_content_hashes[hash_string] = file
                    files_to_keep.remove(existing_file)
                    files_to_keep.append(file)
            else:
                file_content_hashes[hash_string] = file
                files_to_keep.append(file)
        except Exception as e:
            print(f"[red][DEDUPER][/red] Failed to process file [dodger_blue1]{file.name}[/dodger_blue1]: {e}")
            files_to_keep.append(file)

    return files_to_delete


def dedupe_fuzzy(directory: str | Path) -> list[Path]:
    """
    Remove duplicate subtitles in the specified directory based on content similarity.
    Checks only subtitle files in the same language group.
    """
    directory = Path(directory)

    # read all subtitle files and store content, path, tag_count, lang_tag
    subtitle_data = []
    for path in directory.glob("*.srt"):
        if not path.is_file():
            continue
        try:
            content = subhelper.get_srt_content(path)
            if not content:
                continue

            tag_count = count_formatting_tags(content)
            lang_tag = get_base_language_tag(path.name)
            stripped_content = subhelper.get_srt_content(path, True)
            subtitle_data.append([stripped_content, path, tag_count, lang_tag])
        except Exception as e:
            continue

    deleted_files = []
    # group subtitles by language tag
    subtitles_by_lang = defaultdict(list)
    for item in subtitle_data:
        subtitles_by_lang[item[3]].append(item)

    # dedupe within each language group
    for lang, group in subtitles_by_lang.items():
        i = 0
        while i < len(group):
            content_i, path_i, tags_i, _ = group[i]
            j = i + 1
            while j < len(group):
                content_j, path_j, tags_j, _ = group[j]
                try:
                    similarity = fuzz.token_sort_ratio(content_i, content_j)
                    if similarity >= SIMILARITY_THRESHOLD:
                        # decide which to delete based on tag count
                        special_case = prefer_fr_fr(path_i, path_j)
                        if special_case:
                            kept, deleted = special_case
                            deleted_subtitle, kept_subtitle = deleted, kept
                        else:
                            deleted_subtitle, kept_subtitle = (path_j, path_i) if tags_i >= tags_j else (path_i, path_j)
                        try:
                            Path(deleted_subtitle).unlink()
                            normalized_path = remove_numbered_suffix(kept_subtitle)
                        except Exception as e:
                            j += 1
                            continue
                        deleted_files.append(deleted_subtitle)

                        # update the path in the group list if it was normalized
                        if normalized_path != kept_subtitle:
                            if kept_subtitle == path_i:
                                group[i][1] = normalized_path
                            else:
                                group[j][1] = normalized_path
                        # remove deleted entry from the group to avoid future comparisons
                        if deleted_subtitle == path_j:
                            group.pop(j)
                            continue  # j stays the same
                        else:
                            group.pop(i)
                            i -= 1
                            break
                except Exception as e:
                    pass
                j += 1
            i += 1
    return deleted_files


def dedupe(directory: str | Path) -> tuple[list[Path], list[Path]]:
    """
    High level function that performs deduping (md5 hash and fuzzy) of .vtt/.srt subs.
    Operations performed in order:
        - Deletes all non-English forced subtitles.
        - MD5 hash dedupes .vtt files.
        - Converts all .vtt subs to .srt.
        - Second MD5 hash dedupe pass on converted .vtt -> .srt subtitles.
        - Third dedupe pass using fuzzy similarity to dedupe .srt subtitles which would be
          considered worse versions of existing subtitles in the same language group.
        - Fixes en, en-US, and en-GB subtitle file-names assigning the correct tag based on content.
        - Applies -419 or -ES to generic es subtitle file-names if applicaple.
        - Cleans up file-names to remove unnecessary region tags and numbered suffixes.
        - Runs subby's common issue fixer on remaining .srt files.

    Returns a tuple of two lists containing Path objects to all files which were deduped.
    """
    directory = Path(directory)
    # remove forced subs (keeping English forced subs)
    forced_deduped = remove_forced_subtitles(directory)

    # if no subs are left after removing forced, deduping is finished
    if len(subhelper.get_subtitle_files(directory, "vtt")) == 0:
        return [], []

    # dedupe all subs using md5 hash comparison
    # this is done first as it's much quicker than fuzzy deduping
    md5_deduped = dedupe_md5(directory)

    # convert remaining vtt subs to srt
    convert_vtt_to_srt(directory)

    # do a second pass of md5 deduping after conversion to srt
    # this can catch files which have differences in vtt format
    # but which are identical in srt format
    md5_deduped = md5_deduped + dedupe_md5(directory)

    # third dedupe pass is a fuzzy dedupe to potentially catch stray unwanted files
    # which are not exact duplicates, but are worse versions of a sub that already exists
    # e.g. two fr-FR subs one containing formatting tags and one without, keep the one with tags
    fuzzy_deduped = dedupe_fuzzy(directory)

    # rename en, en-US, en-GB properly
    subhelper.fix_us_uk_subtitles(directory)

    # rename es to es-ES or es-419 if a dialect is detected
    subhelper.fix_es_subtitles(directory)

    # fix sdh file-names
    subhelper.fix_sdh_subtitles(directory)

    # clean up the remaining subs file names
    cleanup_filenames(directory)

    # run subby fix common issues on all subs
    fix_common_issues(directory)
    return fuzzy_deduped, md5_deduped, forced_deduped
