import os

import pytest


@pytest.fixture(autouse=True)
def no_real_ai_credentials(monkeypatch):
    for name in [key for key in os.environ if key.startswith("DASHPI_AI_")]:
        monkeypatch.delenv(name)
