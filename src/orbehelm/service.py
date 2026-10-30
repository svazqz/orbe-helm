"""Bounded loopback readiness checks; no ORM, credential, or agent CLI dependency."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from . import __version__
from .core import OrbeHelmError
from .layout import identity, installation, server_url

MAX_HEALTH = 16384


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def health_payload(root, ready=True):
    data = installation(root)
    ready = ready and (data is None or data.get('complete') is True)
    return {'service': 'orbehelm', 'version': __version__, 'protocol_version': 1,
            'ready': ready, **identity(root)}


def server_status(root):
    url = server_url(root)
    failure = {'ready': False, 'reachable': False, 'url': url}
    try:
        opener = build_opener(ProxyHandler({}), NoRedirects())
        with opener.open(Request(url + '/healthz', headers={'Accept': 'application/json'}), timeout=2) as response:
            failure['reachable'] = True
            if response.status != 200:
                return {**failure, 'detail': 'Server is not ready.'}
            encoded = response.read(MAX_HEALTH + 1)
        if len(encoded) > MAX_HEALTH:
            return {**failure, 'detail': 'Invalid server health response.'}
        payload = json.loads(encoded)
        if not isinstance(payload, dict) or any(payload.get(key) != value
                for key, value in health_payload(root).items()):
            return {**failure, 'detail': 'Endpoint is not a ready, matching OrbeHelm installation.'}
        return {'ready': True, 'reachable': True, 'url': url, 'version': __version__}
    except HTTPError:
        return {**failure, 'reachable': True, 'detail': 'Endpoint returned an HTTP error; server is not ready.'}
    except (OSError, URLError, ValueError, UnicodeError):
        return {**failure, 'detail': 'OrbeHelm server is unavailable.'}


def require_server(root):
    """Compatibility alias: native work requires local storage, never a web listener."""
    return require_storage(root)


def require_storage(root):
    data = installation(root)
    if data is not None and data.get('complete') is not True:
        raise OrbeHelmError('Installation is incomplete; rerun setup.sh before starting an orbe')
    from .compatibility import database_file
    if database_file(root).exists():
        from .product.database import Store
        store = Store(root)
        store.close()
    return {'ready': True, 'local': True}
