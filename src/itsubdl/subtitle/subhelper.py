import re
from collections import Counter
from pathlib import Path

from subby import SubRipFile

from itsubdl.subtitle.subtitlepatterns import SDH, FileName, Tags

US_SPELLING_SET = {
    "analyze", "apologize", "armor", "behavior", "catalog", "canceled", "center", "check", "color", "colorful",
    "counselor", "defense", "enroll", "enrollment", "favorite", "favor", "fiber", "fulfill", "fulfillment", "gray",
    "honor", "humor", "idolize", "instill", "jewelry", "judgment", "labor", "license", "liter", "maneuver", "maximize",
    "memorize", "meter", "modeling", "modeled", "modeler", "mold", "organize", "organization", "parlor", "practice", "program",
    "realize", "recognize", "rumor", "skeptic", "specialty", "theater", "traveling", "traveled", "vigor", "visualize",
    "yogurt", "curb", "neighbor", "paralyze", "offense", "pretense", "ton", "donut", "plow", "smolder", "tire", "likable",
    "labeled", "willful", "aluminum", "aging", "flavor", "endeavor", "sulfur", "distill", "mom", "anemia", "feces", "candor",
    "rigor", "vapor", "counseling", "authorize", "capitalize", "characterize", "criticize", "emphasize", "generalize",
    "equalize", "minimize", "mobilize", "optimize", "summarize", "licorice", "siphon", "pants", "cilantro", "eggplant",
    "scallion", "broil", "plexiglass", "dumpster", "scepter"
}
UK_SPELLING_SET = {
    "analyse", "apologise", "armour", "behaviour", "catalogue", "cancelling", "cancelled", "centre", "cheque",
    "colour", "colourful", "counsellor", "defence", "enrol", "enrolment", "favourite", "favour", "fibre", "fulfil",
    "fulfilment", "grey", "honour", "humour", "idolise", "instil", "jewellery", "judgement", "labour", "licence", "litre",
    "manoeuvre", "maximise", "memorise", "metre", "modelling", "modelled", "modeller", "mould", "organise", "organisation",
    "parlour", "practise", "programme", "realise", "recognise", "rumour", "sceptic", "speciality", "theatre", "travelling",
    "travelled", "vigour", "visualise", "yoghurt", "kerb", "neighbour", "paralyse", "offence", "pretence", "tonne",
    "plough", "smoulder", "tyre", "likeable", "labelled", "wilful", "learnt", "aluminium", "whilst", "ageing", "flavour",
    "endeavour", "sulphur", "distil", "practise", "arse", "maths", "mum", "anaemia", "faeces", "candour", "rigour", "vapour",
    "counselling", "authorise", "capitalise", "characterise", "criticise", "emphasise", "generalise", "equalise", "minimise",
    "mobilise", "optimise", "summarise", "liquorice", "syphon", "nappy", "trousers", "quid", "tosser", "knackered", "courgette",
    "aubergine", "perspex", "sceptre"
}
CASTILIAN_SPELLING_SET = {
    "vosotros", "vale", "móvil", "ordenador", "gilipollas", "zumo", "patata", "conducir", "sobremesa", "grifo",
    "tiovivo", "coche", "camarero", "venga", "genial", "maíz", "aparcamiento", "marido", "tarta", "piso", "pendiente",
    "ascensor", "cazadora", "coste", "enfadado", "quedar", "quedado", "judía", "judías", "césped", "vídeo", "fregona",
    "bragas", "fichero", "apetecer", "majo", "miedica", "repelús", "escaqueado", "chachi", "niñato", "chapuza", "vuestra",
    "vuestro", "hacedlo", "mirad", "concentraos", "mola", "flipado", "guay", "capullo", "puñeta"
}
LATIN_AMERICAN_SPELLING_SET = {
    "carro", "mesero", "mozo", "dale", "celular", "elote", "frijol", "frijoles", "troca", "estacionamiento", "parqueo", "rentarse",
    "lentes", "esposa", "esposo", "departamento", "arete", "aretes", "elevador", "básquetbol", "chamarra", "costo", "boludo",
    "enojado", "refrigerador", "poroto", "anteojos", "jugo", "subte", "computador", "computadora", "pileta", "video",
    "canilla", "trapeador", "archivo", "antojar"
}


def get_subtitle_files(directory: str | Path, extension: str | None = None) -> list[Path]:
    """Get all subtitle files in the specified directory. If extension is None, get all .srt and .vtt"""
    path = Path(directory)
    if extension is None:
        return list(path.glob("*.srt")) + list(path.glob("*.vtt"))
    return list(path.glob(f"*.{extension}"))


