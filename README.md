# locast2dvr

This application provides an interface between locast.org and [Plex Media Server (PMS)](https://plex.tv) or [Emby](https://emby.media) by acting like a [HDHomerun](https://www.silicondust.com/) Tuner.

locast2dvr can imitate one or more DVR tuners and provides geo cloaking across regions.

locast2dvr is a rewrite of [locast2plex](https://github.com/tgorgdotcom/locast2plex). Thanks to the locast2plex developers for writing it and figuring out how to stitch things together!

I rewrote locast2plex to be able to more easily add functionality, use libraries wherever possible (like HTTP, m3u, starting multiple devices, etc) and some code clean up (command line argument parsing, automatic download of FCC facilities, etc).

## Features
- Override your location using zipcode or GPS coordinates
- Multiple DVR tuners in a single server
- SSDP for easy discovery of DVR devices in PMS or Emby

## Prerequisites
- Active locast.org account with an active donation. Locast doesn't allow you to stream without a donation.
- Make sure [ffmpeg](https://ffmpeg.org/) is installed and available on your `$PATH`.

## Install
```sh
$ pip install locast2dvr
```

## Usage
```sh
locast2dvr --config my_config_file
```

## Configuration
locast2dvr parameters can be specified as either command line arguments or in a configuration file that can be specified using that `--config` argument.

### Configuration parameters

Useful parameters:

- `username` (required): locast.org username
- `password` (required): locast.org password
- `uid`: a unique identifier that is used by PMS/Emby to identify a specific DVR device. (*NOTE: If this parameter isn't specified, it will be automatically generated, but not persisted!*)
- `bind`: address to bind the locast2dvr service to (defaults to `127.0.0.1`)
- `port`: tcp port to bind the locast2dvr service to (defaults to `6077`)
- `ffmpeg`: path to `ffmpeg` binary (optional if `ffmpeg` is in `$PATH`).
- `verbose`: enable verbose logging of HTTP requests
- `override-location`: override the location using latitude and longitude
- `override-zipcodes`: override the location using one or more zipcodes. This argument takes a comma separated list of zipcodes and will start multiple instances. (see [Multi regions](#multi_regions) for more info)

Developer/debugging parameters:
- `bytes-per-read`: number of bytes to read from `ffmpeg` each iteration (defaults to `1152000`)
- `tuner-count`: tuner count that is exposed to PMS/Emby (defaults to `3`)
- `device-model`: model reported to PMS/Emby (defaults to `HDHR3-US`)
- `device-firmware`: model firmware reported to PMS/Emby (defaults to `hdhomerun3_atsc`)
- `device-version`: firmware version reported to PMS/Emby (defaults to `1.2.3456`)

### Location overrides

By default locast2dvr uses your IP address to determine your location, but it also allows you to override the locast.org location you're creating a DVR for. There are 3 mutually exclusive options:

- `override-location`, which takes a `<latitude>,<longitude>` argument. E.g. `--override-location 40.7128,-74.0060` for New York.
- `override-zipcodes`, which takes a comma separated list of zipcodes as an argument. E.g. `--override-zipcodes 90210,55111` for Los Angeles and Minneapolis.

### <a name="multi_region"></a>Multi regions

locast2dvr allows starting multiple instances. This is done using the `override-zipcodes` option. A [file with all available locast regions](https://github.com/wouterdebie/locast2dvr/blob/main/regions) is included in the locast2dvr distribution.

When using multiple regions, locast2dvr will start multiple instances on TCP ports starting at the value that is specified with the `port` (or the default `6077`) argument and incremented by one. Also, the UUID of each device will be appended with `_x`, where `x` is incremented by one for each instance.

Note: PMS supports multiple devices, but not multiple Electronic Programming Guides (EPGs). Emby does support both.

## TODO
- Unit tests
- Re-download FCC facilities once in a while, since the might go stale
- Document how to daemonize
- Dockerize?
- Ubunut packages?
- Redo FCC facilities implementation, since there's a O(n) lookup for each facility lookup. This doesn't happen often, but just seems wrong. It's probably better to create a mapping that allows for fast lookups when starting locast2dvr.
