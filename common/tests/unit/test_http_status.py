from __future__ import annotations

from common.constants import http_status


def test_http_status_constants_exist_and_values():
    assert http_status.HTTP_200_OK == 200
    assert http_status.HTTP_201_CREATED == 201
    assert http_status.HTTP_404_NOT_FOUND == 404
    assert http_status.HTTP_422_UNPROCESSABLE_ENTITY == 422
    assert http_status.HTTP_500_INTERNAL_SERVER_ERROR == 500


