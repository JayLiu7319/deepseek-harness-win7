"""Actual pure proxy policy observations."""
from dsh.host.http_proxy_policy import resolve_proxy_policy, proxy_for_url, bypasses_proxy, is_loopback_host, is_supported_proxy_url

class Lookup:
    def __init__(self,values):self.values=values
    def get(self,name):return {'value':self.values[name]} if name in self.values else None

def execute(test):
    if test['operation']=='loopback':return [is_loopback_host(host) for host in test['hosts']]
    if test['operation']=='bypass':return [bypasses_proxy(case['noProxy'],case['url']) for case in test['requests']]
    if test['operation']=='supported':return [is_supported_proxy_url(url) for url in test['urls']]
    result=resolve_proxy_policy(Lookup(test.get('env',{})))
    return dict(result,routes=[proxy_for_url(result['policy'],url) for url in test.get('urls',[])])
