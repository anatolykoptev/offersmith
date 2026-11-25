import os
from pathlib import Path

import pytest

from ats_check import health

FIX = Path(__file__).parent / "fixtures"
# hermetic: the fifth extractor family is a stand-in, whatever `filee` the machine has (tests that set the variable themselves override it)
os.environ["ATS_CHECK_FILEE"] = str(Path(__file__).parent / "fake_filee")
# hermetic: the optional OpenResume layer is off (tests/test_openresume.py turns it on for its own runs, from the value saved here)
OPENRESUME_HOME = os.environ.get("ATS_CHECK_OPENRESUME")
os.environ["ATS_CHECK_OPENRESUME"] = "off"
# hermetic: no offersmith.toml from the cwd or ~/.config, no OFFERSMITH_* paths from the shell
os.environ["OFFERSMITH_CONFIG"] = ""
for _v in ("OFFERSMITH_MASTER", "OFFERSMITH_GUARD", "OFFERSMITH_OUT", "OFFERSMITH_WORKDAY_BASE", "ATS_CHECK_WORKDAY_BASE"):
    os.environ.pop(_v, None)
_cache: dict = {}


@pytest.fixture(scope="session")
def run_health():
    def _run(name: str):
        if name not in _cache:
            _cache[name] = health.run(FIX / f"{name}.pdf")
        return _cache[name]
    return _run
