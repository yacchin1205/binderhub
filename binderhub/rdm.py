from tornado.web import authenticated
import urllib.parse

from .base import BaseHandler


class RDMRedirectHandler(BaseHandler):
    """Redirect handler from RDM JupyterHub addon"""

    @authenticated
    def get(self, host, project, path=None):
        rdm_url = 'https://{host}/{project}'.format(host=host, project=project)
        if path is not None and len(path) > 1:
            npath = path[:-1] if path.endswith('/') else path
            rdm_url += '/files{path}'.format(path=npath)
        url = '/v2/rdm/{url}/master'.format(url=urllib.parse.quote(rdm_url, safe=''))
        self.redirect(url)

class WEKO3RedirectHandler(BaseHandler):
    """Redirect handler from WEKO3 JupyterHub addon"""

    @authenticated
    def get(self, host, bucket, files):
        weko3_url = 'https://{host}/{bucket}{files}'.format(host=host, bucket=bucket, files=files)
        url = '/v2/weko3/{url}/master'.format(url=urllib.parse.quote(weko3_url, safe=''))
        self.redirect(url)
