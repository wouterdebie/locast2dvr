import threading
import unittest
from datetime import datetime
from logging import Logger

import m3u8
from freezegun import freeze_time
from locast2dvr.locast.service import (DMA_URL, IP_URL, LOGIN_URL,
                                       STATIONS_URL, USER_URL, WATCH_URL, Geo,
                                       LocastService, LocationInvalidError,
                                       UserInvalidError)
from locast2dvr.utils import Configuration
from mock import MagicMock, PropertyMock, patch
from requests.exceptions import HTTPError


class TestGeo(unittest.TestCase):
    def test_init(self):
        g = Geo("90210")
        self.assertEqual(g.zipcode, "90210")
        g = Geo(None, {"longitude": 10.1234, "latitude": 56.023})
        self.assertEqual(g.coords, {"longitude": 10.1234, "latitude": 56.023})

    def test_repr(self):

        self.assertEqual(repr(Geo("90210")), "Geo(zipcode: 90210)")
        self.assertEqual(repr(Geo()), "Geo(None)")
        self.assertEqual(
            repr(Geo(None, {"longitude": 10.1234, "latitude": 56.023})),
            "Geo(coords: {'longitude': 10.1234, 'latitude': 56.023})")

    def test_equality(self):
        self.assertEqual(Geo("90210"), Geo("90210"))
        self.assertEqual(Geo(None, {"longitude": 10.1234, "latitude": 56.023}),
                         Geo(None, {"longitude": 10.1234, "latitude": 56.023}))


class TestLocastService(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "cache_stations": False
        })

    def test_init(self):
        service = LocastService(self.config, Geo("90210"))
        self.assertEqual(service.coords, None)
        self.assertEqual(service.zipcode, "90210")
        self.assertEqual(service.config, self.config)
        self.assertEqual(service.location, None)
        self.assertEqual(service.active, False)
        self.assertEqual(service.dma, None)
        self.assertEqual(service.city, None)
        self.assertIsInstance(service._channel_lock, type(threading.Lock()))

    @patch("locast2dvr.locast.service.Facilities")
    def test_start(self, facilities: MagicMock()):
        service = LocastService(self.config, Geo("90210"))
        facilities.instance.return_value = instance = MagicMock()
        service._load_location_data = load_location_data = MagicMock()
        service._update_cache = update_cache = MagicMock()

        service.start()
        self.assertEqual(service._fcc_facilities, instance)
        load_location_data.assert_called()
        update_cache.assert_not_called()

    @patch("locast2dvr.locast.service.Facilities")
    def test_start_with_cache(self, facilities: MagicMock()):
        self.config.cache_stations = True
        service = LocastService(self.config, Geo("90210"))
        facilities.instance.return_value = instance = MagicMock()
        service._load_location_data = load_location_data = MagicMock()
        service._update_cache = update_cache = MagicMock()

        service.start()
        self.assertEqual(service._fcc_facilities, instance)
        load_location_data.assert_called()
        update_cache.assert_called()

    @freeze_time("2021-01-01 04:00:00")
    def test_is_token_valid(self):
        service = LocastService(self.config, MagicMock())
        service.last_login = datetime(2021, 1, 1, 3, 30)
        self.assertTrue(service._is_token_valid())

    @freeze_time("2021-01-01 04:00:00")
    def test_is_token_invalid(self):
        service = LocastService(self.config, MagicMock())
        service.last_login = datetime(2021, 1, 1, 2, 30)
        self.assertFalse(service._is_token_valid())

    def test_validate_token_valid(self):
        service = LocastService(self.config, MagicMock())
        service._is_token_valid = validate_token = MagicMock()
        validate_token.return_value = True
        service.login = login = MagicMock()

        service._validate_token()
        login.assert_not_called()

    def test_validate_token_invalid(self):
        service = LocastService(self.config, MagicMock())
        service._is_token_valid = validate_token = MagicMock()
        validate_token.return_value = False
        service.login = login = MagicMock()

        service._validate_token()
        login.assert_called()

    def test_load_location_data(self):
        service = LocastService(self.config, MagicMock())
        service._find_location = find_location = MagicMock()
        service.active = True

        try:
            service._load_location_data()
        except LocationInvalidError as e:
            self.fail(e)

        find_location.assert_called()

    def test_load_location_data_fail(self):
        service = LocastService(self.config, MagicMock())
        service._find_location = find_location = MagicMock()
        service.active = False

        with self.assertRaises(LocationInvalidError):
            service._load_location_data()
            find_location.assert_called()

    def test_detect_call_sign(self):
        service = LocastService(self.config, MagicMock())
        self.assertEqual(service._detect_callsign("WLTV1"), ("WLTV", "1"))
        self.assertEqual(service._detect_callsign("KLTV1"), ("KLTV", "1"))
        self.assertEqual(service._detect_callsign("KLTVAA1"), ("KLTV", "1"))
        self.assertEqual(service._detect_callsign("KLTV"), ("KLTV", ''))
        self.assertEqual(service._detect_callsign("FLTV1"), None)


