import distutils.spawn
import sys

from tabulate import tabulate

from .dvr import DVR, Multiplexer
from .locast import Geo, LocastService
from .ssdp import SSDPServer
from .utils import Configuration, LoggingHandler


class Main(LoggingHandler):
    def __init__(self, config: Configuration) -> None:
        super().__init__()
        self.config = config
        self.login()
        self.ssdp = SSDPServer()
        self._init_geos()
        self._init_multiplexer()
        self._init_dvrs()

    def _init_geos(self):
        # Create Geo objects based on configuration.
        if self.config.override_location:
            (lat, lon) = self.config.override_location.split(",")
            self.geos = [Geo(latlon={
                'latitude': lat,
                'longitude': lon
            })]
        elif self.config.override_zipcodes:
            self.geos = [Geo(z.strip())
                         for z in self.config.override_zipcodes.split(',')]
        else:
            # No location information means current location
            self.geos = [Geo()]

    def _init_multiplexer(self):
        if self.config.multiplex and self.config.multiplex_debug:
            self.multiplexer = Multiplexer(
                self.config.port + len(self.geos), self.config, self.ssdp)
        elif self.config.multiplex:
            self.multiplexer = Multiplexer(
                self.config.port, self.config, self.ssdp)

    def _init_dvrs(self):
        dvrs = []
        for i, geo in enumerate(self.geos):
            dvrs.append(DVR(geo, self._uid(i), self.config,
                            self.ssdp, port=self._port(i)))
        self.dvrs = dvrs

    def _port(self, i):
        if (self.config.multiplex and self.config.multiplex_debug) or not self.config.multiplex:
            return self.config.port + i

    def _uid(self, i):
        return f"{self.config.uid}_{i}"

    def start(self):
        self.check_ffmpeg()
        self.ssdp.start()

        # Start all DVRs
        [dvr.start() for dvr in self.dvrs]

        if self.multiplexer:
            self.multiplexer.register(self.dvrs)
            self.multiplexer.start()

        self.report()

    def report(self):
        self.log.info("DVRs:")
        header = ["City", "Zipcode", "DMA", "UID", "URL"]
        dvrs = [[d.city, d.zipcode, d.dma, d.uid, d.url or "(not listening)"]
                for d in self.dvrs]
        for l in tabulate(dvrs, header).split("\n"):
            self.log.info(f"  {l}")

        if self.multiplexer:
            self.log.info("")
            self.log.info("Multiplexer:")
            header = ["UID", "URL"]
            m = [[self.multiplexer.uid, self.multiplexer.url]]
            for l in tabulate(m, header).split("\n"):
                self.log.info(f"  {l}")

    def check_ffmpeg(self):
        # Test if we have a valid ffmpeg executable
        self.config.ffmpeg = distutils.spawn.find_executable(
            self.config.ffmpeg or 'ffmpeg')
        if self.config.ffmpeg:
            self.log.info(f'Using ffmpeg at {self.config.ffmpeg}')
        else:
            self.log.warn('ffmpeg not found! Only use as a m3u tuner!')

    def login(self):
        # Login to locast.org. We only have to do this once.
        try:
            LocastService.login(self.config.username, self.config.password)
        except Exception as err:
            self.log.error(err)
            sys.exit(1)
