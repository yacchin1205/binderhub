# Copy from https://github.com/jupyterhub/jupyterhub/blob/master/jupyterhub/apihandlers/auth.py
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import json
import uuid

from ..base import BaseHandler
from oauthlib import oauth2
from tornado import web
from tornado.log import app_log

# constant, not configurable
SESSION_COOKIE_NAME = 'binderhub-session-id'


class OAuthHandler(BaseHandler):
    def initialize(self, oauth_provider, hub_url):
        super().initialize()
        self.oauth_provider = oauth_provider
        self.hub_url = hub_url

    def extract_oauth_params(self):
        """extract oauthlib params from a request
        Returns:
        (uri, http_method, body, headers)
        """
        return (
            self.request.uri,
            self.request.method,
            self.request.body,
            self.request.headers,
        )

    def make_absolute_redirect_uri(self, uri):
        """Make absolute redirect URIs
        internal redirect uris, e.g. `/user/foo/oauth_handler`
        are allowed in jupyterhub, but oauthlib prohibits them.
        Add `$HOST` header to redirect_uri to make them acceptable.
        Currently unused in favor of monkeypatching
        oauthlib.is_absolute_uri to skip the check
        """
        redirect_uri = self.get_argument('redirect_uri')
        if not redirect_uri or not redirect_uri.startswith('/'):
            return uri
        # make absolute local redirects full URLs
        # to satisfy oauthlib's absolute URI requirement
        redirect_uri = (
            self.request.protocol + "://" + self.request.headers['Host'] + redirect_uri
        )
        parsed_url = urlparse(uri)
        query_list = parse_qsl(parsed_url.query, keep_blank_values=True)
        for idx, item in enumerate(query_list):
            if item[0] == 'redirect_uri':
                query_list[idx] = ('redirect_uri', redirect_uri)
                break

        return urlunparse(urlparse(uri)._replace(query=urlencode(query_list)))

    def add_credentials(self, credentials=None):
        """Add oauth credentials
        Adds user, session_id, client to oauth credentials
        """
        if credentials is None:
            credentials = {}
        else:
            credentials = credentials.copy()

        session_id = self.get_session_cookie()
        if session_id is None:
            session_id = self.set_session_cookie()

        user = self.current_user

        # Extra credentials we need in the validator
        credentials.update({'user': user, 'handler': self, 'session_id': session_id})
        return credentials

    def get_session_cookie(self):
        """Get the session id from a cookie
        Returns None if no session id is stored
        """
        return self.get_cookie(SESSION_COOKIE_NAME, None)

    def set_session_cookie(self):
        """Set a new session id cookie
        new session id is returned
        Session id cookie is *not* encrypted,
        so other services on this domain can read it.
        """
        session_id = uuid.uuid4().hex
        self._set_cookie(SESSION_COOKIE_NAME, session_id, encrypted=False)
        return session_id

    def _set_cookie(self, key, value, encrypted=True, **overrides):
        """Setting any cookie should go through here
        if encrypted use tornado's set_secure_cookie,
        otherwise set plaintext cookies.
        """
        # tornado <4.2 have a bug that consider secure==True as soon as
        # 'secure' kwarg is passed to set_secure_cookie
        kwargs = {'httponly': True}
        if self.request.protocol == 'https':
            kwargs['secure'] = True

        kwargs.update(self.settings.get('cookie_options', {}))
        kwargs.update(overrides)

        if encrypted:
            set_cookie = self.set_secure_cookie
        else:
            set_cookie = self.set_cookie

        app_log.debug("Setting cookie %s: %s", key, kwargs)
        set_cookie(key, value, **kwargs)

    def send_oauth_response(self, headers, body, status):
        """Send oauth response from provider return values
        Provider methods return headers, body, and status
        to be set on the response.
        This method applies these values to the Handler
        and sends the response.
        """
        self.set_status(status)
        for key, value in headers.items():
            self.set_header(key, value)
        if body:
            self.write(body)

