from typing import Literal

# List of supported country codes for Serper.dev (Google Search API)
# Based on ISO 3166-1 alpha-2
SUPPORTED_COUNTRIES = Literal[
    "af", "al", "dz", "as", "ad", "ao", "ag", "ar", "am", "aw", "au", "at", "az",
    "bs", "bh", "bd", "bb", "by", "be", "bz", "bj", "bm", "bt", "bo", "ba", "bw",
    "br", "bn", "bg", "bf", "bi", "kh", "cm", "ca", "cv", "cf", "td", "cl", "co",
    "km", "cg", "cd", "ck", "cr", "ci", "hr", "cu", "cw", "cy", "cz", "dk", "dj",
    "dm", "do", "ec", "eg", "sv", "gq", "er", "ee", "sz", "et", "fj", "fi", "fr",
    "ga", "gm", "ge", "de", "gh", "gi", "gr", "gl", "gd", "gp", "gu", "gt", "gn",
    "gw", "gy", "ht", "hn", "hk", "hu", "is", "in", "id", "ir", "iq", "ie", "il",
    "it", "jm", "jp", "jo", "kz", "ke", "ki", "kw", "kg", "la", "lv", "lb", "ls",
    "lr", "ly", "li", "lt", "lu", "mo", "mg", "mw", "my", "mv", "ml", "mt", "mh",
    "mr", "mu", "mx", "fm", "md", "mc", "mn", "me", "ms", "ma", "mz", "mm", "na",
    "nr", "np", "nl", "nc", "nz", "ni", "ne", "ng", "nu", "mk", "no", "om", "pk",
    "pw", "ps", "pa", "pg", "py", "pe", "ph", "pn", "pl", "pt", "pr", "qa", "re",
    "ro", "ru", "rw", "bl", "sh", "kn", "lc", "mf", "pm", "vc", "ws", "sm", "st",
    "sa", "sn", "rs", "sc", "sl", "sg", "sx", "sk", "si", "sb", "so", "za", "kr",
    "ss", "es", "lk", "sd", "sr", "se", "ch", "sy", "tw", "tj", "tz", "th", "tl",
    "tg", "tk", "to", "tt", "tn", "tr", "tm", "tc", "tv", "ug", "ua", "ae", "uk",
    "us", "uy", "uz", "vu", "ve", "vn", "wf", "ye", "zm", "zw"
]

# Set for runtime validation
VALID_COUNTRY_CODES = {
    "af", "al", "dz", "as", "ad", "ao", "ag", "ar", "am", "aw", "au", "at", "az",
    "bs", "bh", "bd", "bb", "by", "be", "bz", "bj", "bm", "bt", "bo", "ba", "bw",
    "br", "bn", "bg", "bf", "bi", "kh", "cm", "ca", "cv", "cf", "td", "cl", "co",
    "km", "cg", "cd", "ck", "cr", "ci", "hr", "cu", "cw", "cy", "cz", "dk", "dj",
    "dm", "do", "ec", "eg", "sv", "gq", "er", "ee", "sz", "et", "fj", "fi", "fr",
    "ga", "gm", "ge", "de", "gh", "gi", "gr", "gl", "gd", "gp", "gu", "gt", "gn",
    "gw", "gy", "ht", "hn", "hk", "hu", "is", "in", "id", "ir", "iq", "ie", "il",
    "it", "jm", "jp", "jo", "kz", "ke", "ki", "kw", "kg", "la", "lv", "lb", "ls",
    "lr", "ly", "li", "lt", "lu", "mo", "mg", "mw", "my", "mv", "ml", "mt", "mh",
    "mr", "mu", "mx", "fm", "md", "mc", "mn", "me", "ms", "ma", "mz", "mm", "na",
    "nr", "np", "nl", "nc", "nz", "ni", "ne", "ng", "nu", "mk", "no", "om", "pk",
    "pw", "ps", "pa", "pg", "py", "pe", "ph", "pn", "pl", "pt", "pr", "qa", "re",
    "ro", "ru", "rw", "bl", "sh", "kn", "lc", "mf", "pm", "vc", "ws", "sm", "st",
    "sa", "sn", "rs", "sc", "sl", "sg", "sx", "sk", "si", "sb", "so", "za", "kr",
    "ss", "es", "lk", "sd", "sr", "se", "ch", "sy", "tw", "tj", "tz", "th", "tl",
    "tg", "tk", "to", "tt", "tn", "tr", "tm", "tc", "tv", "ug", "ua", "ae", "uk",
    "us", "uy", "uz", "vu", "ve", "vn", "wf", "ye", "zm", "zw", "global"
}
