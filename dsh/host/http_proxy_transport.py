"""Owned HTTP CONNECT sockets, including TLS inside an HTTPS proxy tunnel."""
import base64
import http.client
import io
import ssl
from urllib.parse import unquote, urlsplit

from dsh.host.http_proxy_policy import parse_url


def proxy_authorization(proxy):
    parsed = parse_url(proxy)
    text = proxy.strip().split(':', 1)[1].replace('\\', '/')
    credentials = urlsplit(parsed['protocol'] + '//' + text.lstrip('/'))
    if credentials.username is None:
        return None
    token = ('%s:%s' % (unquote(credentials.username), unquote(credentials.password or ''))).encode('utf-8')
    return 'Basic ' + base64.b64encode(token).decode('ascii')


def proxy_request_target(connection, url):
    host = '[' + connection.host + ']' if ':' in connection.host else connection.host
    authority = host if connection.port == 80 else '%s:%s' % (host, connection.port)
    return 'http://' + authority + url


class _RawTls(io.RawIOBase):
    def __init__(self, transport):
        super().__init__()
        self.transport = transport
        transport._readers += 1

    def readable(self):
        return True

    def readinto(self, buffer):
        return self.transport.recv_into(buffer)

    def close(self):
        if not self.closed:
            self.transport._readers -= 1
            self.transport._finish_close()
        super().close()


class TlsSocket:
    """SSL MemoryBIO over a socket or an existing TLS stream.

    The optional wait/check callbacks retain the streaming caller's own timeout
    and cancellation owner. No handshake or CONNECT step gets a private deadline.
    """
    def __init__(self, lower, hostname, context=None, wait=None, check=None):
        self.lower, self.wait, self.check = lower, wait, check or (lambda: None)
        self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.ssl = (context or ssl.create_default_context()).wrap_bio(self.incoming, self.outgoing, server_hostname=hostname)
        self.pending = b''
        self._readers, self._closed, self._eof = 0, False, False
        self._io(self.ssl.do_handshake)

    def _call(self, fn, *args):
        while True:
            self.check()
            try:
                return fn(*args)
            except BlockingIOError:
                if self.wait is None:
                    raise
                self.wait(self.lower, write=getattr(fn, '__name__', '') == 'send')
            except ssl.SSLWantReadError:
                if self.wait is None:
                    raise
                self.wait(self.lower)
            except ssl.SSLWantWriteError:
                if self.wait is None:
                    raise
                self.wait(self.lower, write=True)

    def _flush(self):
        while self.pending or self.outgoing.pending:
            if not self.pending:
                self.pending = self.outgoing.read()
            count = self._call(self.lower.send, self.pending)
            if not count:
                raise OSError('proxy TLS socket closed during write')
            self.pending = self.pending[count:]

    def _io(self, fn, *args):
        while True:
            self.check()
            try:
                result = fn(*args)
            except ssl.SSLWantReadError:
                self._flush()
                data = self._call(self.lower.recv, 65536)
                if not data:
                    if self._eof:
                        raise ssl.SSLEOFError('proxy TLS socket closed unexpectedly')
                    self._eof = True
                    self.incoming.write_eof()
                else:
                    self.incoming.write(data)
            except ssl.SSLWantWriteError:
                self._flush()
            else:
                self._flush()
                return result

    def send(self, data):
        return self._io(self.ssl.write, data)

    def sendall(self, data):
        pending = memoryview(data)
        while pending:
            pending = pending[self.send(pending):]

    def recv(self, count, flags=0):
        if flags:
            raise ValueError('TLS recv flags are unsupported')
        return self._io(self.ssl.read, count)

    def recv_into(self, buffer, count=0, flags=0):
        value = self.recv(count or len(buffer), flags)
        buffer[:len(value)] = value
        return len(value)

    def makefile(self, mode='rb', buffering=None):
        if mode != 'rb':
            raise ValueError('proxy TLS socket supports binary readers only')
        raw = _RawTls(self)
        return raw if buffering == 0 else io.BufferedReader(raw)

    def fileno(self):
        return self.lower.fileno()

    def settimeout(self, value):
        self.lower.settimeout(value)

    def gettimeout(self):
        return self.lower.gettimeout()

    def shutdown(self, how):
        self.lower.shutdown(how)

    def close(self):
        self._closed = True
        self._finish_close()

    def _finish_close(self):
        if self._closed and not self._readers:
            self.lower.close()


def connect_proxy(connection, proxy, origin_scheme, context=None, wait=None, check=None):
    """Open an owned tunnel; never send origin credentials to the proxy hop."""
    parsed = parse_url(proxy)
    proxy_host, proxy_port = parsed['hostname'], parsed['port']
    sock = connection._create_connection((proxy_host, proxy_port), connection.timeout, connection.source_address)
    connection.sock = sock
    try:
        if parsed['protocol'] == 'https:':
            connection.sock = TlsSocket(sock, proxy_host, context=context, wait=wait, check=check)
        if origin_scheme == 'http':
            return
        host = '[' + connection.host + ']' if ':' in connection.host else connection.host
        authority = '%s:%s' % (host, connection.port)
        headers = ['CONNECT %s HTTP/1.1' % authority, 'Host: ' + authority]
        authorization = proxy_authorization(proxy)
        if authorization is not None:
            headers.append('Proxy-Authorization: ' + authorization)
        connection.send(('\r\n'.join(headers) + '\r\n\r\n').encode('ascii'))
        response = connection.response_class(connection.sock, method='CONNECT')
        try:
            response.begin()
            if response.status != 200:
                raise OSError('Tunnel connection failed: %s %s' % (response.status, response.reason))
        finally:
            response.close()
        if origin_scheme == 'https':
            connection.sock = TlsSocket(connection.sock, connection.host, context=context, wait=wait, check=check)
    except BaseException:
        connection.sock.close()
        connection.sock = None
        raise
