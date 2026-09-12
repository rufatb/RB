"""Credential-safe, bounded text for operational failures, never raw responses."""
import os
import re


def safe_detail(value, limit=240):
    """Redact URLs, credential-shaped tokens and configured secrets before truncation."""
    text = str(value)
    for name, secret in os.environ.items():
        if any(tag in name.upper() for tag in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET')) and len(secret) >= 6:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'https?://[^\s<>\"\']+', '[URL REDACTED]', text, flags=re.I)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]', text)
    text = re.sub(r'(?i)\b(?:api[_-]?key|api[_-]?token|authorization|password|secret)\s*[:=]\s*[^\s,;]+',
                  '[CREDENTIAL REDACTED]', text)
    text = re.sub(r'[\x00-\x1f\x7f]+', ' ', text)
    return text[:limit]


def safe_error(layer, exc, detail=None):
    return {'layer': safe_detail(layer, 60), 'error': type(exc).__name__,
            'detail': safe_detail(type(exc).__name__ if detail is None else detail)}
