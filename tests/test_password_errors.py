"""
Tests for wrong-password handling. No real PDF is needed.

pdfplumber wraps pdfminer's PDFPasswordIncorrect inside its own exception.
These tests copy that behaviour with a stand-in wrapper. (The real behaviour
was checked against password-protected fake statements.)

Run from the project folder:  py -m pytest
"""

import pytest
from pdfminer.pdfdocument import PDFPasswordIncorrect

from analyzer import parser
from analyzer.parser import (
    StatementError,
    WrongPasswordError,
    _is_password_error,
    read_statement_full,
)


class Wrapper(Exception):
    """Stands in for pdfplumber's own exception type."""


def _open_that_raises(error):
    def fake_open(*args, **kwargs):
        raise error
    return fake_open


# ---------- recognising the error ----------

def test_a_direct_password_error_is_recognised():
    assert _is_password_error(PDFPasswordIncorrect())


def test_a_wrapped_password_error_is_recognised():
    assert _is_password_error(Wrapper(PDFPasswordIncorrect()))


def test_a_twice_wrapped_password_error_is_recognised():
    assert _is_password_error(Wrapper(Wrapper(PDFPasswordIncorrect())))


def test_a_chained_password_error_is_recognised():
    try:
        try:
            raise PDFPasswordIncorrect()
        except PDFPasswordIncorrect as inner:
            raise Wrapper() from inner
    except Wrapper as outer:
        assert _is_password_error(outer)


def test_unrelated_errors_are_not_password_errors():
    assert not _is_password_error(ValueError("boom"))
    assert not _is_password_error(Wrapper(ValueError("broken file")))


# ---------- what the user is told ----------

def test_a_wrong_password_gets_the_clear_message():
    original = parser.pdfplumber.open
    parser.pdfplumber.open = _open_that_raises(Wrapper(PDFPasswordIncorrect()))
    try:
        with pytest.raises(WrongPasswordError):
            read_statement_full("statement.pdf", "wrong")
    finally:
        parser.pdfplumber.open = original


def test_other_failures_get_the_general_message_not_the_password_one():
    original = parser.pdfplumber.open
    parser.pdfplumber.open = _open_that_raises(Wrapper(ValueError("broken file")))
    try:
        try:
            read_statement_full("statement.pdf", "anything")
        except StatementError as error:
            assert not isinstance(error, WrongPasswordError)
            assert "could not be read" in str(error)
        else:
            raise AssertionError("an error was expected")
    finally:
        parser.pdfplumber.open = original