class TestFindLocation(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({})

    def test_with_coords(self):
        service = LocastService(self.config, Geo(
            None, {"longitude": 1.0, "latitude": 2.0}))
        service._set_attrs_from_geo = set_attrs = MagicMock()

        service._find_location()

        url = f"{DMA_URL}/2.0/1.0"
        set_attrs.assert_called_with(url)

    def test_with_zipcode(self):
        service = LocastService(self.config, Geo("90210"))
        service._set_attrs_from_geo = set_attrs = MagicMock()

        service._find_location()

        url = f"{DMA_URL}/zip/90210"
        set_attrs.assert_called_with(url)

    def test_with_ip(self):
        service = LocastService(self.config, Geo())
        service._set_attrs_from_geo = set_attrs = MagicMock()

        service._find_location()

        set_attrs.assert_called_with(IP_URL)


@patch('locast2dvr.locast.service.requests')
class TestSetAttrsFromGeo(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({})

    def test_success(self, requests: MagicMock):
        requests.get.return_value = response = MagicMock()
        service = LocastService(self.config, MagicMock())
        response.status_code = 200
        response.json.return_value = {
            'latitude': 1.0,
            'longitude': 2.0,
            'DMA': 123,
            'active': True,
            'name': 'Chicago'
        }

        try:
            service._set_attrs_from_geo("geo_url")
        except LocationInvalidError as e:
            self.fail(e)

        requests.get.assert_called_with(
            "geo_url", headers={'Content-Type': 'application/json'})
        response.raise_for_status.assert_called()
        self.assertEqual(service.location, {"latitude": 1.0, "longitude": 2.0})
        self.assertEqual(service.dma, "123")
        self.assertEqual(service.active, True)
        self.assertEqual(service.city, 'Chicago')

    def test_unknown_geo(self, requests: MagicMock):
        requests.get.return_value = response = MagicMock()
        service = LocastService(self.config, MagicMock())
        response.status_code = 204

        with self.assertRaises(LocationInvalidError):
            service._set_attrs_from_geo("geo_url")

        requests.get.assert_called_with(
            "geo_url", headers={'Content-Type': 'application/json'})
        response.raise_for_status.assert_called()

    def test_unknown_http_error(self, requests: MagicMock):
        requests.get.return_value = response = MagicMock()
        service = LocastService(self.config, MagicMock())
        response.raise_for_status.side_effect = HTTPError

        with self.assertRaises(LocationInvalidError):
            service._set_attrs_from_geo("geo_url")

        requests.get.assert_called_with(
            "geo_url", headers={'Content-Type': 'application/json'})
        response.raise_for_status.assert_called()


@patch('locast2dvr.locast.service.requests')
class TestServiceClassMethods(unittest.TestCase):
    def test_class_variables(self, _):
        self.assertIsInstance(LocastService.log, Logger)
        self.assertIsInstance(LocastService._login_lock,
                              type(threading.Lock()))

    @patch('locast2dvr.locast.service.LocastService._validate_user')
    def test_login_successful(self, validate_user: MagicMock(), requests: MagicMock()):
        requests.post = post = MagicMock()
        post.return_value = response = MagicMock()
        response.json.return_value = {
            "token": "specialToken"
        }

        LocastService.login("my_user", "secret")
        post.assert_called_once_with(LOGIN_URL,
                                     json={
                                         "username": "my_user",
                                         "password": "secret"
                                     },
                                     headers={
                                         'Content-Type': 'application/json'}
                                     )

        response.raise_for_status.assert_called_once()
        validate_user.assert_called_once()
        self.assertEqual(LocastService.token, "specialToken")

    @patch('locast2dvr.locast.service.LocastService._validate_user')
    def test_login_failed(self, validate_user: MagicMock(), requests: MagicMock()):
        requests.post = post = MagicMock()
        post.return_value = response = MagicMock()
        response.raise_for_status.side_effect = HTTPError
        response.json.return_value = {
            "token": "specialToken"
        }

        with self.assertRaises(UserInvalidError):
            LocastService.login("my_user", "wrong_password")
            validate_user.assert_not_called()
            self.assertEqual(LocastService.token, None)

    @freeze_time('2021-01-01')
    def test_validate_user_successful(self, requests: MagicMock()):
        LocastService.token = "locast_token"
        requests.get = get = MagicMock()
        get.return_value = response = MagicMock()
        response.json.return_value = {
            "didDonate": True,
            "donationExpire": 1612159200000
        }

        try:
            LocastService._validate_user()
        except UserInvalidError as e:
            self.fail(e)

        requests.get.assert_called_once_with(
            USER_URL, headers={
                'Content-Type': 'application/json',
                'authorization': 'Bearer locast_token'})

    def test_validate_user_no_donation(self, requests: MagicMock()):
        LocastService.token = "locast_token"
        requests.get = get = MagicMock()
        get.return_value = response = MagicMock()
        response.json.return_value = {
            "didDonate": False,
            "donationExpire": 1609480800000
        }

        with self.assertRaises(UserInvalidError):
            LocastService._validate_user()

    @freeze_time('2021-02-02')
    def test_validate_user_donation_expired(self, requests: MagicMock()):
        LocastService.token = "locast_token"
        requests.get = get = MagicMock()
        get.return_value = response = MagicMock()
        response.json.return_value = {
            "didDonate": True,
            "donationExpire": 1609480800000
        }

        with self.assertRaises(UserInvalidError):
            LocastService._validate_user()


class TestGetStations(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "cache_stations": True,
            "days": 8,
            "cache_timeout": 3600
        })

    def test_get_stations_with_cache(self):
        self.config.cache_stations = True
        service = LocastService(self.config, MagicMock())
        service._stations = stations = MagicMock()
        service._get_stations = get_stations = MagicMock()

        result = service.get_stations()

        self.assertEqual(result, stations)
        get_stations.assert_not_called()

    def test_get_stations_no_cache(self):
        self.config.cache_stations = False
        service = LocastService(self.config, MagicMock())
        service._get_stations = get_stations = MagicMock()
        get_stations.return_value = stations = MagicMock()

        result = service.get_stations()

        self.assertEqual(result, stations)
        get_stations.assert_called()

    @patch("locast2dvr.locast.service.threading.Timer")
    def test_update_cache(self, timer: MagicMock):
        timer.return_value = timer_instance = MagicMock()

        service = LocastService(self.config, MagicMock())
        service._get_stations = MagicMock()
        service._get_stations.return_value = stations = MagicMock()

        service._update_cache()

        self.assertEqual(service._stations, stations)
        timer.assert_called_with(3600, service._update_cache)
        timer_instance.start.assert_called()

    def test_internal_get_stations_simple_case(self):
        stations = [{
            "callSign": "2.1 CBS"
        }]

        service = LocastService(self.config, MagicMock())
        service.city = "Chicago"
        service.timezone = "America/Chicago"
        service._get_locast_stations = get_locast_stations = MagicMock()
        get_locast_stations.return_value = stations

        result = service._get_stations()

        expected = [{
            "callSign": "2.1 CBS",
            "channel": "2.1",
            "city": "Chicago",
            "timezone": "America/Chicago"
        }]
        get_locast_stations.assert_called()
        self.assertEqual(result, expected)

    def test_internal_get_stations_facility_lookup(self):
        stations = [
            {
                "callSign": "CBS",
                "name": "WLTV1"
            },
            {
                "callSign": "WLTV2",
                "name": "NPR"
            }
        ]

        service = LocastService(self.config, MagicMock())
        service.dma = "123"
        service.city = "Chicago"
        service.timezone = "America/Chicago"
        service._get_locast_stations = get_locast_stations = MagicMock()
        get_locast_stations.return_value = stations
        service._detect_callsign = MagicMock()
        service._detect_callsign.side_effect = [("WLTV", 1), None, ("WLTV", 2)]
        service._fcc_facilities = MagicMock()
        service._fcc_facilities.by_dma_and_call_sign.side_effect = [
            {
                "channel": "2",
                "analog": False
            },
            {
                "channel": "1",
                "analog": True
            }
        ]

        result = service._get_stations()

        expected = [
            {
                "callSign": "CBS",
                "name": "WLTV1",
                "channel": "2.1",
                "city": "Chicago",
                "timezone": "America/Chicago"
            },
            {
                'callSign': 'WLTV2',
                'name': 'NPR',
                'city': 'Chicago',
                'channel': '1',
                "timezone": "America/Chicago"
            }
        ]
        get_locast_stations.assert_called()
        service._fcc_facilities.by_dma_and_call_sign.assert_called_with(
            "123", "WLTV")
        self.assertEqual(result, expected)

    def test_internal_get_stations_facility_lookup_no_result(self):
        stations = [
            {
                "callSign": "CBS",
                "name": "WLTV1"
            },
            {
                "callSign": "WLTV2",
                "name": "NPR"
            }
        ]

        service = LocastService(self.config, MagicMock())
        service.dma = "123"
        service.city = "Chicago"
        service.timezone = "America/Chicago"
        service._get_locast_stations = get_locast_stations = MagicMock()
        get_locast_stations.return_value = stations
        service._detect_callsign = MagicMock()
        service._detect_callsign.side_effect = [("WLTV", 1), None, ("WLTV", 2)]
        service._fcc_facilities = MagicMock()
        service._fcc_facilities.by_dma_and_call_sign.return_value = None

        result = service._get_stations()

        expected = [
            {
                "callSign": "CBS",
                "name": "WLTV1",
                "channel": "1000",
                "city": "Chicago",
                "timezone": "America/Chicago"
            },
            {
                'callSign': 'WLTV2',
                'name': 'NPR',
                'city': 'Chicago',
                'channel': '1001',
                'timezone': "America/Chicago"
            }
        ]
        get_locast_stations.assert_called()
        service._fcc_facilities.by_dma_and_call_sign.assert_called_with(
            "123", "WLTV")
        self.assertEqual(result, expected)

    def test_internal_get_stations_no_call_sign(self):
        stations = [
            {
                "callSign": "CBS",
                "name": "WLTV1"
            },
            {
                "callSign": "WLTV2",
                "name": "NPR"
            }
        ]

        service = LocastService(self.config, MagicMock())
        service.dma = "123"
        service.city = "Chicago"
        service.timezone = "America/Chicago"
        service._get_locast_stations = get_locast_stations = MagicMock()
        get_locast_stations.return_value = stations
        service._detect_callsign = MagicMock()
        service._detect_callsign.return_value = None

        result = service._get_stations()

        expected = [
            {
                "callSign": "CBS",
                "name": "WLTV1",
                "channel": "1000",
                "city": "Chicago",
                "timezone": "America/Chicago"
            },
            {
                'callSign': 'WLTV2',
                'name': 'NPR',
                'city': 'Chicago',
                'channel': '1001',
                'timezone': 'America/Chicago'
            }
        ]
        get_locast_stations.assert_called()

        self.assertEqual(result, expected)


@freeze_time("2021-01-01")
@patch('locast2dvr.locast.service.requests')
class TestGetLocastStations(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "days": 8
        })

    def test_get(self, requests: MagicMock()):
        service = LocastService(self.config, MagicMock())
        service._validate_token = MagicMock()
        service.token = "TOKEN"
        service.dma = "123"
        requests.get = get = MagicMock()
        requests.get.return_value = response = MagicMock()
        response.json.return_value = ["foo", "bar"]

        result = service._get_locast_stations()

        response.raise_for_status.assert_called()
        get.assert_called_once_with(
            f'{STATIONS_URL}/123?startTime=2021-01-01T00:00:00-00:00&hours=192',
            headers={
                'Content-Type': 'application/json',
                'authorization': 'Bearer TOKEN'})

        response.json.assert_called()
        self.assertEqual(result, ["foo", "bar"])


