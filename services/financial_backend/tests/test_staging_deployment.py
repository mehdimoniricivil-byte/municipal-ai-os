from pathlib import Path


SERVICE_DIR = Path(__file__).parents[1]


def test_staging_port_is_dynamic_across_compose_and_proxy_scripts():
    compose = (SERVICE_DIR / "docker-compose.staging.yml").read_text(encoding="utf-8")
    deploy = (SERVICE_DIR / "scripts" / "deploy_staging.sh").read_text(encoding="utf-8")
    proxy = (SERVICE_DIR / "scripts" / "publish_staging_proxy.sh").read_text(encoding="utf-8")

    assert "${FINANCIAL_STAGING_PORT:-8300}:8000" in compose
    assert "seq 8300 8399" in deploy
    assert "FINANCIAL_STAGING_PORT=${STAGING_PORT}" in deploy
    assert '127.0.0.1:${STAGING_PORT}' in deploy
    assert '127.0.0.1:${STAGING_PORT}' in proxy
    assert 'proxy_pass http://127.0.0.1:" port ";"' in proxy
    assert 'proxy_pass http://127.0.0.1:" port "/;"' not in proxy
    assert "127.0.0.1:8002" not in compose + deploy + proxy
