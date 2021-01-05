import logging
import re
import threading
from datetime import datetime
from typing import Optional, Tuple

import m3u8
import requests
from locast2dvr.utils import Configuration, LoggingHandler

from .fcc import Facilities

LOGIN_URL = "https://api.locastnet.org/api/user/login"
USER_URL = "https://api.locastnet.org/api/user/me"
DMA_URL = "https://api.locastnet.org/api/watch/dma"
IP_URL = 'https://api.locastnet.org/api/watch/dma/ip'
STATIONS_URL = 'https://api.locastnet.org/api/watch/epg'
WATCH_URL = 'https://api.locastnet.org/api/watch/station'

TOKEN_LIFETIME = 3600


class Geo:
    def __init__(self, zipcode: Optional[str] = None, latlon: Optional[dict] = None):
        """Object containing location information

        Args:
            zipcode (Optional[str], optional): Zipcode. Defaults to None.
            latlon (Optional[dict], optional): Dict containing latitude and longitude. Defaults to None.
        """
        self.zipcode = zipcode
        self.latlon = latlon

    def __repr__(self) -> str:
        if self.zipcode:
            return f"Geo(zipcode: {self.zipcode})"
        elif self.latlon:
            return f"Geo(latlon: {self.latlon})"
        else:
            return f"Geo(None)"


class LocationInvalidError(Exception):
    pass


class UserInvalidError(Exception):
    pass


