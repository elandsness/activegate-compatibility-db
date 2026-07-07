"""Bootstrap verification script.

- Imports `src.api.app` and calls the `/api/health` endpoint via Flask test client.
- Imports `src.cli.main` and invokes CLI commands via Click's CliRunner.

Run with:

```bash
python scripts/verify_bootstrap.py
```
"""

import os
import sys
from importlib import import_module
from click.testing import CliRunner

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'src'))

def test_api_health():
    api = import_module('src.api.app')
    app = getattr(api, 'app')
    client = app.test_client()
    resp = client.get('/api/health')
    print('\n/api/health ->', resp.status_code, resp.get_json())

def test_cli_commands():
    cli_mod = import_module('src.cli.main')
    cli = getattr(cli_mod, 'cli')
    runner = CliRunner()

    print('\nRunning `agi --help`')
    r = runner.invoke(cli, ['--help'])
    print('Exit:', r.exit_code)
    print(r.output)

    print('\nRunning `agi status`')
    r = runner.invoke(cli, ['status'])
    print('Exit:', r.exit_code)
    print(r.output)

    print('\nRunning `agi check -c 1.330 -t 1.335 --json`')
    r = runner.invoke(cli, ['check', '-c', '1.330', '-t', '1.335', '--json'])
    print('Exit:', r.exit_code)
    print(r.output)

if __name__ == '__main__':
    test_api_health()
    test_cli_commands()
