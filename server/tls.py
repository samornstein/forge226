"""Verified HTTPS using Python defaults, with a system-bundle fallback on macOS.

Never disable certificate validation. Respect explicit certificate configuration.
"""
import os,ssl,sys,urllib.request
from pathlib import Path

def verified_context():
    paths=ssl.get_default_verify_paths()
    configured=any(os.environ.get(k) for k in ('SSL_CERT_FILE','SSL_CERT_DIR'))
    system=Path('/etc/ssl/cert.pem')
    if not configured and sys.platform=='darwin' and not paths.cafile and not paths.capath and system.is_file():
        return ssl.create_default_context(cafile=str(system))
    return ssl.create_default_context()

def https_handler():
    return urllib.request.HTTPSHandler(context=verified_context())

def network_error(provider,exc):
    reason=getattr(exc,'reason',exc)
    if isinstance(reason,ssl.SSLCertVerificationError):
        return provider+' TLS certificate verification failed. Check the Python/system certificate installation; do not disable verification. Existing data retained.'
    if isinstance(reason,TimeoutError):
        return provider+' connection timed out. Retry later; existing data retained.'
    return provider+' could not be reached (network or DNS error). Existing data retained.'
