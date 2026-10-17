"""Stacked actual policy installs, restoration and subprocess environment."""
import asyncio,os
from unittest.mock import patch
from dsh.host.http_proxy import install_proxy_from_environment,proxy_route_for,proxy_environment_for_child,cleared_proxy_env
from dsh.subprocess.service import scrubbed_parent_env
from dsh.host.http_proxy_policy import PROXY_ENV_NAMES
from scripts.oracles.http_proxy_current_python import Lookup

def execute(test):
    async def run():
        with patch.dict(os.environ,test.get('ambient',{}),clear=True):
            initial={key:os.environ.get(key) for key in PROXY_ENV_NAMES};stages=[];disposers=[]
            def observe(reported):
                routes=[]
                for url in test['urls']:
                    route=proxy_route_for(url);routes.append({k:v for k,v in route.items() if k!='dispatcher'})
                child=scrubbed_parent_env()
                child={key.upper():value for key,value in child.items()} if os.name=='nt' else child
                return dict(reported=reported,routes=routes,overlay=proxy_environment_for_child(),published={key:os.environ.get(key) for key in PROXY_ENV_NAMES},child=child)
            try:
                for values in test['installs']:
                    reported=[];disposers.append(await install_proxy_from_environment(Lookup(values),reported.append));stages.append(observe(reported))
                while disposers:
                    await disposers.pop()();stages.append(observe([]))
                return dict(stages=stages,restored={key:os.environ.get(key) for key in PROXY_ENV_NAMES}==initial,cleared=cleared_proxy_env())
            finally:
                for dispose in reversed(disposers):await dispose()
    return asyncio.run(run())
