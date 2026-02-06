from typing import Any

from . import get_session_stats


def assert_session_stats(crawler, expected: dict[str, Any]):
    actual = get_session_stats(crawler)
    if not expected or any(k.startswith("scrapy-zyte-api/sessions") for k in expected):
        pass
    elif any(k.startswith("/") for k in expected):
        expected = {f"scrapy-zyte-api/sessions{k}": v for k, v in expected.items()}
    elif any(isinstance(v, dict) for v in expected.values()):
        expected = {
            f"scrapy-zyte-api/sessions/pools/{pool}/{stat}": value
            for pool, stats in expected.items()
            for stat, value in stats.items()
        }
    else:
        expected = {
            f"scrapy-zyte-api/sessions/pools/{pool}/{stat}": value
            for pool, (init, use) in expected.items()
            for stat, value in (("init/check-passed", init), ("use/check-passed", use))
        }
    assert actual == expected
