# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from ..exceptions import APIError, ProtocolError

if TYPE_CHECKING:
    from ..client import NR2301Client


VPNProtocol = Literal["pptp", "l2tp", "l2tp/ipsec"]
_VPN_PROTOCOLS = {"pptp", "l2tp", "l2tp/ipsec"}


class VPNStatus(TypedDict, total=False):
    result: int
    vpn_status: str


class VPNProfile(TypedDict, total=False):
    index: str
    vpn_name: str
    protocol_type: str
    vpn_server: str
    vpn_user_name: str
    vpn_user_password: str
    vpn_secure: str


class VPNProfilesResponse(TypedDict, total=False):
    result: int
    vpn_client_active_index: str
    vpn_client_enable: str
    vpn_clients: list[VPNProfile]


class VPNNamespace:
    """Evidence-backed NR2301 VPN-client helpers.

    Profile reads and writes can carry passwords and L2TP/IPsec pre-shared
    keys. Callers must treat profile objects as secret-bearing data and avoid
    routine/public logging.
    """

    def __init__(self, client: NR2301Client) -> None:
        self._client = client

    def status(self, *, timeout: float | None = None) -> VPNStatus:
        """Return the raw VPN client connection-status response."""

        return cast(
            VPNStatus,
            self._client.call(
                "cm",
                "get_vpn_client_connect_status",
                timeout=timeout,
            ),
        )

    def profiles(self, *, timeout: float | None = None) -> VPNProfilesResponse:
        """Return the raw configured VPN client profiles.

        The response may contain VPN passwords and L2TP/IPsec pre-shared keys.
        Applications must treat the returned object as secret-bearing data and
        avoid routine logging or public diagnostics.
        """

        return cast(
            VPNProfilesResponse,
            self._client.call("cm", "get_vpn_clients", timeout=timeout),
        )

    def set_enabled(
        self,
        enabled: bool,
        *,
        timeout: float | None = None,
    ) -> VPNProfilesResponse:
        """Enable/disable the VPN client subsystem and require read-back."""

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        expected = "enable" if enabled else "disable"
        current = self.profiles(timeout=timeout)
        if self._global_state(current) == expected:
            return current

        self._client.call(
            "cm",
            "open_close_vpn_clients",
            data={"vpn_client_enable": expected},
            timeout=timeout,
        )
        verified = self.profiles(timeout=timeout)
        actual = self._global_state(verified)
        if actual != expected:
            raise APIError(
                "VPN global enable state did not match read-back",
                method_id="cm/open_close_vpn_clients",
                response={"expected": expected, "actual": actual},
            )
        return verified

    def add_profile(
        self,
        *,
        name: str,
        protocol: VPNProtocol,
        server: str,
        username: str,
        password: str,
        secure: str = "",
        timeout: float | None = None,
    ) -> VPNProfile:
        """Add one VPN profile and return its read-back object.

        Secret values are sent to the router but are never copied into
        SDK-generated error details.
        """

        payload = self._profile_payload(
            index="-1",
            name=name,
            protocol=protocol,
            server=server,
            username=username,
            password=password,
            secure=secure,
        )
        before = self.profiles(timeout=timeout)
        before_indices = set(self._profile_map(before))

        self._client.call(
            "cm",
            "add_vpn_client_item",
            data=payload,
            timeout=timeout,
        )

        after = self.profiles(timeout=timeout)
        after_map = self._profile_map(after)
        new_indices = [index for index in after_map if index not in before_indices]
        matches = [
            after_map[index]
            for index in new_indices
            if self._public_profile_matches(after_map[index], payload)
        ]
        if len(matches) != 1:
            raise APIError(
                "VPN profile add could not be verified by read-back",
                method_id="cm/add_vpn_client_item",
                response={
                    "profile_count_before": len(before_indices),
                    "profile_count_after": len(after_map),
                    "new_profile_count": len(new_indices),
                    "matching_new_profile_count": len(matches),
                },
            )
        return cast(VPNProfile, dict(matches[0]))

    def edit_profile(
        self,
        index: str | int,
        *,
        name: str,
        protocol: VPNProtocol,
        server: str,
        username: str,
        password: str,
        secure: str = "",
        timeout: float | None = None,
    ) -> VPNProfile:
        """Replace the full documented profile object and verify public fields."""

        normalized_index = self._normalize_index(index)
        payload = self._profile_payload(
            index=normalized_index,
            name=name,
            protocol=protocol,
            server=server,
            username=username,
            password=password,
            secure=secure,
        )
        before = self._profile_map(self.profiles(timeout=timeout))
        if normalized_index not in before:
            raise ValueError("VPN profile index does not exist")

        self._client.call(
            "cm",
            "edit_vpn_client_item",
            data=payload,
            timeout=timeout,
        )
        after = self._profile_map(self.profiles(timeout=timeout))
        profile = after.get(normalized_index)
        if profile is None or not self._public_profile_matches(profile, payload):
            raise APIError(
                "VPN profile edit could not be verified by read-back",
                method_id="cm/edit_vpn_client_item",
                response={
                    "index": normalized_index,
                    "profile_present": profile is not None,
                },
            )
        return cast(VPNProfile, dict(profile))

    def delete_profile(
        self,
        index: str | int,
        *,
        timeout: float | None = None,
    ) -> VPNProfilesResponse:
        """Delete one existing profile and require it to disappear on read-back."""

        normalized_index = self._normalize_index(index)
        before = self._profile_map(self.profiles(timeout=timeout))
        if normalized_index not in before:
            raise ValueError("VPN profile index does not exist")

        self._client.call(
            "cm",
            "del_vpn_client_item",
            data={"index": normalized_index},
            timeout=timeout,
        )
        verified = self.profiles(timeout=timeout)
        if normalized_index in self._profile_map(verified):
            raise APIError(
                "VPN profile delete could not be verified by read-back",
                method_id="cm/del_vpn_client_item",
                response={"index": normalized_index, "profile_present": True},
            )
        return verified

    def set_profile_active(
        self,
        index: str | int,
        active: bool,
        *,
        timeout: float | None = None,
    ) -> VPNProfilesResponse:
        """Mark one existing profile active/inactive and verify active index."""

        if not isinstance(active, bool):
            raise TypeError("active must be a bool")
        normalized_index = self._normalize_index(index)
        current = self.profiles(timeout=timeout)
        profiles = self._profile_map(current)
        if normalized_index not in profiles:
            raise ValueError("VPN profile index does not exist")

        current_active = self._active_index(current)
        if (active and current_active == normalized_index) or (
            not active and current_active != normalized_index
        ):
            return current

        self._client.call(
            "cm",
            "active_vpn_client_item",
            data={
                "index": normalized_index,
                "vpn_active": "active" if active else "inactive",
            },
            timeout=timeout,
        )
        verified = self.profiles(timeout=timeout)
        actual = self._active_index(verified)
        ok = actual == normalized_index if active else actual != normalized_index
        if not ok:
            raise APIError(
                "VPN active-profile state did not match read-back",
                method_id="cm/active_vpn_client_item",
                response={
                    "index": normalized_index,
                    "expected_active": active,
                    "actual_active_index": actual,
                },
            )
        return verified

    @staticmethod
    def _profile_payload(
        *,
        index: str,
        name: str,
        protocol: VPNProtocol,
        server: str,
        username: str,
        password: str,
        secure: str,
    ) -> dict[str, str]:
        for field, value in {
            "name": name,
            "server": server,
            "username": username,
            "password": password,
            "secure": secure,
        }.items():
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a str")
        if not name.strip():
            raise ValueError("name must not be empty")
        if not server.strip():
            raise ValueError("server must not be empty")
        if protocol not in _VPN_PROTOCOLS:
            raise ValueError("protocol must be 'pptp', 'l2tp' or 'l2tp/ipsec'")

        return {
            "index": index,
            "vpn_name": name,
            "protocol_type": protocol,
            "vpn_server": server,
            "vpn_user_name": username,
            "vpn_user_password": password,
            "vpn_secure": secure,
        }

    @classmethod
    def _profile_map(
        cls,
        response: Mapping[str, Any],
    ) -> dict[str, Mapping[str, Any]]:
        raw = response.get("vpn_clients")
        if not isinstance(raw, list):
            raise ProtocolError("cm/get_vpn_clients did not return vpn_clients as a list")

        result: dict[str, Mapping[str, Any]] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                raise ProtocolError("cm/get_vpn_clients returned a non-object profile")
            index = cls._normalize_index(item.get("index"))
            if index in result:
                raise ProtocolError("cm/get_vpn_clients returned duplicate profile indices")
            result[index] = item
        return result

    @staticmethod
    def _public_profile_matches(
        actual: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> bool:
        # Deliberately exclude password/PSK from diagnostics/comparison. Some
        # firmware may redact secret fields even when the write succeeded.
        fields = ("vpn_name", "protocol_type", "vpn_server", "vpn_user_name")
        return all(actual.get(field) == expected.get(field) for field in fields)

    @staticmethod
    def _global_state(response: Mapping[str, Any]) -> str:
        value = response.get("vpn_client_enable")
        if value not in {"enable", "disable"}:
            raise ProtocolError(
                "cm/get_vpn_clients returned invalid vpn_client_enable"
            )
        return cast(str, value)

    @classmethod
    def _active_index(cls, response: Mapping[str, Any]) -> str | None:
        value = response.get("vpn_client_active_index")
        if value in {None, "", "-1"}:
            return None
        return cls._normalize_index(value)

    @staticmethod
    def _normalize_index(value: object) -> str:
        if isinstance(value, bool):
            raise TypeError("VPN profile index must be a string or integer")
        if isinstance(value, int):
            if value < 0:
                raise ValueError("VPN profile index must not be negative")
            return str(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("VPN profile index must not be empty")
            if not stripped.isdigit():
                raise ValueError("VPN profile index must be numeric")
            return str(int(stripped))
        raise TypeError("VPN profile index must be a string or integer")
