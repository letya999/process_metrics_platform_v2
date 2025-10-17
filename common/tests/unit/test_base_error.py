from __future__ import annotations

import pytest

from common.errors.base_error import (
    BaseServiceError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
)


def test_base_service_error_to_dict():
    err = BaseServiceError("bad", code="E_BAD", details={"field": "x"})
    d = err.to_dict()
    assert d["message"] == "bad"
    assert d["code"] == "E_BAD"
    assert d["details"] == {"field": "x"}


@pytest.mark.parametrize(
    "exc_class, code_expected",
    [
        (NotFoundError, None),
        (ValidationError, None),
        (AuthenticationError, None),
    ],
)
def test_subclass_behavior(exc_class, code_expected):
    e = exc_class("msg")
    assert isinstance(e, BaseServiceError)
    assert e.message == "msg"
    assert e.code is code_expected


