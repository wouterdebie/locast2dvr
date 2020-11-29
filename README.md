# locast4plex

This application provides an interface between locast.org and Plex Media Server (PMS). This requires a locast account that is actively donating to locast.org.

locast4plex imitates one or more DVR tuners and provides geo cloaking across regions.

locast4plex is a rewrite of [locast2plex](https://github.com/tgorgdotcom/locast2plex). Thanks to the locast2plex developers for writing it and figuring out how to stitch things together!

I rewrote locast2plex to be able to more easily add functionality, use libraries wherever possible (like HTTP, m3u, etc) and some code clean up (command line argument parsing, automatic download of FCC facilities, etc).

## Features
- Override your location
- Multiple DVR tuners in a single server
- SSDP for easy discovery of DVR devices in PMS

## Prerequisites
- Active locast.org account with an active donation. Locast doesn't allow you to stream without a donation.
- Make sure [ffmpeg](https://ffmpeg.org/) is installed and available on your `$PATH`.

## Install
```sh
$ pip install locast4plex
```

## Usage
```sh
locast4plex --config my_config_file
```

## Configuration
locast4plex parameters can be specified as either command line arguments or in a configuration file that can be specified using that `--config` argument.

### Configuration parameters

Useful parameters:

- `username` (required): locast.org username
- `password` (required): locast.org password
- `uid`: a unique identifier that is used by PMS to identify a specific DVR device. (*NOTE: If this parameter isn't specified, it will be automatically generated, but not persisted!*)
- `bind`: address to bind the locast4plex service to (defaults to `0.0.0.0`)
- `port`: tcp port to bind the locast4plex service to (defaults to `6077`)
- `ffmpeg`: path to `ffmpeg` binary (optional if `ffmpeg` is in `$PATH`).
- `verbose`: enable verbose logging of HTTP requests
- `override-location`: override the location using latitude and longitude
- `override-zipcodes`: override the location using one or more zipcodes. This argument takes a comma separated list of zipcodes and will start multiple instances. (see [Multi regions](#multi_regions) for more info)

Developer/debugging parameters:
- `bytes-per-read`: number of bytes to read from `ffmpeg` each iteration (defaults to `1152000`)
- `tuner-count`: tuner count that is exposed to PMS (defaults to `3`)
- `device-model`: model reported to PMS (defaults to `HDHR3-US`)
- `device-firmware`: model firmware reported to PMS (defaults to `hdhomerun3_atsc`)
- `device-version`: firmware version reported to PMS (defaults to `1.2.3456`)

### Location overrides

By default locast4plex uses your IP address to determine your location, but it also allows you to override the locast.org location you're creating a DVR for. There are 3 mutually exclusive options:

- `override-location`, which takes a `<latitude>,<longitude>` argument. E.g. `--override-location 40.7128,-74.0060` for New York.
- `override-zipcodes`, which takes a comma separated list of zipcodes as an argument. E.g. `--override-zipcodes 90210,55111` for Los Angeles and Minneapolis.

### <a name="multi_region"></a>Multi regions

locast4plex allows starting multiple instances. This is done using the `override-zipcodes` option. A [file with all available locast regions](https://github.com/wouterdebie/locast4plex/blob/main/regions) is included in the locast4plex distribution.

When using multiple regions, locast4plex will start multiple instances on TCP ports starting at the value that is specified with the `port` (or the default `6077`) argument and incremented by one. Also, the UUID of each device will be appended with `_x`, where `x` is incremented by one for each instance.

In PMS you will have to add separate devices for each region you create.

Note that if any of the zipcodes is invalid (meaning locast isn't available for a zipcode), the server will stop completely.

## TODO
- Unit tests
- Re-download FCC facilities once in a while, since the might go stale
- Document how to daemonize
- Dockerize?
- Redo FCC facilities implementation, since there's a O(n) lookup for each facility lookup. This doesn't happen often, but just seems wrong. It's probably better to create a mapping that allows for fast lookups when starting locast4plex.