@patch('locast2dvr.locast.service.requests')
@patch('locast2dvr.locast.service.m3u8')
class TestStreamUri(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration({
            "days": 8
        })

    def test_get(self, m3u8, requests: MagicMock()):
        service = LocastService(self.config, MagicMock())
        service._validate_token = MagicMock()
        service.token = "TOKEN"
        service.location = {
            "latitude": "10.0",
            "longitude": "-34.5"
        }
        requests.get = get = MagicMock()
        requests.get.return_value = response = MagicMock()
        response.json.return_value = {
            "streamUrl": "stream_url"
        }

        m3u8.load.return_value = m3u_data = MagicMock()
        m3u_data.playlists = []

        result = service.get_station_stream_uri("1000")

        response.raise_for_status.assert_called()
        get.assert_called_once_with(
            f'{WATCH_URL}/1000/10.0/-34.5',
            headers={
                'Content-Type': 'application/json',
                'authorization': 'Bearer TOKEN',
                'User-Agent': "curl/7.64.1"})

        response.json.assert_called()
        self.assertEqual(result, "stream_url")
        m3u8.load.assert_called_with("stream_url")

    def test_get_playlist(self, _m3u8, requests: MagicMock()):
        service = LocastService(self.config, MagicMock())
        service._validate_token = MagicMock()
        service.token = "TOKEN"
        service.location = {
            "latitude": "10.0",
            "longitude": "-34.5"
        }
        requests.get = get = MagicMock()
        requests.get.return_value = response = MagicMock()
        response.json.return_value = {
            "streamUrl": "http://stream_url/foo"
        }

        m3u_data = m3u8.loads("""#EXTM3U
            #EXT-X-VERSION:3
            #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1600000,RESOLUTION=854x480
            ../variant/5fq9TaMBBU9Qp87sj8IRbWh7QK01B4b5PNvMbHHcyCmvY2GoVIpufr0oIGBWuT88ZCWnUERTb3dzCYoeSbzYTBwV9XSQftUljPy3qfRVvAJq.m3u8
            #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1024000,RESOLUTION=640x360
            ../variant/5fq9TaMBBU9Qp87sj8IRbWh7QK01B4b5PNvMbHHcyCmvY2GoVIpufr0oIGBWuT88YXtZOaPXHcKs0P2wjlxc0oBTepH6VhAy6lODslybGe0z.m3u8
            #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2700000,RESOLUTION=1280x720
            ../variant/5fq9TaMBBU9Qp87sj8IRbWh7QK01B4b5PNvMbHHcyCmvY2GoVIpufr0oIGBWuT88YgHlZ1zmnMfSC8xXfEy2AvYS1rcvAjmOaxKgKvYM7w7h.m3u8
            """.lstrip().rstrip())
        _m3u8.load.return_value = m3u_data
        m3u_data.base_uri = "http://stream_url/foo"
        result = service.get_station_stream_uri("1000")

        response.raise_for_status.assert_called()
        get.assert_called_once_with(
            f'{WATCH_URL}/1000/10.0/-34.5',
            headers={
                'Content-Type': 'application/json',
                'authorization': 'Bearer TOKEN',
                'User-Agent': "curl/7.64.1"})

        response.json.assert_called()
        self.assertEqual(
            result, "http://stream_url/variant/5fq9TaMBBU9Qp87sj8IRbWh7QK01B4b5PNvMbHHcyCmvY2GoVIpufr0oIGBWuT88YgHlZ1zmnMfSC8xXfEy2AvYS1rcvAjmOaxKgKvYM7w7h.m3u8")
