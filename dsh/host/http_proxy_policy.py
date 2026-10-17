"""Transport-free rc3 outbound proxy policy, compatible with Python 3.8."""
import ipaddress
import re
from urllib.parse import unquote, urlsplit

import idna


LOOPBACK_NO_PROXY = ['localhost', '127.0.0.1', '::1', '[::1]']
POLICY_ENV_NAMES = {'httpProxy': ['http_proxy', 'HTTP_PROXY'],
                    'httpsProxy': ['https_proxy', 'HTTPS_PROXY'],
                    'noProxy': ['no_proxy', 'NO_PROXY']}
PROXY_ENV_NAMES = [name for names in POLICY_ENV_NAMES.values() for name in names] + ['all_proxy', 'ALL_PROXY']
DIRECT_POLICY = {'noProxy': '', 'source': 'none'}
JS_SPACE = '\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def parse_url(value):
    """Return URL protocol/ASCII hostname/effective port, or None if invalid.

    Policy observes only these URL fields; preserve the original proxy spelling
    in the policy itself. Special-scheme hosts use URL-style numeric IPv4.
    """
    text = value.strip(''.join(chr(n) for n in range(33))).replace('\t', '').replace('\r', '').replace('\n', '')
    match = re.match(r'^([A-Za-z][A-Za-z0-9+.-]*):', text)
    if match is None:
        return None
    scheme = match.group(1).lower()
    if scheme not in ('http', 'https', 'ws', 'wss', 'ftp', 'file'):
        return {'protocol': scheme + ':', 'hostname': '', 'port': None}
    rest = text[match.end():].replace('\\', '/')
    try:
        parsed = urlsplit(scheme + '://' + rest.lstrip('/'))
        host = parsed.hostname
        port = parsed.port
        if not host:
            return None
        if ':' in host:
            if '%' in host:
                return None
            host = str(ipaddress.IPv6Address(host))
        else:
            host = unquote(host, errors='strict')
            if re.search(r'[\x00-\x20\x7f%/:<>?@\[\]\\^|]', host):
                return None
            host = (host if host.isascii() else idna.encode(host, uts46=True, std3_rules=False).decode('ascii')).lower()
            parts = host.rstrip('.').split('.')
            def number(part):
                if part.lower().startswith('0x'):
                    return int(part[2:] or '0', 16)
                if len(part) > 1 and part.startswith('0'):
                    return int(part, 8)
                return int(part, 10)
            try:
                number(parts[-1])
                numeric = True
            except ValueError:
                numeric = parts[-1].isdigit()
            if numeric:
                if len(parts) > 4 or any(not part for part in parts):
                    return None
                values = [number(part) for part in parts]
                if any(n > 255 or n < 0 for n in values[:-1]) or not 0 <= values[-1] < 256 ** (5 - len(values)):
                    return None
                address = values[-1] + sum(n * 256 ** (3 - i) for i, n in enumerate(values[:-1]))
                host = str(ipaddress.IPv4Address(address))
        return {'protocol': scheme + ':', 'hostname': host,
                'port': port if port is not None else (443 if scheme in ('https', 'wss') else 80 if scheme in ('http', 'ws') else 21 if scheme == 'ftp' else None)}
    except (ValueError, UnicodeError, idna.IDNAError):
        return None


def is_supported_proxy_url(value):
    parsed = parse_url(value)
    return parsed is not None and parsed['protocol'] in ('http:', 'https:')


def _read_env(env, lower):
    for name in (lower, lower.upper()):
        entry = env.get(name)
        if entry is not None:
            value = (entry.get('value') if isinstance(entry, dict) else entry.value).strip(JS_SPACE)
            if value:
                return name, value
    return None


