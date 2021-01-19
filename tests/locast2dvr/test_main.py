import unittest

from mock import MagicMock, patch

from locast2dvr.dvr import DVR
from locast2dvr.locast import Geo
from locast2dvr.main import Main
from locast2dvr.utils import Configuration


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "verbose": 0,
            "logfile": None
        })

    def test_main(self):
        main = Main(self.config)
        self.assertEqual(main.config, self.config)
        self.assertEqual(main.geos, [])
        self.assertEqual(main.dvrs, [])
        self.assertEqual(main.multiplexer, None)
        self.assertEqual(main.ssdp, None)


class TestGeos(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "verbose": 0,
            "logfile": None
        })

    def test_override_locations(self):
        self.config.override_location = '1.99,2.33'
        self.config.override_zipcodes = None

        main = Main(self.config)
        main._init_geos()
        geo = Geo(coords={
            'latitude': '1.99',
            'longitude': '2.33'
        })
        self.assertEqual(len(main.geos), 1)
        self.assertEqual(main.geos[0], geo)

    def test_override_zipcodes(self):
        self.config.override_location = None
        self.config.override_zipcodes = '90210,11011'

        main = Main(self.config)
        main._init_geos()

        self.assertEqual(len(main.geos), 2)
        self.assertEqual(main.geos[0], Geo('90210'))
        self.assertEqual(main.geos[1], Geo('11011'))

    def test_override_none(self):
        self.config.override_location = None
        self.config.override_zipcodes = None

        main = Main(self.config)
        main._init_geos()

        self.assertEqual(len(main.geos), 1)
        self.assertEqual(main.geos[0], Geo())


class TestMultiplexer(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'multiplex': False,
            'multiplex_debug': False,
            'port': 6077
        })

    @patch('locast2dvr.main.Multiplexer')
    def test_multiplex_debug(self, multiplexer: MagicMock):
        self.config.multiplex = True
        self.config.multiplex_debug = True
        main = Main(self.config)
        main.geos = [Geo()]
        main._init_multiplexer()
        multiplexer.assert_called_once_with(self.config, 6078, main.ssdp)

    @patch('locast2dvr.main.Multiplexer')
    def test_multiplex(self, multiplexer: MagicMock):
        self.config.multiplex = True
        main = Main(self.config)
        main.geos = [Geo()]
        main._init_multiplexer()
        multiplexer.assert_called_once_with(self.config, 6077, main.ssdp)

    def test_multiplex_none(self):
        main = Main(self.config)
        main._init_multiplexer()
        self.assertIsNone(main.multiplexer)


@patch('locast2dvr.main.DVR')
class TestDVRs(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'uid': 'TEST',
            'multiplex': False,
            'multiplex_debug': False,
            'port': 6077
        })

    def test_dvrs(self, dvr: MagicMock):
        main = Main(self.config)
        g1 = Geo()
        g2 = Geo()
        main.geos = [g1, g2]
        main._init_dvrs()
        self.assertEqual(len(main.dvrs), 2)
        dvr.assert_any_call(g1, 'TEST_0', main.config, main.ssdp, port=6077)
        dvr.assert_any_call(g1, 'TEST_1', main.config, main.ssdp, port=6078)

    def test_dvrs_multiplex(self, dvr: MagicMock):
        self.config.multiplex = True
        main = Main(self.config)
        g1 = Geo()
        g2 = Geo()
        main.geos = [g1, g2]
        main._init_dvrs()
        self.assertEqual(len(main.dvrs), 2)
        dvr.assert_any_call(g1, 'TEST_0', main.config, main.ssdp, port=None)
        dvr.assert_any_call(g2, 'TEST_1', main.config, main.ssdp, port=None)

    def test_dvrs_multiplex_debug(self, dvr: MagicMock):
        self.config.multiplex = True
        self.config.multiplex_debug = True
        main = Main(self.config)
        g1 = Geo()
        g2 = Geo()
        main.geos = [g1, g2]
        main._init_dvrs()
        self.assertEqual(len(main.dvrs), 2)
        dvr.assert_any_call(g1, 'TEST_0', main.config, main.ssdp, port=6077)
        dvr.assert_any_call(g1, 'TEST_1', main.config, main.ssdp, port=6078)


class TestUtilities(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'uid': 'TEST',
            'multiplex': False,
            'multiplex_debug': False,
            'port': 6077
        })

    def test_port(self):
        main = Main(self.config)
        port = main._port(0)
        self.assertEqual(port, 6077)
        port = main._port(1)
        self.assertEqual(port, 6078)

    def test_port_multiplex(self):
        self.config.multiplex = True
        main = Main(self.config)
        port = main._port(0)
        self.assertEqual(port, None)
        port = main._port(1)
        self.assertEqual(port, None)

    def test_port_multiplex_debug(self):
        self.config.multiplex = True
        self.config.multiplex_debug = True
        main = Main(self.config)
        port = main._port(0)
        self.assertEqual(port, 6077)
        port = main._port(1)
        self.assertEqual(port, 6078)

    def test_uid(self):
        main = Main(self.config)
        uid = main._uid(0)
        self.assertEqual(uid, "TEST_0")
        uid = main._uid(1)
        self.assertEqual(uid, "TEST_1")


