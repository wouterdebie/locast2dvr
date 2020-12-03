import logging
import os
import threading

import waitress
from .http_interface import FlaskApp
from .locast import Geo, Service
from .ssdp import SSDPServer
from .utils import Configuration


class DVR:
    def __init__(self, geo: Geo, port: int, uid: str, config: Configuration, ssdp: SSDPServer):
        """Representation of a DVR. This class ties a Flask app to a locast.Service
           and starts an HTTP server on the given port. It also registers the DVR on
           using SSDP to make it easy for PMS to find the device.

        Args:
            geo (locast.Geo): Geo object containing what content this DVR is representing
            port (int): TCP port the DVR listens to. Will not listen on TCP when port == 0
            uid (str): Unique identifier of this DVR
            config (Configuration): global application configuration
            ssdp (SSDPServer): SSDP server instance to register at
            http (bool, optional): Start an HTTP server [defaults to True]
        """
        self.geo = geo
        self.config = config
        self.port = port
        self.uid = uid
        self.ssdp = ssdp

    def start(self):
        """Start the DVR 'device'
        """
        try:
            self.locast_service = Service(self.geo)
        except Exception as err:
            logging.error(err)
            os._exit(1)

        # Create a Flask app that handles the interaction with PMS/Emby if we need to. Here
        # we tie the locast.Service to the Flask app.
        if self.port > 0:
            logging.info(
                f"Starting DVR for {self.locast_service.city} at http://{self.config.bind_address}:{self.port}")
            start_http(self.config, self.port, self.uid,
                       self.locast_service, self.ssdp)


def start_http(config: Configuration, port: int, uid: str, locast_service: Service, ssdp: SSDPServer):
    """Start the Flask app and serve it

    Args:
        config (Configuration): Global configuration object
        port (int): TCP port to listen to
        uid (str): uid to announce on SSDP
        locast_service (Service): Locast service bound to the Flask app
        ssdp (SSDPServer): SSDP server to announce on
    """

    # Create a FlaskApp and tie it to the locast_service
    app = FlaskApp(config, port, uid, locast_service)

    # Insert logging middle ware if we want verbose access logging
    if config.verbose > 0:
        from paste.translogger import TransLogger
        format = (f'{config.bind_address}:{port} %(REMOTE_ADDR)s - %(REMOTE_USER)s '
                  '"%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" '
                  '%(status)s %(bytes)s "%(HTTP_REFERER)s" "%(HTTP_USER_AGENT)s"')
        app = TransLogger(
            app, logger=logging.getLogger(), format=format)

    # Start the Flask app on a separate thread
    threading.Thread(target=waitress.serve, args=(app,),
                     kwargs={'host': config.bind_address,
                             'port': port,
                             '_quiet': True}).start()

    # Register our Flask app and start an SSDPServer for this specific instance
    # on a separate thread
    ssdp.register('local', f'uuid:{uid}::upnp:rootdevice',
                  'upnp:rootdevice', f'http://{config.bind_address}:{port}/device.xml')


class Multiplexer:
    def __init__(self, port: int, config: Configuration, ssdp: SSDPServer):
        """Object that behaves like a `locast.Service`, but multiplexes multiple DVRs

        Args:
            port (int): TCP port to bind to
            config (Configuration): global configuration object
        """
        self.port = port
        self.config = config
        self.dvrs = []
        self.city = "Multiplexer"
        self.uid = f"{config.uid}_MULTI"
        self.ssdp = ssdp

    def start(self):
        """Start the multiplexer. This will start a Flask app.
        """
        logging.info(
            f"Starting Multiplexer at http://{self.config.bind_address}:{self.port}")
        start_http(self.config, self.port, self.uid, self, self.ssdp)

    def register(self, dvr: DVR):
        """Register a DVR to multiplex

        Args:
            dvr (DVR): a DVR
        """
        logging.info(f"Registering {dvr} with Mutiplexer")
        self.dvrs.append(dvr)

    def get_stations(self) -> list:
        """Get all stations for all registered DVRs

        Returns:
            list: A list with all station information
        """
        logging.info(f"Multiplexer: getting all station")
        self.station_service_mapping = {}
        stations = []

        for d in self.dvrs:
            for station in d.locast_service.get_stations():
                stations.append(station)
                self.station_service_mapping[str(
                    station['id'])] = d.locast_service

        logging.info(f"Multiplexer: {len(stations)} individual stations")

        return stations

    def get_station_stream_uri(self, station_id: str) -> str:
        """Return the stream URL for a specific station_id

        Args:
            station_id (str): Station ID

        Returns:
            str: URL
        """
        return self.station_service_mapping[station_id].get_station_stream_uri(station_id)
