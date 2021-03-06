"""
    WebServer
    ~~~~~~~~~

    The web server is based on `aiohttp <https://github.com/KeepSafe/aiohttp/>`_ package.
"""
import asyncio

from aiohttp import web
from IPy import IP

from harpseal.web.classes import Response
from harpseal.web.router import Router

__all__ = ['WebServer', 'Resposne']

class WebServer(object):
    """Harpseal WebServer Class

    :param parent: Harpseal instance
    """

    def __init__(self, parent):
        #: (:class:`harpseal.app.Harpseal`) Harpseal instance
        self.parent = parent
        self.app = None
        self.handler = None
        self.server = None
        #: (:class:`harpseal.web.router.Router`) Web router
        self.router = None
        #: (:class:`list`) IP whitelist
        self.whitelist = [IP(allow) for allow in parent.config['server']['allows']]

    def __del__(self):
        yield from self.handler.finish_connections(1.0)
        self.server.close()
        yield from self.server.wait_closed()
        yield from self.app.finish()

    @asyncio.coroutine
    def whitelist_middleware(self, app, handler):
        """Deny if user's ipaddress is not in the whitelist."""
        @asyncio.coroutine
        def middleware(req):
            peername = req.transport.get_extra_info('peername')
            if peername is not None:
                host, port = peername
                isinwhites = any([host in white for white in self.whitelist])
                if not isinwhites:
                    error = {
                        'ok': False,
                        'reason': 'Your ipaddress is not in the whitelist of allowed IPs.',
                    }
                    return Response(error)
            return (yield from handler(req))
        return middleware

    @asyncio.coroutine
    def jsonp_middleware(self, app, handler):
        """Retrurn data as JSONP callback format when `callback` parameter given."""
        @asyncio.coroutine
        def middleware(req):
            callback = req.GET.get('callback', None)
            data = yield from handler(req)
            if callback:
                body = data._body.decode('utf-8')
                body = '{}({})'.format(callback, body)
                data._body = body.encode('utf-8')
                data.content_length = len(body)
            return data
        return middleware

    @asyncio.coroutine
    def authenticate_middleware(self, app, handler):
        """Deny if key is set and does not match with `key` parameter given."""
        key = self.parent.config['server'].get('key', '')
        @asyncio.coroutine
        def middleware(req):
            data = yield from handler(req)
            if key:
                given = req.GET.get('key', '')
                if key != given:
                    data = Response({
                        'ok': False,
                        'reason': 'Invalid authentication credential.',
                    })
            return data
        return middleware

    @asyncio.coroutine
    def execute(self):
        """Start a web server."""
        self.app = web.Application(middlewares=[self.whitelist_middleware,
                                                self.authenticate_middleware,
                                                self.jsonp_middleware])
        self.handler = self.app.make_handler()
        self.server = self.parent.loop.create_server(self.handler,
                                                     self.parent.config['server']['host'],
                                                     self.parent.config['server']['port'])
        yield from self.server
        self.router = Router(self.app, plugins=self.parent.plugins)
