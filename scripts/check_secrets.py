#!/usr/bin/env python3
"""Scan tracked/staged files without printing secrets. Complement with Gitleaks."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'Google API key': rb'AIza[0-9A-Za-z_-]{25,}',
    'Google credential': rb'\bAQ\.[0-9A-Za-z_-]{25,}',
    'provider API key': rb'\bsk-[0-9A-Za-z_-]{20,}',
    'GitHub token': rb'\bgh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}',
    'private key': rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
}


def local_secrets():
    values = dict(os.environ)
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                values[name.strip()] = value.strip().strip('\"\'')
    return [v.encode() for k, v in values.items() if len(v) >= 12 and any(x in k.upper() for x in ('API_KEY', 'SECRET', 'TOKEN', 'PASSWORD'))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    secrets = local_secrets()
    findings = []
    count = 0
    for name in filter(None, paths):
        path = Path(name)
        if path.name != '.env.example' and (path.name.startswith('.env') or path.suffix in {'.pem', '.key', '.p12', '.pfx', '.sqlite3'} or '.sqlite3-' in path.name):
            findings.append((name, 'credential filename'))
        if any(part in {'.venv', 'venv', '.ssh', '.ollama', 'memory'} for part in path.parts):
            findings.append((name, 'private/generated directory'))
        data = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT) if args.staged else (ROOT / name).read_bytes()
        count += 1
        for label, pattern in PATTERNS.items():
            if re.search(pattern, data):
                findings.append((name, label))
        if any(secret in data for secret in secrets):
            findings.append((name, 'matches a locally configured secret'))
    for name, label in findings:
        print(f'BLOCKED: {name}: {label}')
    if not count:
        print('No tracked files. Stage the intended source files before scanning.')
        return 1
    print(f'Scanned {count} files; {len(findings)} findings. Secret values are never printed.')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
