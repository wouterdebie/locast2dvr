
import types
import unittest

from mock import DEFAULT, MagicMock, patch

from locast2dvr.tuner import Tuner
from locast2dvr.utils import Configuration


def create_tuner(config, geo=MagicMock(), ssdp=MagicMock(), uid="Tuner_0", port=6077):
    return Tuner(geo, uid, config, ssdp, port)


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


class TestTuner(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'bind_address': '1.2.3.4'
        })

    def test_tuner(self):
        with patch('locast2dvr.tuner.LocastService') as service:
            geo = MagicMock()
            uid = MagicMock()
            port = 6077
            ssdp = MagicMock()

            tuner = create_tuner(self.config, geo, ssdp, uid, port)

            self.assertEqual(tuner.geo, geo)
            self.assertEqual(tuner.uid, uid)
            self.assertEqual(tuner.config, self.config)
            self.assertEqual(tuner.port, port)
            self.assertEqual(tuner.ssdp, ssdp)

            service.assert_called_once_with(self.config, geo)


@patch('locast2dvr.tuner.LocastService')
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
        tuner = create_tuner(self.config, port=6077)

        self.assertEqual(tuner.city, "City")
        self.assertEqual(tuner.zipcode, "11111")
        self.assertEqual(tuner.dma, "345")
        self.assertEqual(tuner.url, "http://1.2.3.4:6077")
        self.assertEqual(tuner.timezone, "America/New_York")

    def test_no_port(self, *args):
        tuner = create_tuner(self.config, port=None)
        self.assertEqual(tuner.url, None)


@patch('locast2dvr.tuner.LocastService')
class TestTunerStart(unittest.TestCase):
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
        tuner = create_tuner(self.config, port=port, uid=uid, ssdp=ssdp)
        log = MagicMock()
        tuner.log = log
        with patch("locast2dvr.tuner.start_http") as http:
            tuner.start()

            http.assert_called_once_with(
                self.config, port, uid, service.return_value, ssdp, log
            )
            tuner.locast_service.start.assert_called()

    def test_start_no_port(self, service):
        service.return_value = MagicMock()
        uid = MagicMock()
        port = None
        ssdp = MagicMock()
        with patch("locast2dvr.tuner.start_http") as http:
            tuner = create_tuner(self.config, port=port, uid=uid, ssdp=ssdp)
            log = MagicMock()
            tuner.log = log

            tuner.start()
            self.assertEqual(http.call_count, 0)

    @patch('locast2dvr.tuner.os._exit')
    def test_start_locast_error(self, exit, service):
        service.return_value = MagicMock()

        tuner = create_tuner(self.config, MagicMock())
        tuner.locast_service.start.side_effect = Exception(
            "Failed starting locast service")
        tuner.start()
        exit.assert_called_with(1)


@patch('locast2dvr.tuner.LocastService')
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
        tuner = create_tuner(self.config, port=6077)
        self.assertEqual(str(
            tuner), "Tuner(city: City, zip: 11111, dma: 345, uid: Tuner_0, url: http://1.2.3.4:6077)")

    def test_repr_no_port(self, service):
        x = MagicMock()
        x.city = "City"
        x.zipcode = "11111"
        x.dma = "345"
        service.return_value = x
        tuner = create_tuner(self.config, port=None)
        self.assertEqual(str(
            tuner), "Tuner(city: City, zip: 11111, dma: 345, uid: Tuner_0)")
