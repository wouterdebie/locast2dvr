import logging
import os
import re
import subprocess
import threading
import traceback
from datetime import datetime, timedelta
from time import sleep
from typing import IO, OrderedDict

import m3u8
import pytz
import requests
import waitress
from flask import Flask, Response, jsonify, redirect, request
from flask.templating import render_template
from locast2dvr.locast import LocastService
from locast2dvr.ssdp import SSDPServer
from locast2dvr.utils import Configuration
from paste.translogger import TransLogger


def start_http(config: Configuration, port: int, uid: str, locast_service: LocastService,
               ssdp: SSDPServer, log: logging.Logger):
    """Start the Flask app and serve it

    Args:
        config (Configuration): Global configuration object
        port (int): TCP port to listen to
        uid (str): uid to announce on SSDP
        locast_service (Service): Locast service bound to the Flask app
        ssdp (SSDPServer): SSDP server to announce on
    """
    # Create a FlaskApp and tie it to the locast_service
    app = HTTPInterface(config, port, uid, locast_service)

    # Insert logging middle ware if we want verbose access logging
    if config.verbose > 0:
        logger = logging.getLogger("HTTPInterface")
        format = (f'{config.bind_address}:{port} %(REMOTE_ADDR)s - %(REMOTE_USER)s '
                  '"%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" '
                  '%(status)s %(bytes)s "%(HTTP_REFERER)s" "%(HTTP_USER_AGENT)s"')
        app = TransLogger(
            app, logger=logger, format=format)

    def _excepthook(args):
        if args.exc_type == OSError:
            log.error(args.exc_value)
            log.error(traceback.print_tb(args.exc_traceback))
            os._exit(-1)
        else:
            log.error('Unhandled error: ', args)

    threading.excepthook = _excepthook

    # Start the Flask app on a separate thread
    threading.Thread(target=waitress.serve, args=(app,),
                     kwargs={'host': config.bind_address,
                             'port': port,
                             'threads': config.http_threads,
                             '_quiet': True}).start()

    # Register our Flask app and start an SSDPServer for this specific instance
    # on a separate thread
    if config.ssdp:
        ssdp.register('local', f'uuid:{uid}::upnp:rootdevice',
                      'upnp:rootdevice', f'http://{config.bind_address}:{port}/device.xml')


