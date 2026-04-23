from __future__ import annotations

import pytest

from bot.privacy import hash_guild, hash_id, hash_user


def test_same_input_returns_same_hash():
    assert hash_id(42, category='user', secret='k') == hash_id(
        42, category='user', secret='k'
    )


def test_category_namespaces_prevent_correlation():
    u = hash_id(42, category='user', secret='k')
    g = hash_id(42, category='guild', secret='k')
    assert u != g


def test_key_rotation_invalidates_all_hashes():
    a = hash_id(42, category='user', secret='old')
    b = hash_id(42, category='user', secret='new')
    assert a != b


def test_hash_length_is_fixed():
    h = hash_id(1, category='user', secret='k')
    assert len(h) == 32
    assert all(c in '0123456789abcdef' for c in h)


def test_accepts_int_or_str():
    assert hash_id(1, category='user', secret='k') == hash_id(
        '1', category='user', secret='k'
    )


def test_empty_secret_raises():
    with pytest.raises(ValueError, match='must not be empty'):
        hash_id(1, category='user', secret='')


def test_helper_functions_delegate_correctly():
    assert hash_user(1, secret='k') == hash_id(1, category='user', secret='k')
    assert hash_guild(1, secret='k') == hash_id(
        1, category='guild', secret='k'
    )
