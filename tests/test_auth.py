import hashlib
import re

import pytest

from nr2301.auth import challenge_response, generate_user_id, login_result_text


def test_generate_user_id_matches_verified_frontend_compatible_shape():
    user_id = generate_user_id()
    assert re.fullmatch(r"[a-z0-9]{8}", user_id)


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
