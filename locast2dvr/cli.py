#!/usr/bin/env python3
import distutils.spawn
import logging
import sys
import threading

import click
import click_config_file
from click_option_group import MutuallyExclusiveOptionGroup, optgroup

from .ssdp import SSDPServer
from .utils import Configuration


@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.option('-U', '--username', required=True, type=click.STRING, help='Locast username', metavar='USERNAME')
@click.password_option('-P', '--password', required=True, help='Locast password', metavar='PASSWORD')
@click.option('-u', '--uid', type=click.STRING, help='Unique identifier of the device', metavar='UID', required=True)
@click.option('-b', '--bind', 'bind_address', default="127.0.0.1", show_default=True, help='Bind IP address', metavar='IP_ADDR', )
@click.option('-p', '--port', default=6077, show_default=True, help='Bind tcp port', metavar='PORT')
@click.option('-f', '--ffmpeg', help='Path to ffmpeg binary', metavar='PATH', default='ffmpeg', show_default=True)
@click.option('-v', '--verbose', count=True, help='Enable verbose logging')
@optgroup.group('\nLocation overrides', cls=MutuallyExclusiveOptionGroup)
@optgroup.option('--override-location', type=str, help='Override location', metavar="LAT,LONG")
@optgroup.option('--override-zipcodes', type=str, help='Override zipcodes', metavar='ZIP')
@optgroup.group('\nDebug options')
@optgroup.option('--bytes-per-read', type=int, default=1152000, show_default=True, help='Bytes per read', metavar='BYTES')
@optgroup.option('--tuner-count', default=3, show_default=True, help='Tuner count', metavar='COUNT')
@optgroup.option('--device-model', default='HDHR3-US', show_default=True, help='HDHomerun device model reported to clients')
@optgroup.option('--device-firmware', default='hdhomerun3_atsc', show_default=True, help='Model firmware reported to clients')
@optgroup.option('--device-version', default='1.2.3456', show_default=True, help='Model version reported to clients')
@click_config_file.configuration_option()
def cli(*args, **config):
    """Locast to DVR (like Plex or Emby) integration server"""
    c = Configuration(config)

    log_level = logging.DEBUG if c.verbose >= 2 else logging.INFO

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p', level=log_level)

    # Test if we have a valid ffmpeg executable
    c.ffmpeg = distutils.spawn.find_executable(c.ffmpeg or 'ffmpeg')
    if c.ffmpeg:
        logging.info(f'Using ffmpeg at {c.ffmpeg}')
    else:
        logging.error('ffmpeg not found')
        sys.exit(1)

    from .dvr import DVR
    from .locast import Geo, Service

    # Login to locast.org. We only have to do this once
    try:
        Service.login(c.username, c.password)
    except Exception as err:
        logging.error(err)
        sys.exit(1)

    # Create Geo objects based on configuration.
    if c.override_location:
        (lat, lon) = c.override_location.split(",")
        geos = [Geo(latlon={
            'latitude': lat,
            'longitude': lon
        })]
    elif c.override_zipcodes:
        geos = [Geo(z.strip()) for z in c.override_zipcodes.split(',')]
    else:
        geos = [Geo()]  # No location information means current location

    ssdp = SSDPServer()
    threading.Thread(target=ssdp.run).start()

    # Start as many DVR instances as there are geos.
    for i, geo in enumerate(geos):
        port = c.port + i
        uid = f"{c.uid}_{i}"
        DVR(geo, port, uid, c, ssdp).start()
