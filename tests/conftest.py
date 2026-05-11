import json
from pathlib import Path

import pytest


@pytest.fixture
def no_musicbrainz_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(self):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        "app.providers.musicbrainz.MusicBrainzProvider._respect_rate_limit",
        _noop,
    )


def load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))
