
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
        x.timezone = "America/New_York"
        service.return_value = x
        dvr = create_dvr(self.config, port=6077)

        self.assertEqual(dvr.city, "City")
        self.assertEqual(dvr.zipcode, "11111")
        self.assertEqual(dvr.dma, "345")
        self.assertEqual(dvr.url, "http://1.2.3.4:6077")
        self.assertEqual(dvr.timezone, "America/New_York")

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
        with patch("locast2dvr.dvr.start_http") as http:
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
        with patch("locast2dvr.dvr.start_http") as http:
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
