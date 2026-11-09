Test-only certificates for `tests/test_ytdlp_windows_trust.py`, standing in for an
antivirus or company proxy that inspects HTTPS by adding its own root to Windows.

- `root.pem` / `root.der`: a self-signed root, trusted nowhere. Its private key was
  deleted after signing, so it can't sign anything else.
- `server.pem` / `server.key`: a certificate for `127.0.0.1` signed by that root,
  used by the test's local HTTPS server.

Nothing here is installed into any real certificate store.
