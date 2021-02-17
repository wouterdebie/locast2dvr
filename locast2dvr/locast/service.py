import logging
import re
import threading
from datetime import datetime
from typing import Optional, Tuple
import uuid

import m3u8
import requests
from locast2dvr.utils import Configuration, LoggingHandler
from requests.exceptions import HTTPError
from timezonefinder import TimezoneFinder

from .fcc import Facilities


LOGIN_URL = "https://api.locastnet.org/api/user/login"
USER_URL = "https://api.locastnet.org/api/user/me"
DMA_URL = "https://api.locastnet.org/api/watch/dma"
IP_URL = 'https://api.locastnet.org/api/watch/dma/ip'
STATIONS_URL = 'https://api.locastnet.org/api/watch/epg'
WATCH_URL = 'https://api.locastnet.org/api/watch/station'

TOKEN_LIFETIME = 3600


class Geo:
    def __init__(self, zipcode: Optional[str] = None, coords: Optional[dict] = None):
        """Object containing location information

        Args:
            zipcode (Optional[str], optional): Zipcode. Defaults to None.
            coords (Optional[dict], optional): Dict containing latitude and longitude. Defaults to None.
        """
        self.zipcode = zipcode
        self.coords = coords

    def __repr__(self) -> str:
        if self.zipcode:
            return f"Geo(zipcode: {self.zipcode})"
        elif self.coords:
            return f"Geo(coords: {self.coords})"
        else:
            return f"Geo(None)"

    def __eq__(self, other):
        return self.coords == other.coords and \
            self.zipcode == other.zipcode


class LocationInvalidError(Exception):
    pass


class UserInvalidError(Exception):
    pass


class LocastService(LoggingHandler):
    _logged_in = False
    log = logging.getLogger("LocastService")  # Necessary for class methods
    _login_lock = threading.Lock()

    def __init__(self, config: Configuration, geo: Geo):
        """Locast service interface based on a specific location

        Args:
            geo (Geo): Location information
            config (Configuration): Global configuration
        """
        super().__init__()
        self.coords = geo.coords
        self.zipcode = geo.zipcode

        self.config = config

        self.location = None
        self.active = False
        self.dma = None
        self.city = None
        self.timezone = None

        self._channel_lock = threading.Lock()

    def start(self):
        self.uid = "foo"
        self._fcc_facilities = Facilities.instance()
        self._load_location_data()
        self.uid = str(uuid.uuid5(uuid.UUID(self.config.uid), str(self.dma)))
        # Start cache updater timer if necessary, otherwise, just preload
        # stations once
        if self.config.cache_stations:
            self._update_cache()

    @classmethod
    def login(cls, username: str = None, password: str = None):
        """Log in to locast.org

        This is a class method, so we only have to login once.

        Args:
            username (str): Username
            password (str): Password

        """
        with cls._login_lock:
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
            except HTTPError as err:
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
        r = cls.get(USER_URL, authenticated=True)

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
        with self._login_lock:
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
           method is used to determine the location (coords, zip or IP)
        """
        if self.coords:
            self._set_attrs_from_geo(
                f'{DMA_URL}/{self.coords["latitude"]}/{self.coords["longitude"]}')
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
            r = self.get(url)
        except HTTPError as err:
            raise LocationInvalidError(err)

        if r.status_code == 204:
            raise LocationInvalidError(f"Geo not found for {url}")

        geo = r.json()
        self.location = {
            'latitude': geo['latitude'], 'longitude': geo['longitude']}
        self.dma = str(geo['DMA'])
        self.active = geo['active']
        self.city = geo['name']
        self.timezone = TimezoneFinder().timezone_at(
            lng=self.location['longitude'], lat=self.location['latitude'])

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
            with self._channel_lock:
                return self._stations
        else:
            return self._get_stations()

    def _update_cache(self):
        """Update the station cache

        After this method is done fetching station information, it will schedule itself to run again after
        `self.config.cache_timeout` seconds.add()
        """
        stations = self._get_stations()
        with self._channel_lock:
            self._stations = stations
        timer = threading.Timer(self.config.cache_timeout, self._update_cache)
        timer.setDaemon(True)
        timer.start()

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
            station['timezone'] = self.timezone
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
            self.log.warning(
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
        url = f'{STATIONS_URL}/{self.dma}?startTime={start_time}&hours={self.config.days * 24}'
        r = self.get(url, authenticated=True)

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
        r = self.get(url, authenticated=True)

        # Stream URLs can either be just URLs or m3u8 playlists with multiple resolutions
        stream_url = r.json()["streamUrl"]
        m3u8_data = m3u8.load(stream_url)
        if len(m3u8_data.playlists) == 0:
            return stream_url

        # Sort the playlists by resolution and take the top
        best_resolution = sorted(m3u8_data.playlists,
                                 key=lambda pl: pl.stream_info.resolution).pop()

        return best_resolution.absolute_uri

    @classmethod
    def get(cls, url: str, authenticated=False, extra_headers={}):
        """Utility method for making HTTP GET requests. Note that Locast.token needs
        to be set when authenticated=True.

        Args:
            url (str): URL to get
            authenticated (bool, optional): Use an authenticated request. Defaults to False.
            extra_headers (dict, optional): Optional additional heades. Defaults to {}.

        Returns:
            [type]: [description]
        """
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36"
        }

        headers.update(extra_headers)

        if authenticated:
            headers.update({'authorization': f'Bearer {cls.token}'})

        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r
