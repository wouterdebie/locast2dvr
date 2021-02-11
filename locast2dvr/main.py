import distutils.spawn
import platform
import sys

from tabulate import tabulate

from locast2dvr import __version__ as locast_version

from .dvr import DVR
from .locast import Geo, LocastService
from .multiplexer import Multiplexer
from .ssdp import SSDPServer
from .utils import Configuration, LoggingHandler


class Main(LoggingHandler):
    def __init__(self, config: Configuration) -> None:
        super().__init__()
        LoggingHandler.init_logging(config)
        platform_description = f"{platform.python_implementation()} {platform.python_version()}, {platform.platform()}"
        self.log.info(
            f"locast2dvr {locast_version} running on {platform_description} starting")

        self.config = config
        self.geos: list[Geo] = []
        self.dvrs: list[DVR] = []
        self.multiplexer: Multiplexer = None
        self.ssdp: SSDPServer = None

    def start(self):
        self.ssdp = SSDPServer()

        self._login()
        self._init_geos()

        self._init_multiplexer()
        self._init_dvrs()
        self._check_ffmpeg()
        if self.config.ssdp:
            self.ssdp.start()

        # Start all DVRs
        for dvr in self.dvrs:
            dvr.start()

        if self.multiplexer:
            self.multiplexer.register(self.dvrs)
            self.multiplexer.start()

        self._report()

    def _init_geos(self):
        # Create Geo objects based on configuration.
        if self.config.override_location:
            (lat, lon) = self.config.override_location.split(",")
            self.geos = [Geo(coords={
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
                self.config, self.config.port + len(self.geos),  self.ssdp)
        elif self.config.multiplex:
            self.multiplexer = Multiplexer(
                self.config, self.config.port, self.ssdp)
        else:
            self.multiplexer = None

    def _init_dvrs(self):
        dvrs = []
        for i, geo in enumerate(self.geos):
            dvrs.append(DVR(geo, self._uid(i), self.config,
                            self.ssdp, port=self._port(i)))
        self.dvrs: list[DVR] = dvrs

    def _port(self, i: int):
        if (self.config.multiplex and self.config.multiplex_debug) or not self.config.multiplex:
            return self.config.port + i

    def _uid(self, i):
        return f"{self.config.uid}_{i}"

    def _report(self):
        self.log.info("DVRs:")
        header = ["City", "Zipcode", "DMA", "UID", "TZ", "URL"]
        dvrs = [[d.city, d.zipcode, d.dma, d.uid, d.timezone, d.url or "(not listening)"]
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

    def _check_ffmpeg(self):
        # Test if we have a valid ffmpeg executable
        if self.config.direct:
            self.log.info('Direct streaming.. not using ffmpeg')
        else:
            self.config.ffmpeg = distutils.spawn.find_executable(
                self.config.ffmpeg or 'ffmpeg')
            if self.config.ffmpeg:
                self.log.info(f'Using ffmpeg at {self.config.ffmpeg}')
            else:
                self.log.warn(
                    'ffmpeg not found! Falling back to direct streaming..')
                self.config.direct = True

    def _login(self):
        # Login to locast.org. We only have to do this once.
        try:
            LocastService.login(self.config.username, self.config.password)
        except Exception as err:
            self.log.error(err)
            sys.exit(1)
