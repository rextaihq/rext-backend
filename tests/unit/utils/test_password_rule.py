"""The password rule is the one the app tells people (rext-control #939).

The sign-up form says "At least 8 characters" and checks the breached list. The backend also
asked for an upper-case letter, a lower-case letter, a number and a symbol, one unmet rule at
a time, so a passphrase the form accepted was refused up to four times. And the breached list
was asked only by the browser: the API itself took any password that met the four rules.

Now: at least 8 characters, at most 72 bytes, not a password known from a breach. The list is
asked from the server (the first five characters of the password's SHA-1, nothing else), for
no more than two seconds, and the commonest passwords are refused without it.
"""

import asyncio
import hashlib

import pytest

import src.utils.password_utils as password_utils
from src.api.middleware.exceptions import RextValidationException
from src.utils.password_utils import (
    BREACHED_PASSWORD_MESSAGE,
    ensure_password_not_breached,
    password_is_breached,
    validate_password_strength,
)


def _range_holding(password, count="42"):
    """The list's answer for a password's beginning, with its ending in it and two others."""
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    return (
        "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n"
        f"{digest[5:]}:{count}\r\n"
        "00D4F6E8FA6EECAD2A3AA415EEC418D38EC:0"
    )


@pytest.fixture
def asked(monkeypatch):
    """The list switched on, answering from the test: what it was asked, and what it says."""
    monkeypatch.setenv("REXT_PASSWORD_BREACH_CHECK", "on")
    calls = {"prefixes": [], "answer": ""}

    async def answer(prefix):
        calls["prefixes"].append(prefix)
        if isinstance(calls["answer"], Exception):
            raise calls["answer"]
        return calls["answer"]

    monkeypatch.setattr(password_utils, "_breach_range", answer)
    return calls


@pytest.mark.parametrize(
    "password",
    [
        "blueberry pancakes",  # the passphrase the form accepted and the backend refused
        "alllowercase",
        "ALLUPPERCASE",
        "nodigitsorsymbols",
        "correct horse battery staple",
        "pässwörter sind lang",
        "8chars!!",
        "a" * 72,
    ],
)
def test_a_password_needs_no_mix_of_letters_numbers_and_symbols(password):
    validate_password_strength(password)


def test_every_unmet_part_is_told_in_one_answer():
    with pytest.raises(RextValidationException) as refused:
        validate_password_strength("<short>")

    messages = [detail["message"] for detail in refused.value.details]
    assert messages == [
        "Password cannot contain < or >, HTML/script tags, or hidden characters",
        "Password must be at least 8 characters",
    ]
    assert refused.value.message == ". ".join(messages)
    assert {detail["field"] for detail in refused.value.details} == {"password"}


def test_the_limit_is_72_bytes_and_says_so():
    validate_password_strength("é" * 36)  # 72 bytes
    with pytest.raises(RextValidationException) as refused:
        validate_password_strength("é" * 37)

    assert refused.value.message.startswith("Password must be at most 72 bytes: 72 plain letters")


@pytest.mark.parametrize(
    "password", ["password", "12345678", "Password1", "QWERTYUIOP", "iloveyou"]
)
def test_the_commonest_passwords_are_refused_without_asking_the_list(password, asked):
    with pytest.raises(RextValidationException) as refused:
        validate_password_strength(password)

    assert refused.value.message == BREACHED_PASSWORD_MESSAGE
    assert asked["prefixes"] == []


async def test_a_password_known_from_a_breach_is_refused_in_the_dashboards_sentence(asked):
    asked["answer"] = _range_holding("blueberry pancakes")

    with pytest.raises(RextValidationException) as refused:
        await ensure_password_not_breached("blueberry pancakes")

    assert refused.value.message == (
        "This password has appeared in a data breach. Please choose a different password"
    )
    assert [detail["field"] for detail in refused.value.details] == ["password"]


async def test_only_the_first_five_characters_of_the_hash_leave_the_server(asked):
    await password_is_breached("blueberry pancakes")

    digest = hashlib.sha1(b"blueberry pancakes", usedforsecurity=False).hexdigest().upper()
    assert asked["prefixes"] == [digest[:5]]


async def test_a_password_the_list_does_not_hold_is_allowed(asked):
    asked["answer"] = _range_holding("another password entirely")

    await ensure_password_not_breached("blueberry pancakes")
    assert not await password_is_breached("blueberry pancakes")


async def test_a_padding_line_is_no_password(asked):
    """The list pads its answer with endings that carry a count of 0."""
    asked["answer"] = _range_holding("blueberry pancakes", count="0")

    assert not await password_is_breached("blueberry pancakes")


async def test_a_list_that_cannot_be_reached_allows_the_password(asked):
    asked["answer"] = ConnectionError("no route")

    await ensure_password_not_breached("blueberry pancakes")


async def test_a_slow_list_never_holds_a_sign_up_past_its_limit(asked, monkeypatch):
    monkeypatch.setattr(password_utils, "_BREACH_RANGE_SECONDS", 0.05)

    async def slow(prefix):
        await asyncio.sleep(5)
        return _range_holding("blueberry pancakes")

    monkeypatch.setattr(password_utils, "_breach_range", slow)
    started = asyncio.get_running_loop().time()

    assert not await password_is_breached("blueberry pancakes")
    assert asyncio.get_running_loop().time() - started < 1


async def test_the_list_is_not_asked_when_it_is_switched_off(asked, monkeypatch):
    monkeypatch.setenv("REXT_PASSWORD_BREACH_CHECK", "off")
    asked["answer"] = _range_holding("blueberry pancakes")

    assert not await password_is_breached("blueberry pancakes")
    assert asked["prefixes"] == []
