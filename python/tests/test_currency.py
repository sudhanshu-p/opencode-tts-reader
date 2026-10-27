from tts_service.currency import normalize_currency
from tts_service.text import filter_for_speech


def clean(raw: str) -> str:
    return " ".join(filter_for_speech(raw).split())


def test_symbol_prefix_magnitudes() -> None:
    assert normalize_currency("$13B") == "13 billion dollars"
    assert normalize_currency("$13.5M") == "13.5 million dollars"
    assert normalize_currency("€2.5M") == "2.5 million euros"
    assert normalize_currency("£500k") == "500 thousand pounds"
    assert normalize_currency("¥13B") == "13 billion yen"


def test_symbol_suffix_magnitudes() -> None:
    assert normalize_currency("13B$") == "13 billion dollars"
    assert normalize_currency("13 B$") == "13 billion dollars"
    assert normalize_currency("13.5€") == "13.5 euros"
    assert normalize_currency("13zł") == "13 zlotys"
    assert normalize_currency("13Kč") == "13 korunas"


def test_indian_magnitudes() -> None:
    assert normalize_currency("₹5Cr") == "5 crore rupees"
    assert normalize_currency("₹5L") == "5 lakh rupees"


def test_singular_and_plural_units() -> None:
    assert normalize_currency("$1") == "1 dollar"
    assert normalize_currency("€1") == "1 euro"
    assert normalize_currency("₹1") == "1 rupee"
    assert normalize_currency("$1B") == "1 billion dollars"


def test_iso_codes_before_and_after_amounts() -> None:
    assert normalize_currency("USD 13B") == "13 billion US dollars"
    assert normalize_currency("13B USD") == "13 billion US dollars"
    assert normalize_currency("SEK 2M") == "2 million Swedish kronor"
    assert normalize_currency("13B EUR") == "13 billion euros"
    assert normalize_currency("USD 13 billion") == "13 billion US dollars"


def test_magnitude_followed_by_currency_word() -> None:
    assert normalize_currency("13B dollars") == "13 billion dollars"
    assert normalize_currency("13bn euros") == "13 billion euros"
    assert normalize_currency("13 million dollars") == "13 million dollars"


def test_qualified_symbols() -> None:
    assert normalize_currency("US$1") == "1 US dollar"
    assert normalize_currency("C$5M") == "5 million Canadian dollars"
    assert normalize_currency("HK$3M") == "3 million Hong Kong dollars"
    assert normalize_currency("R$2B") == "2 billion Brazilian reais"
    assert normalize_currency("NZ$10k") == "10 thousand New Zealand dollars"


def test_currency_words_are_added_when_spelled_magnitude_follows() -> None:
    assert normalize_currency("$13 million") == "13 million dollars"
    assert normalize_currency("$13 million dollars") == "13 million dollars"
    assert normalize_currency("£2 billion") == "2 billion pounds"


def test_amount_separators() -> None:
    assert normalize_currency("$13,000") == "13000 dollars"
    assert normalize_currency("$1,234.56") == "1234.56 dollars"
    assert normalize_currency("13,5€") == "13.5 euros"


def test_mixed_code_and_symbol() -> None:
    assert normalize_currency("$13B USD") == "13 billion US dollars"


def test_multiple_amounts_in_one_sentence() -> None:
    text = "Revenue was $13B and profit was $2.5M."
    assert normalize_currency(text) == (
        "Revenue was 13 billion dollars and profit was 2.5 million dollars."
    )


def test_plain_prose_is_untouched() -> None:
    assert normalize_currency("13 dollars") == "13 dollars"
    assert normalize_currency("13 billion dollars") == "13 billion dollars"
    assert normalize_currency("It is 13ft wide.") == "It is 13ft wide."
    assert normalize_currency("Version 13B is out.") == "Version 13B is out."


def test_latex_is_untouched() -> None:
    assert normalize_currency("$x^2$") == "$x^2$"
    assert normalize_currency("$5$") == "$5$"


def test_ambiguous_codes_are_left_alone_without_a_magnitude() -> None:
    assert normalize_currency("AMD 13") == "AMD 13"
    assert normalize_currency("PHP 13") == "PHP 13"
    assert normalize_currency("ALL 13 tests pass.") == "ALL 13 tests pass."
    assert normalize_currency("TOP 13 students") == "TOP 13 students"


def test_ambiguous_codes_normalize_with_a_magnitude() -> None:
    assert normalize_currency("AMD 13B") == "13 billion Armenian drams"
    assert normalize_currency("13B AMD") == "13 billion Armenian drams"


def test_safe_codes_normalize_without_a_magnitude() -> None:
    assert normalize_currency("USD 13") == "13 US dollars"
    assert normalize_currency("13 BRL") == "13 Brazilian reais"


def test_filter_removes_inline_code_before_normalizing() -> None:
    assert clean("Cost is `$13B` today.") == "Cost is today."


def test_filter_normalizes_currency_in_reply() -> None:
    assert clean("Revenue hit 13B$ this quarter.") == (
        "Revenue hit 13 billion dollars this quarter."
    )
    assert clean("We raised $2.5M at a $13B valuation.") == (
        "We raised 2.5 million dollars at a 13 billion dollars valuation."
    )
