import logging
import os

from .http import start_http
from .locast import Geo, LocastService
from .ssdp import SSDPServer
from .utils import Configuration, LoggingHandler


class Tuner(LoggingHandler):
    def __init__(self, geo: Geo, uid: str, config: Configuration, ssdp: SSDPServer, port: int = None):
        """Representation of a Tuner. This class ties a Flask app to a locast.Service
           and starts an HTTP server on the given port. It also registers the Tuner on
           using SSDP to make it easy for PMS to find the device.

        Args:
            geo (locast.Geo): Geo object containing what content this Tuner is representing
            uid (str): Unique identifier of this Tuner
            config (Configuration): global application configuration
            ssdp (SSDPServer): SSDP server instance to register at
            port (int, optional): TCP port the Tuner listens to. Will not listen on TCP when port == 0
        """
        super().__init__()
        self.geo = geo
        self.config = config
        self.port = port
        self.uid = uid
        self.ssdp = ssdp
        self.locast_service = LocastService(self.config, self.geo)

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
    def timezone(self):
        return self.locast_service.timezone

    @property
    def url(self):
        if self.port:
            return f"http://{self.config.bind_address}:{self.port}"

    def start(self):
        """Start the Tuner 'device'"""
        try:
            self.locast_service.start()
            if self.port:
                start_http(self.config, self.port, self.uid,
                           self.locast_service, self.ssdp, self.log)
                self.log.info(f"{self} HTTP interface started")
            self.log.info(f"{self} started")
        except Exception as e:
            logging.exception(e)
            os._exit(1)

    def __repr__(self) -> str:
        if self.port:
            return f"Tuner(city: {self.city}, zip: {self.zipcode}, dma: {self.dma}, uid: {self.uid}, url: {self.url})"
        else:
            return f"Tuner(city: {self.city}, zip: {self.zipcode}, dma: {self.dma}, uid: {self.uid})"
