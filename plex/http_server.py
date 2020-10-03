from flask import Flask, Response
from flask import request
import subprocess

from flask.templating import render_template
from flask import jsonify
# import http.client as http_client
# http_client.HTTPConnection.debuglevel = 1


def PlexHTTPServer(c, locast_service):

    app = Flask(__name__)

    stations = locast_service.get_stations()
    station_scan = False

    url_base = f'{c.bind_address}:{c.port}'

    @app.route('/', methods=['GET'])
    @app.route('/device.xml', methods=['GET'])
    def device_xml():
        xml = render_template('device.xml',
                              device_model=c.device_model,
                              uuid=c.uuid,
                              url_base=url_base)
        return Response(xml, mimetype='text/xml')

    @app.route('/discover.json', methods=['GET'])
    def discover_json():
        data = {
            "FriendlyName": "Locast4Plex",
            "Manufacturer": "Silicondust",
            "ModelNumber": c.device_model,
            "FirmwareName": c.device_firmware,
            "TunerCount": c.tuner_count,
            "FirmwareVersion": c.device_firmware,
            "DeviceID": c.uuid,
            "DeviceAuth": "locast4plex",
            "BaseURL": f"http://{url_base}",
            "LineupURL": f"http://{url_base}/lineup.json"
        }
        return jsonify(data)

    @app.route('/lineup_status.json', methods=['GET'])
    def lineup_status_json():
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

    @app.route('/lineup.json', methods=['GET'])
    def lineup_json():
        return jsonify([{
            "GuideNumber": station['channel'],
            "GuideName": station['name'],
            "URL": f"http://{url_base}/watch/{station['id']}"
        } for station in stations])

    @app.route('/lineup.xml', methods=['GET'])
    def lineup_xml():
        xml = render_template('lineup.xml',
                              stations=stations,
                              url_base=url_base)
        return Response(xml, mimetype='text/xml')

    @app.route('/lineup.post', methods=['POST'])
    def lineup_post():
        scan = request.args.get('scan')
        if scan == 'start':
            station_scan = True
            stations = locast_service.get_stations()
            station_scan = False

            return ('', 204)
        return ('f{scan} is not a valid scan command', 400)

    @app.route('/watch/<channel_id>')
    def watch(channel_id):
        uri = locast_service.get_station_stream_uri(channel_id)
        ffmpeg_proc = subprocess.Popen(
            ["ffmpeg", "-i", uri, "-codec", "copy", "-f", "mpegts", "pipe:1"],
            stdout=subprocess.PIPE)

        def stream():
            while True:
                try:
                    yield ffmpeg_proc.stdout.read(c.bytes_per_read)
                except:
                    print("SOMETHING HAPPENED!")
                    ffmpeg_proc.terminate()
                    ffmpeg_proc.communicate()
                    break

        return Response(stream(), content_type='video/mpeg; codecs="avc1.4D401E')

    return app
