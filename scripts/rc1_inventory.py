"""Inventory rc.1 responsibilities and distinguish registration from observed activation."""
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PIN = 'a66e4702047846cdaa10c66c9d3df3951f5ea70d'


def generate(source, active=False, runtime_reports=()):
    from scripts.migration_inventory import classification
    from dsh.boot.plugin_registry import HARNESS_PLUGIN_CLASSES
    from dsh.boot.profile import PROFILE_TEMPLATES
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], encoding='utf-8').strip()
    if head != PIN or subprocess.check_output(['git', '-C', str(source), 'diff', 'HEAD', '--']):
        raise ValueError('Candidate Source must be clean pinned rc.1')
    # NUL paths preserve Unicode, whitespace and Git path identities.
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode('utf-8').rstrip('\0').split('\0')
    manifests = []
    for path in tracked:
        if Path(path).name != 'package.json':
            continue
        raw = (source / path).read_bytes()
        body = json.loads(raw.decode('utf-8'))
        role, responsibility = classification('reference/' + path)
        manifests.append(dict(path=path, name=body.get('name'), sha256=hashlib.sha256(raw).hexdigest(),
            classification=role, responsibility=responsibility, body=body))
    by_name = {row['name']: row for row in manifests if row['name']}
    def package_name(name):
        return next((candidate for candidate in sorted(by_name, key=len, reverse=True)
                     if name == candidate or name.startswith(candidate + '/')), name)
    declarations = {}
    for row in manifests:
        path = Path(row['path']).parent / 'cordis.patch.yml'
        if str(path.as_posix()) in tracked:
            text = (source / path).read_text(encoding='utf-8')
            declarations[row['name']] = [dict(name=match.group(1), source=path.as_posix(),
                line=text.count('\n', 0, match.start()) + 1, policy='declared row; activation/disabled/JS conditions not evaluated')
                for match in re.finditer(r"\bname:\s*['\"](@[^'\"]+)['\"]", text)]
    profiles = {}
    for profile, template in PROFILE_TEMPLATES.items():
        roots = list(template['bundles'])
        pending, reached = deque(roots), set()
        while pending:
            name = pending.popleft()
            if name in reached:
                continue
            reached.add(name)
            for row in declarations.get(name, []):
                pending.append(package_name(row['name']))
            owner = by_name.get(name)
            if owner is not None:
                for kind in ('dependencies', 'peerDependencies', 'optionalDependencies'):
                    pending.extend(dep for dep in owner['body'].get(kind, {}) if dep in by_name)
        profiles[profile] = dict(roots=roots, declared_dependency_closure=sorted(reached),
            limitation='Installation profile template + literal candidate bundle rows + non-dev workspace dependencies; potential reachability, never observed activation')
    contracts = [json.loads(path.read_text(encoding='utf-8')) for path in (ROOT / 'migration/contracts').glob('*.json')]
    history = ROOT / 'migration/history/2026-10-14-alpha1/modules.json'
    old = json.loads((history if history.is_file() else ROOT / 'migration/modules.json').read_text(encoding='utf-8'))
    old_paths = {row['path'][len('reference/'):]: row for row in old['manifests']}
    changed = subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only', '-z', old['target_upstream'], PIN]).decode('utf-8').rstrip('\0').split('\0')
    paired = {
        '@deepseek-ai/dsh-file-reference': ['grammar', 'mentions'],
        '@deepseek-ai/dsh-file-reference-local': ['searches', 'searchLimits'],
        '@deepseek-ai/dsh-session-turn-outline': ['outline', 'changes', 'checkpoint'],
        '@deepseek-ai/dsh-session-projection': ['changes', 'checkpoint', 'projectionLineage'],
        '@deepseek-ai/dsh-session': ['positions', 'indexed', 'lineage', 'strictHeaders'],
        '@deepseek-ai/dsh-session-persistence-jsonl': ['storageLineage'],
        '@deepseek-ai/dsh-system-prompt': ['orders'],
        '@deepseek-ai/dsh-agent-loop': ['turnBoundary', 'turnBoundaryEvents'],
        '@deepseek-ai/dsh-schedule': ['scheduleProjection', 'scheduleStates'],
        '@deepseek-ai/dsh-llm-retry': ['retryProjection'],
    }
    observed = {}
    receipts = []
    for path in runtime_reports:
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('status') != 'qualified' or report.get('side') != 'native':
            raise ValueError('Only qualified native browser observations may describe activation')
        receipts.append(dict(path=path.as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for phase in report['phases']:
            for entry in phase['hostReceipt']['loaderEntries']:
                observed.setdefault(package_name(entry['name']), []).append(dict(
                    preset=report['preset'], phase=phase['name'], entry=entry))
    for row in manifests:
        owner = Path(row['path']).parent.as_posix()
        affected = [path for path in changed if path == row['path'] or owner != '.' and path.startswith(owner + '/')]
        runtime_changed = [path for path in affected if '/src/' in path]
        related = [contract['id'] for contract in contracts if any(
            path == 'reference/' + row['path'] or path.startswith('reference/' + owner + '/')
            for path in contract.get('source_paths', []))]
        implementation = HARNESS_PLUGIN_CLASSES.get(row['name'])
        aliases = {name: provider for name, provider in HARNESS_PLUGIN_CLASSES.items()
                   if name == row['name'] or row['name'] and name.startswith(row['name'] + '/')}
        runtime_profiles = [name for name, profile in profiles.items() if row['name'] in profile['declared_dependency_closure']]
        body = row.pop('body')
        row.update(owner=owner, workspace_dependencies=[dict(name=name, kind=kind, version=version)
            for kind in ('dependencies', 'peerDependencies', 'optionalDependencies', 'devDependencies')
            for name, version in sorted(body.get(kind, {}).items()) if name in by_name],
            change='added' if row['path'] not in old_paths else 'changed' if affected else 'unchanged',
            changed_paths=affected, declared_profiles=runtime_profiles, python_loader_provider=implementation,
            changed_runtime_sources=runtime_changed,
            python_loader_entrypoints=aliases,
            observed_loader_entries=observed.get(row['name'], []),
            client_bundle='lib/client.js' if (source / owner / 'lib/client.js').is_file() else None,
            historical_alpha_contracts=related, rc1_bounded_paired_cases=paired.get(row['name'], []),
            parity='not-certified-by-inventory',
            evidence_scope='Loader provider and alpha contract discovery require rc1 requalification; listed candidate paired cases cover only their observations',
            gap='Requalify changed provider, consumers and source tests' if implementation else
                'Original built client; verify active rows and browser journeys' if row['classification'] == 'frontend' else
                'Map actual Python service/consumer or platform/build responsibility; missing Loader row alone is not a missing capability',
            priority='P1-independent' if any(name in owner for name in ('lsp', 'e2b', 'exa', 'perplexity')) else
                'P0-review' if (runtime_changed or row['path'] not in old_paths) and runtime_profiles else 'P1-review' if affected else 'review',
            priority_basis='Candidate triage only: declared dependency reach is not observed activation; promote to a release blocker after provider/consumer review',
            action_items=['A03', 'A04'] if owner.startswith(('packages/core/session', 'packages/session/')) else
                ['A05'] if 'file-reference' in owner else ['A06'] if row['classification'] == 'frontend' else
                ['A04', 'A07'] if runtime_profiles else ['A07'],
            platform_policy='Win7/Python3.8 adapter qualification required' if row['classification'] == 'platform' else
                'Optional LSP stdio server; no new default dependency' if 'lsp' in owner else
                'Optional external cloud credentials and real-provider evidence' if any(name in owner for name in ('e2b', 'exa', 'perplexity')) else
                'Retain upstream ownership; classify implementation before choosing a platform adaptation')
    return dict(schema_version=2, target_upstream=PIN, historical_upstream=old['target_upstream'],
        active_upstream=PIN if active else None,
        scope='active rc1 capability triage; registration and executable observations are separate; optional providers are not default-profile parity claims' if active else 'candidate inventory, not active baseline or accepted parity',
        runtime_receipts=receipts,
        counts=dict(manifests=len(manifests), classifications=dict(Counter(row['classification'] for row in manifests))),
        profiles=profiles, bundle_declarations=declarations,
        removed_manifests=[dict(path=path, name=row['name'], action='preserve historical evidence; triage canonical retirement and user-data compatibility')
            for path, row in old_paths.items() if path not in {entry['path'] for entry in manifests}],
        manifests=sorted(manifests, key=lambda row: row['path']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--active', action='store_true')
    parser.add_argument('--runtime-report', type=Path, action='append', default=[])
    args = parser.parse_args()
    value = generate(args.source_root.resolve(), args.active, args.runtime_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(value['counts']))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
