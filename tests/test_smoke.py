"""Smoke test: package imports cleanly."""

def test_pulse_imports():
    import pulse
    assert pulse.__version__ == "0.1.0"


def test_collectors_imports():
    import collectors
    assert collectors is not None
