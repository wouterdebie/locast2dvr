# Even though these imports seem unused, we patch them
import os
import traceback
import types
import unittest

from mock import DEFAULT, MagicMock, patch

from locast2dvr.dvr import DVR
from locast2dvr.utils import Configuration


def create_dvr(config, geo=MagicMock(), ssdp=MagicMock(), uid="DVR_0", port=6077):
    return DVR(geo, uid, config, ssdp, port)


def free_var(val):
    def nested():
        return val
    return nested.__closure__[0]


def nested(outer, innerName, **freeVars):
    if isinstance(outer, (types.FunctionType, types.MethodType)):
        outer = outer.__getattribute__('__code__')
    for const in outer.co_consts:
        if isinstance(const, types.CodeType) and const.co_name == innerName:
            return types.FunctionType(const, globals(), None, None, tuple(
                free_var(freeVars[name]) for name in const.co_freevars))


class TestDVR(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4'
        })

    def test_dvr(self):
        with patch('locast2dvr.dvr.LocastService') as service:
            geo = MagicMock()
            uid = MagicMock()
            port = 6077
            ssdp = MagicMock()

            dvr = create_dvr(self.config, geo, ssdp, uid, port)

            self.assertEqual(dvr.geo, geo)
            self.assertEqual(dvr.uid, uid)
            self.assertEqual(dvr.config, self.config)
            self.assertEqual(dvr.port, port)
            self.assertEqual(dvr.ssdp, ssdp)

            service.assert_called_once_with(self.config, geo)


@patch('locast2dvr.dvr.LocastService')
class TestProperties(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4'
        })

    def test_properties(self, service):
        x = MagicMock()
        x.city = "City"
        x.zipcode = "11111"
        x.dma = "345"
        service.return_value = x
        dvr = create_dvr(self.config, port=6077)

        self.assertEqual(dvr.city, "City")
        self.assertEqual(dvr.zipcode, "11111")
        self.assertEqual(dvr.dma, "345")
        self.assertEqual(dvr.url, "http://1.2.3.4:6077")

    def test_no_port(self, *args):
        dvr = create_dvr(self.config, port=None)
        self.assertEqual(dvr.url, None)


@patch('locast2dvr.dvr.LocastService')
class TestDVRStart(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4'
        })

    def test_start(self, service):
        service.return_value = MagicMock()
        uid = MagicMock()
        port = 6099
        ssdp = MagicMock()
        dvr = create_dvr(self.config, port=port, uid=uid, ssdp=ssdp)
        log = MagicMock()
        dvr.log = log
        with patch("locast2dvr.dvr._start_http") as http:
            dvr.start()

            http.assert_called_once_with(
                self.config, port, uid, service.return_value, ssdp, log
            )
            dvr.locast_service.start.assert_called()

    def test_start_no_port(self, service):
        service.return_value = MagicMock()
        uid = MagicMock()
        port = None
        ssdp = MagicMock()
        with patch("locast2dvr.dvr._start_http") as http:
            dvr = create_dvr(self.config, port=port, uid=uid, ssdp=ssdp)
            log = MagicMock()
            dvr.log = log

            dvr.start()
            self.assertEqual(http.call_count, 0)

    @patch('locast2dvr.dvr.os._exit')
    def test_start_locast_error(self, exit, service):
        service.return_value = MagicMock()

        dvr = create_dvr(self.config, MagicMock())
        dvr.locast_service.start.side_effect = Exception(
            "Failed starting locast service")
        dvr.start()
        exit.assert_called_with(1)


@patch('locast2dvr.dvr.LocastService')
class TestRepr(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4'
        })

    def test_repr(self, service):
        x = MagicMock()
        x.city = "City"
        x.zipcode = "11111"
        x.dma = "345"
        service.return_value = x
        dvr = create_dvr(self.config, port=6077)
        self.assertEqual(str(
            dvr), "DVR(city: City, zip: 11111, dma: 345, uid: DVR_0, url: http://1.2.3.4:6077)")

    def test_repr_no_port(self, service):
        x = MagicMock()
        x.city = "City"
        x.zipcode = "11111"
        x.dma = "345"
        service.return_value = x
        dvr = create_dvr(self.config, port=None)
        self.assertEqual(str(
            dvr), "DVR(city: City, zip: 11111, dma: 345, uid: DVR_0)")


