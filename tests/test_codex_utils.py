from harnesses.codex.utils import _normalize_codex_auth_payload


def test_normalize_codex_auth_payload_converts_integer_last_refresh() -> None:
    payload = {
        "last_refresh": 1778024841,
        "tokens": {
            "access_token": "access",
            "refresh_token": "refresh",
        },
    }

    normalized = _normalize_codex_auth_payload(payload)

    assert normalized["last_refresh"] == "2026-05-05T23:47:21Z"
    assert payload["last_refresh"] == 1778024841
