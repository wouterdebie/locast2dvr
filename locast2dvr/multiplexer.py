from locast2dvr.tuner import Tuner, start_http
from locast2dvr.ssdp.server import SSDPServer
from locast2dvr.utils import Configuration, LoggingHandler


class Multiplexer(LoggingHandler):
    def __init__(self, config: Configuration,  port: int, ssdp: SSDPServer):
        """Object that behaves like a `locast.Service`, but multiplexes multiple Tuners

        Args:
            port (int): TCP port to bind to
            config (Configuration): global configuration object
        """
        super().__init__()
        self.port = port
        self.config = config
        self.tuners = []
        self.city = "Multiplexer"
        self.uid = config.uid
        self.ssdp = ssdp
        self.url = f"http://{self.config.bind_address}:{self.port}"

    def start(self):
        """Start the multiplexer. This will start a Flask app.
        """

        start_http(self.config, self.port, self.uid,
                   self, self.ssdp, self.log)
        if self.config.remap:
            self.log.warn("Will remap duplicate channels!")

        self.log.info(
            f"Started at {self.url}")

    def register(self, tuners: Tuner):
        """Register Tuners to multiplexer

        Args:
            tuners ([Tuner]): List of Tuners
        """
        for tuner in tuners:
            self.log.info(f"Registering {tuner}")
            self.tuners.append(tuner)

    def get_stations(self) -> list:
        """Get all stations for all registered Tuners

        Returns:
            list: A list with all station information
        """

        self.station_service_mapping = {}
        stations = []

        for i, d in enumerate(self.tuners):
            for station in d.locast_service.get_stations():
                stations.append(station)

                if self.config.remap:
                    (station['channel_remapped'], station['callSign_remapped']) = _remap(
                        station, i)

                self.station_service_mapping[str(
                    station['id'])] = d.locast_service

        self.log.info(
            f"Got {len(stations)} stations from {len(self.tuners)} Tuners")

        return stations

    def get_station_stream_uri(self, station_id: str) -> str:
        """Return the stream URL for a specific station_id

        Args:
            station_id (str): Station ID

        Returns:
            str: URL
        """
        self.get_stations()
        return self.station_service_mapping[station_id].get_station_stream_uri(station_id)


def _remap(station: dict, i: int):
    """Remaps a channel number to one based on the Tuner index
    """
    if station['channel'].isdigit():
        new_channel = str(int(station['channel']) + 100 * i)
    else:
        new_channel = str(float(station['channel']) + 100 * i)

    return (new_channel, station['callSign'].replace(station['channel'], new_channel))
