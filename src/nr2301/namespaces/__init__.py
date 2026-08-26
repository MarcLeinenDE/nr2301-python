# SPDX-License-Identifier: GPL-3.0-or-later

from .lan import (
    CombinedDHCPResponse,
    DHCPSettings,
    DNSSettings,
    LANAddress,
    LANAddressResponse,
    LANNamespace,
)
from .mobile import (
    AvailableNetworkModes,
    CellInfo,
    CellularBasicInfo,
    CurrentWANInfo,
    MobileNamespace,
    NetworkSettings,
    NetworkSettingsResponse,
    SignalInfo,
    WANContext,
)
from .version import MagicNumberInfo, VersionInfo, VersionNamespace

__all__ = [
    "AvailableNetworkModes",
    "CellInfo",
    "CellularBasicInfo",
    "CombinedDHCPResponse",
    "CurrentWANInfo",
    "DHCPSettings",
    "DNSSettings",
    "LANAddress",
    "LANAddressResponse",
    "LANNamespace",
    "MagicNumberInfo",
    "MobileNamespace",
    "NetworkSettings",
    "NetworkSettingsResponse",
    "SignalInfo",
    "VersionInfo",
    "VersionNamespace",
    "WANContext",
]
