from StringIO import StringIO
from weakref import WeakKeyDictionary

from urlparse import urlparse, urlunparse
from urllib import urlencode

from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer

from twisted.web.client import (
    Agent,
    FileBodyProducer,
    HTTPConnectionPool,
    RedirectAgent,
    ContentDecoderAgent,
    GzipDecoder,
    CookieAgent
)

from twisted.python.components import registerAdapter

from treq.auth import add_auth

from cookielib import CookieJar
from treq._cookies import cookiejar_from_dict


_cookie_jars = WeakKeyDictionary()


def cookies(response):
    jar = cookiejar_from_dict({})

    resp_jar = _cookie_jars.get(response, None)

    if resp_jar is not None:
        for cookie in resp_jar:
            jar.set_cookie(cookie)

    return jar


def _flatten_param_dict(params):
    for key, values_or_value in params.iteritems():
        if isinstance(values_or_value, list):
            for value in values_or_value:
                yield (key, value)

        else:
            yield (key, values_or_value)


def _combine_query_params(url, params):
    parsed_url = urlparse(url)

    qs = []

    if parsed_url.query:
        qs.extend([parsed_url.query, '&'])

    if isinstance(params, dict):
        params = list(_flatten_param_dict(params))

    qs.append(urlencode(params))

    return urlunparse((parsed_url[0], parsed_url[1],
                       parsed_url[2], parsed_url[3],
                       ''.join(qs), parsed_url[5]))


def _from_bytes(orig_bytes):
    return FileBodyProducer(StringIO(orig_bytes))


def _from_file(orig_file):
    return FileBodyProducer(orig_file)


registerAdapter(_from_bytes, str, IBodyProducer)
registerAdapter(_from_file, file, IBodyProducer)
registerAdapter(_from_file, StringIO, IBodyProducer)


class HTTPClient(object):
    def __init__(self, agent, cookiejar=None):
        self._agent = agent
        self._cookiejar = cookiejar

    @classmethod
    def with_config(cls, **kwargs):
        reactor = kwargs.get('reactor')
        if not reactor:
            from twisted.internet import reactor

        agent = Agent(
            reactor,
            pool=HTTPConnectionPool(
                reactor,
                persistent=kwargs.get('persistent', True)))

        cookiejar = None
        cookies = kwargs.get('cookies')

        if cookies:
            if isinstance(cookies, dict):
                cookiejar = cookiejar_from_dict(cookies)
            elif isinstance(cookies, CookieJar):
                cookiejar = cookies

        if cookiejar is None:
            cookiejar = CookieJar()

        agent = CookieAgent(agent, cookiejar)

        if kwargs.get('allow_redirects', True):
            agent = RedirectAgent(agent)

        agent = ContentDecoderAgent(agent, [('gzip', GzipDecoder)])

        auth = kwargs.get('auth')
        if auth:
            agent = add_auth(agent, auth)

        return cls(agent, cookiejar=cookiejar)

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def put(self, url, data=None, **kwargs):
        return self.request('PUT', url, data=data, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self.request('POST', url, data=data, **kwargs)

    def head(self, url, **kwargs):
        return self.request('HEAD', url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request('DELETE', url, **kwargs)

    def request(self, method, url, **kwargs):
        method = method.upper()

        params = kwargs.get('params')
        if params:
            url = _combine_query_params(url, params)

        headers = kwargs.get('headers')

        if headers:
            if isinstance(headers, dict):
                h = Headers({})
                for k, v in headers.iteritems():
                    if isinstance(v, str):
                        h.addRawHeader(k, v)
                    else:
                        h.setRawHeaders(k, v)

                headers = h
        else:
            headers = Headers({})

        data = kwargs.get('data')
        bodyProducer = None
        if data:
            if isinstance(data, dict):
                data = list(_flatten_param_dict(data))

            if isinstance(data, list):
                headers.setRawHeaders(
                    'content-type', ['application/x-www-form-urlencoded'])
                data = urlencode(data)

            bodyProducer = IBodyProducer(data)

        d = self._agent.request(
            method, url, headers=headers, bodyProducer=bodyProducer)

        if self._cookiejar is not None:
            def _add_cookies(resp):
                _cookie_jars[resp] = self._cookiejar
                return resp

            d.addCallback(_add_cookies)

        return d
