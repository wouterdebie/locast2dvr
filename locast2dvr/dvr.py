import logging
import os
import threading

import waitress

from .http import HTTPInterface
from .locast import Geo, LocastService
from .ssdp import SSDPServer
from .utils import Configuration, LoggingHandler


class DVR(LoggingHandler):
    def __init__(self, geo: Geo, uid: str, config: Configuration, ssdp: SSDPServer, port: int = None):
        """Representation of a DVR. This class ties a Flask app to a locast.Service
           and starts an HTTP server on the given port. It also registers the DVR on
           using SSDP to make it easy for PMS to find the device.

        Args:
            geo (locast.Geo): Geo object containing what content this DVR is representing
            uid (str): Unique identifier of this DVR
            config (Configuration): global application configuration
            ssdp (SSDPServer): SSDP server instance to register at
            port (int, optional): TCP port the DVR listens to. Will not listen on TCP when port == 0
        """
        super().__init__()
        self.geo = geo
        self.config = config
        self.port = port
        self.uid = uid
        self.ssdp = ssdp
        try:
            self.locast_service = LocastService(self.geo, self.config)
            self.log.info(f"{self} created")

        except Exception as err:
            logging.error(err)
            os._exit(1)

    @property
    def city(self):
        return self.locast_service.city

    @property
    def zipcode(self):
        return self.locast_service.zipcode

    @property
    def dma(self):
        return self.locast_service.dma

    @property
    def url(self):
        if self.port:
            return f"http://{self.config.bind_address}:{self.port}"

    def start(self):
        """Start the DVR 'device'"""

        # Create a Flask app that handles the interaction with PMS/Emby if we need to. Here
        # we tie the locast.Service to the Flask app.
        if self.port:
            start_http(self.config, self.port, self.uid,
                       self.locast_service, self.ssdp)
            self.log.info(f"{self} HTTP interface started")

    def __repr__(self) -> str:
        if self.port:
            return f"DVR(city: {self.city}, zip: {self.zipcode}, dma: {self.dma}, uid: {self.uid}, url: {self.url})"
        else:
            return f"DVR(city: {self.city}, zip: {self.zipcode}, dma: {self.dma}, uid: {self.uid})"


def start_http(config: Configuration, port: int, uid: str, locast_service: LocastService, ssdp: SSDPServer):
    """Start the Flask app and serve it

    Args:
        config (Configuration): Global configuration object
        port (int): TCP port to listen to
        uid (str): uid to announce on SSDP
        locast_service (Service): Locast service bound to the Flask app
        ssdp (SSDPServer): SSDP server to announce on
    """

    # Create a FlaskApp and tie it to the locast_service
    app = HTTPInterface(config, port, uid, locast_service)

    # Insert logging middle ware if we want verbose access logging
    if config.verbose > 0:
        from paste.translogger import TransLogger
        format = (f'{config.bind_address}:{port} %(REMOTE_ADDR)s - %(REMOTE_USER)s '
                  '"%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" '
                  '%(status)s %(bytes)s "%(HTTP_REFERER)s" "%(HTTP_USER_AGENT)s"')
        app = TransLogger(
            app, logger=logging.getLogger("HTTPInterface"), format=format)

    # Start the Flask app on a separate thread
    threading.Thread(target=waitress.serve, args=(app,),
                     kwargs={'host': config.bind_address,
                             'port': port,
                             '_quiet': True}).start()

    # Register our Flask app and start an SSDPServer for this specific instance
    # on a separate thread
    ssdp.register('local', f'uuid:{uid}::upnp:rootdevice',
                  'upnp:rootdevice', f'http://{config.bind_address}:{port}/device.xml')


class Multiplexer(LoggingHandler):
    def __init__(self, port: int, config: Configuration, ssdp: SSDPServer):
        """Object that behaves like a `locast.Service`, but multiplexes multiple DVRs

        Args:
            port (int): TCP port to bind to
            config (Configuration): global configuration object
        """
        super().__init__()
        self.port = port
        self.config = config
        self.dvrs = []
        self.city = "Multiplexer"
        self.uid = f"{config.uid}_MULTI"
        self.ssdp = ssdp
        self.url = f"http://{self.config.bind_address}:{self.port}"

    def start(self):
        """Start the multiplexer. This will start a Flask app.
        """

        start_http(self.config, self.port, self.uid, self, self.ssdp)
        self.log.info(
            f"Started at {self.url}")

    def register(self, dvrs: DVR):
        """Register DVRs to multiplexer

        Args:
            dvrs ([DVR]): List of DVRs
        """
        for dvr in dvrs:
            self.log.info(f"Registering {dvr}")
            self.dvrs.append(dvr)

    def get_stations(self) -> list:
        """Get all stations for all registered DVRs

        Args:
            use_cache (bool, optional): Cache the stations for `cache_time` seconds. Defaults to True.
            cache_time (str, optional): Seconds before cache is evicted. Defaults to 3600.

        Returns:
            list: A list with all station information
        """
        self.log.info(
            f"Loading all stations..")
        self.station_service_mapping = {}
        stations = []

        for d in self.dvrs:
            for station in d.locast_service.get_stations():
                stations.append(station)
                self.station_service_mapping[str(
                    station['id'])] = d.locast_service

        self.log.info(
            f"Got {len(stations)} stations from {len(self.dvrs)} DVRs")

        return stations

    def get_station_stream_uri(self, station_id: str) -> str:
        """Return the stream URL for a specific station_id

        Args:
            station_id (str): Station ID

        Returns:
            str: URL
        """
        return self.station_service_mapping[station_id].get_station_stream_uri(station_id)
