"""Version + upstream-pin parity."""
import re

import tbd


def test_version():
    assert tbd.VERSION == "3.5.2"  # the tbd-3.5.2-compat branch


def test_upstream_pin():
    # A full 40-char git SHA must be recorded so upstream drift is traceable.
    assert re.fullmatch(r"[0-9a-f]{40}", tbd.UPSTREAM_SHA)
    assert tbd.UPSTREAM_VERSION == tbd.VERSION
    assert tbd.UPSTREAM_REPO.endswith("rd2/tbd")
