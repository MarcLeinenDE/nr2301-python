# SPDX-License-Identifier: GPL-3.0-or-later

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
    "CurrentWANInfo",
    "MagicNumberInfo",
    "MobileNamespace",
    "NetworkSettings",
    "NetworkSettingsResponse",
    "SignalInfo",
    "VersionInfo",
    "VersionNamespace",
    "WANContext",
]
