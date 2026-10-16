"""Cache boundary over real YAML, with hostile contract mutations."""
import copy
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / '.github/workflows/quality-gate.yml'
PIN = '0057852bfaa89a56745cba8c7296529d2fc39830'
CACHE_PATH = '${{ github.workspace }}/.devsift/local/nuget'
KEY = "devsift-nuget-v1-${{ runner.os }}-${{ runner.arch }}-sdk9.0.205-go1.21.3-node24-${{ hashFiles('native/**/*.csproj', 'native/**/packages.lock.json', 'native/**/global.json', 'native/**/NuGet.Config', 'native/**/Directory.Build.props', 'native/**/Directory.Build.targets', 'native/frontend/package-lock.json', 'native/go/go.mod', 'requirements-dev.txt') }}"
GUARD = "success() && github.event_name == 'push' && github.ref == 'refs/heads/main' && steps.nuget-cache.outputs.cache-hit != 'true' && steps.nuget-cache.outputs.cache-primary-key != ''"


def contract(workflow):
    def require(ok):
        if not ok:
            raise AssertionError('Unsafe cache contract')
    require(workflow['permissions'] == {'contents': 'read'})
    analysis = workflow['jobs']['analysis']
    require(analysis.get('permissions', workflow['permissions']) == {'contents': 'read'})
    steps = analysis['steps']
    restores = [s for s in steps if s.get('id') == 'nuget-cache']
    saves = [s for s in steps if s.get('id') == 'save-nuget-cache']
    require(len(restores) == len(saves) == 1)
    restore, save = restores[0], saves[0]
    require(set(restore) == {'name', 'id', 'uses', 'with'})
    require(restore['uses'] == 'actions/cache/restore@' + PIN)
    require(restore['with'] == {'path': CACHE_PATH, 'key': KEY,
                               'enableCrossOsArchive': 'false', 'fail-on-cache-miss': 'false'})
    require(set(save) == {'name', 'id', 'uses', 'if', 'with'})
    require(save['uses'] == 'actions/cache/save@' + PIN)
    require(save['if'] == GUARD)
    require(save['with'] == {'path': CACHE_PATH, 'key': '${{ steps.nuget-cache.outputs.cache-primary-key }}'})
    setup = next(s for s in steps if s.get('id') == 'setup-native')
    scan = next(s for s in steps if s.get('id') == 'quality')
    require('if' not in setup and 'if' not in scan)
    require(setup['run'].strip() == 'python tools/build_native.py')
    require(steps.index(restore) < steps.index(setup) < steps.index(scan) < steps.index(save) < len(steps)-1)
    require(all(steps.index(s) < steps.index(restore) for s in steps
                if s.get('uses', '').startswith(('actions/setup-', 'actions/checkout@'))))
    for job in workflow['jobs'].values():
        for step in job['steps']:
            if step.get('uses', '').startswith('actions/cache'):
                require(job is analysis and (step is restore or step is save))
    require(analysis['strategy']['matrix'] == {'os': ['ubuntu-latest', 'windows-latest']})


class CacheContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml
        cls.workflow = yaml.load(PATH.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)

    def test_exact_cache_boundary(self):
        contract(self.workflow)

    def test_hostile_cache_mutations_rejected(self):
        def mutate(fn):
            item = copy.deepcopy(self.workflow)
            steps = item['jobs']['analysis']['steps']
            restore = next(s for s in steps if s.get('id') == 'nuget-cache')
            save = next(s for s in steps if s.get('id') == 'save-nuget-cache')
            fn(item, steps, restore, save)
            return item
        mutations = [
            lambda w, ss, r, s: r.update(uses='actions/cache@'+PIN),
            lambda w, ss, r, s: r.update(uses='actions/cache/restore@v4'),
            lambda w, ss, r, s: r['with'].update({'restore-keys': 'devsift-nuget-'}),
            lambda w, ss, r, s: r['with'].update(path='${{ github.workspace }}/.devsift/local'),
            lambda w, ss, r, s: s['with'].update(path='~/.nuget'),
            lambda w, ss, r, s: r['with'].update(enableCrossOsArchive='true'),
            lambda w, ss, r, s: r['with'].update(key=KEY.replace('runner.arch', 'github.head_ref')),
            lambda w, ss, r, s: r['with'].update(key=KEY.replace("'native/**/packages.lock.json', ", '')),
            lambda w, ss, r, s: s.update({'if': 'success()'}),
            lambda w, ss, r, s: s.update({'if': GUARD.replace("github.event_name == 'push'", "github.event_name == 'pull_request'")}),
            lambda w, ss, r, s: s.update({'if': GUARD.replace(" && github.ref == 'refs/heads/main'", '')}),
            lambda w, ss, r, s: s['with'].update(key='different-key'),
            lambda w, ss, r, s: r['with'].update(key=KEY.replace('runner.os', 'github.event.pull_request.title')),
            lambda w, ss, r, s: r['with'].update({'lookup-only': 'true'}),
            lambda w, ss, r, s: s.update({'if': GUARD.replace('success()', 'always()')}),
            lambda w, ss, r, s: next(x for x in ss if x.get('id')=='setup-native').update({'if': "steps.nuget-cache.outputs.cache-hit != 'true'"}),
            lambda w, ss, r, s: next(x for x in ss if x.get('id')=='quality').update({'if': "steps.nuget-cache.outputs.cache-hit != 'true'"}),
            lambda w, ss, r, s: w['permissions'].update({'contents': 'write'}),
            lambda w, ss, r, s: w['jobs']['publish-sarif']['steps'].append(copy.deepcopy(s)),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(AssertionError):
                contract(mutate(mutation))


if __name__ == '__main__':
    unittest.main()
