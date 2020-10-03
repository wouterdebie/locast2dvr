import requests
import logging
import re
import m3u8
from datetime import datetime
from .fcc import Facilities

LOGIN_URL = "https://api.locastnet.org/api/user/login"
USER_URL = "https://api.locastnet.org/api/user/me"
DMA_URL = "https://api.locastnet.org/api/watch/dma"
IP_URL = 'https://api.locastnet.org/api/watch/dma/ip'
STATIONS_URL = 'https://api.locastnet.org/api/watch/epg'
WATCH_URL = 'https://api.locastnet.org/api/watch/station'


class Service:
    def __init__(self, username, password, latlon=None, zipcode=None):
        self.username = username
        self.password = password
        self.latlon = latlon
        self.zipcode = zipcode

        self.logged_in = False
        self.location = None
        self.active = False
        self.dma = None
        self.city = None

    def login(self):
        logging.info(f"Locast logging in with {self.username}")
        try:
            r = requests.post(LOGIN_URL, json={
                "username": self.username, "password": self.password},
                headers={'Content-Type': 'application/json'})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logging.error(f'Login failed: {err}')
            return False

        self.token = r.json()['token']
        self.logged_in = True
        return True

    def valid_user(self):
        try:
            r = requests.get(USER_URL, headers={
                             'Content-Type': 'application/json',
                             'authorization': 'Bearer ' + self.token})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)
        pass

        user_info = r.json()
        logging.info(user_info)
        if user_info['didDonate'] and datetime.now() > datetime.fromtimestamp(user_info['donationExpire'] / 1000):
            logging.error("Donation expired")
            return False
        elif not user_info['didDonate']:
            logging.error("User didn't donate")
            return False

        try:
            self._find_location()
        except SystemExit as err:
            raise err

        if not self.active:
            logging.error(f'Locast not available in {self.city}')

        return self.active

    def _find_location(self):
        if self.latlon:
            self._set_attrs_from_geo(
                f'{DMA_URL}/{self.latlon["latitude"]}/{self.latlon["longitude"]}')
        elif self.zipcode:
            self._set_attrs_from_geo(f'{DMA_URL}/zip/{self.zipcode}')
        else:
            self._set_attrs_from_geo(IP_URL)

    def _set_attrs_from_geo(self, url):
        try:
            r = requests.get(url, headers={'Content-Type': 'application/json'})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(err)

        geo = r.json()
        self.location = {
            'latitude': geo['latitude'], 'longitude': geo['longitude']}
        self.dma = int(geo['DMA'])
        self.active = geo['active']
        self.city = geo['name']
        logging.info(geo)

    def _load_stations(self):
        if not self.logged_in:
            raise SystemExit("User not logged in")
        try:
            r = requests.get(f'{STATIONS_URL}/{self.dma}', headers={
                             'Content-Type': 'application/json',
                             'authorization': 'Bearer ' + self.token})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logging.error(f'Error while getting stations: {err}')
            return None

        self.locast_stations = r.json()
        self.facilities = Facilities()

    def get_stations(self):
        self._load_stations()

        fake_channel = 1000
        for station in self.locast_stations:
            m = re.match(r'(\d+\.\d+) .+', station['callSign'])
            if m:
                station['channel'] = m.group(1)
                continue  # Done with this station

            result = self._detect_callsign(
                station['callSign']) or self._detect_callsign(station['name'])
            if result:
                (call_sign, station_type, subchannel) = result
                fcc_station = self._find_fcc_station(call_sign)
                if fcc_station:
                    station['channel'] = fcc_station["channel"] if fcc_station[
                        'analog'] else f'{fcc_station["channel"]}.{subchannel or 1}'
                    continue  # Done with this sation

            # Can't find the channel name, so assign a fake channel
            station['channel'] = str(fake_channel)
            fake_channel += 1

        return self.locast_stations

    def _detect_callsign(self, call_sign):
        m = re.match(r'^([KW][A-Z]{2,3})([A-Z]{0,2})(\d{0,2})$', call_sign)
        if m:
            return m.groups()

    def _find_fcc_station(self, call_sign):
        for facility in self.facilities.facilities:
            if facility['nielsen_dma'] == self.facilities.dma_mapping[self.dma] and \
                    call_sign == facility['fac_callsign'].split("-")[0]:
                return {
                    "channel": facility['tv_virtual_channel'] or facility['fac_channel'],
                    "analog": facility['tv_virtual_channel'] == None
                }

    def get_station_stream_uri(self, station_id):
        url = f'{WATCH_URL}/{station_id}/{self.location["latitude"]}/{self.location["longitude"]}'

        try:
            r = requests.get(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'authorization': f'Bearer {self.token}',
                    'User-Agent': "curl/7.64.1"})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logging.error(f'Error while getting station URL: {err}')
            return None

        stream_url = r.json()["streamUrl"]
        m3u8_data = m3u8.load(stream_url)
        if len(m3u8_data.playlists) == 0:
            return stream_url

        best_resolution = sorted(m3u8_data.playlists,
                                 key=lambda pl: pl.stream_info.resolution).pop()

        logging.info(f'Resolution: {best_resolution}')
        return best_resolution.absolute_uri
