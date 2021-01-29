import re
from tornado.log import app_log
from . import orm


class BinderHubTokenProvider:
    def __init__(self, db):
        self.db = db

    def get_user_token(self, request):
        token = self._get_token(request)
        if token is None:
            return None
        orm_token = orm.OAuthAccessToken.find(self.db, token)
        if orm_token is None:
            return None
        app_log.debug('Found token for %s', orm_token.user_id)
        return orm_token.user_id

    def _get_token(self, handler):
        token = handler.get_argument('token', None)
        if token is not None:
            return token
        authheader = handler.request.headers.get('Authorization')
        if authheader is None:
            return None
        matched = re.match(r'^Bearer\s+(.+)$', authheader)
        if matched is None:
            return None
        return matched.group(1)
