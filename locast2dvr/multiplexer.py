import logging
import threading

import waitress

from .dvr import DVR
from .http_interface import FlaskApp
from .utils import Configuration


class Multiplexer:
    def __init__(self, port: int, config: Configuration):
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

    def start(self):
        """Start the multiplexer. This will start a Flask app.
        """
        logging.info(
            f"Starting Multiplexer at {self.config.bind_address}:{self.port}")
        # Create a Flask app that handles the interaction with PMS. Here
        # we tie the locast.Service to the Flask app
        app = FlaskApp(self.config, self.port, self.uid, self)

        # Insert logging middle ware if we want verbose access logging
        if self.config.verbose > 0:
            from paste.translogger import TransLogger
            app = TransLogger(app)

        # Start the Flask app on a separate thread
        threading.Thread(target=waitress.serve, args=(app,),
                         kwargs={'host': self.config.bind_address,
                                 'port': self.port}).start()

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
        self.station_mapping = {}
        stations = []

        for d in self.dvrs:
            for station in d.locast_service.get_stations():
                stations.append(station)

        logging.info(f"Multiplexer: {len(stations)} individual stations")

        return stations

    def get_station_stream_uri(self, station_id: str) -> str:
        """Return the stream URL for a specific station_id

        Args:
            station_id (str): Station ID

        Returns:
            str: URL
        """
        return self.station_mapping[station_id].get_station_stream_uri(station_id)
