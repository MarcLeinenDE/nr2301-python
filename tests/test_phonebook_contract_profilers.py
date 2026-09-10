from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "examples/explore_phonebook_multi_contact_contracts.py",
        "examples/explore_phonebook_text_representation.py",
    ],
)
def test_phonebook_contract_profiler_compiles_and_is_hard_gated(path):
    source = Path(path).read_text(encoding="utf-8")
    compile(source, path, "exec")

    assert 'NR2301_WRITE_INTEGRATION") != "1"' in source
    assert 'NR2301_PHONEBOOK_REQUIRE_EMPTY") != "1"' in source
    assert "NR2301_PASSWORD" in source
    assert 'if __name__ == "__main__":' in source
    assert "FINAL_INDEX_SET_MATCH" in source


def test_multi_contact_profiler_covers_non_guessed_candidate_matrix():
    source = Path("examples/explore_phonebook_multi_contact_contracts.py").read_text(
        encoding="utf-8"
    )

    for label in (
        "COMMA_STRING",
        "STRING_LIST",
        "INT_LIST",
        "JSON_ARRAY_STRING",
    ):
        assert label in source

    assert "count\": \"2\"" in source
    assert "move_contacts_to_group" in source
    assert "delete_pb" in source
    assert "PHONEBOOK_MULTI_CONTRACT_PROFILER = PASS" in source


def test_text_representation_profiler_uses_only_synthetic_cases_and_decoders():
    source = Path("examples/explore_phonebook_text_representation.py").read_text(
        encoding="utf-8"
    )

    assert "example.invalid" in source
    assert "UTF16BE_HEX" in source
    assert "UTF16LE_HEX" in source
    assert "UTF8_HEX" in source
    assert "BASE64_UTF8" in source
    assert "URL_PERCENT_ENCODED" in source
    assert "OUTPUT_CODEPOINTS" in source
    assert "PHONEBOOK_TEXT_REPRESENTATION_PROFILER = PASS" in source
