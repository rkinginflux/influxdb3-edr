"""Unit tests of smoke-client logic using explicitly mocked API responses."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('smoke_client',ROOT/'scripts/smoke-test.py')
assert SPEC is not None and SPEC.loader is not None
smoke=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class SmokeClient(unittest.TestCase):
    def test_base_url_rejects_embedded_auth_and_api_paths(self):
        for value in ['https://user:password@example.com','https://example.com/api/v3/query_sql','file:///example','https://example.com?secret=value']:
            with self.assertRaises(argparse.ArgumentTypeError):smoke.base_url(value)
        self.assertEqual(smoke.base_url('https://example.com/'),'https://example.com')

    def test_token_file_accepts_raw_and_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'token'
            for value in ['synthetic-fixture-token\n',json.dumps({'token':'synthetic-fixture-token'})]:
                path.write_text(value)
                self.assertEqual(smoke.load_token(path),'synthetic-fixture-token')

    def test_token_file_rejects_multiple_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'token'
            path.write_text('one\ntwo')
            with self.assertRaises(ValueError):smoke.load_token(path)

    def test_auth_requests_do_not_follow_redirects(self):
        self.assertIsNone(smoke.NoRedirect().redirect_request(None,None,302,'Found',{},'https://other.example.com'))

    def test_smoke_logic_writes_only_source_and_compares_complete_point(self):
        marker='syntheticuniquemarker'
        point=[{'check_id':marker,'value':42,'time':'2026-01-01T00:00:00Z'}]
        argv=['smoke-test.py','--source-write-url','https://source-write.example.com','--source-query-url','https://source-query.example.com','--destination-write-url','https://destination-write.example.com','--destination-query-url','https://destination-query.example.com','--source-token-file','source-token','--destination-token-file','destination-token']
        with patch('sys.argv',argv),patch.object(smoke,'load_token',return_value='synthetic-fixture-token'),patch.object(smoke,'ensure_database') as configure,patch.object(smoke,'request',return_value=b'') as write,patch.object(smoke,'query',side_effect=[point,point]) as query,patch.object(smoke.uuid,'uuid4',return_value=types.SimpleNamespace(hex=marker)),contextlib.redirect_stdout(io.StringIO()) as output:
            smoke.main()
        self.assertEqual(configure.call_count,2)
        self.assertEqual(write.call_count,1)
        self.assertEqual(write.call_args.args[0],'https://source-write.example.com')
        self.assertIn('check_id='+marker,write.call_args.args[3])
        self.assertEqual(query.call_count,2)
        self.assertIn('PASS:',output.getvalue())
        self.assertNotIn('synthetic-fixture-token',output.getvalue())


if __name__=='__main__':unittest.main()
