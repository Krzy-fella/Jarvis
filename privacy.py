"""Best-effort secret redaction for tool results and provider errors."""
import os
import re


def redact(text):
    text = str(text)
    for name, value in os.environ.items():
        if len(value) >= 8 and any(word in name.upper() for word in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
            text = text.replace(value, '[REDACTED]')
    for pattern in [r'AIza[0-9A-Za-z_-]{20,}', r'\bAQ\.[0-9A-Za-z_-]{25,}', r'\bsk-[0-9A-Za-z_-]{16,}', r'\bgh[pousr]_[0-9A-Za-z]{20,}', r'github_pat_[0-9A-Za-z_]{20,}']:
        text = re.sub(pattern, '[REDACTED]', text)
    return text