@patch('locast2dvr.main.SSDPServer')
class TestStart(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({'verbose': 0, 'logfile': None})

    def test_startup_order(self, ssdp_server: MagicMock):
        with patch.multiple('locast2dvr.main.Main', _login=MagicMock(),
                            _init_geos=MagicMock(),
                            _init_multiplexer=MagicMock(),
                            _init_dvrs=MagicMock(),
                            _check_ffmpeg=MagicMock(),
                            _report=MagicMock()):

            ssdp_instance = MagicMock()
            ssdp_server.return_value = ssdp_instance
            main = Main(self.config)

            dvr1 = MagicMock()
            dvr2 = MagicMock()
            main.dvrs = [dvr1, dvr2]

            main.start()

            main._login.assert_called_once()
            main._init_geos.assert_called_once()
            main._init_dvrs.assert_called_once()
            main._check_ffmpeg.assert_called_once()
            main._report.assert_called_once()
            dvr1.start.assert_called_once()
            dvr2.start.assert_called_once()
            ssdp_server.assert_called()
            ssdp_instance.start.assert_called()

    def test_startup_with_multiplexer(self, *args):
        with patch.multiple('locast2dvr.main.Main', _login=MagicMock(return_value='New_Key'),
                            _init_geos=MagicMock(),
                            _init_multiplexer=MagicMock(),
                            _init_dvrs=MagicMock(),
                            _check_ffmpeg=MagicMock(),
                            _report=MagicMock()):
            main = Main(self.config)

            dvrs = [MagicMock(), MagicMock()]
            main.dvrs = dvrs
            main.multiplexer = MagicMock()

            main.start()

            main.multiplexer.register.assert_called_once_with(dvrs)
            main.multiplexer.start.assert_called()


class TestReport(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({'verbose': 0, 'logfile': None})

    def test_report(self):
        main = Main(self.config)
        dvr1 = MagicMock(spec=DVR)
        dvr1.city = "TestTown"
        dvr1.zipcode = "111111"
        dvr1.dma = "373"
        dvr1.uid = "TEST_0"
        dvr1.url = None

        dvr2 = MagicMock(spec=DVR)
        dvr2.city = "TestTown2"
        dvr2.zipcode = "111112"
        dvr2.dma = "372"
        dvr2.uid = "TEST_1"
        dvr2.url = "http://localhost:6789"

        main.dvrs = [dvr1, dvr2]
        main.log = MagicMock()

        main._report()

        self.assertEqual(len(main.log.info.mock_calls), 5)

    def test_report_with_multiplexer(self):
        main = Main(self.config)
        main.multiplexer = MagicMock()
        dvr1 = MagicMock(spec=DVR)
        dvr1.city = "TestTown"
        dvr1.zipcode = "111111"
        dvr1.dma = "373"
        dvr1.uid = "TEST_0"
        dvr1.url = None

        dvr2 = MagicMock(spec=DVR)
        dvr2.city = "TestTown2"
        dvr2.zipcode = "111112"
        dvr2.dma = "372"
        dvr2.uid = "TEST_1"
        dvr2.url = "http://localhost:6789"

        main.dvrs = [dvr1, dvr2]
        main.log = MagicMock()
        main.multiplexer.url = "http://localhost:7890"
        main.multiplexer.uid = "MULTI"

        main._report()

        self.assertEqual(len(main.log.info.mock_calls), 10)


class TestFFMPEG(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({'verbose': 0, 'logfile': None})

    def test_ffmpeg_default(self):
        self.config.ffmpeg = None
        with patch('locast2dvr.main.distutils.spawn.find_executable') as f:
            f.return_value = '/usr/local/bin/ffmpeg-test'
            main = Main(self.config)
            main.log = MagicMock()

            main._check_ffmpeg()
            self.assertEqual(main.config.ffmpeg, '/usr/local/bin/ffmpeg-test')
            f.assert_called_once_with('ffmpeg')

    def test_ffmpeg_from_config(self):
        self.config.ffmpeg = '/usr/bin/ffmpeg-test'
        with patch('locast2dvr.main.distutils.spawn.find_executable') as f:
            f.return_value = '/usr/bin/ffmpeg-test'
            main = Main(self.config)
            main.log = MagicMock()

            main._check_ffmpeg()
            self.assertEqual(main.config.ffmpeg, '/usr/bin/ffmpeg-test')
            f.assert_called_once_with('/usr/bin/ffmpeg-test')

    def test_no_ffmpeg(self):
        self.config.ffmpeg = None
        with patch('locast2dvr.main.distutils.spawn.find_executable') as f:
            f.return_value = None
            main = Main(self.config)
            main.log = MagicMock()

            main._check_ffmpeg()
            self.assertEqual(main.config.ffmpeg, None)
            f.assert_called_once_with('ffmpeg')


class TestLogin(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            'verbose': 0,
            'logfile': None,
            'username': 'foo',
            'password': 'secret'
        })

    def test_login_successfull(self):
        with patch('locast2dvr.main.LocastService') as service:
            main = Main(self.config)
            main._login()
            service.login.assert_called_once_with('foo', 'secret')

    @patch('locast2dvr.main.sys')
    def test_login_unsuccessfull(self, sys: MagicMock):
        with patch('locast2dvr.main.LocastService') as service:
            main = Main(self.config)
            service.login.side_effect = Exception("oops!")
            main._login()
            service.login.assert_called_once_with('foo', 'secret')
            sys.exit.assert_called_once_with(1)
