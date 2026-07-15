from mycrm.modules.identity.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def test_passwords_are_hashed_with_argon2id() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_session_tokens_are_random_and_only_deterministic_hashes_are_stored() -> None:
    first = create_session_token()
    second = create_session_token()

    assert first != second
    assert len(first) >= 40
    assert hash_session_token(first, "secret-a") == hash_session_token(first, "secret-a")
    assert hash_session_token(first, "secret-a") != hash_session_token(first, "secret-b")
    assert hash_session_token(first, "secret-a") != first
