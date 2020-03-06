from datetime import datetime
import logging
import sqlite3
import uuid

from tornado.web import authenticated
from requests_oauthlib import OAuth2Session

from .base import BaseHandler
from .utils import url_path_join


logger = logging.getLogger(__file__)


class TokenStore(object):

    def __init__(self, path):
        self.connect = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._create()

    def _create(self):
        c = self.connect.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repo_session';")
        if c.fetchone() is not None:
            c.close()
            return
        c.execute("""CREATE TABLE repo_session
            (user text, provider_id text, token text, state text, acquired timestamp,
             expires timestamp, provider_name text, spec text);""")
        self.connect.commit()
        c.close()

    def get_token_for(self, user, provider_name, provider_id):
        c = self.connect.cursor()
        c.execute("""SELECT token, expires FROM repo_session
            WHERE user=? AND provider_name=? AND provider_id=? AND token IS NOT NULL;""",
                  (user, provider_name, provider_id))
        result = c.fetchone()
        c.close()
        if result is None:
            return None
        token, expires = result
        if expires < datetime.utcnow():
            return None
        return token

    def new_session(self, spec, user, provider_name, provider_id):
        logger.info('User: {}, Provider: {}'.format(user, provider_id))
        state = str(uuid.uuid1())
        c = self.connect.cursor()
        c.execute("""INSERT INTO repo_session (user, provider_name, provider_id, state, spec)
            VALUES (?, ?, ?, ?, ?);""", (user, provider_name, provider_id, state, spec))
        self.connect.commit()
        c.close()
        return state

    def get_session(self, user, state):
        c = self.connect.cursor()
        c.execute("""SELECT provider_name, spec FROM repo_session
            WHERE user=? AND state=?;""", (user, state))
        provider_name, spec = c.fetchone()
        c.close()
        return (provider_name, spec)

    def register_token(self, user, state, token, expires):
        c = self.connect.cursor()
        c.execute("""UPDATE repo_session
            SET token=?, acquired=?, expires=?
            WHERE user=? AND state=? AND token IS NULL;""",
                  (token, datetime.utcnow(), expires,
                   user, state))
        self.connect.commit()
        c.execute("""SELECT spec FROM repo_session
            WHERE user=? AND state=?;""", (user, state))
        spec = c.fetchone()[0]
        c.close()
        return spec


class OAuth2Client(object):

    def __init__(self, host):
        self.host = host

    def get_authorization_url(self, state, hub_url):
        session = self._create_session(hub_url)
        auth_url, _ = session.authorization_url(self.host['oauth_authorize_url'],
                                                state=state)
        return auth_url

    def fetch_token(self, authorization_response, hub_url):
        session = self._create_session(hub_url)
        return session.fetch_token(self.host['oauth_token_url'],
                                   authorization_response=authorization_response,
                                   client_secret=self.host['client_secret'],
                                   include_client_id=True)

    def _create_session(self, hub_url):
        redirect_uri = url_path_join(hub_url, '/repoauth/callback')
        return OAuth2Session(self.host['client_id'],
                             redirect_uri=redirect_uri,
                             scope=['osf.full_read'])


class RepoAuthCallbackHandler(BaseHandler):
    """A callback handler for authorization for repositories"""

    def initialize(self, hub_url):
        super().initialize()
        self.hub_url = hub_url
        self.tokenstore = TokenStore(self.settings['repo_token_store'])

    @authenticated
    async def get(self):
        state = self.get_query_argument('state')
        logger.info('Callback: {}, state={}'.format(self.request.uri, state))
        user = self.get_current_user()
        provider_name, spec = self.tokenstore.get_session(user, state)
        provider = self.get_provider(provider_name, spec)
        token = provider.fetch_authorized_token(self.request.uri, self.hub_url)
        expires = datetime.utcfromtimestamp(token['expires_at'])
        logger.info('Token: {}'.format(expires))
        spec = self.tokenstore.register_token(user, state, token['access_token'], expires)
        self.redirect(url_path_join(self.hub_url, '/v2', provider_name, spec))