def HTTPInterface(config: Configuration, port: int, uid: str, locast_service: LocastService, station_scan=False) -> Flask:
    """Create a Flask app that is used to interface with PMS and acts like a DVR device

    Args:
        config (utils.Configuration): locast2dvr configuration object
        port (int): TCP port this app will be bound to
        uid (str): Unique ID for this app. PMS uses this to identify DVRs
        locast_service (locast.Service): Locast service object
        station_scan (bool): used for testing only (default: False)

    Returns:
        Flask: A Flask app that can interface with PMS and mimics a DVR device
    """
    log = logging.getLogger("HTTPInterface")
    app = Flask(__name__)

    host_and_port = f'{config.bind_address}:{port}'

    @app.route('/', methods=['GET'])
    @app.route('/device.xml', methods=['GET'])
    def device_xml() -> Response:
        """Render an XML when /device.xml is called.

        Returns:
            Response: XML response
        """
        xml = render_template('device.xml',
                              device_model=config.device_model,
                              device_version=config.device_version,
                              friendly_name=locast_service.city,
                              uid=uid,
                              host_and_port=host_and_port)
        return Response(xml, mimetype='text/xml')

    @app.route('/discover.json', methods=['GET'])
    def discover_json() -> Response:
        """Return data about the device in JSON

        Returns:
            Response: JSON response containing device information
        """
        data = {
            "FriendlyName": locast_service.city,
            "Manufacturer": "locast2dvr",
            "ModelNumber": config.device_model,
            "FirmwareName": config.device_firmware,
            "TunerCount": config.tuner_count,
            "FirmwareVersion": config.device_version,
            "DeviceID": uid,
            "DeviceAuth": "locast2dvr",
            "BaseURL": f"http://{host_and_port}",
            "LineupURL": f"http://{host_and_port}/lineup.json"
        }
        return jsonify(data)

    @app.route('/lineup_status.json', methods=['GET'])
    def lineup_status_json() -> Response:
        """Provide a (somewhat fake) status about the scanning process

        Returns:
            Response: JSON containing scanning information
        """
        if station_scan:
            lineup_status = {
                "ScanInProgress": True,
                "Progress": 50,
                "Found": 5
            }
        else:
            lineup_status = {
                "ScanInProgress": False,
                "ScanPossible": True,
                "Source": "Antenna",
                "SourceList": ["Antenna"]
            }
        return jsonify(lineup_status)

    @app.route('/lineup.m3u', methods=['GET'])
    @app.route('/tuner.m3u', methods=['GET'])
    def m3u() -> Response:
        """Returns all stations in m3u format

        Returns:
            Response: m3u in text/plain
        """
        m3uText = "#EXTM3U\n"
        for station in locast_service.get_stations():
            callsign = name_only(station.get("callSign_remapped") or station.get(
                "callSign") or station.get("name"))
            city = station["city"]
            logo = station.get("logoUrl") or station.get("logo226Url")
            channel = station.get("channel_remapped") or station["channel"]
            networks = "Network" if callsign in [
                'ABC', 'CBS', 'NBC', 'FOX', 'CW', 'PBS'] else ""
            groups = ";".join(filter(None, [city, networks]))
            url = f"http://{host_and_port}/watch/{station['id']}.m3u"

            tvg_name = f"{callsign} ({city})" if config.multiplex else callsign

            m3uText += f'#EXTINF:-1 tvg-id="channel.{station["id"]}" tvg-name="{tvg_name}" tvg-logo="{logo}" tvg-chno="{channel}" group-title="{groups}", {callsign}'

            if config.multiplex:
                m3uText += f' ({city})'
            m3uText += f'\n{url}\n\n'
        return m3uText

    @app.template_filter()
    def name_only(value: str) -> str:
        """Get the name part of a callSign. '4.1 CBS' -> 'CBS'

        Args:
            value (str): String to parse

        Returns:
            str: Parsed string or original value
        """
        m = re.match(r'\d+\.\d+ (.+)', value)
        if m:
            return m.group(1)
        else:
            return value

    @app.route('/lineup.json', methods=['GET'])
    def lineup_json() -> Response:
        """Returns a URL for each station that PMS can use to stream in JSON

        Returns:
            Response: JSON containing the GuideNumber, GuideName and URL for each channel
        """
        watch = "watch_direct" if config.direct else "watch"

        return jsonify([{
            "GuideNumber": station.get('channel_remapped') or station['channel'],
            "GuideName": station['name'],
            "URL": f"http://{host_and_port}/{watch}/{station['id']}"
        } for station in locast_service.get_stations()])

    @app.route('/epg', methods=['GET'])
    def epg() -> Response:
        """Returns the Electronic Programming Guide in json format

        Returns:
            Response: JSON containing the EPG for this DMA
        """
        return jsonify(locast_service.get_stations())

    @app.route('/config', methods=['GET'])
    def output_config() -> Response:
        """Returns the Electronic Programming Guide in json format

        Returns:
            Response: JSON containing the EPG for this DMA
        """
        c = dict(config)
        c['password'] = "*********"
        print(config)
        return jsonify(c)

    @app.template_filter()
    def format_date(value: int) -> str:
        """Convert an epoch timestamp to YYYYmmdd

        Args:
            value (str): Epoch timestamp string

        Returns:
            str: String as YYYYmmdd
        """

        return (datetime(1970, 1, 1) + timedelta(milliseconds=value)).strftime('%Y%m%d')

    @app.template_filter()
    def format_date_iso(value: int) -> str:
        """Convert an epoch timestamp to YYYY-mm-dd

        Args:
            value (str): Epoch timestamp string

        Returns:
            str: String as YYYY-mm-dd
        """

        return (datetime(1970, 1, 1) + timedelta(milliseconds=value)).strftime('%Y-%m-%d')

    @app.template_filter()
    def format_time(value: int) -> str:
        """Return an epoch timestamp to YYYYmmdddHHMMSS

        Args:
            value (str): Epoch timestamp string

        Returns:
            str: String as YYYYmmdddHHMMSS
        """
        return (datetime(1970, 1, 1) + timedelta(milliseconds=value)).strftime('%Y%m%d%H%M%S')

    @app.template_filter()
    def format_time_local_iso(value: int, timezone: str) -> str:
        """Return an epoch timestamp to YYYY-mm-dd HH:MM:SS in local timezone

        Args:
            value (int): Epoch timestamp string
            timezone (str): Time zone (e.g. America/New_York)

        Returns:
            str: String as YYYY-mm-dd HH:MM:SS
        """
        datetime_in_utc = datetime(1970, 1, 1) + timedelta(milliseconds=value)
        datetime_in_local = pytz.timezone(timezone).fromutc(datetime_in_utc)
        return datetime_in_local.strftime('%Y-%m-%d %H:%M:%S')

    @app.template_filter()
    def aspect(value: str) -> str:
        """Convert a locast 'videoProperties' string to an aspect ratio

        Args:
            value (str): locast 'videoProperties' string

        Returns:
            str: aspect ratio. Either '4:3' or '16:9'
        """
        for r in ["1080", "720", "HDTV"]:
            if r in value:
                return "16:9"
        return "4:3"

    @app.template_filter()
    def quality(value: str) -> str:
        """Convert a locast 'videoProperties' string to a quality

        Args:
            value (str): locast 'videoProperties' string

        Returns:
            str: quality. Either 'SD' or 'HDTV'
        """
        if "HDTV" in value:
            return "HDTV"
        else:
            return "SD"

    @app.route('/epg.xml', methods=['GET'])
    def epg_xml() -> Response:
        """Render the EPG as XMLTV. This will trigger a refetch of all stations from locast.

        Returns:
            Response: XMLTV
        """
        xml = render_template('epg.xml',
                              stations=locast_service.get_stations(),
                              url_base=host_and_port)
        return Response(xml, mimetype='text/xml')

    @app.route('/lineup.xml', methods=['GET'])
    def lineup_xml() -> Response:
        """Returns a URL for each station that PMS can use to stream in XML

        Returns:
            Response: XML containing the GuideNumber, GuideName and URL for each channel
        """
        watch = "watch_direct" if config.direct else "watch"
        xml = render_template('lineup.xml',
                              stations=locast_service.get_stations(),
                              url_base=host_and_port,
                              watch=watch).encode("utf-8")
        return Response(xml, mimetype='text/xml')

    @app.route('/lineup.post', methods=['POST', 'GET'])
    def lineup_post():
        """Initiate a rescan of stations for this DVR"""
        scan = request.args.get('scan')
        if scan == 'start':
            station_scan = True
            stations = locast_service.get_stations()
            station_scan = False
            return ('', 204)

        return (f'{scan} is not a valid scan command', 400)

    @app.route('/watch/<channel_id>.m3u')
    def watch_m3u(channel_id: str) -> Response:
        """Stream the channel based on it's ID. This route redirects to a locast m3u.

        Args:
            channel_id (str): Channel ID

        Returns:
            Response: Redirect to a locast m3u
        """
        log.info(
            f"Watching channel {channel_id} on {host_and_port} for {locast_service.city} using m3u")
        return redirect(locast_service.get_station_stream_uri(channel_id), code=302)

    @app.route('/watch/<channel_id>')
    def watch_ffmpeg(channel_id: str) -> Response:
        """Stream a channel based on it's ID. The route streams data as long as its connected.
           This method starts ffmpeg and reads n bytes at a time.

        Args:
            channel_id (str): Channel ID

        Returns:
            Response: HTTP response with content_type 'video/mpeg; codecs="avc1.4D401E"'
        """
        log.info(
            f"Watching channel {channel_id} on {host_and_port} for {locast_service.city} using ffmpeg")
        uri = locast_service.get_station_stream_uri(channel_id)

        ffmpeg = config.ffmpeg or 'ffmpeg'

        # Start ffmpeg as a subprocess to extract the mpeg stream and copy it to the incoming
        # connection. ffmpeg will take care of demuxing the mpegts stream and following m3u directions
        ffmpeg_cmd = [ffmpeg, "-i", uri, "-codec",
                      "copy", "-f", "mpegts", "pipe:1"]

        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # use a signal to indicate threads running or not
        signal = RunningSignal(True)

        # Start a thread that reads ffmpeg stderr and logs it to our logger.
        t = threading.Thread(target=_log_output, args=(
            config, ffmpeg_proc.stderr, signal))
        t.setDaemon(True)
        t.start()

        return Response(_stream_ffmpeg(config, ffmpeg_proc, signal), content_type='video/mpeg; codecs="avc1.4D401E')

    @app.route('/watch_direct/<channel_id>')
    def watch_direct(channel_id: str) -> Response:
        """Stream a channel based on it's ID. The route streams data as long as its connected.
           This method starts ffmpeg and reads n bytes at a time.

        Args:
            channel_id (str): Channel ID

        Returns:
            Response: HTTP response with content_type 'video/mpeg; codecs="avc1.4D401E"'
        """
        log.info(
            f"Watching channel {channel_id} on {host_and_port} for {locast_service.city} using direct")

        stream_uri = locast_service.get_station_stream_uri(channel_id)

        return Response(_stream_direct(config, stream_uri, log), content_type='video/mpeg; codecs="avc1.4D401E', direct_passthrough=True)
    return app


