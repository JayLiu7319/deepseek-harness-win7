This self-signed localhost certificate and public test private key are only for
loopback TLS regression tests. They are not deployment credentials and must not
be trusted outside the test-created SSL context.

`proxy-test-cert.pem` and its public test key serve `origin.test`, `localhost`
and `127.0.0.1` in local HTTP proxy / nested TLS regressions. The proxy fixture
maps the reserved `.test` name to its own local listener; no public service is
contacted. Generated with OpenSSL `req -x509 -newkey rsa:2048 -sha256 -nodes
-days 3650 -subj /CN=origin.test -addext
subjectAltName=DNS:origin.test,DNS:localhost,IP:127.0.0.1`.