def get_srt_content(file_path: str | Path, strip_tags: bool = False) -> str:
    """
    Get the content of the SRT file as one continuous string excluding
    timestamps, indicies, and optionally excluding tags
    """
    file_path = Path(file_path)
    if not file_path or file_path.suffix.lower() != ".srt":
        return ""

    srt = SubRipFile.from_string(file_path.read_text(encoding='utf-8'))
    if not srt:
        return ""

    content = ""
    for line in srt:
        if strip_tags:
            stripped_line_content = Tags.TAG_STRIP.sub('', line.content).strip()
        else:
            stripped_line_content = line.content.strip()
        stripped_line_content = stripped_line_content.replace("…", "...").replace("․", ".")
        content += stripped_line_content + " "

    return content.strip().replace("\n", " ")


def get_srt_words(file_path: str | Path, strip_tags: bool = False) -> list[str] | None:
    """Get the content of an SRT file as a list of words."""
    file_path = Path(file_path)
    if not file_path or file_path.suffix.lower() != ".srt":
        return None

    srt = SubRipFile.from_string(file_path.read_text(encoding='utf-8'))
    if not srt:
        return None

    words = []
    for line in srt:
        if strip_tags:
            stripped_line_content = Tags.TAG_STRIP.sub('', line.content).strip()
        else:
            stripped_line_content = line.content.strip()
        words.extend(re.sub(r'[^a-zà-ÿ ]', '', stripped_line_content.lower()).split())

    return words


def get_unique_filename(file_path: str | Path, used_filenames: set[str] = None) -> Path:
    """
    Get a unique filename by incrementing numeric suffixes if needed.
    If the filename ends with -N (1-2 digits), it increments N until no conflict.
    """
    file_path = Path(file_path)
    path_str = str(file_path)
    if used_filenames is None:
        used_filenames = set()

    # if the path doesn't exist and is not used, return as is
    if not file_path.exists() and path_str not in used_filenames:
        used_filenames.add(path_str)
        return file_path

    stem = file_path.stem
    m = FileName.NUMBERED_SUFFIX.match(stem)

    if m:
        # file already ends in -N, so we start incrementing from N+1
        main_stem = m.group(1)
        i = int(m.group(2)) + 1
    else:
        # file has no numeric suffix, so we start with -1
        main_stem = stem
        i = 1

    while True:
        new_file_path = file_path.parent / f"{main_stem}-{i}{file_path.suffix}"
        new_path_str = str(new_file_path)
        if not new_file_path.exists() and new_path_str not in used_filenames:
            used_filenames.add(new_path_str)
            return new_file_path

        i += 1


def get_dialect(words: list[str], set_a: set[str], set_b: set[str],
                tag_a: str, tag_b: str, neutral_tag: str) -> str:
    """
    Returns the language tag which matches the given spelling sets
    and tags based on the given subtitle content as a word list
    """
    word_counts = Counter(words)

    count_a = sum(word_counts[w] for w in set_a if w in word_counts)
    count_b = sum(word_counts[w] for w in set_b if w in word_counts)

    if count_a > count_b * 1.5:
        return tag_a
    elif count_b > count_a * 1.5:
        return tag_b
    else:
        return neutral_tag


def is_subtitle_file(path: str | Path) -> bool:
    """Returns True if the file is a subtitle file, False otherwise."""
    return Path(path).suffix.lower() in ('.srt', '.vtt')


def is_sdh_subtitle(file_path: str | Path) -> bool:
    """Use a simple heuristic to detect if a subtitle file is SDH with weighted pattern scoring."""
    if not file_path:
        return False
    file_path = Path(file_path)
    if file_path.suffix.lower() != ".srt":
        return False
    content = get_srt_content(file_path, True)

    sdh_score = 0.0

    # ♪ or ♫
    sdh_score += len(SDH.MUSIC_NOTES.findall(content)) * 2
    # [ ... ]
    sdh_score += len(SDH.BRACKETS.findall(content)) * 2
    # ( ... )
    unwanted_suffixes = ["ar", "ja", "ko", "th", "yue-Hant", "zh", "zh-Hans", "zh-Hant"]
    if not any(file_path.stem.lower().endswith(suffix) for suffix in unwanted_suffixes):
        sdh_score += len(SDH.PARENTHESIS.findall(content)) * 0.4
    # JOHN: John:
    sdh_score += len(SDH.SPEAKER.findall(content)) * 0.4

    return sdh_score >= 45


def strip_numbered_suffix(filename: str) -> str:
    """
    Strips a 1 or 2 digit numbered suffix e.g. "-1" or "-20"
    from the end of the string if it exists
    """
    if not filename:
        return filename
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix

    m = FileName.NUMBERED_SUFFIX.match(stem)
    if m:
        new_stem = m.group(1)
    else:
        new_stem = stem

    return f"{new_stem}{suffix}"


