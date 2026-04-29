"""
app/utils/fx.py — Currency conversion using a static JSON rate table.

All rates are relative to USD (1 USD = X currency).
Source file: app/utils/currencies.json

No external API calls — fully offline for MVP.
"""

import json
import os
from pathlib import Path
from typing import Optional
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Load currency data from JSON
# ---------------------------------------------------------------------------
_CURRENCIES_FILE = Path(__file__).parent / "currencies.json"

def _load_currencies() -> dict:
    try:
        with open(_CURRENCIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Remove comment key
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        logger.error(f"Failed to load currencies.json: {e}")
        return {"USD": {"rate": 1.0, "symbol": "$", "name": "US Dollar", "country_codes": ["US"]}}

_CURRENCY_DATA: dict = _load_currencies()

# USD rates: 1 USD = X <currency>
_USD_RATES: dict[str, float] = {
    code: info["rate"]
    for code, info in _CURRENCY_DATA.items()
}

# Build full cross-rate table: X → USD → Y
RATES: dict[str, float] = {}
for _from, _from_rate in _USD_RATES.items():
    for _to, _to_rate in _USD_RATES.items():
        if _from != _to and _from_rate > 0:
            RATES[f"{_from}_{_to}"] = _to_rate / _from_rate

# Country code → currency code mapping
_COUNTRY_TO_CURRENCY: dict[str, str] = {}
for _code, _info in _CURRENCY_DATA.items():
    for _country in _info.get("country_codes", []):
        _COUNTRY_TO_CURRENCY[_country.upper()] = _code


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_currency(amount: float, from_curr: str, to_curr: str) -> tuple[float, float]:
    """
    Convert *amount* from *from_curr* to *to_curr*.

    Returns:
        (converted_amount: float, rate: float)
        Falls back to (amount, 1.0) if the pair is unknown.
    """
    from_curr = from_curr.upper().strip()
    to_curr   = to_curr.upper().strip()

    if from_curr == to_curr:
        return round(amount, 2), 1.0

    pair = f"{from_curr}_{to_curr}"
    rate = RATES.get(pair)

    if rate is None:
        logger.debug(f"fx: unknown pair {pair}, returning as-is")
        return round(amount, 2), 1.0

    return round(amount * rate, 2), round(rate, 6)


def to_usd(amount: float, currency: str) -> float:
    """Convert any amount to USD."""
    result, _ = convert_currency(amount, currency, "USD")
    return result


def get_currency_for_country(country_code: str) -> str:
    """
    Return the ISO currency code for a given ISO country code.
    Falls back to "USD" if unknown.

    Examples:
        get_currency_for_country("SA") → "SAR"
        get_currency_for_country("TR") → "TRY"
        get_currency_for_country("YE") → "YER"
    """
    return _COUNTRY_TO_CURRENCY.get(country_code.upper(), "USD")


def get_currency_info(currency_code: str) -> Optional[dict]:
    """Return full info dict for a currency code, or None if unknown."""
    return _CURRENCY_DATA.get(currency_code.upper())


def list_supported_currencies() -> list[dict]:
    """Return all supported currencies with their metadata."""
    return [
        {
            "code":    code,
            "symbol":  info["symbol"],
            "name":    info["name"],
            "rate_to_usd": info["rate"],
        }
        for code, info in _CURRENCY_DATA.items()
    ]


def normalize_to_user_currency(
    amount: float,
    from_currency: str,
    user_country: str,
) -> tuple[float, str, float]:
    """
    Convert an amount to the user's home currency based on their country.

    Returns:
        (converted_amount, target_currency_code, exchange_rate)

    Example:
        User is from Saudi Arabia (SA), statement has USD amounts:
        normalize_to_user_currency(100.0, "USD", "SA") → (375.0, "SAR", 3.75)
    """
    target_currency = get_currency_for_country(user_country)
    converted, rate = convert_currency(amount, from_currency, target_currency)
    return converted, target_currency, rate
