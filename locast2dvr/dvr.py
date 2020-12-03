import logging
import os
import threading

import waitress
from .http_interface import FlaskApp
from .locast import Geo, Service
from .ssdp import SSDPServer
from .utils import Configuration


class DVR:
    def __init__(self, geo: Geo, port: int, uid: str, config: Configuration, ssdp: SSDPServer, http=True):
        """Representation of a DVR. This class ties a Flask app to a locast.Service
           and starts an HTTP server on the given port. It also registers the DVR on
           using SSDP to make it easy for PMS to find the device.

        Args:
            geo (locast.Geo): Geo object containing what content this DVR is representing
            port (int): TCP port the DVR listens to
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
        self.http = http

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
        if self.http:
            app = FlaskApp(self.config, self.port,
                           self.uid, self.locast_service)

            # Insert logging middle ware if we want verbose access logging
            if self.config.verbose > 0:
                from paste.translogger import TransLogger
                app = TransLogger(app)

            # Start the Flask app on a separate thread
            threading.Thread(target=waitress.serve, args=(app,),
                             kwargs={'host': self.config.bind_address,
                                     'port': self.port}).start()

            # Register our Flask app and start an SSDPServer for this specific instance
            # on a separate thread
            self.ssdp.register('local', f'uuid:{self.uid}::upnp:rootdevice',
                               'upnp:rootdevice', f'http://{self.config.bind_address}:{self.port}/device.xml')