class LocastService(LoggingHandler):
    _logged_in = False
    _fcc_facilities = Facilities()
    log = logging.getLogger("LocastService")

    def __init__(self, geo: Geo, config: Configuration):
        """Locast service interface based on a specific location

        Args:
            geo (Geo): Location information
            config (Configuration): Global configuration
        """
        super().__init__()
        self.latlon = geo.latlon
        self.zipcode = geo.zipcode

        self.config = config

        self.location = None
        self.active = False
        self.dma = None
        self.city = None

        self._load_location_data()

        # Start cache updater timer if necessary, otherwise, just preload
        # stations once
        if config.cache_stations:
            self._lock = threading.Lock()
            self._update_cache()

    @classmethod
    def login(cls, username: str = None, password: str = None) -> bool:
        """Log in to locast.org

        This is a class method, so we only have to login once.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            bool: True if successful, False otherwise

        """

        if username:
            cls.username = username
        if password:
            cls.password = password

        cls.log.info(f"Logging in with {cls.username}")
        try:
            r = requests.post(LOGIN_URL,
                              json={
                                  "username": cls.username,
                                  "password": cls.password
                              },
                              headers={'Content-Type': 'application/json'})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise UserInvalidError(f'Login failed: {err}')

        cls.token = r.json()['token']
        cls._logged_in = True
        cls.last_login = datetime.now()

        cls._validate_user()

        cls.log.info("Locast login successful")

    @classmethod
    def _validate_user(cls) -> bool:
        """Validate if the user has an active donation

        Returns:
            bool: True if successful, otherwise False
        """

        r = requests.get(USER_URL, headers={
            'Content-Type': 'application/json',
                            'authorization': 'Bearer ' + cls.token})
        r.raise_for_status()

        user_info = r.json()

        if user_info['didDonate'] and datetime.now() > datetime.fromtimestamp(user_info['donationExpire'] / 1000):
            raise UserInvalidError("Donation expired")
        elif not user_info['didDonate']:
            raise UserInvalidError("User didn't donate")

    def _is_token_valid(self) -> bool:
        """Check if the last login was longer than ``TOKEN_LIFETIME`` ago

        Returns:
            bool: True if valid, False otherwise
        """
        return (datetime.now() - self.last_login).seconds < TOKEN_LIFETIME

    def _validate_token(self):
        """Validate if the login token is still valid. If not, login again to
           obtain a new token
        """
        if not self._is_token_valid():
            self.log.info("Login token expired!")
            self.login()

    def _load_location_data(self):
        """Load location data

        Raises:
            LocationInvalidError: If locast doesn't support the location
        """
        self._find_location()
        if not self.active:
            raise LocationInvalidError(f'Locast not available in {self.city}')

    def _find_location(self):
        """Set the location data (lat, long, dma and city) based on what
           method is used to determine the location (latlon, zip or IP)
        """
        if self.latlon:
            self._set_attrs_from_geo(
                f'{DMA_URL}/{self.latlon["latitude"]}/{self.latlon["longitude"]}')
        elif self.zipcode:
            self._set_attrs_from_geo(f'{DMA_URL}/zip/{self.zipcode}')
        else:
            self._set_attrs_from_geo(IP_URL)

    def _set_attrs_from_geo(self, url: str):
        """Set location data (lat, long, dma and city) based on the url that is passed in

        Args:
            url (str): Locast URL that is used to lookup a location

        Raises:
            LocationInvalidError: If the HTTP request fails or if the location is not found
        """
        try:
            r = requests.get(url, headers={'Content-Type': 'application/json'})
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise LocationInvalidError(err)

        if r.status_code == 204:
            raise LocationInvalidError(f"Geo not found for {url}")

        geo = r.json()
        self.location = {
            'latitude': geo['latitude'], 'longitude': geo['longitude']}
        self.dma = int(geo['DMA'])
        self.active = geo['active']
        self.city = geo['name']

    def get_stations(self) -> list:
        """Get all station information and return in such a way that PMS can use it

        This is done by getting station information from locast.org and and where necessary
        complement channel numbers this with data from the FCC.

        Some locast stations already have the channel number (like 4.1 CBS) as part of the call sign,
        while others don't (like KUSDDT2). In this case we first split the call sign (KUSD) from the
        sub channel number (2) and lookup the channel number using the FCC facilities.
        FCC call signs can be in either the 'name' or 'callSign' property of a Locast station.

        Lastly, if we can't find a channel number, we just make something up, but this should rarely
        happen.

        Note: if caching is disabled, calling this method will lead to calling locast for channel information
              (incl EPG data) every time.

        Returns:
            list: stations
        """

        if self.config.cache_stations:
            with self._lock:
                return self._stations
        else:
            return self._get_stations()

    def _update_cache(self):
        """Update the station cache

        After this method is done fetching station information, it will schedule itself to run again after
        `self.config.cache_timeout` seconds.add()
        """
        stations = self._get_stations()
        with self._lock:
            self._stations = stations
        threading.Timer(self.config.cache_timeout, self._update_cache).start()

    def _get_stations(self) -> list:
        """Actual implementation of retrieving all station information

        Returns:
            list: stations
        """
        self.log.info(
            f"Loading stations for {self.city} (cache: {self.config.cache_stations}, cache timeout: {self.config.cache_timeout}, days: {self.config.days})")
        stations = self._get_locast_stations()

        fake_channel = 1000
        for station in stations:
            station['city'] = self.city
            # See if station conforms to "X.Y Name"
            m = re.match(r'(\d+\.\d+) .+', station['callSign'])
            if m:
                station['channel'] = m.group(1)
                continue  # Done with this station

            # Check if we can use the callSign or name to figure out the channel number
            # This is done by first detecting the call sign, station type and subchannel
            # and looking the channel number up from the FCC facilities
            result = (self._detect_callsign(station['name']) or
                      self._detect_callsign(station['callSign']))
            if result:  # name or callSign match to a valid call sign
                (call_sign, subchannel) = result

                # Lookup the station from FCC facilities
                fcc_station = self._fcc_facilities.by_dma_and_call_sign(
                    self.dma, call_sign)
                if fcc_station:
                    station['channel'] = fcc_station["channel"] if fcc_station[
                        'analog'] else f'{fcc_station["channel"]}.{subchannel or 1}'
                    continue  # Done with this sation

            # Can't find the channel number, so we make something up - This shouldn't really happen
            self.log.warn(
                f"Channel (name: {station['name']}, callSign: {station['callSign']}) not found. Assigning {fake_channel}")
            station['channel'] = str(fake_channel)
            fake_channel += 1

        return stations

    def _get_locast_stations(self) -> list:
        """Get all the stations from locast for the current DMA

        Returns:
            list: Locast stations

        Raises:
            HTTPError: if the HTTP request to locast fails
        """
        self._validate_token()
        start_time = datetime.utcnow().strftime("%Y-%m-%dT00:00:00-00:00")
        r = requests.get(f'{STATIONS_URL}/{self.dma}?startTime={start_time}&hours={self.config.days * 24}', headers={
            'Content-Type': 'application/json',
            'authorization': 'Bearer ' + self.token})
        r.raise_for_status()

        return r.json()

    def _detect_callsign(self, input: str) -> Tuple[str, str]:
        """Detect a call sign and possibly subchannel from a string

        Args:
            input (str): String to find a callsign in

        Returns:
            Tuple[str, str]: tuple with callsign and subchannel
            None: in case no callsign was found
        """
        m = re.match(r'^([KW][A-Z]{2,3})[A-Z]{0,2}(\d{0,2})$', input)
        if m:
            (call_sign, subchannel) = m.groups()
            return (call_sign, subchannel)
        return None

    def get_station_stream_uri(self, station_id: str) -> str:
        """Get the steam URL for a station. This always returns the URL with the highest resolution.

        Args:
            station_id (str): Locast station ID

        Returns:
            str: URL with the stream

        Raises:
            HTTPError: in case the request to locast.org fails
        """
        self._validate_token()
        url = f'{WATCH_URL}/{station_id}/{self.location["latitude"]}/{self.location["longitude"]}'

        r = requests.get(
            url,
            headers={
                'Content-Type': 'application/json',
                'authorization': f'Bearer {self.token}',
                'User-Agent': "curl/7.64.1"})
        r.raise_for_status()

        # Stream URLs can either be just URLs or m3u8 playlists with muliple resolutions
        stream_url = r.json()["streamUrl"]
        m3u8_data = m3u8.load(stream_url)
        if len(m3u8_data.playlists) == 0:
            return stream_url

        # Sort the playlists by resolution and take the top
        best_resolution = sorted(m3u8_data.playlists,
                                 key=lambda pl: pl.stream_info.resolution).pop()

        return best_resolution.absolute_uri