def fix_sdh_subtitles(folder_path: str | Path):
    """
    Add [sdh] tag if it is missing to a subtitle file
    based on subtitle content hueristics.
    """
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        print(f"{folder_path} is not a valid directory")
        return

    srt_files = get_subtitle_files(folder_path, "srt")
    if not srt_files:
        return

    for srt_file in srt_files:
        if not is_sdh_subtitle(srt_file):
            continue

        # skip if [sdh] already in stem
        if "[sdh]" in srt_file.stem:
            continue

        stem = srt_file.stem
        suffix = srt_file.suffix
        parent = srt_file.parent

        # detect numeric suffix (e.g., -1, -2) at the end of the stem
        m = FileName.NUMBERED_SUFFIX.match(stem)
        if m:
            main_stem = m.group(1)
            numeric_suffix = f"-{m.group(2)}"
        else:
            main_stem = stem
            numeric_suffix = ""

        # insert [sdh] before numeric suffix
        new_stem = f"{main_stem}[sdh]{numeric_suffix}"
        desired_path = parent / f"{new_stem}{suffix}"

        # get safe filename
        final_path = get_unique_filename(desired_path)

        # rename
        if final_path != srt_file:
            try:
                srt_file.rename(final_path)
            except Exception as e:
                print(f"Failed to rename {srt_file} -> {final_path}: {e}")
                pass


def fix_us_uk_filename(file_path: str | Path) -> Path:
    """
    Detect whether a subtitle is US or UK English based on word spellings,
    then rename the file with an appropriate language tag.
    """
    file_path = Path(file_path)
    words = get_srt_words(file_path, True)
    if not words:
        return

    lang_tag = get_dialect(
        words,
        US_SPELLING_SET, UK_SPELLING_SET,
        tag_a="en-US",
        tag_b="en-GB",
        neutral_tag="en"
    )

    # split stem into base and bracket suffix
    stem = file_path.stem
    m = re.match(r'^(.*?)(\[[^\]]*\])?$', stem)
    base = m.group(1)
    bracket = m.group(2) or ''

    # detect current language tag in base
    current_tag_match = re.search(r'\.en(-US|-GB)?$', base, re.IGNORECASE)
    current_tag = current_tag_match.group(0)[1:] if current_tag_match else None

    # only replace if different from detected
    if current_tag != lang_tag:
        base = re.sub(r'\.en(-US|-GB)?$', '', base, flags=re.IGNORECASE)
        new_name = f"{base}.{lang_tag}{bracket}"
        new_file_path = get_unique_filename(file_path.with_name(f"{new_name}{file_path.suffix}"))
        if not new_file_path.exists():
            file_path.rename(new_file_path)
            return new_file_path


def fix_us_uk_subtitles(folder_path, recursive: bool = False):
    """
    Fixes all English subtitles to be tagged with the correct dialect (en-US/en-GB).
    If no dialect could be detected, the language tag will be set to "en".
    Parameters:
        folder_path: Path to the folder containing subtitle files.
        recursive: If True, search subfolders recursively.
    """
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        print(f"{folder_path} is not a valid directory")
        return

    glob_pattern = "**/*" if recursive else "*"

    for file_path in folder_path.glob(f"{glob_pattern}.srt"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".srt"}:
            continue
        if FileName.ENGLISH_LANG_TAG.search(file_path.stem):
            fix_us_uk_filename(file_path)


def fix_es_filename(file_path: str | Path) -> Path:
    """
    Detect whether a subtitle is es-ES or es-419 Spanish based on word spellings,
    then rename the file with an appropriate language tag.
    """
    file_path = Path(file_path)
    if not re.search(r'\.es(\[sdh\])?$', file_path.stem, re.IGNORECASE):
        return
    words = get_srt_words(file_path, True)
    if not words:
        return

    lang_tag = get_dialect(
        words,
        CASTILIAN_SPELLING_SET,
        LATIN_AMERICAN_SPELLING_SET,
        tag_a="es-ES",
        tag_b="es-419",
        neutral_tag="es"
    )

    # split stem into base and bracket suffix
    stem = file_path.stem
    m = re.match(r'^(.*?)(\[[^\]]*\])?$', stem)
    base = m.group(1)
    bracket = m.group(2) or ''

    # detect current language tag in base
    current_tag_match = re.search(r'\.es$', base, re.IGNORECASE)
    current_tag = current_tag_match.group(0)[1:] if current_tag_match else None

    # only replace if different from detected
    if current_tag != lang_tag:
        base = re.sub(r'\.es?$', '', base, flags=re.IGNORECASE)
        new_name = f"{base}.{lang_tag}{bracket}"
        new_file_path = get_unique_filename(file_path.with_name(f"{new_name}{file_path.suffix}"))
        if not new_file_path.exists():
            file_path.rename(new_file_path)
            return new_file_path


def fix_es_subtitles(folder_path, recursive: bool = False):
    """
    Fixes all English subtitles to be tagged with the correct dialect (en-US/en-GB).
    If no dialect could be detected, the language tag will be set to "en".
    Parameters:
        folder_path: Path to the folder containing subtitle files.
        recursive: If True, search subfolders recursively.
    """
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        print(f"{folder_path} is not a valid directory")
        return

    glob_pattern = "**/*" if recursive else "*"

    for file_path in folder_path.glob(f"{glob_pattern}.srt"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".srt"}:
            continue
        fix_es_filename(file_path)
