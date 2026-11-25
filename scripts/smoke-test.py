#!/usr/bin/env python3
"""Write a unique source test point and compare full SQL results downstream.

This performs real database operations only when explicitly invoked. Tokens are
read from local files, never printed or passed in command-line arguments.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def base_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError('Use an HTTP(S) base URL without embedded credentials')
    if parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise argparse.ArgumentTypeError('Use a base URL without a path, query, or fragment')
    return value.rstrip('/')


def load_token(path):
    raw = Path(path).read_text().strip()
    if raw.startswith('{'):
        raw = json.loads(raw)['token']
    if not raw or '\n' in raw or '\r' in raw:
        raise ValueError('Token file must contain one token or admin-token JSON')
    return raw


def request(base, path, token, payload, raw=False):
    body = payload.encode() if raw else json.dumps(payload).encode()
    req = urllib.request.Request(base+path, data=body, headers={
        'Authorization':'Bearer '+token,
        'Content-Type':'text/plain' if raw else 'application/json',
    })
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
        data = response.read()
        return json.loads(data) if data and not raw else data


def ensure_database(base, token, database):
    try:
        request(base, '/api/v3/configure/database', token, {'db':database})
    except urllib.error.HTTPError as error:
        message = error.read().decode(errors='replace').lower()
        if error.code not in (400, 409) or 'already exists' not in message:
            raise RuntimeError(f'Database creation failed: HTTP {error.code}') from None


def query(base, token, database, marker):
    return request(base, '/api/v3/query_sql', token, {
        'db':database,
        'q':f"SELECT check_id, value, time FROM edr_install_check WHERE check_id = '{marker}' ORDER BY time",
        'format':'json',
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ('source', 'destination'):
        parser.add_argument(f'--{role}-write-url', required=True, type=base_url)
        parser.add_argument(f'--{role}-query-url', required=True, type=base_url)
        parser.add_argument(f'--{role}-token-file', required=True, type=Path)
    parser.add_argument('--database', default='edr_smoke')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    source_token = load_token(args.source_token_file)
    destination_token = load_token(args.destination_token_file)
    ensure_database(args.source_write_url, source_token, args.database)
    ensure_database(args.destination_write_url, destination_token, args.database)
    marker = uuid.uuid4().hex
    line = f'edr_install_check,check_id={marker} value=42i {time.time_ns()}'
    request(args.source_write_url, '/api/v3/write_lp?'+urllib.parse.urlencode({'db':args.database,'precision':'nanosecond'}), source_token, line, raw=True)
    deadline = time.monotonic()+args.timeout
    last = 'awaiting query visibility'
    while time.monotonic() < deadline:
        try:
            source = query(args.source_query_url, source_token, args.database, marker)
            destination = query(args.destination_query_url, destination_token, args.database, marker)
            if source and source == destination:
                assert len(source) == 1 and source[0]['value'] == 42
                print('PASS: unique test point matches source and destination, including tags, field, and timestamp')
                print('Test database:', args.database, '| check_id:', marker)
                return
            last = 'test point absent or source/destination rows differ'
        except urllib.error.HTTPError as error:
            last = f'query HTTP {error.code}'
        except urllib.error.URLError:
            last = 'query endpoint unavailable'
        time.sleep(2)
    raise SystemExit('FAIL: replication not verified before timeout; '+last)


if __name__ == '__main__':
    main()
