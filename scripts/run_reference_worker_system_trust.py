"""Run the read-only reference-worker proof using the operating system CA store.

Optional: install `truststore` into the executing Python environment.
This launcher changes only this process's urllib HTTPS opener; it never disables
certificate or hostname verification, edits global trust, or grants an effect.
The canonical proof remains scripts/m6_reference_worker_live_proof.py.
"""

import runpy
import ssl
from pathlib import Path
from urllib import request


def main() -> None:
    try:
        import truststore
    except ImportError as exc:
        raise RuntimeError("optional truststore package is required for system trust") from exc

    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("system trust requires certificate and hostname verification")
    request.install_opener(request.build_opener(request.HTTPSHandler(context=context)))
    runpy.run_path(
        str(Path(__file__).with_name("m6_reference_worker_live_proof.py")),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
