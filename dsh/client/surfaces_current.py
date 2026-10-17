"""Pure host halves of the five rc.3 browser-only packages."""
from dsh.client.surfaces import _empty_host_half

for _slug in ('resources', 'ui-sidebar-right', 'ui-sidebar-documentpreview',
              'ui-sidebar-files', 'ui-open-in-app'):
    _name = ''.join(word.capitalize() for word in _slug.split('-')) + 'Host'
    globals()[_name] = _empty_host_half(
        _name, '@deepseek-ai/dsh-client-' + _slug,
        'packages/client/' + _slug + '/src/index.ts')