class OAuthAuthorizeHandler(OAuthHandler):
    """Implement OAuth authorization endpoint(s)"""

    def _complete_login(self, uri, headers, scopes, credentials):
        try:
            headers, body, status = self.oauth_provider.create_authorization_response(
                uri, 'POST', '', headers, scopes, credentials
            )

        except oauth2.FatalClientError as e:
            # TODO: human error page
            raise
        self.send_oauth_response(headers, body, status)

    def needs_oauth_confirm(self, user, oauth_client):
        """Return whether the given oauth client needs to prompt for access for the given user
        Checks list for oauth clients that don't need confirmation
        (i.e. the user's own server)
        .. versionadded: 1.1
        """
        if oauth_client.identifier in self.settings.get('oauth_no_confirm_list', set()):
            return False
        # default: require confirmation
        return True

    @web.authenticated
    async def get(self):
        """GET /oauth/authorization
        Render oauth confirmation page:
        "Server at ... would like permission to ...".
        Users accessing their own server or a blessed service
        will skip confirmation.
        """

        uri, http_method, body, headers = self.extract_oauth_params()
        try:
            scopes, credentials = self.oauth_provider.validate_authorization_request(
                uri, http_method, body, headers
            )
            credentials = self.add_credentials(credentials)
            client = self.oauth_provider.fetch_by_client_id(credentials['client_id'])
            if not self.needs_oauth_confirm(self.current_user, client):
                app_log.debug(
                    "Skipping oauth confirmation for %s accessing %s",
                    self.current_user,
                    client.description,
                )
                # this is the pre-1.0 behavior for all oauth
                self._complete_login(uri, headers, scopes, credentials)
                return

            # Render oauth 'Authorize application...' page
            auth_state = None
            self.render_template(
                "oauth.html",
                auth_state=auth_state,
                scopes=scopes,
                oauth_client=client,
            )

        # Errors that should be shown to the user on the provider website
        except oauth2.FatalClientError as e:
            raise web.HTTPError(e.status_code, e.description)

        # Errors embedded in the redirect URI back to the client
        except oauth2.OAuth2Error as e:
            app_log.error("OAuth error: %s", e.description)
            self.redirect(e.in_uri(e.redirect_uri))

    @web.authenticated
    def post(self):
        uri, http_method, body, headers = self.extract_oauth_params()
        referer = self.request.headers.get('Referer', 'no referer')
        full_url = self.request.full_url()
        # trim protocol, which cannot be trusted with multiple layers of proxies anyway
        # Referer is set by browser, but full_url can be modified by proxy layers to appear as http
        # when it is actually https
        referer_proto, _, stripped_referer = referer.partition("://")
        referer_proto = referer_proto.lower()
        req_proto, _, stripped_full_url = full_url.partition("://")
        req_proto = req_proto.lower()
        if referer_proto != req_proto:
            app_log.warning("Protocol mismatch: %s != %s", referer, full_url)
            if req_proto == "https":
                # insecure origin to secure target is not allowed
                raise web.HTTPError(
                    403, "Not allowing authorization form submitted from insecure page"
                )
        if stripped_referer != stripped_full_url:
            # OAuth post must be made to the URL it came from
            app_log.error("Original OAuth POST from %s != %s", referer, full_url)
            app_log.error(
                "Stripped OAuth POST from %s != %s", stripped_referer, stripped_full_url
            )
            raise web.HTTPError(
                403, "Authorization form must be sent from authorization page"
            )

        # The scopes the user actually authorized, i.e. checkboxes
        # that were selected.
        scopes = self.get_arguments('scopes')
        # credentials we need in the validator
        credentials = self.add_credentials()

        try:
            headers, body, status = self.oauth_provider.create_authorization_response(
                uri, http_method, body, headers, scopes, credentials
            )
        except oauth2.FatalClientError as e:
            raise web.HTTPError(e.status_code, e.description)
        else:
            self.send_oauth_response(headers, body, status)


class OAuthTokenHandler(OAuthHandler):
    def post(self):
        uri, http_method, body, headers = self.extract_oauth_params()
        credentials = {}

        try:
            headers, body, status = self.oauth_provider.create_token_response(
                uri, http_method, body, headers, credentials
            )
        except oauth2.FatalClientError as e:
            raise web.HTTPError(e.status_code, e.description)
        else:
            self.send_oauth_response(headers, body, status)


class ServiceListHandler(BaseHandler):
    def initialize(self, oauth_provider, hub_url):
        super().initialize()
        self.oauth_provider = oauth_provider
        self.hub_url = hub_url

    @web.authenticated
    def get(self):
        self.set_header("Content-type", "application/json")
        self.write(json.dumps([
            {
                "type": "jupyterhub",
                "url": self.hub_url,
            }
        ]))


default_handlers = [
    (r"/api/oauth2/authorize", OAuthAuthorizeHandler),
    (r"/api/oauth2/token", OAuthTokenHandler),
    (r"/api/services", ServiceListHandler),
]
