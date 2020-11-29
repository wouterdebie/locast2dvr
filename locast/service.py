import requests
import logging
import re
import m3u8
from datetime import datetime
from .fcc import Facilities
from typing import Optional, Tuple

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


class LocationInvalidError(Exception):
    pass


class UserInvalidError(Exception):
    pass


class Service:
    _logged_in = False
    _fcc_facilities = Facilities()

    def __init__(self, geo: Geo):
        """Locast service interface based on a specific location

        Args:
            geo (Geo): Location information
        """
        self.latlon = geo.latlon
        self.zipcode = geo.zipcode

        self.location = None
        self.active = False
        self.dma = None
        self.city = None

        self._load_location_data()

    @classmethod
    def login(cls, username: str, password: str) -> bool:
        """Log in to locast.org

        This is a class method, so we only have to login once.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            bool: True if successful, False otherwise

        """
        cls.username = username
        cls.password = password
        logging.info(f"Locast logging in with {cls.username}")
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

        logging.info("Locast login successful")

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
        logging.debug(user_info)

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
            logging.info("Token expired, logging in again...")
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

        logging.info(
            f'Location: {self.city}, dma: {self.dma}, zip: {self.zipcode}')

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
        logging.debug(geo)

    def get_stations(self) -> dict:
        """Get all station information and return in such a way that PMS can use it

        This is done by getting station information from locast.org and and where necessary
        complement channel numbers this with data from the FCC.

        Returns:
            dict: [description]
        """
        locast_stations = self._get_locast_stations()

        fake_channel = 1000
        for station in locast_stations:
            # See if station conforms to "X.Y Name"
            m = re.match(r'(\d+\.\d+) .+', station['callSign'])
            if m:
                station['channel'] = m.group(1)
                continue  # Done with this station

            # Check if we can use the callSign or name to figure out the channel number
            # This is done by first detecting the call sign, station type and subchannel
            # and looking the channel number up from the FCC facilities
            result = (self._detect_callsign(station['callSign']) or
                      self._detect_callsign(station['name']))
            if result:  # name or callSign match to a valid call sign
                (call_sign, subchannel) = result

                # Lookup the station from FCC facilities
                fcc_station = self._fcc_facilities.by_dma_and_call_sign(
                    self.dma, call_sign)
                if fcc_station:
                    station['channel'] = fcc_station["channel"] if fcc_station[
                        'analog'] else f'{fcc_station["channel"]}.{subchannel or 1}'
                    continue  # Done with this sation

            # Can't find the channel number, so we make something up
            station['channel'] = str(fake_channel)
            fake_channel += 1

        return locast_stations

    def _get_locast_stations(self) -> dict:
        """Get all the stations from locast for the current DMA

        Returns:
            dict: Locast stations

        Raises:
            HTTPError: if the HTTP request to locast fails
        """
        self._validate_token()

        r = requests.get(f'{STATIONS_URL}/{self.dma}', headers={
            'Content-Type': 'application/json',
            'authorization': 'Bearer ' + self.token})
        r.raise_for_status()

        return r.json()

    def _detect_callsign(self, input: str) -> Tuple[str, str]:
        print(input)
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
        """Get the steam URL for a station

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

        logging.info(f'Resolution: {best_resolution}')
        return best_resolution.absolute_uri
