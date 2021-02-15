import threading
import unittest

from freezegun import freeze_time
from locast2dvr.locast.fcc import CHECK_INTERVAL, FACILITIES_URL, Facilities
from mock import MagicMock, mock_open, patch


def create_facility():
    with patch('locast2dvr.locast.fcc.Path') as Path:
        Path.home.return_value = '/home/user'
        return Facilities()


@patch('locast2dvr.locast.fcc.Facilities._run')
class TestFCCInstance(unittest.TestCase):
    def test_instance(self, run: MagicMock):
        with patch('locast2dvr.locast.fcc.Facilities.__init__') as init:
            init.return_value = None
            first = Facilities.instance()
            second = Facilities.instance()

            self.assertEqual(first, second)
            run.assert_called_once()


@patch('locast2dvr.locast.fcc.Path')
class TestFCCInit(unittest.TestCase):

    def test_init(self, Path):
        Path.home.return_value = '/home/user'
        f = Facilities()

        self.assertEqual(f._dma_facilities_map, {})
        self.assertEqual(f._locast_dmas, [])
        self.assertEqual(f.cache_dir, '/home/user/.locast2dvr')
        self.assertEqual(f.cache_file, '/home/user/.locast2dvr/facilities.zip')
        self.assertIsInstance(f._lock, type(threading.Lock()))


class TestFCCLookup(unittest.TestCase):
    def test_by_dma_and_call_sign(self):
        f = create_facility()
        facility1 = {
            'tv_virtual_channel': None,
            'fac_channel': '1'
        }
        facility2 = {
            'tv_virtual_channel': '1.1',
            'fac_channel': '1'
        }

        f._dma_facilities_map = {
            ("123", "WWLTV"): facility1,
            ("345", "WW4L"): facility2
        }

        ret1 = f.by_dma_and_call_sign("123", "WWLTV")
        ret2 = f.by_dma_and_call_sign("345", "WW4L")
        ret3 = f.by_dma_and_call_sign("111", "WW4L")
        ret4 = f.by_dma_and_call_sign("123", "WWOZ")

        self.assertEqual(ret1, {"channel": '1', "analog": True})
        self.assertEqual(ret2, {"channel": '1.1', "analog": False})
        self.assertIsNone(ret3)
        self.assertIsNone(ret4)


@freeze_time("2021-01-01")
@patch('locast2dvr.locast.fcc.os.path.exists')
@patch('locast2dvr.locast.fcc.os.path.getmtime')
@patch('locast2dvr.locast.fcc.threading.Timer')
class TestFCCRun(unittest.TestCase):
    def test_cache_file_not_existing(self, timer: MagicMock, getmtime: MagicMock,
                                     exists: MagicMock):

        exists.return_value = False

        f = create_facility()
        f._download = download = MagicMock()
        download.return_value = "downloaded data"
        f._write_cache_file = write_cache_file = MagicMock()
        f._read_cache_file = read_cache_file = MagicMock()
        f._process = process = MagicMock()
        f._unzip = unzip = MagicMock()
        timer.return_value = timer_instance = MagicMock()

        f._run()

        download.assert_called()
        process.assert_called()
        unzip.assert_called()
        getmtime.assert_not_called()
        write_cache_file.assert_called_once_with("downloaded data")
        read_cache_file.assert_not_called()

        timer.assert_called_once_with(CHECK_INTERVAL, f._run)
        timer_instance.start.assert_called()

    def test_file_existing_data_too_old(self, timer: MagicMock, getmtime: MagicMock,
                                        exists: MagicMock):

        exists.return_value = True
        getmtime.return_value = 1609369200  # 25 hours old
        f = create_facility()
        f._download = download = MagicMock()
        download.return_value = "downloaded data"
        f._write_cache_file = write_cache_file = MagicMock()
        f._read_cache_file = read_cache_file = MagicMock()
        f._process = process = MagicMock()
        f._unzip = unzip = MagicMock()
        timer.return_value = timer_instance = MagicMock()

        f._run()

        download.assert_called()
        process.assert_called()
        unzip.assert_called()
        getmtime.assert_called_once_with(
            '/home/user/.locast2dvr/facilities.zip')
        write_cache_file.assert_called_once_with("downloaded data")
        read_cache_file.assert_not_called()

        timer.assert_called_once_with(CHECK_INTERVAL, f._run)
        timer_instance.start.assert_called()

    def test_file_existing_data_not_too_old(self, timer: MagicMock, getmtime: MagicMock,
                                            exists: MagicMock):

        exists.return_value = True
        getmtime.return_value = 1609477200  # 1 hour old
        f = create_facility()
        f._download = download = MagicMock()
        download.return_value = "downloaded data"
        f._write_cache_file = write_cache_file = MagicMock()
        f._read_cache_file = read_cache_file = MagicMock()
        f._process = process = MagicMock()
        f._unzip = unzip = MagicMock()
        timer.return_value = timer_instance = MagicMock()

        f._run()

        download.assert_not_called()
        process.assert_called()
        unzip.assert_called()
        getmtime.assert_called_once_with(
            '/home/user/.locast2dvr/facilities.zip')
        write_cache_file.assert_not_called()
        read_cache_file.assert_called_once()

        timer.assert_called_once_with(CHECK_INTERVAL, f._run)
        timer_instance.start.assert_called()

    def test_started_and_data_not_too_old(self, timer: MagicMock, getmtime: MagicMock,
                                          exists: MagicMock):

        exists.return_value = True
        getmtime.return_value = 1609477200  # 1 hour old

        f = create_facility()
        f._download = download = MagicMock()
        download.return_value = "downloaded data"
        f._write_cache_file = write_cache_file = MagicMock()
        f._read_cache_file = read_cache_file = MagicMock()
        f._process = process = MagicMock()
        f._unzip = unzip = MagicMock()
        timer.return_value = timer_instance = MagicMock()
        f._dma_facilities_map = {"key": "value"}

        f._run()

        download.assert_not_called()
        process.assert_not_called()
        unzip.assert_not_called()
        getmtime.assert_called_once_with(
            '/home/user/.locast2dvr/facilities.zip')
        write_cache_file.assert_not_called()
        read_cache_file.assert_not_called()

        timer.assert_called_once_with(CHECK_INTERVAL, f._run)
        timer_instance.start.assert_called()


