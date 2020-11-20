#!/usr/bin/env python3
import enum
import click
import click_config_file
from click_option_group import optgroup, MutuallyExclusiveOptionGroup
import locast
import logging
import threading
import sys
import os

from utils import Configuration
from plex import PlexHTTPServer
from ssdp import SSDPServer
import waitress
from paste.translogger import TransLogger

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.DEBUG)


@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.option('-U', '--username', required=True, type=click.STRING, help='Locast username', metavar='USERNAME')
@click.password_option('-P', '--password', required=True, help='Locast password', metavar='PASSWORD')
@click.option('-u', '--uuid', type=click.STRING, help='UUID', metavar='UUID', required=True)
@click.option('-b', '--bind', 'bind_address', default="0.0.0.0", show_default=True, help='Bind IP address', metavar='IP_ADDR', )
@click.option('-p', '--port', default=6077, show_default=True, help='Bind tcp port', metavar='PORT')
@click.option('-v', '--verbose', is_flag=True, help='Enable verbse logging')
@optgroup.group('Location overrides', cls=MutuallyExclusiveOptionGroup)
@optgroup.option('--override-location', type=str, help='Override location', metavar="LAT,LONG")
@optgroup.option('--override-zipcode', type=str, help='Override zipcode', metavar='ZIP')
@optgroup.option('--regions_file', type=click.File(), help="Regions file", metavar='FILE')
@click.option('--bytes-per-read', type=int, default=1152000, show_default=True, help='Bytes per read', metavar='BYTES')
@click.option('--tuner-count', default=3, show_default=True, help='Tuner count', metavar='COUNT')
@click.option('--device-model', default='HDHR3-US', show_default=True, help='Model name reported to Plex')
@click.option('--device-firmware', default='hdhomerun3_atsc', show_default=True, help='Model firmware reported to Plex')
@click.option('--device-version', default='hdhomerun3_atsc', show_default=True, help='Model version reported to Plex')
@click_config_file.configuration_option()
def cli(*args, **config):
    c = Configuration(config)

    if c.override_location:
        (lat, lon) = c.override_location.split(",")
        geos = [locast.Geo(latlon={
            'latitude': lat,
            'longitude': lon
        })]
    elif c.override_zipcode:
        geos = [locast.Geo(c.zipcode)]
    elif c.regions_file:
        geos = [locast.Geo(zipcode=z.rstrip())
                for z in c.regions_file.readlines() if not z.startswith("#")]
    else:
        geos = [locast.Geo()]

    # Login to locast
    if not locast.Service.login(c.username, c.password):
        sys.exit(1)
    else:
        logging.info("Locast login successful")

    for i, geo in enumerate(geos):
        locast_service = locast.Service(geo)
        if not locast_service.valid_user():
            os._exit(1)

        port = c.port + i
        uuid = f"{c.uuid}_{i}"

        # Start Flask app on separate thread
        app = PlexHTTPServer(c, uuid, locast_service)

        if c.verbose:
            app = TransLogger(app)

        threading.Thread(target=waitress.serve,
                         args=(app,),
                         kwargs={
                             'host': c.bind_address,
                             'port': port}).start()

        ssdp = SSDPServer()
        ssdp.register('local', f'uuid:{uuid}::upnp:rootdevice',
                      'upnp:rootdevice', f'http://{c.bind_address}:{port}/device.xml')
        threading.Thread(target=ssdp.run).start()
