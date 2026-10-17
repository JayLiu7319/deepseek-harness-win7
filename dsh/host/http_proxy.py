"""Process-wide rc3 proxy installation and explicit request/child routing."""
import copy
import http.client
import os
import urllib.request

from dsh.host.http_proxy_policy import (
    POLICY_ENV_NAMES, PROXY_ENV_NAMES, is_supported_proxy_url, proxy_for_url,
    resolve_proxy_policy,
)
from dsh.host.http_proxy_transport import connect_proxy, proxy_authorization, proxy_request_target


_active = None
_inherited = None
_installed = None


def _snapshot():
    return {name: os.environ.get(name) for names in POLICY_ENV_NAMES.values() for name in names}


def _write(values):
    previous = _snapshot()
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    return previous


def proxy_route_for(url):
    if _active is None or _installed is None:
        return {'proxied': False}
    proxy = proxy_for_url(_active, url)
    return {'proxied': False} if proxy is None else {'proxied': True, 'proxy': proxy, 'dispatcher': _installed}


def proxy_handler():
    """Disable ambient urllib routing only while an explicit policy is installed."""
    return urllib.request.ProxyHandler({}) if _active is not None else urllib.request.ProxyHandler()


def _connection_factory(connection_type, route, scheme, context=None):
    class Connection(connection_type):
        def putrequest(self, method, url, *args, **kwargs):
            if scheme == 'http':
                url = proxy_request_target(self, url)
            super().putrequest(method, url, *args, **kwargs)
            authorization = proxy_authorization(route['proxy'])
            if scheme == 'http' and authorization is not None:
                self.putheader('Proxy-Authorization', authorization)

        def connect(self):
            connect_proxy(self, route['proxy'], scheme, context=context)
    return Connection


class _Http(urllib.request.HTTPHandler):
    def http_open(self, request):
        route = proxy_route_for(request.full_url)
        factory = _connection_factory(http.client.HTTPConnection, route, 'http') if route['proxied'] else http.client.HTTPConnection
        return self.do_open(factory, request)


class _Https(urllib.request.HTTPSHandler):
    def https_open(self, request):
        route = proxy_route_for(request.full_url)
        factory = _connection_factory(http.client.HTTPSConnection, route, 'https', self._context) if route['proxied'] else http.client.HTTPSConnection
        return self.do_open(factory, request, context=self._context, check_hostname=self._check_hostname)


def build_opener(*handlers):
    """For consumers that build their own opener rather than using urlopen."""
    if _active is None:
        return urllib.request.build_opener(*handlers)
    return urllib.request.build_opener(proxy_handler(), _Http(), _Https(), *handlers)


async def install_proxy_from_environment(env, report):
    global _active, _inherited, _installed
    resolution = resolve_proxy_policy(env)
    for item in resolution['diagnostics']:
        report(item['message'])
    policy = copy.deepcopy(resolution['policy'])
    previous = (_active, _inherited, _installed, urllib.request._opener)
    saved_env = None
    if policy['source'] != 'none':
        if _inherited is None:
            _inherited = _snapshot()
        saved_env = _write({name: policy.get(field) for field, names in POLICY_ENV_NAMES.items() for name in names})
    elif _inherited is not None:
        saved_env = _write(_inherited)
    # One stable identity accompanies every captured route. Individual urllib
    # requests own their sockets; restoring the policy never closes admitted IO.
    _active, _installed = policy, object() if policy['source'] != 'none' else None
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({}), _Http(), _Https()))
    disposed = False

    async def dispose():
        nonlocal disposed
        global _active, _inherited, _installed
        if disposed:
            return
        disposed = True
        _active, _inherited, _installed, opener = previous
        urllib.request._opener = opener
        if saved_env is not None:
            _write(saved_env)
    return dispose


def proxy_environment_for_child():
    if _active is None or _active['source'] == 'none' or _inherited is None:
        return {}
    overlay = {'NODE_USE_ENV_PROXY': '1'}
    for field, names in POLICY_ENV_NAMES.items():
        named = field != 'noProxy' and any(_inherited[name] is not None for name in names)
        for name in names:
            overlay[name] = _inherited[name] if named else _active.get(field)
    if any(overlay[name] is not None and not is_supported_proxy_url(overlay[name])
           for name in POLICY_ENV_NAMES['httpProxy'] + POLICY_ENV_NAMES['httpsProxy']):
        overlay.pop('NODE_USE_ENV_PROXY', None)
    return overlay


def cleared_proxy_env():
    return {name: None for name in PROXY_ENV_NAMES}


def requests_session():
    """An owned requests consumer, e.g. OTel, with the same per-URL matcher."""
    import requests
    class Adapter(requests.adapters.HTTPAdapter):
        def cert_verify(self, connection, url, verify, cert):
            # A forwarding HTTPS proxy still has a TLS peer even when its
            # target URL is HTTP. requests otherwise disables its verification.
            if getattr(connection, 'scheme', None) == 'https' and url.startswith('http:'):
                url = 'https:' + url[len('http:'):]
            return super().cert_verify(connection, url, verify, cert)

    class Session(requests.Session):
        def send(self, request, **kwargs):
            if _active is not None:
                route = proxy_route_for(request.url)
                kwargs['proxies'] = {'http': route['proxy'], 'https': route['proxy']} if route['proxied'] else {}
            return super().send(request, **kwargs)
    session = Session()
    session.mount('http://', Adapter())
    session.mount('https://', Adapter())
    return session


installProxyFromEnvironment = install_proxy_from_environment
proxyRouteFor = proxy_route_for
proxyEnvironmentForChild = proxy_environment_for_child
clearedProxyEnv = cleared_proxy_env
