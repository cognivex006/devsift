"""YAML security contract: mutations must not silently widen token/source scope."""
import copy
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / '.github/workflows/quality-gate.yml'
PINS = {
    'actions/checkout': '11d5960a326750d5838078e36cf38b85af677262',
    'actions/setup-python': 'a26af69be951a213d495a4c3e4e4022e16d87065',
    'actions/setup-dotnet': '67a3573c9a986a3f9c594539f4ab511d57bb3ce9',
    'actions/setup-go': '40f1582b2485089dde7abd97c1529aa768e1baff',
    'actions/setup-node': '49933ea5288caeca8642d1e84afbd3f7d6820020',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
    'actions/download-artifact': 'd3f86a106a0bac45b974a628896c90dbdf5c8093',
    'github/codeql-action/upload-sarif': '6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee',
}


def require(condition):
    if not condition:
        raise AssertionError('Unsafe or unsupported quality workflow contract')


def contract(workflow):
    require(set(workflow['on']) == {'push', 'pull_request'})
    require(all(workflow['on'][trigger]['branches'] == ['main'] for trigger in ('push', 'pull_request')))
    require(workflow['permissions'] == {'contents': 'read'})
    require(set(workflow['jobs']) == {'analysis', 'publish-sarif'})
    for job in workflow['jobs'].values():
        for step in job['steps']:
            if 'uses' in step:
                action, separator, sha = step['uses'].partition('@')
                require(separator and action in PINS and sha == PINS[action])
            require(step.get('continue-on-error', 'false') == 'false')
    analysis = workflow['jobs']['analysis']
    require(set(analysis) <= {'strategy', 'runs-on', 'timeout-minutes', 'steps', 'permissions'})
    require(analysis.get('permissions', workflow['permissions']) == {'contents': 'read'})
    require(analysis['timeout-minutes'] == '20')
    require(analysis['runs-on'] == '${{ matrix.os }}')
    require(analysis['strategy']['matrix'] == {'os': ['ubuntu-latest', 'windows-latest']})
    steps = analysis['steps']
    require(len(steps) == 9)
    require([step['uses'].split('@')[0] for step in steps if 'uses' in step] == [
        'actions/checkout', 'actions/setup-python', 'actions/setup-dotnet', 'actions/setup-go',
        'actions/setup-node', 'actions/upload-artifact'])
    require(steps[0]['if'] == "runner.os == 'Windows'" and steps[0]['shell'] == 'pwsh')
    require(steps[0]['run'].strip() == 'git config --global core.autocrlf false')
    require(steps[1]['uses'] == 'actions/checkout@' + PINS['actions/checkout'])
    require(steps[1]['with'] == {'fetch-depth': '0', 'persist-credentials': 'false'})
    configurations = {step['uses'].split('@')[0]: step.get('with', {}) for step in steps if 'uses' in step}
    require(configurations['actions/setup-python'] == {'python-version': '3.12'})
    require(configurations['actions/setup-dotnet'] == {'dotnet-version': '9.0.205'})
    require(configurations['actions/setup-go'] == {'go-version': '1.21.3', 'cache': 'false'})
    require(configurations['actions/setup-node'] == {'node-version': '24'})
    setup = next(step for step in steps if step.get('id') == 'setup-native')
    scan = next(step for step in steps if step.get('id') == 'quality')
    require(setup['run'].strip() == 'python tools/build_native.py')
    require(steps.index(setup) < steps.index(scan))
    require(scan['shell'] == 'pwsh')
    require(scan['run'].strip() == 'python tools/run_quality_ci.py --output "$env:RUNNER_TEMP/devsift-quality"\nexit $LASTEXITCODE')
    require(scan['env'] == {'DEVSIFT_BASE_SHA': "${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || github.event.before }}"})
    for step in steps:
        require('${{' not in step.get('run', ''))
    upload = steps[-1]
    require(upload['uses'] == 'actions/upload-artifact@' + PINS['actions/upload-artifact'])
    require(upload['if'] == 'always()' and steps.index(upload) > steps.index(scan))
    require(upload['with'] == {'name': 'devsift-quality-${{ matrix.os }}',
                              'path': '${{ runner.temp }}/devsift-quality/report.md\n${{ runner.temp }}/devsift-quality/findings.json\n${{ runner.temp }}/devsift-quality/results.sarif\n',
                              'if-no-files-found': 'error', 'retention-days': '7'})
    publisher = workflow['jobs']['publish-sarif']
    require(set(publisher) == {'needs', 'if', 'permissions', 'strategy', 'runs-on', 'timeout-minutes', 'steps'})
    require(publisher['timeout-minutes'] == '10')
    require(publisher['needs'] == 'analysis')
    require(publisher['if'].strip() == "${{ !cancelled() && vars.DEVSIFT_SARIF_UPLOAD == 'true' && (github.event_name == 'push' || (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository)) }}")
    require(publisher['permissions'] == {'contents': 'read', 'security-events': 'write'})
    require(publisher['runs-on'] == 'ubuntu-latest')
    require(publisher['strategy']['matrix'] == {'source_os': ['ubuntu-latest', 'windows-latest']})
    publish = publisher['steps']
    require(len(publish) == 3 and all('run' not in step for step in publish))
    require([step['uses'].split('@')[0] for step in publish] == [
        'actions/checkout', 'actions/download-artifact', 'github/codeql-action/upload-sarif'])
    require(publish[0]['with'] == {'persist-credentials': 'false', 'fetch-depth': '1'})
    require(publish[1]['with'] == {'name': 'devsift-quality-${{ matrix.source_os }}',
                                 'path': '${{ runner.temp }}/devsift-publish'})
    require(publish[2]['with'] == {'sarif_file': '${{ runner.temp }}/devsift-publish/results.sarif',
                                 'category': 'devsift-${{ matrix.source_os }}'})


class QualityWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml  # Pinned development dependency; never a runtime dependency.
        cls.workflow = yaml.load(PATH.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)

    def test_workflow_implements_read_only_analysis_and_separate_optional_publish(self):
        contract(self.workflow)

    def test_privilege_trigger_action_and_source_interpolation_mutations_fail(self):
        bad = []
        item = copy.deepcopy(self.workflow); item['on']['pull_request_target'] = item['on'].pop('pull_request'); bad.append(item)
        item = copy.deepcopy(self.workflow); item['permissions']['security-events'] = 'write'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['permissions'] = {'contents': 'write'}; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['continue-on-error'] = 'true'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'][1]['uses'] = 'actions/checkout@v4'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'][1]['with']['persist-credentials'] = 'true'; bad.append(item)
        item = copy.deepcopy(self.workflow); next(s for s in item['jobs']['analysis']['steps'] if s.get('id') == 'quality')['run'] += '\necho ${{ github.event.pull_request.title }}'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'].insert(6, {'run': 'python unexpected_source_hook.py'}); bad.append(item)
        for workflow in bad:
            with self.assertRaises(AssertionError):
                contract(workflow)

    def test_gate_artifact_and_publisher_mutations_fail(self):
        bad = []
        item = copy.deepcopy(self.workflow); next(s for s in item['jobs']['analysis']['steps'] if s.get('id') == 'quality')['continue-on-error'] = 'true'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'][-1]['if'] = 'success()'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'][-1]['with']['path'] = '${{ github.workspace }}/**'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['analysis']['steps'][-1]['with']['if-no-files-found'] = 'ignore'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['publish-sarif']['if'] = "${{ vars.DEVSIFT_SARIF_UPLOAD == 'true' }}"; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['publish-sarif']['if'] = item['jobs']['publish-sarif']['if'].replace('!cancelled()', 'always()'); bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['publish-sarif']['steps'].append({'run': 'python source.py'}); bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['publish-sarif']['steps'][1]['with']['run-id'] = 'arbitrary-run'; bad.append(item)
        item = copy.deepcopy(self.workflow); item['jobs']['publish-sarif']['steps'][2]['with']['sarif_file'] = '${{ github.workspace }}/results.sarif'; bad.append(item)
        for workflow in bad:
            with self.assertRaises(AssertionError):
                contract(workflow)


if __name__ == '__main__':
    unittest.main()