@patch('locast2dvr.locast.fcc.requests.get')
class TestFCCDownload(unittest.TestCase):
    def test_download(self, get: MagicMock()):
        get.return_value = response = MagicMock()
        response.content = "download content"
        f = create_facility()

        data = f._download()

        get.assert_called_once_with(FACILITIES_URL)
        response.raise_for_status.assert_called()
        self.assertEqual(data, "download content")


class TestFCCWriteCacheFile(unittest.TestCase):
    def test_write_cache_file(self):
        f = create_facility()
        with patch("builtins.open", mock_open()) as mock_file:
            f._write_cache_file("write data")
            mock_file.assert_called_with(
                "/home/user/.locast2dvr/facilities.zip", mode="wb")


class TestFCCReadCacheFile(unittest.TestCase):
    def test_read_cache_file(self):
        f = create_facility()
        with patch("builtins.open", mock_open(read_data="some data")) as mock_file:
            data = f._read_cache_file()
            mock_file.assert_called_with(
                "/home/user/.locast2dvr/facilities.zip", "rb")
            self.assertEqual(data, "some data")


@patch('locast2dvr.locast.fcc.zipfile.ZipFile')
@patch('locast2dvr.locast.fcc.io.BytesIO')
class TestFCCUnzip(unittest.TestCase):
    def test_unzip(self, bytesio: MagicMock, ZipFile: MagicMock):
        ZipFile.return_value = zipfile = MagicMock()
        bytesio.return_value = bytesio_instance = MagicMock()
        zipfile.read.return_value = read_result = MagicMock()
        data = bytes("data data", "utf-8")
        f = create_facility()
        f._unzip(data)

        bytesio.assert_called_once_with(data)
        ZipFile.assert_called_once_with(bytesio_instance)
        zipfile.read.assert_called_once_with('facility.dat')
        read_result.decode.assert_called_once_with('utf-8')


FACILITY_DATA = """
VICKSBURG|MS||FISHER, WAYLAND, COOPER|2001 PENN AVE, NW|WLOO|36|WASHINGTON|US|602.000000|DT|DC|06/16/2009|CDT|84253|06/01/2021|LICEN|20006|1851|M||04/15/2013|3912|3913|||MY NETWORK|JACKSON MS|35|06/04/2013|^|

ODESSA|TX||1146 19TH ST NW|SUITE 200|KWWT|30|WASHINGTON|US|566.000000|DT|DC|06/16/2009|CDT|84410|08/01/2022|LICEN|20036||M||03/14/2006|8618|8619|||CW|ODESSA-MIDLAND|30|08/26/2020|^|

UVALDE|TX||122 EAST CALERA ST.||DK30AI|30|UVALDE|US|566.000000|TX|TX||TTL|66||PRCAN|78801||M||09/24/1985|||||||||^|
"""


