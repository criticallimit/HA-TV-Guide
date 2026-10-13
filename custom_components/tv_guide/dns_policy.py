"""DNS address filtering for a future dedicated EPG HTTP connector.

Do not use this module as a substitute for checking the actual connection peer.
"""

import ipaddress


def validate_resolved_addresses(records: list[dict]) -> list[dict]:
    """Require every DNS answer to resolve to a globally routable address."""
    if not records:
        raise ValueError("The feed host has no DNS addresses")
    for record in records:
        try:
            address = ipaddress.ip_address(record["host"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid DNS result") from exc
        if not address.is_global:
            raise ValueError("Feed host resolves to a non-public IP address")
    return records
