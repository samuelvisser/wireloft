from pathlib import Path


NGINX_CONFIG = Path(__file__).parents[2] / ".docker" / "app" / "nginx.conf"


def _location_block(config: str, path: str) -> str:
    start = config.index(f"location {path} {{")
    end = config.index("\n    }", start)
    return config[start:end]


def test_public_feed_routes_are_proxied_to_backend():
    config = NGINX_CONFIG.read_text()

    feeds_block = _location_block(config, "/feeds/")
    assert "proxy_pass http://127.0.0.1:5001;" in feeds_block
    assert "try_files" not in feeds_block


def test_public_feed_location_is_not_left_to_spa_fallback():
    config = NGINX_CONFIG.read_text()

    assert config.index("location /feeds/ {") < config.index("location / {")
