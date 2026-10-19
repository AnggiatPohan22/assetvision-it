"""Shared identifier value rules, independent of database configuration or ORM imports."""

import enum
import re


class IdentifierType(enum.StrEnum):
    SERIAL_NUMBER = "SERIAL_NUMBER"
    MAC_LAN = "MAC_LAN"
    MAC_WLAN = "MAC_WLAN"
    BSSID = "BSSID"
    HOSTNAME = "HOSTNAME"
    MANAGEMENT_ID = "MANAGEMENT_ID"


MAC_TYPES = {IdentifierType.MAC_LAN, IdentifierType.MAC_WLAN, IdentifierType.BSSID}


def normalize_identifier(kind: IdentifierType, raw: str) -> str:
    value = raw.strip()
    if not value or len(value) > 255 or any(ord(char) < 32 for char in value):
        raise ValueError("Identifier must contain 1-255 printable characters")
    if kind in MAC_TYPES:
        if not re.fullmatch(
            r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|"
            r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}|(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4})",
            value,
        ):
            raise ValueError("Invalid MAC address")
        compact = re.sub(r"[:.\-]", "", value).upper()
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))
    if kind == IdentifierType.SERIAL_NUMBER and value.upper() in {"UNKNOWN", "N/A", "NA", "-"}:
        raise ValueError("Missing serial numbers must not be represented by placeholder claims")
    # Serial and management IDs preserve case; their upstream case rules are unknown.
    return value.lower() if kind == IdentifierType.HOSTNAME else value
