import hashlib

import pytest

from nr2301.auth import challenge_response, login_result_text


def test_challenge_response_matches_protocol_formula():
    rand = "abc123"
    password = "secret"
    expected = hashlib.md5(f"{rand}{password}".encode()).hexdigest()
    assert challenge_response(rand, password) == expected


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (1, "password error"),
        (2, "username error"),
        (3, "success"),
        (6, "account locked"),
    ],
)
def test_login_result_text(code, text):
    assert login_result_text(code) == text
