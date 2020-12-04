# locast2dvr

This application provides an interface between locast.org and [Plex Media Server (PMS)](https://plex.tv) or [Emby](https://emby.media) by acting like a [HDHomerun](https://www.silicondust.com/) or an m3u Tuner and an XMLTV provider.

`locast2dvr` can imitate one or more DVR tuners and provides geo cloaking across regions.

`locast2dvr` is a rewrite of [locast2plex](https://github.com/tgorgdotcom/locast2plex). Thanks to the locast2plex developers for writing it and figuring out how to stitch things together!

I rewrote locast2plex to be able to more easily add functionality, use libraries wherever possible (like HTTP, m3u, starting multiple devices, etc) and some code clean up (command line argument parsing, automatic download of FCC facilities, etc). Even though this project started as a locast to PMS interface, it's more focused on integrating locast with Emby, since Emby provides a bit more functionality when it comes to Live TV and DVR (like m3u tuners, XMLTV, etc).

## Features
- Override your location using zipcode or GPS coordinates
- Multiple DVR tuners in a single server, either as separate servers or as one (multi-/megaplexing)
- SSDP for easy discovery of DVR devices in PMS or Emby
- Acts like either a HDHomerun Tuner or m3u tuner
- Provides locast EPG information as an XMLTV guide

## Prerequisites
- Active locast.org account with an active donation. Locast doesn't allow you to stream without a donation.
- Make sure [ffmpeg](https://ffmpeg.org/) is installed and available on your `$PATH`.

## Install
```sh
$ pip install `locast2dvr`
```

## Usage
```sh
`locast2dvr` --config my_config_file
```

## Configuration
`locast2dvr` parameters can be specified as either command line arguments or in a configuration file that can be specified using that `--config` argument.

### Configuration parameters

Useful parameters:

- `username` (required): locast.org username
- `password` (required): locast.org password
- `uid`: a unique identifier that is used by PMS/Emby to identify a specific DVR device. (*NOTE: If this parameter isn't specified, it will be automatically generated, but not persisted!*)
- `bind`: address to bind the `locast2dvr` service to (defaults to `127.0.0.1`)
- `port`: tcp port to bind the `locast2dvr` service to (defaults to `6077`)
- `ffmpeg`: path to `ffmpeg` binary (optional if `ffmpeg` is in `$PATH`).
- `verbose`: enable verbose logging of HTTP requests
- `override-location`: override the location using latitude and longitude
- `override-zipcodes`: override the location using one or more zipcodes. This argument takes a comma separated list of zipcodes and will start multiple instances. (see [Multi regions](#multi_regions) for more info)

Multi-/megaplexing:
- `multiplex`: Multiplex devices besides starting separate DVR instances
- `megaplex`: Multiplex devices and only start one HTTP interface

Developer/debugging parameters:
- `bytes-per-read`: number of bytes to read from `ffmpeg` each iteration (defaults to `1152000`)
- `tuner-count`: tuner count that is exposed to PMS/Emby (defaults to `3`)
- `device-model`: model reported to PMS/Emby (defaults to `HDHR3-US`)
- `device-firmware`: model firmware reported to PMS/Emby (defaults to `hdhomerun3_atsc`)
- `device-version`: firmware version reported to PMS/Emby (defaults to `1.2.3456`)

For more help use `--help`
### Location overrides

By default `locast2dvr` uses your IP address to determine your location, but it also allows you to override the locast.org location you're creating a DVR for. There are 3 mutually exclusive options:

- `override-location`, which takes a `<latitude>,<longitude>` argument. E.g. `--override-location 40.7128,-74.0060` for New York.
- `override-zipcodes`, which takes a comma separated list of zipcodes as an argument. E.g. `--override-zipcodes 90210,55111` for Los Angeles and Minneapolis.

### <a name="multi_region"></a>Multi regions

`locast2dvr` allows starting multiple instances. This is done using the `override-zipcodes` option. A [file with all available locast regions](https://github.com/wouterdebie/`locast2dvr`/blob/main/regions) is included in the `locast2dvr` distribution.

When using multiple regions, `locast2dvr` will start multiple instances on TCP ports starting at the value that is specified with the `port` (or the default `6077`) argument and incremented by one. Also, the UUID of each device will be appended with `_x`, where `x` is incremented by one for each instance.

Note: PMS supports multiple devices, but does not support multiple Electronic Programming Guides (EPGs). Emby does support both. I personally use Emby since it allows for multiple EPGs.

### Usage in PMS or Emby

#### Tuners
`locast2dvr` can act as both a HDHomerun device or as an m3u tuner. Plex mainly supports HDHomerun, while Emby supports both. In case `locast2dvr` is used as an HDHomerun device it will use `ffmpeg` to copy the `mpegts` stream from locast to the Media server. When using `locast2dvr` as an m3u tuner, it will pass on the m3u from locast to the media server without any decoding.

- For use as a HDHomerun tuner, use `IP:PORT` (defaults to `127.0.0.1:6077`) to connect
- For use as an m3u tuner, use `http://IP:PORT/lineup.m3u` (defaults to `http://127.0.0.1:6077/lineup.m3u`) as the URL to connect.

#### EPG
`locast2dvr` also provides Electronic Programming Guide (EPG) information from locast. This is served in [XMLTV](http://wiki.xmltv.org/) format. Emby has support for XMLTV and can be used by adding `http://IP:PORT/epg.xml`  (defaults to `http://127.0.0.1:6077/epg.xml`) as an XMLTV TV Guide Data Provider.

### Multiplexing

`locast2dvr` normally starts an HTTP instance for each DVR, starting at `port` (default `6077`). But with the option `--multiplex`, it will start a single HTTP interface multiplexing all DVRs through one interface for both streaming and EPG. Any channels that have the same call sign (like 4.1 ABC) will be deduped.

For example: if you use `--multiplex --override-zipcodes=90210,55111`, all channels from both zipcodes will be available, but multiplexed at `localhost:6077`.

In case you still want all HTTP interfaces to start besides the multiplexer, `--multiplex-debug` can be used. This will start the multiplexer the next port after the last DVR.

For example: if you use `--multiplex --override-zipcodes=90210,55111` it will normally start HTTP interfaces on `127.0.0.1:6077` and `127.0.0.1:6078`. The multiplexer will be started on `127.0.0.1:6079`.

Note: This type of multiplexing makes sense in Emby, since you can add a single tuner at `http://PORT:IP` or `http://PORT:IP/lineup.m3u` and a single EPG at `http://PORT:IP/epg.xml`

## Development
- Clone this repo
- Create a virtual env and activate it `python -m venv venv && . ./venv/bin/activate`
- Install requirements `pip install -r requirements.txt`
- Install locast2dvr as editable `pip install --editable .`

You should now be able to develope and test your changes by running `$ locast2dvr`
