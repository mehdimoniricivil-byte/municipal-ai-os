from pathlib import Path

from app.services.health import health_report


class FakeResult:
    pass


class FakeSession:
    def execute(self, _query):
        return FakeResult()


def test_health_report_checks_storage(tmp_path: Path):
    report, status = health_report(FakeSession(), str(tmp_path))
    assert status == 200
    assert report["checks"]["database"]["status"] == "ok"
    assert report["checks"]["storage"]["status"] == "ok"
