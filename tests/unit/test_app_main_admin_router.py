import importlib
import sys
import types


def test_app_main_includes_admin_router_with_limiter():
    # Mock slowapi to avoid actual network/state issues during import
    slowapi_mod = types.ModuleType("slowapi")
    errors_mod = types.ModuleType("slowapi.errors")
    util_mod = types.ModuleType("slowapi.util")

    class _Limiter:
        def __init__(self, *args, **kwargs):
            self.key_func = kwargs.get("key_func")

        def limit(self, *_args, **_kwargs):
            def _decorator(fn):
                return fn

            return _decorator

    class _RateLimitExceeded(Exception):
        pass

    def _handler(*_args, **_kwargs):
        return None

    def _get_remote_address(_request):
        return "127.0.0.1"

    slowapi_mod.Limiter = _Limiter
    slowapi_mod._rate_limit_exceeded_handler = _handler
    errors_mod.RateLimitExceeded = _RateLimitExceeded
    util_mod.get_remote_address = _get_remote_address

    sys.modules["slowapi"] = slowapi_mod
    sys.modules["slowapi.errors"] = errors_mod
    sys.modules["slowapi.util"] = util_mod

    # Mock app.limiter
    limiter_mod = types.ModuleType("app.limiter")
    mock_limiter = _Limiter(key_func=_get_remote_address)
    limiter_mod.limiter = mock_limiter
    sys.modules["app.limiter"] = limiter_mod

    sys.modules.pop("app.main", None)

    app_main = importlib.import_module("app.main")

    # Verify admin routes are included
    assert any(
        route.path == "/api/v1/admin/auth/login" for route in app_main.app.routes
    )

    # Verify limiter is set in app state
    assert app_main.app.state.limiter == mock_limiter