class RunningSignal:
    def __init__(self, running: bool) -> None:
        """Class that is used to signal status between logging, ffmpeg and interface threads

        Args:
            running (bool): Initial state
        """
        self._running = running

    def running(self) -> bool:
        """Returns if whatever needs to run is running

        Returns:
            bool: the thing is running
        """
        return self._running

    def stop(self):
        """Stop runningn
        """
        self._running = False


def _stream_ffmpeg(config: Configuration, ffmpeg_proc: subprocess.Popen, signal: RunningSignal):
    """Yields n bytes from ffmpeg and terminates the ffmpeg subprocess on exceptions (like client disconnecting)
    Args:
        config (Configuration): Global locast2dvr config object
        ffmpeg_proc (subprocess.Popen): FFMPeg process that has been started
        signal (RunningSignal): Signal used to communicate running status

    Yields:
        bytes: raw mpeg bytes from ffmpeg
    """
    while True:
        try:
            yield ffmpeg_proc.stdout.read(config.bytes_per_read)
        except:
            ffmpeg_proc.terminate()
            ffmpeg_proc.communicate()
            signal.stop()
            break


def _stream_direct(config: Configuration, stream_uri: str, log: logging.Logger):
    """Stream direct by parsing the locast m3u8 stream uri, downloading the .ts files (mpeg stream)
    and yielding them to the connecting client. This function is used as a generator for a
    Flask Response object.

    Args:
        config (Configuration): Global locast2dvr config object
        stream_uri (str): Locast stream location (m3u8 file)
        log (logging.Logger): Logger to be used for logging

    Yields:
        bytes: full mpeg clip
    """
    # Ordered dict of URI->dict to keep track of what segments we have served
    # and which we haven't. We do it this way because we load an updated m3u8
    # every time we have served all known segments, but since timing isn't
    # synced we could (and want to) encountered segments that we have already
    # served.
    segments = OrderedDict()
    start_time = datetime.utcnow()
    total_secs_served = 0
    while True:
        try:
            added = 0
            removed = 0
            # Update current segments
            playlist = m3u8.load(stream_uri)

            # Only add new segments to our segments OrderedDict
            for m3u8_segment in playlist.segments:
                uri = m3u8_segment.absolute_uri
                if uri not in segments:
                    segments[uri] = {
                        "played": False,
                        "duration": m3u8_segment.duration
                    }
                    log.debug(f"Added {uri} to play queue")
                    added += 1

                # Update when we have last seen this segment. Used for cleanup
                segments[uri]["last_seen"] = datetime.utcnow()

            # Clean up list, so we're not iterating a massive list in the future
            # We transform our OrderedDict into a list, since we can't mutate
            # the dict when iterating over it.
            for uri, data in list(segments.items()):
                # Remove the segment if it has been played and hasn't been updated
                # in the last 10 seconds (i.e. it wasn't in the last updates).
                # We have to make sure the segment isn't in the m3u8 file anymore,
                # because otherwise it will be seen as a new segment.
                if data["played"] and (datetime.utcnow() - data["last_seen"]).total_seconds() > 10:
                    log.debug(f"Removed {uri} from play queue")
                    del segments[uri]
                    removed += 1

            log.info(f"Added {added} new segments, removed {removed}")

            for uri, data in segments.items():
                if not data["played"]:
                    # Download the chunk
                    chunk = requests.get(uri).content

                    # Mark this chunk as played
                    # segments[uri]["played"] = True
                    data['played'] = True

                    # Chunk might have expired, move on to the next one
                    if not chunk:
                        continue

                    # Since yielding a chunk happens pretty much instantly and is not
                    # related to the speed the connecting client consumes the stream,
                    # we preferrably wait here. If we don't wait, we will be requesting
                    # the m3u8 file from locast at a high (and unnecessary) rate after
                    # we're done serving the first 10 chunks.
                    #
                    # The duration of a chunk is caputured in the m3u8 data, but since
                    # we're downloading the clip to serve it to the client as well,
                    # we need some time, rather than waiting the full `duration` before
                    # serving the next clip. However, if we would wait a fixed number of
                    # seconds (say 8 for a 10 second clip), we would drain the queue of
                    # clips, since the 2 second difference will compound over time.
                    # E.g. in case there are 10 clips of 10 seconds served and we would
                    # run 2 seconds ahead with every serving, we'd run out of clips
                    # after 50 iterations (10*10/2).
                    #
                    # In order to counter this effect, we will try to stay ahead of
                    # locast by a fixed amount of seconds. In order to do this we use
                    # the following algorithm:
                    # - We calculate the amount of seconds served to our client
                    #   (total_secs_served). This is the sum of all the durations taken
                    #   from the m3u8 playlist of previously served chunks.
                    # - We calculate the time that has passed since we started to serve
                    #   the stream (runtime). Since yielding a chunk doesn't take as long
                    #   as the actual playback time, runtime will be less than
                    #   total_secs_played.
                    # - We calculate the target difference between runtime and
                    #   total_secs_served, which is 50% of the duration of the chunk we're
                    #   about to serve. In case of a 10 sec chunk, this will be 5 seconds.
                    # - Then we calculate the actual wait time, which is the
                    #   total_secs_served - target difference - runtime.
                    #
                    # Example:
                    # - 10 second chunks
                    # - Total seconds served (before serving the current chunk): 220 sec
                    # - Total runtime since beginning of this stream: 204
                    # - Target: 5 seconds ahead of playback in order to account for
                    #   downloading and processing of the next chunk
                    # - Wait time: 220 - 5 - 204 = 11 sec

                    duration = data['duration']
                    runtime = (datetime.utcnow() - start_time).total_seconds()
                    target_diff = 0.5 * duration

                    if total_secs_served > 0:
                        wait = total_secs_served - target_diff - runtime
                    else:
                        wait = 0

                    log.info(f"Serving {uri} ({duration}s) in, {wait:.2f}s")

                    # We can't wait negative time..
                    if wait > 0:
                        sleep(wait)
                    yield chunk
                    total_secs_served += duration
        except:
            break


def _log_output(config: Configuration, stderr: IO, signal: RunningSignal):
    """Function that is used in a separate thread to log ffmpeg output


    Args:
        config (Configuration): Global locast2dvr configuration object
        stderr (IO): Stderr IO that will be logged
        signal (RunningSignal): Signal used to communicate running status
    """
    if config.verbose > 0:
        logger = logging.getLogger("ffmpeg")
        while signal.running():
            try:
                line = _readline(stderr)
                if line != '':
                    logger.info(line)
            except:
                pass
        logger.debug("Logging thread ended")


def _readline(stderr: IO) -> str:
    """Read a line from stderr

    Args:
        stderr (IO): Input

    Returns:
        str: Utf-8 decoded line with newlines stripped
    """
    return stderr.readline().decode('utf-8').rstrip()
