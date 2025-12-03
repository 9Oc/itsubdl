import re


class FileName:
    ENGLISH_LANG_TAG = re.compile(r'\.en(-US|-GB)?(\[(sdh|forced)\])?$', re.IGNORECASE)
    # NUMBERED_SUFFIX = re.compile(r'^(.*?)-(\d+)(?:\.[^.]+)?$', re.IGNORECASE)
    NUMBERED_SUFFIX = re.compile(r'^(.*?)(?<!\d)-(\d{1,2})(\.[^.]+)?$', re.IGNORECASE)
    CLEANUP_RULES = [
        (re.compile(r'cmn-Hant'), 'zh-Hant', 'cmn'),
        (re.compile(r'cmn-Hans'), 'zh-Hans', 'cmn'),
        (re.compile(r'\.cc'), '[sdh]', 'cc'),
        (re.compile(r'\.forced'), '[forced]', 'forced'),
    ]
    SIMPLIFY_LOCALES = [
        'ar-001', 'ar-SA', 'bg-BG', 'ca-ES', 'cs-CZ', 'da-DK', 'de-DE', 'el-GR',
        'et-EE', 'et-ET', 'eu-ES', 'fi-FI', 'fil-PH', 'gl-ES', 'he-IL', 'hi-IN',
        'hr-HR', 'hu-HU', 'id-ID', 'is-IS', 'it-IT', 'ja-JP', 'kn-IN', 'ko-KR',
        'lv-LV', 'lt-LT', 'mk-MK', 'ml-IN', 'mr-IN', 'ms-MY', 'nb-NO', 'nl-NL',
        'nn-NO', 'no-NO', 'pl-PL', 'ro-RO', 'ru-RU', 'sk-SK', 'sl-SI', 'sl-SL',
        'sq-AL', 'sr-Latn', 'sr-RS', 'sv-SE', 'ta-IN', 'te-IN', 'th-TH', 'tr-TR',
        'uk-UA', 'vi-VN'
    ]


class SDH:
    BRACKETS = re.compile(r"\[.*?\]")
    PARENTHESIS = re.compile(r"\(.*?\)")
    SPEAKER = re.compile(r"^[A-Za-z0-9_]+:\s")  # e.g. JOHN: Hello
    MUSIC_NOTES = re.compile(r"[♪♫]")


class Tags:
    TAG_STRIP = re.compile(
        r'</?i>|</?u>|</?b>|{\s*\\an[1-9]\s*}|<font.*?>|</font>', flags=re.IGNORECASE)
    TAG_COUNT = re.compile(r'</?i>|{\s*\\an8\s*}', flags=re.IGNORECASE)


class Timestamp:
    SRT_TIMESTAMP = re.compile(r'\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?\s*-->\s*\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?(?:\s+.*)?')
