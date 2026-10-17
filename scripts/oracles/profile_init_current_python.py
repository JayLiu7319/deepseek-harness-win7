"""Current launcher arguments and exclusive template initialization IO."""
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.cli.args import parse_dsh_args
from dsh.boot.profile_boot import initialize_profile_from_default
from dsh.boot.profile import PROFILE_TEMPLATES


def execute(test):
    if test['operation']=='args':
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            try:return dict(value=parse_dsh_args(test['argv'],'1.2.3'))
            except SystemExit as error:return dict(exit=error.code)
    with tempfile.TemporaryDirectory(prefix='rc3-profile-init-') as directory:
        home=Path(directory);target=home/'profiles'/test.get('name','rescue')
        for name,content in test.get('files',{}).items():
            path=home/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        if test.get('existingDirectory'):target.mkdir(parents=True,exist_ok=True)
        before={str(path.relative_to(home)):path.read_bytes() for path in home.rglob('*') if path.is_file()}
        # Existing product convenience profiles are explicit adaptations;
        # paired original metadata/diagnostics use its exact five templates.
        templates={key:PROFILE_TEMPLATES[key] for key in ('acp','web','headless','sdk','sdk-minimal')}
        with patch('dsh.boot.profile_boot.PROFILE_TEMPLATES',templates):
            try:
                initialize_profile_from_default(test.get('name','rescue'),test.get('template','web'),str(home));outcome=dict(ok=True)
            except Exception as error:outcome=dict(error=str(error).replace(str(home),'$HOME').replace('\\','/'))
        after={str(path.relative_to(home)):path.read_bytes() for path in home.rglob('*') if path.is_file()}
        manifest=target/'package.json'
        return dict(outcome=outcome,exists=target.exists(),beforePreserved=all(after.get(key)==data for key,data in before.items()),files=sorted(str(path.relative_to(target)).replace('\\','/') for path in target.rglob('*') if path.is_file()) if target.is_dir() else [],manifest=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() and not test.get('invalidManifest') else None)
