"""The optional system-trust proof launcher must fail closed."""

import runpy
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_reference_worker_system_trust.py"


def _load():
    return runpy.run_path(str(SCRIPT), run_name="system_trust_test")["main"]


def test_launcher_uses_tls_client_context_and_existing_proof(monkeypatch):
    main = _load()
    import urllib.request

    ctx = SimpleNamespace(verify_mode=ssl.CERT_REQUIRED, check_hostname=True)
    events = []
    monkeypatch.setitem(sys.modules, "truststore", SimpleNamespace(
        SSLContext=lambda protocol: (events.append(("protocol", protocol)) or ctx)
    ))
    monkeypatch.setattr(urllib.request, "HTTPSHandler",
                        lambda **kw: (events.append(("handler", kw)) or "handler"))
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *args: (events.append(("build", args)) or "opener"))
    monkeypatch.setattr(urllib.request, "install_opener",
                        lambda opener: events.append(("install", opener)))
    monkeypatch.setattr(runpy, "run_path",
                        lambda path, run_name: events.append(("proof", Path(path).name, run_name)))
    main()
    assert events == [
        ("protocol", ssl.PROTOCOL_TLS_CLIENT),
        ("handler", {"context": ctx}),
        ("build", ("handler",)),
        ("install", "opener"),
        ("proof", "m6_reference_worker_live_proof.py", "__main__"),
    ]


def test_missing_truststore_fails_before_opener_or_proof(monkeypatch):
    main = _load()
    import urllib.request
    monkeypatch.setitem(sys.modules, "truststore", None)
    install = Mock()
    proof = Mock()
    monkeypatch.setattr(urllib.request, "install_opener", install)
    monkeypatch.setattr(runpy, "run_path", proof)
    with pytest.raises(RuntimeError, match="truststore"):
        main()
    install.assert_not_called()
    proof.assert_not_called()


def test_broken_system_trust_context_fails_before_install(monkeypatch):
    main = _load()
    import urllib.request
    def fail(_protocol):
        raise RuntimeError("system certificate store unavailable")
    monkeypatch.setitem(sys.modules, "truststore",
                       SimpleNamespace(SSLContext=fail))
    install = Mock()
    proof = Mock()
    monkeypatch.setattr(urllib.request, "install_opener", install)
    monkeypatch.setattr(runpy, "run_path", proof)
    with pytest.raises(RuntimeError, match="certificate store unavailable"):
        main()
    install.assert_not_called()
    proof.assert_not_called()


@pytest.mark.parametrize("verify_mode,check_hostname", [
    (ssl.CERT_NONE, False),
    (ssl.CERT_NONE, True),
    (ssl.CERT_REQUIRED, False),
])
def test_launcher_refuses_unverified_trust_context(
    monkeypatch, verify_mode, check_hostname
):
    main = _load()
    import urllib.request
    monkeypatch.setitem(sys.modules, "truststore", SimpleNamespace(
        SSLContext=lambda protocol: SimpleNamespace(
            verify_mode=verify_mode, check_hostname=check_hostname
        )
    ))
    install = Mock()
    proof = Mock()
    monkeypatch.setattr(urllib.request, "install_opener", install)
    monkeypatch.setattr(runpy, "run_path", proof)
    with pytest.raises(RuntimeError, match="verification"):
        main()
    install.assert_not_called()
    proof.assert_not_called()