@freeze_time("2021-01-01")
class TestFCCProcess(unittest.TestCase):

    @freeze_time("2021-01-01")
    def test_success(self):
        f = create_facility()
        f._find_locast_dma_id_by_fcc_dma_name = mapper = MagicMock()
        mapper.side_effect = ['1', '2', '3']

        f._process(FACILITY_DATA)
        self.assertEqual(len(f._dma_facilities_map), 2)
        self.assertEqual(list(f._dma_facilities_map.keys()), [
                         ('1', 'WLOO'), ('2', 'KWWT')])

    @freeze_time("2021-01-01")
    def test_broken_data(self):
        f = create_facility()
        f._find_locast_dma_id_by_fcc_dma_name = mapper = MagicMock()
        mapper.side_effect = ['1', '2', '3']

        too_short = "ODESSA|TX||1146 19TH ST NW|SUITE 200|KWWT|30|WASHINGTON|US|566.000000|DT|DC|06/16/2009|CDT|84410|08/01/2022|LICEN|20036||M||03/14/2006|8618|8619|||CW|ODESSA-MIDLAND|30|^|"
        with self.assertRaises(Exception):
            f._process(too_short)

        too_long = "ODESSA|TX||1146 19TH ST NW|SUITE 200|KWWT|30|WASHINGTON|US|566.000000|DT|DC|06/16/2009|CDT|84410|08/01/2022|LICEN|20036||M||03/14/2006|8618|8619|||CW|ODESSA-MIDLAND|30|foo|bar|^|"
        with self.assertRaises(Exception):
            f._process(too_long)

    @freeze_time("2050-01-01")
    def test_licence_expired(self):
        f = create_facility()
        f._find_locast_dma_id_by_fcc_dma_name = mapper = MagicMock()

        f._process(FACILITY_DATA)
        mapper.assert_not_called()
        self.assertEqual(len(f._dma_facilities_map), 0)

    @freeze_time("2021-01-01")
    def test_no_locast_dma(self):
        f = create_facility()
        f._find_locast_dma_id_by_fcc_dma_name = mapper = MagicMock()
        mapper.side_effect = [None, None, None]

        f._process(FACILITY_DATA)
        self.assertEqual(len(f._dma_facilities_map), 0)


LOCAST_DMAS = [{'id': 512, 'name': 'Baltimore'}, {'id': 501, 'name': 'New York'}, {'id': 527, 'name': 'Indianapolis'}, {'id': 803, 'name': 'Los Angeles'}, {'id': 504, 'name': 'Philadelphia'}, {'id': 623, 'name': 'Dallas'}, {'id': 624, 'name': 'Sioux City'}, {'id': 511, 'name': 'Washington DC'}, {'id': 764, 'name': 'Rapid City'}, {'id': 807, 'name': 'San Francisco'}, {'id': 506, 'name': 'Boston'}, {'id': 602, 'name': 'Chicago'}, {
    'id': 753, 'name': 'Phoenix'}, {'id': 528, 'name': 'Miami'}, {'id': 725, 'name': 'Sioux Falls'}, {'id': 539, 'name': 'Tampa Bay'}, {'id': 490, 'name': 'Puerto Rico'}, {'id': 577, 'name': 'Scranton'}, {'id': 613, 'name': 'Minneapolis'}, {'id': 669, 'name': 'Madison'}, {'id': 548, 'name': 'West Palm Beach'}, {'id': 819, 'name': 'Seattle'}, {'id': 524, 'name': 'Atlanta'}, {'id': 751, 'name': 'Denver'}, {'id': 505, 'name': 'Detroit'}]


@patch("locast2dvr.locast.fcc.requests.get")
class TestFCCMapFCCToLocastDMA(unittest.TestCase):
    def test_not_loaded(self, get: MagicMock):
        get.return_value = response = MagicMock()
        response.json.return_value = LOCAST_DMAS
        f = create_facility()

        self.assertEqual(
            f._find_locast_dma_id_by_fcc_dma_name("NEW YORK"), '501')
        get.assert_called_once()
        self.assertEqual(f._locast_dmas, LOCAST_DMAS)

    def test_loaded(self, get: MagicMock):
        f = create_facility()
        f._locast_dmas = LOCAST_DMAS

        get.assert_not_called()
        self.assertEqual(
            f._find_locast_dma_id_by_fcc_dma_name("TAMPA BAY"), '539')
        self.assertEqual(f._find_locast_dma_id_by_fcc_dma_name(
            "BOSTON (MANCHESTER)"), '506')
        self.assertEqual(f._find_locast_dma_id_by_fcc_dma_name(
            "MIAMI-FT. LAUDERDALE"), '528')
        self.assertEqual(
            f._find_locast_dma_id_by_fcc_dma_name("TAMPA BAY"), '539')
        self.assertEqual(
            f._find_locast_dma_id_by_fcc_dma_name("NEW ORLEANS"), None)
