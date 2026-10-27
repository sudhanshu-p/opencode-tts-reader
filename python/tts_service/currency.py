"""Expand currency shorthand into words the speech engine reads naturally.

Handles prefix and suffix symbols (``$13B`` and ``13B$``), ISO codes
(``USD 13B`` and ``13B USD``), and magnitude suffixes (``K``, ``M``, ``B``,
``T``, ``bn``, ``Cr``, ``L``). Amounts in prose are left alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple


class _Unit(NamedTuple):
    singular: str
    plural: str


def _unit(singular: str, plural: str | None = None) -> _Unit:
    return _Unit(singular, singular + "s" if plural is None else plural)


_SYMBOL_UNITS: dict[str, _Unit] = {
    "US$": _unit("US dollar"),
    "CA$": _unit("Canadian dollar"),
    "C$": _unit("Canadian dollar"),
    "AU$": _unit("Australian dollar"),
    "A$": _unit("Australian dollar"),
    "SG$": _unit("Singapore dollar"),
    "S$": _unit("Singapore dollar"),
    "HK$": _unit("Hong Kong dollar"),
    "NZ$": _unit("New Zealand dollar"),
    "MX$": _unit("Mexican peso"),
    "NT$": _unit("New Taiwan dollar"),
    "RD$": _unit("Dominican peso"),
    "TT$": _unit("Trinidad and Tobago dollar"),
    "EC$": _unit("East Caribbean dollar"),
    "BD$": _unit("Bermudian dollar"),
    "KY$": _unit("Cayman Islands dollar"),
    "FJ$": _unit("Fijian dollar"),
    "AR$": _unit("Argentine peso"),
    "CL$": _unit("Chilean peso"),
    "CO$": _unit("Colombian peso"),
    "J$": _unit("Jamaican dollar"),
    "B$": _unit("Bahamian dollar"),
    "R$": _unit("Brazilian real", "Brazilian reais"),
    "CN¥": _unit("Chinese yuan", "Chinese yuan"),
    "JP¥": _unit("Japanese yen", "Japanese yen"),
    "$": _unit("dollar"),
    "€": _unit("euro"),
    "£": _unit("pound"),
    "¥": _unit("yen", "yen"),
    "₹": _unit("rupee"),
    "₩": _unit("won", "won"),
    "₽": _unit("ruble"),
    "₺": _unit("lira"),
    "₪": _unit("shekel"),
    "₫": _unit("dong", "dong"),
    "₴": _unit("hryvnia"),
    "₦": _unit("naira"),
    "₱": _unit("peso"),
    "฿": _unit("baht", "baht"),
    "₡": _unit("colon", "colones"),
    "₲": _unit("guarani", "guaranies"),
    "₵": _unit("cedi"),
    "₸": _unit("tenge", "tenge"),
    "₭": _unit("kip", "kip"),
    "₮": _unit("tugrik"),
    "₾": _unit("lari", "lari"),
    "₼": _unit("manat"),
    "֏": _unit("dram"),
    "؋": _unit("afghani"),
    "﷼": _unit("rial"),
    "元": _unit("yuan", "yuan"),
    "円": _unit("yen", "yen"),
    "원": _unit("won", "won"),
    "zł": _unit("zloty", "zlotys"),
    "Kč": _unit("koruna", "korunas"),
    "kr": _unit("krona", "kronor"),
    "lei": _unit("leu", "lei"),
    "лв": _unit("lev", "leva"),
    "ден": _unit("denar"),
    "руб": _unit("ruble"),
    "грн": _unit("hryvnia"),
    "сум": _unit("som", "som"),
    "Rs.": _unit("rupee"),
    "Rs": _unit("rupee"),
    "RM": _unit("ringgit", "ringgit"),
    "Rp": _unit("rupiah"),
    "S/.": _unit("sol", "soles"),
    "Bs.": _unit("boliviano"),
    "د.إ": _unit("dirham"),
    "ر.س": _unit("riyal"),
    "ج.م": _unit("Egyptian pound"),
    "د.ك": _unit("Kuwaiti dinar"),
    "د.ب": _unit("Bahraini dinar"),
    "ر.ع": _unit("Omani rial"),
    "د.ا": _unit("Jordanian dinar"),
    "ل.ل": _unit("Lebanese pound"),
    "د.ت": _unit("Tunisian dinar"),
    "د.ج": _unit("Algerian dinar"),
    "د.م": _unit("Moroccan dirham"),
    "د.ل": _unit("Libyan dinar"),
    "د.ع": _unit("Iraqi dinar"),
    "د.ي": _unit("Yemeni rial"),
}

_CODE_UNITS: dict[str, _Unit] = {
    "USD": _unit("US dollar"),
    "EUR": _unit("euro"),
    "GBP": _unit("British pound"),
    "JPY": _unit("yen", "yen"),
    "CNY": _unit("Chinese yuan", "Chinese yuan"),
    "RMB": _unit("Chinese yuan", "Chinese yuan"),
    "INR": _unit("rupee"),
    "CAD": _unit("Canadian dollar"),
    "AUD": _unit("Australian dollar"),
    "NZD": _unit("New Zealand dollar"),
    "CHF": _unit("Swiss franc"),
    "SEK": _unit("Swedish krona", "Swedish kronor"),
    "NOK": _unit("Norwegian krone", "Norwegian kroner"),
    "DKK": _unit("Danish krone", "Danish kroner"),
    "ISK": _unit("Icelandic krona", "Icelandic kronur"),
    "PLN": _unit("Polish zloty", "Polish zlotys"),
    "CZK": _unit("Czech koruna", "Czech korunas"),
    "HUF": _unit("Hungarian forint"),
    "RON": _unit("Romanian leu", "Romanian lei"),
    "BGN": _unit("Bulgarian lev", "Bulgarian leva"),
    "RSD": _unit("Serbian dinar"),
    "MKD": _unit("Macedonian denar"),
    "RUB": _unit("Russian ruble"),
    "UAH": _unit("Ukrainian hryvnia"),
    "TRY": _unit("Turkish lira"),
    "ILS": _unit("Israeli shekel"),
    "AED": _unit("UAE dirham"),
    "SAR": _unit("Saudi riyal"),
    "QAR": _unit("Qatari riyal"),
    "KWD": _unit("Kuwaiti dinar"),
    "BHD": _unit("Bahraini dinar"),
    "OMR": _unit("Omani rial"),
    "JOD": _unit("Jordanian dinar"),
    "EGP": _unit("Egyptian pound"),
    "ZAR": _unit("South African rand", "South African rand"),
    "NGN": _unit("Nigerian naira"),
    "KES": _unit("Kenyan shilling"),
    "GHS": _unit("Ghanaian cedi"),
    "MAD": _unit("Moroccan dirham"),
    "TND": _unit("Tunisian dinar"),
    "DZD": _unit("Algerian dinar"),
    "BRL": _unit("Brazilian real", "Brazilian reais"),
    "MXN": _unit("Mexican peso"),
    "ARS": _unit("Argentine peso"),
    "CLP": _unit("Chilean peso"),
    "COP": _unit("Colombian peso"),
    "PEN": _unit("Peruvian sol", "Peruvian soles"),
    "UYU": _unit("Uruguayan peso"),
    "KRW": _unit("South Korean won", "South Korean won"),
    "SGD": _unit("Singapore dollar"),
    "HKD": _unit("Hong Kong dollar"),
    "TWD": _unit("New Taiwan dollar"),
    "THB": _unit("Thai baht", "Thai baht"),
    "IDR": _unit("Indonesian rupiah"),
    "MYR": _unit("Malaysian ringgit", "Malaysian ringgit"),
    "PHP": _unit("Philippine peso"),
    "VND": _unit("Vietnamese dong", "Vietnamese dong"),
    "PKR": _unit("Pakistani rupee"),
    "BDT": _unit("Bangladeshi taka"),
    "LKR": _unit("Sri Lankan rupee"),
    "NPR": _unit("Nepalese rupee"),
    "MMK": _unit("Myanmar kyat"),
    "KHR": _unit("Cambodian riel"),
    "LAK": _unit("Lao kip", "Lao kip"),
    "MNT": _unit("Mongolian tugrik"),
    "KZT": _unit("Kazakhstani tenge", "Kazakhstani tenge"),
    "UZS": _unit("Uzbekistani som", "Uzbekistani som"),
    "AZN": _unit("Azerbaijani manat"),
    "GEL": _unit("Georgian lari", "Georgian lari"),
    "AMD": _unit("Armenian dram"),
    "BYN": _unit("Belarusian ruble"),
    "MDL": _unit("Moldovan leu", "Moldovan lei"),
    "BAM": _unit("Bosnia-Herzegovina convertible mark"),
    "XOF": _unit("West African CFA franc"),
    "XAF": _unit("Central African CFA franc"),
    "XCD": _unit("East Caribbean dollar"),
    "TTD": _unit("Trinidad and Tobago dollar"),
    "JMD": _unit("Jamaican dollar"),
    "BSD": _unit("Bahamian dollar"),
    "BBD": _unit("Barbadian dollar"),
    "BZD": _unit("Belize dollar"),
    "GTQ": _unit("Guatemalan quetzal", "Guatemalan quetzales"),
    "CRC": _unit("Costa Rican colon", "Costa Rican colones"),
    "DOP": _unit("Dominican peso"),
    "HNL": _unit("Honduran lempira"),
    "NIO": _unit("Nicaraguan cordoba"),
    "PAB": _unit("Panamanian balboa"),
    "PYG": _unit("Paraguayan guarani", "Paraguayan guaranies"),
    "BOB": _unit("Bolivian boliviano"),
    "VES": _unit("Venezuelan bolivar"),
    "CUP": _unit("Cuban peso"),
    "HTG": _unit("Haitian gourde"),
    "ETB": _unit("Ethiopian birr", "Ethiopian birr"),
    "TZS": _unit("Tanzanian shilling"),
    "UGX": _unit("Ugandan shilling"),
    "RWF": _unit("Rwandan franc"),
    "BIF": _unit("Burundian franc"),
    "MWK": _unit("Malawian kwacha"),
    "ZMW": _unit("Zambian kwacha"),
    "MZN": _unit("Mozambican metical", "Mozambican meticais"),
    "AOA": _unit("Angolan kwanza"),
    "NAD": _unit("Namibian dollar"),
    "BWP": _unit("Botswana pula", "Botswana pula"),
    "MUR": _unit("Mauritian rupee"),
    "SCR": _unit("Seychellois rupee"),
    "MVR": _unit("Maldivian rufiyaa"),
    "AFN": _unit("Afghan afghani"),
    "IQD": _unit("Iraqi dinar"),
    "IRR": _unit("Iranian rial"),
    "SYP": _unit("Syrian pound"),
    "LBP": _unit("Lebanese pound"),
    "YER": _unit("Yemeni rial"),
    "SDG": _unit("Sudanese pound"),
    "LYD": _unit("Libyan dinar"),
    "XPF": _unit("CFP franc"),
    "FJD": _unit("Fijian dollar"),
    "PGK": _unit("Papua New Guinean kina", "Papua New Guinean kina"),
    "WST": _unit("Samoan tala", "Samoan tala"),
    "TOP": _unit("Tongan paanga", "Tongan paanga"),
    "VUV": _unit("Vanuatu vatu", "Vanuatu vatu"),
    "SBD": _unit("Solomon Islands dollar"),
    "KGS": _unit("Kyrgyzstani som", "Kyrgyzstani som"),
    "TJS": _unit("Tajikistani somoni"),
    "TMT": _unit("Turkmenistani manat"),
    "BTN": _unit("Bhutanese ngultrum"),
    "BND": _unit("Brunei dollar"),
}

_MAGNITUDE_WORDS: dict[str, str] = {
    "THOUSAND": "thousand",
    "MILLION": "million",
    "BILLION": "billion",
    "TRILLION": "trillion",
    "CRORE": "crore",
    "LAKH": "lakh",
    "LAC": "lakh",
    "K": "thousand",
    "M": "million",
    "MN": "million",
    "B": "billion",
    "BN": "billion",
    "T": "trillion",
    "TN": "trillion",
    "TRN": "trillion",
    "CR": "crore",
    "L": "lakh",
}

_MAGNITUDE = (
    r"(?i:thousand|million|billion|trillion|crore|lakh|lac|"
    r"trn|bn|mn|tn|cr|k|m|b|t|l)"
)
_MAGNITUDE_ABBR = r"(?i:trn|bn|mn|tn|cr|lakh|lac|k|m|b|t|l)"
_AMOUNT = r"(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)"

_WORD_TO_UNIT: dict[str, _Unit] = {}
for _entry in (*_SYMBOL_UNITS.values(), *_CODE_UNITS.values()):
    _WORD_TO_UNIT.setdefault(_entry.singular.lower(), _entry)
    _WORD_TO_UNIT.setdefault(_entry.plural.lower(), _entry)

_SYNONYMS: dict[str, _Unit] = {
    "buck": _SYMBOL_UNITS["$"],
    "bucks": _SYMBOL_UNITS["$"],
    "quid": _SYMBOL_UNITS["£"],
    "pence": _unit("penny", "pence"),
}
_WORD_TO_UNIT.update(_SYNONYMS)


def _alternation(values: Iterable[str]) -> str:
    return "|".join(
        re.escape(value) for value in sorted(values, key=lambda item: (-len(item), item))
    )


# Codes that are also common English words or technical acronyms. They are only
# expanded when a magnitude makes the money reading unambiguous ("AMD 13B") or
# when the code follows the amount, which is far less common in prose.
_AMBIGUOUS_CODES = {
    "ALL",
    "AMD",
    "BAM",
    "BOB",
    "BSD",
    "BTN",
    "COP",
    "CUP",
    "DOP",
    "GEL",
    "IRR",
    "LBP",
    "MAD",
    "MNT",
    "NIO",
    "PEN",
    "PHP",
    "RON",
    "SCR",
    "SDG",
    "TOP",
    "TRY",
}

_SAFE_CODE_UNITS = {
    code: unit for code, unit in _CODE_UNITS.items() if code not in _AMBIGUOUS_CODES
}
_AMBIGUOUS_CODE_UNITS = {
    code: unit for code, unit in _CODE_UNITS.items() if code in _AMBIGUOUS_CODES
}

_SYMBOL_ALT = _alternation(_SYMBOL_UNITS)
_SAFE_CODE_ALT = _alternation(_SAFE_CODE_UNITS)
_AMBIGUOUS_CODE_ALT = _alternation(_AMBIGUOUS_CODE_UNITS)
_WORD_ALT = _alternation(_WORD_TO_UNIT)
_SYMBOL_CHARS = "".join(sorted({key for key in _SYMBOL_UNITS if len(key) == 1}))
_SYMBOL_CLASS = re.escape(_SYMBOL_CHARS)

_CODE_PREFIX_RE = re.compile(
    rf"(?<!\w)(?P<code>{_SAFE_CODE_ALT})[ \t]*(?P<amount>{_AMOUNT})"
    rf"(?:[ \t]*(?P<magnitude>{_MAGNITUDE}))?"
    rf"(?:[ \t]+(?P<word>(?i:{_WORD_ALT})))?"
    rf"(?!\w)"
)

_CODE_PREFIX_MAGNITUDE_RE = re.compile(
    rf"(?<!\w)(?P<code>{_AMBIGUOUS_CODE_ALT})[ \t]*(?P<amount>{_AMOUNT})"
    rf"[ \t]*(?P<magnitude>{_MAGNITUDE_ABBR})"
    rf"(?:[ \t]+(?P<word>(?i:{_WORD_ALT})))?"
    rf"(?!\w)"
)

_CODE_SUFFIX_RE = re.compile(
    rf"(?<![\w.^_=+*/<>{{}}])(?P<amount>{_AMOUNT})"
    rf"(?:[ \t]*(?P<magnitude>{_MAGNITUDE}))?[ \t]*"
    rf"(?P<code>{_SAFE_CODE_ALT})(?!\w)"
)

_CODE_SUFFIX_MAGNITUDE_RE = re.compile(
    rf"(?<![\w.^_=+*/<>{{}}])(?P<amount>{_AMOUNT})"
    rf"[ \t]*(?P<magnitude>{_MAGNITUDE_ABBR})[ \t]*"
    rf"(?P<code>{_AMBIGUOUS_CODE_ALT})(?!\w)"
)

_SYMBOL_PREFIX_RE = re.compile(
    rf"(?<![\w{_SYMBOL_CLASS}])(?P<symbol>{_SYMBOL_ALT})[ \t]*"
    rf"(?P<amount>{_AMOUNT})"
    rf"(?:[ \t]*(?P<magnitude>{_MAGNITUDE}))?"
    rf"(?:[ \t]+(?P<word>(?i:{_WORD_ALT})))?"
    rf"(?![\w{_SYMBOL_CLASS}])"
)

_SYMBOL_SUFFIX_RE = re.compile(
    rf"(?<![\w.^_=+*/<>{{}}{_SYMBOL_CLASS}])(?P<amount>{_AMOUNT})"
    rf"(?:[ \t]*(?P<magnitude>{_MAGNITUDE}))?[ \t]*"
    rf"(?P<symbol>{_SYMBOL_ALT})(?![\w{_SYMBOL_CLASS}])"
)

_WORD_MAGNITUDE_RE = re.compile(
    rf"(?<![\w.])(?P<amount>{_AMOUNT})[ \t]*"
    rf"(?P<magnitude>{_MAGNITUDE_ABBR})[ \t]+"
    rf"(?P<word>(?i:{_WORD_ALT}))(?!\w)"
)

_PATTERNS = (
    _CODE_PREFIX_RE,
    _CODE_PREFIX_MAGNITUDE_RE,
    _CODE_SUFFIX_RE,
    _CODE_SUFFIX_MAGNITUDE_RE,
    _SYMBOL_PREFIX_RE,
    _SYMBOL_SUFFIX_RE,
    _WORD_MAGNITUDE_RE,
)


def _clean_amount(raw: str) -> str:
    """Drop thousands separators and accept a comma as a decimal mark."""
    if "," not in raw:
        return raw
    if "." in raw:
        return raw.replace(",", "")
    parts = raw.split(",")
    if len(parts) == 2 and len(parts[1]) != 3:
        return f"{parts[0]}.{parts[1]}"
    if all(len(part) == 3 for part in parts[1:]):
        return "".join(parts)
    return raw.replace(",", "")


def _is_one(amount: str) -> bool:
    try:
        return float(amount) == 1.0
    except ValueError:
        return False


def _pick(unit: _Unit, plural: bool) -> str:
    return unit.plural if plural else unit.singular


def _magnitude_word(raw: str) -> str:
    return _MAGNITUDE_WORDS.get(raw.upper(), raw.lower())


def _format(amount: str, magnitude: str | None, unit_name: str) -> str:
    if magnitude is None:
        return f"{amount} {unit_name}"
    return f"{amount} {_magnitude_word(magnitude)} {unit_name}"


def _replace(match: re.Match[str]) -> str:
    groups = match.groupdict()
    amount = _clean_amount(groups["amount"])
    magnitude = groups.get("magnitude")
    word = groups.get("word")
    symbol = groups.get("symbol")
    code = groups.get("code")

    plural = magnitude is not None or not _is_one(amount)

    if word is not None:
        unit = _WORD_TO_UNIT.get(word.lower())
        if unit is None:
            return match.group(0)
        return _format(amount, magnitude, _pick(unit, plural))

    if symbol is not None:
        unit = _SYMBOL_UNITS.get(symbol)
    elif code is not None:
        unit = _CODE_UNITS.get(code.upper())
    else:
        unit = None

    if unit is None:
        return match.group(0)
    return _format(amount, magnitude, _pick(unit, plural))


def normalize_currency(text: str) -> str:
    """Rewrite currency shorthand in ``text`` as spoken words."""
    for pattern in _PATTERNS:
        text = pattern.sub(_replace, text)
    return text
