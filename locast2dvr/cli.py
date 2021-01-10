import locast2dvr

import click
import click_config_file
from click_option_group import MutuallyExclusiveOptionGroup, optgroup

from .utils import Configuration
from .main import Main


@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True
))
@click.option('-U', '--username', required=True, type=click.STRING, help='Locast username', metavar='USERNAME')
@click.password_option('-P', '--password', required=True, help='Locast password', metavar='PASSWORD')
@click.option('-u', '--uid', type=click.STRING, help='Unique identifier of the device', metavar='UID', default="LOCAST2DVR", show_default=True)
@click.option('-b', '--bind-address', default="127.0.0.1", show_default=True, help='Bind IP address', metavar='IP_ADDR', )
@click.option('-p', '--port', default=6077, show_default=True, help='Bind TCP port', metavar='PORT')
@click.option('-f', '--ffmpeg', help='Path to ffmpeg binary', metavar='PATH', default='ffmpeg', show_default=True)
@click.option('-v', '--verbose', count=True, help='Enable verbose logging')
@optgroup.group('\nMultiplexing')
@optgroup.option('-m', '--multiplex', is_flag=True, help='Multiplex devices')
@optgroup.option('-M', '--multiplex-debug', is_flag=True, help='Multiplex devices AND start individual instances (multiplexer is started on the last port + 1)')
@optgroup.group('\nLocation overrides', cls=MutuallyExclusiveOptionGroup)
@optgroup.option('-ol', '--override-location', type=str, help='Override location', metavar="LAT,LONG")
@optgroup.option('-oz', '--override-zipcodes', type=str, help='Override zipcodes', metavar='ZIP')
@optgroup.group('\nDebug options')
@optgroup.option('--bytes-per-read', type=int, default=1152000, show_default=True, help='Bytes per read', metavar='BYTES')
@optgroup.option('--tuner-count', default=3, show_default=True, help='Tuner count', metavar='COUNT')
@optgroup.option('--device-model', default='HDHR3-US', show_default=True, help='HDHomerun device model reported to clients')
@optgroup.option('--device-firmware', default='hdhomerun3_atsc', show_default=True, help='Model firmware reported to clients')
@optgroup.option('--device-version', default='1.2.3456', show_default=True, help='Model version reported to clients')
@optgroup.option('--cache-stations', default=True, is_flag=True, show_default=True, help='Cache station data')
@optgroup.option('--cache-timeout', default=3600, show_default=True, help='Time to cache station data in seconds')
@optgroup.group('\nMisc options')
@optgroup.option('-d', '--days', default=8, show_default=True, help='Amount of days to get EPG data for', metavar='DAYS')
@optgroup.option('-r', '--remap', is_flag=True, help='Remap channel numbers when multiplexing based on DVR index')
@click_config_file.configuration_option()
def cli(*args, **config):
    """Locast to DVR (like Plex or Emby) integration server"""
    config = Configuration(config)
    Main(config).start()