def _accept(candidate, diagnostics):
    if candidate is None:
        return 'absent', None
    name, value = candidate
    parsed = parse_url(value)
    if parsed is None:
        kind, message = 'invalid', '%s is not a valid URL; connecting directly' % name
    elif parsed['protocol'] in ('socks:', 'socks4:', 'socks4a:', 'socks5:', 'socks5h:'):
        kind, message = 'socks', '%s names a SOCKS proxy, which is not supported; connecting directly for that scheme — set an http:// or https:// proxy URL instead' % name
    elif parsed['protocol'] not in ('http:', 'https:'):
        kind, message = 'invalid', '%s uses the unsupported %s// scheme; connecting directly for that scheme — set an http:// or https:// proxy URL instead' % (name, parsed['protocol'])
    else:
        return 'accepted', value
    diagnostics.append({'kind': kind, 'origin': name, 'message': message})
    return 'rejected', None


def resolve_proxy_policy(env):
    diagnostics = []
    all_kind, all_value = _accept(_read_env(env, 'all_proxy'), diagnostics)
    http_kind, http_value = _accept(_read_env(env, 'http_proxy'), diagnostics)
    https_kind, https_value = _accept(_read_env(env, 'https_proxy'), diagnostics)
    http_proxy = http_value if http_kind != 'absent' else all_value
    https_proxy = https_value if https_kind != 'absent' else all_value or http_proxy
    if http_proxy is None and https_proxy is None:
        return {'policy': dict(DIRECT_POLICY), 'diagnostics': diagnostics}
    supplied = _read_env(env, 'no_proxy')
    entries = [part for part in re.split('[,' + JS_SPACE + ']+', supplied[1] if supplied else '') if part]
    present = {part.lower() for part in entries}
    no_proxy = '*' if '*' in entries else ','.join(entries + [part for part in LOOPBACK_NO_PROXY if part not in present])
    policy = {'noProxy': no_proxy, 'source': 'env'}
    if http_proxy is not None:
        policy['httpProxy'] = http_proxy
    if https_proxy is not None:
        policy['httpsProxy'] = https_proxy
    return {'policy': policy, 'diagnostics': diagnostics}


def is_loopback_host(hostname):
    host = re.sub(r'\.$', '', re.sub(r'^\[|\]$', '', hostname)).lower()
    if host == 'localhost' or host.endswith('.localhost') or host in ('::1', '::', '0.0.0.0'):
        return True
    mapped = re.fullmatch(r'::ffff:([0-9a-f]{1,4}):[0-9a-f]{1,4}', host)
    if mapped:
        return int(mapped.group(1), 16) >> 8 == 127
    if host.startswith('::ffff:'):
        host = host[len('::ffff:'):]
    octet = r'(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)'
    return re.fullmatch(r'127\.' + octet + r'\.' + octet + r'\.' + octet, host, flags=re.ASCII) is not None


def bypasses_proxy(no_proxy, url):
    parsed = parse_url(url) if isinstance(url, str) else url
    host = re.sub(r'\.$', '', parsed['hostname']).lower()
    port = str(parsed['port'] if parsed['port'] is not None else 80)
    for raw in re.split('[,' + JS_SPACE + ']+', no_proxy):
        entry = raw.strip(JS_SPACE).lower()
        if entry == '*':
            return True
        own_port = None
        candidate = entry
        if entry.startswith('[') and ']' in entry:
            close = entry.index(']')
            candidate = entry[1:close]
            if entry[close + 1:].startswith(':'):
                own_port = entry[close + 2:]
        elif entry.count(':') == 1:
            candidate, own_port = entry.split(':', 1)
        if own_port is not None and own_port != port:
            continue
        candidate = re.sub(r'^\*?\.', '', candidate)
        candidate = re.sub(r'\.$', '', candidate)
        if candidate and (host == candidate or host.endswith('.' + candidate)):
            return True
    return False


def proxy_for_url(policy, url):
    parsed = parse_url(url) if isinstance(url, str) else url
    if parsed is None:
        return None
    proxy = policy.get('httpsProxy') if parsed['protocol'] == 'https:' else policy.get('httpProxy') if parsed['protocol'] == 'http:' else None
    if proxy is None or is_loopback_host(parsed['hostname']) or bypasses_proxy(policy['noProxy'], parsed):
        return None
    return proxy