class TestStartHttp(unittest.TestCase):
    def setUp(self) -> None:

        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4',
            'ssdp': True
        })

    @patch('locast2dvr.dvr.LocastService')
    @patch("locast2dvr.dvr.threading")
    @patch("locast2dvr.dvr.waitress.serve")
    @patch("locast2dvr.dvr.HTTPInterface")
    def test_start_http(self, http_interface: MagicMock, waitress: MagicMock,
                        threading: MagicMock, service: MagicMock):
        from locast2dvr.dvr import _start_http
        uid = "DVR_0"
        port = 6666
        ssdp = MagicMock()
        log = MagicMock()
        http_interface_impl = MagicMock()
        http_interface.return_value = http_interface_impl

        thread = MagicMock()
        threading.Thread.return_value = thread
        _start_http(self.config, port, uid, service, ssdp, log)

        http_interface.assert_called_once_with(self.config, port, uid, service)

        threading.Thread.assert_called_once_with(
            target=waitress, args=(http_interface_impl,), kwargs={
                'host': '1.2.3.4',
                'port': 6666,
                '_quiet': True
            })
        thread.start.assert_called_once()
        ssdp.register.assert_called_once_with(
            'local', 'uuid:DVR_0::upnp:rootdevice', 'upnp:rootdevice', 'http://1.2.3.4:6666/device.xml')

    @patch('locast2dvr.dvr.TransLogger')
    @patch('locast2dvr.dvr.LocastService')
    @patch("locast2dvr.dvr.threading")
    @patch("locast2dvr.dvr.waitress.serve")
    @patch("locast2dvr.dvr.HTTPInterface")
    def test_start_verbose(self, http_interface: MagicMock, waitress: MagicMock,
                           threading: MagicMock, service: MagicMock, translogger: MagicMock):

        from locast2dvr.dvr import _start_http

        self.config.verbose = 1
        uid = "DVR_0"
        port = 6666
        ssdp = MagicMock()
        log = MagicMock()
        http_interface_impl = MagicMock()
        http_interface.return_value = http_interface_impl
        translogger_app = MagicMock()
        translogger.return_value = translogger_app
        thread = MagicMock()
        threading.Thread.return_value = thread

        with patch("locast2dvr.dvr.logging.getLogger") as logger:
            _start_http(self.config, port, uid, service, ssdp, log)

        translogger.assert_called_once_with(http_interface_impl,
                                            logger=logger(),
                                            format='1.2.3.4:6666 %(REMOTE_ADDR)s - %(REMOTE_USER)s "%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" %(status)s %(bytes)s "%(HTTP_REFERER)s" "%(HTTP_USER_AGENT)s"')

        threading.Thread.assert_called_once_with(
            target=waitress, args=(translogger_app,), kwargs={
                'host': '1.2.3.4',
                'port': 6666,
                '_quiet': True
            })

    # Slight magic happening here. Since _excepthook is an inner function.
    # We take the inner function, but and call it, but this changes the scope where it's called and
    # therefore we need to patch os._exit and traceback in the current scope.

    @patch('tests.locast2dvr.test_dvr.os._exit')
    @patch('tests.locast2dvr.test_dvr.traceback')
    def test_except_hook(self, tb: MagicMock(), exit: MagicMock()):
        from locast2dvr.dvr import _start_http

        log = MagicMock()
        except_hook = nested(_start_http, '_excepthook', log=log)
        args = MagicMock(exc_type=OSError, exc_value="foo",
                         exc_traceback="bar")

        except_hook(args)
        self.assertEqual(log.error.call_count, 2)
        log.error.assert_called()
        tb.print_tb.assert_called()
        exit.assert_called_once_with(-1)
