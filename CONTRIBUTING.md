# Contributing

Fork the repository, create a branch, and customize it. The project code uses the
MIT license: retain the copyright and license notice when redistributing it.
Third-party dependencies retain their own licenses; they are installed separately.

Use Python 3.11 or newer. Run `python3 scripts/install.py`, then:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_secrets.py
```

Keep keys in your local `.env`. Never include API credentials, phone identifiers,
conversation logs, voice recordings, or personal data in commits, screenshots or
issues. Network/hardware checks should be opt-in; normal tests use mocks.

To add an action: implement it, add its contract to `config.py`, route it in
`main.py`, add relevant confirmation and tests, and update the capability docs.
Model output and external search/file content are untrusted inputs. Validate
arguments before subprocess calls, and quote arguments for any remote shell.

Open a pull request describing the behavior change and how you tested it.
