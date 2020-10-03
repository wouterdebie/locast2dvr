#!/usr/bin/env python3
# import locast4plex
import click
import click_config_file
import uuid
import locast
import logging
import threading

from utils import Configuration
from plex import PlexHTTPServer
from ssdp import SSDPServer

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.DEBUG)


def generate_uuid():
    return str(uuid.uuid4())


@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.option('-U', '--username', required=True, type=click.STRING, help='Locast username', metavar='USERNAME')
@click.password_option('-P', '--password', required=True, help='Locast password', metavar='PASSWORD')
@click.option('-b', '--bind', 'bind_address', default="0.0.0.0", show_default=True, help='Bind IP address', metavar='IP_ADDR', )
@click.option('-p', '--port', default=6077, show_default=True, help='Bind tcp port', metavar='PORT')
# TODO: make lat and long dependent
@click.option('--override-location', type=str, help='Override location', metavar="LAT,LONG")
@click.option('--override-zipcode', 'zipcode', type=str, help='Override zipcode', metavar='ZIP')
@click.option('--bytes-per-read', type=int, default=1152000, show_default=True, help='Bytes per read', metavar='BYTES')
@click.option('--tuner-count', default=3, show_default=True, help='Tuner count', metavar='COUNT')
@click.option('-u', '--uuid', type=click.STRING, help='UUID', metavar='UUID')
@click.option('--device-model', default='HDHR3-US', show_default=True, help='Model name reported to Plex')
@click.option('--device-firmware', default='hdhomerun3_atsc', show_default=True, help='Model firmware reported to Plex')
@click.option('--device-version', default='hdhomerun3_atsc', show_default=True, help='Model version reported to Plex')
@click_config_file.configuration_option()
def cli(*args, **config):
    c = Configuration(config)
    if not c.uuid:
        c.uuid = generate_uuid()

    if c.override_location:
        (lat, lon) = c.override_location.split(",")
        c.latlon = {
            'latitude': lat,
            'longitude': lon
        }
    else:
        c.latlon = None

    locast_service = locast.Service(
        c.username, c.password,
        c.latlon, c.zipcode
    )

    if not (locast_service.login() and locast_service.valid_user()):
        logging.error("Error logging in to Locast")
    logging.info("Locast login successful")

    plex_http_server = PlexHTTPServer(c, locast_service)
    # Start Flask app on separate thread
    threading.Thread(target=plex_http_server.run,
                     kwargs={
                         'host': c.bind_address,
                         'port': c.port, 'passthrough_errors': True}).start()

    ssdp = SSDPServer()
    ssdp.register('local', f'uuid:{c.uuid}::upnp:rootdevice',
                  'upnp:rootdevice', f'http://{c.bind_address}:{c.port}/device.xml')
    threading.Thread(target=ssdp.run)

    print("aap")
