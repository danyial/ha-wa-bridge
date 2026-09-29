"""Phone numbers and WhatsApp chat ids."""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")
# "+49 (0) 151 …": the bracketed trunk zero must not end up in the number.
_TRUNK_ZERO = re.compile(r"\(\s*0\s*\)")

# ITU calling codes for countries whose national numbers start with a trunk
# "0". Countries without a trunk prefix (US, CA, …) don't need an entry:
# their numbers are dialled the same way nationally and internationally.
CALLING_CODES: dict[str, str] = {
    "AT": "43",
    "AU": "61",
    "BE": "32",
    "BG": "359",
    "CH": "41",
    "CZ": "420",
    "DE": "49",
    "DK": "45",
    "EE": "372",
    "ES": "34",
    "FI": "358",
    "FR": "33",
    "GB": "44",
    "GR": "30",
    "HR": "385",
    "HU": "36",
    "IE": "353",
    "IL": "972",
    "IN": "91",
    "IT": "39",
    "JP": "81",
    "LI": "423",
    "LT": "370",
    "LU": "352",
    "LV": "371",
    "NL": "31",
    "NO": "47",
    "NZ": "64",
    "PL": "48",
    "PT": "351",
    "RO": "40",
    "RS": "381",
    "SE": "46",
    "SI": "386",
    "SK": "421",
    "TR": "90",
    "UA": "380",
    "ZA": "27",
}
# Italy keeps the leading 0 of landline numbers in international format
# (06 … -> +39 06 …).
KEEP_LEADING_ZERO = frozenset({"IT"})


def normalize_chat_id(value: str, country: str | None = None) -> str:
    """Turn a phone number into '<digits>@c.us'; keep ids that have a suffix.

    '+49 151 234' and '0049 151 234' are international. A leading single '0'
    is a national number and gets the calling code of `country` (the HA
    country setting), e.g. '0151 234' with DE -> '49151234@c.us'.
    """
    value = value.strip()
    if "@" in value:
        return value
    international = value.startswith("+")
    digits = _NON_DIGITS.sub("", _TRUNK_ZERO.sub("", value))
    if not digits:
        raise ValueError(f"invalid chat id: {value!r}")
    if not international:
        if digits.startswith("00"):
            digits = digits[2:]
        elif digits.startswith("0"):
            country = (country or "").upper()
            code = CALLING_CODES.get(country)
            if code is None:
                raise ValueError(
                    f"national number {value!r} needs a country code; "
                    "use +<country code> or set the Home Assistant country"
                )
            digits = code + (digits if country in KEEP_LEADING_ZERO else digits[1:])
    if not digits or digits.startswith("0"):
        raise ValueError(f"invalid chat id: {value!r}")
    return f"{digits}@c.us"
