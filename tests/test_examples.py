"""Portable example checks and explicitly simulated kubectl/Helm helper tests.

Command doubles below record arguments; they do not contact a cluster, implement
an EDR server, or establish vendor/runtime compatibility.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
state_file = pathlib.Path(os.environ['TEST_STATE'])
state = json.loads(state_file.read_text())
state['calls'].append([name] + args)
if name == 'helm':
    if args and args[0] == 'template' and args[1] == os.environ.get('FAIL_RENDER'):
        state_file.write_text(json.dumps(state))
        sys.exit(1)
else:
    if 'get' in args and 'secret' in args:
        secret = args[args.index('secret') + 1]
        if secret == os.environ.get('FAIL_SECRET_LOOKUP'):
            state_file.write_text(json.dumps(state))
            sys.exit(1)
        if secret in state['secrets']:
            print('secret/' + secret)
    elif 'create' in args and 'secret' in args:
        secret = args[args.index('generic') + 1]
        state['secrets'].append(secret)
    elif 'create' in args and 'namespace' in args:
        print('apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test-namespace')
    elif 'config' in args:
        print('synthetic-test-context')
state_file.write_text(json.dumps(state))
'''


class Examples(unittest.TestCase):
    def test_yaml_parses(self):
        for path in [*ROOT.glob('examples/*.yaml'), *ROOT.glob('manifests/*.yaml')]:
            self.assertTrue(list(yaml.safe_load_all(path.read_text())), path.name)

    def test_link_and_write_token_references(self):
        sender = yaml.safe_load((ROOT/'examples/sender-values.yaml').read_text())
        receiver = yaml.safe_load((ROOT/'examples/receiver-values.yaml').read_text())
        self.assertEqual(sender['tokenStore']['existingSecret'], receiver['tokenStore']['existingSecret'])
        self.assertEqual(sender['downstream']['authToken'], receiver['receiver']['upstreams'][0]['authToken'])
        self.assertEqual(receiver['receiver']['upstreams'][0]['name'], 'edrs-edr')
        self.assertEqual(receiver['receiver']['upstreams'][0]['writeToken'], 'destination-write')
        self.assertIn('edr-destination-write', receiver['tokenStore']['extraSecrets'])

    def test_safe_order_and_distinct_state(self):
        sender = yaml.safe_load((ROOT/'examples/sender-values.yaml').read_text())
        receiver = yaml.safe_load((ROOT/'examples/receiver-values.yaml').read_text())
        self.assertIs(sender['downstream']['idempotentWrites'], False)
        self.assertEqual(sender['downstream']['concurrentSends'], 1)
        self.assertEqual(sender['downstream']['historicFill'], 'none')
        self.assertNotEqual(sender['state']['location'], receiver['state']['location'])

    def test_ui_services_do_not_publish_replication(self):
        docs = list(yaml.safe_load_all((ROOT/'manifests/ui-services.yaml').read_text()))
        self.assertEqual(len(docs), 2)
        for service, instance, port in zip(docs, ['edrs', 'edrr'], [9091, 9092]):
            self.assertEqual(service['spec']['selector']['app.kubernetes.io/instance'], instance)
            self.assertEqual(service['spec']['ports'], [{'name':'observability','protocol':'TCP','port':port,'targetPort':9091}])
            self.assertNotIn('externalIPs', service['spec'])

    def test_bash_syntax_in_docs_and_helpers(self):
        for path in ROOT.glob('scripts/*.sh'):
            subprocess.run(['bash', '-n', str(path)], check=True)
        for path in [ROOT/'README.md', *ROOT.glob('docs/*.md')]:
            for block in re.findall(r'```bash\n(.*?)```', path.read_text(), re.S):
                subprocess.run(['bash', '-n'], input=block, text=True, check=True)

    def test_relative_document_links_exist(self):
        for path in [ROOT/'README.md', *ROOT.glob('docs/*.md')]:
            for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
                if '://' in link or link.startswith('#'):
                    continue
                self.assertTrue((path.parent/link.split('#')[0]).exists(), (path.name, link))


class SimulatedHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT/'scripts', self.root/'scripts')
        (self.root/'bin').mkdir()
        for command in ['kubectl', 'helm']:
            executable = self.root/'bin'/command
            executable.write_text(FAKE_CLI)
            executable.chmod(0o755)
        self.state = self.root/'state.json'
        self.state.write_text(json.dumps({'calls':[], 'secrets':[]}))
        self.env = dict(os.environ, PATH=str(self.root/'bin')+os.pathsep+os.environ['PATH'], TEST_STATE=str(self.state), NAMESPACE='test-namespace')
        (self.root/'credentials').mkdir()
        for filename in ['source-access-key-id','source-secret-access-key','receiver-access-key-id','receiver-secret-access-key','destination-write-token']:
            (self.root/'credentials'/filename).write_text('synthetic-fixture-not-a-real-credential')

    def run_helper(self, name):
        return subprocess.run(['bash', str(self.root/'scripts'/name)], cwd=self.root, env=self.env, capture_output=True, text=True)

    def calls(self):
        return json.loads(self.state.read_text())['calls']

    def configure_install(self, unresolved=False):
        for role in ['sender', 'receiver']:
            data = (ROOT/'examples'/f'{role}-values.yaml').read_text()
            if not unresolved:
                # Test substitutions only, not a deployable environment fixture.
                data = re.sub(r'REPLACE_WITH_[A-Z_]+', 'synthetic-fixture', data)
            (self.root/f'{role}-values.yaml').write_text(data)
        chart = self.root/'delivered-chart.tgz'
        chart.write_bytes(b'not-a-real-chart-used-only-by-the-command-double')
        self.env['EDR_CHART'] = str(chart)

    def test_missing_credentials_stop_before_changes(self):
        (self.root/'credentials/source-access-key-id').unlink()
        result = self.run_helper('create-secrets.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('create' in c or 'apply' in c for c in self.calls()))

    def test_bootstrap_preserves_existing_secrets_and_link(self):
        initial = ['edr-source-storage','edr-receiver-storage','edr-destination-write','edr-link']
        self.state.write_text(json.dumps({'calls':[], 'secrets':initial}))
        result = self.run_helper('create-secrets.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('generic' in c for c in self.calls()))
        self.assertFalse((self.root/'credentials/link-auth').exists())

    def test_bootstrap_creates_references_without_printing_values(self):
        result = self.run_helper('create-secrets.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(self.state.read_text())
        self.assertEqual(set(state['secrets']), {'edr-source-storage','edr-receiver-storage','edr-destination-write','edr-link'})
        self.assertNotIn('synthetic-fixture-not-a-real-credential', result.stdout+result.stderr)
        self.assertEqual((self.root/'credentials/link-auth').stat().st_mode & 0o777, 0o600)

    def test_failed_secret_lookup_does_not_attempt_creation(self):
        self.env['FAIL_SECRET_LOOKUP'] = 'edr-source-storage'
        result = self.run_helper('create-secrets.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('generic' in call for call in self.calls()))

    def test_failed_link_lookup_does_not_rotate_link(self):
        initial = ['edr-source-storage','edr-receiver-storage','edr-destination-write']
        self.state.write_text(json.dumps({'calls':[], 'secrets':initial}))
        self.env['FAIL_SECRET_LOOKUP'] = 'edr-link'
        result = self.run_helper('create-secrets.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('generic' in call for call in self.calls()))
        self.assertFalse((self.root/'credentials/link-auth').exists())

    def test_placeholders_stop_before_helm(self):
        self.configure_install(unresolved=True)
        result = self.run_helper('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0]=='helm' for c in self.calls()))

    def test_both_roles_render_before_receiver_then_sender_install(self):
        self.configure_install()
        result = self.run_helper('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        helm = [c for c in self.calls() if c[0]=='helm']
        self.assertEqual([c[1] for c in helm], ['template','template','upgrade','upgrade'])
        self.assertEqual([c[2] for c in helm[:2]], ['edrr','edrs'])
        self.assertEqual([c[3] for c in helm[2:]], ['edrr','edrs'])

    def test_render_failure_prevents_any_install(self):
        self.configure_install()
        self.env['FAIL_RENDER'] = 'edrs'
        result = self.run_helper('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0]=='helm' and c[1]=='upgrade' for c in self.calls()))


if __name__ == '__main__':
    unittest.main()
