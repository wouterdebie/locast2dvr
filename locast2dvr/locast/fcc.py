import io
import os
import threading
import warnings
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fuzzywuzzy import fuzz

from locast2dvr.utils import LoggingHandler

FACILITIES_URL = 'https://transition.fcc.gov/ftp/Bureaus/MB/Databases/cdbs/facility.zip'
DMA_URL = 'http://api.locastnet.org/api/dma'
CHECK_INTERVAL = 3600
MAX_FILE_AGE = 24 * 60 * 60


class Facilities(LoggingHandler):
    def __init__(self):
        """Provides an interface to FCC 'facilities' that contain information on US TV channels
        """
        super().__init__()
        self._facilities_index = {}
        self._fcc_dmas = set()
        self._dma_mapping = {}

        self.cache_dir = os.path.join(Path.home(), '.locast2dvr')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.cache_file = os.path.join(self.cache_dir, 'facilities.zip')
        self._lock = threading.Lock()
        self._last_check_ts = 0
        self._run()

    def by_dma_and_call_sign(self, dma: str, call_sign: str) -> dict:
        """Look up a facility by Designated Market Area (DMA)

        Args:
            dma (str): Designated Market Area to search through
            call_sign (str): Call sign to look for

        Returns:
            dict: Returns a dict containing the channel name and if the channel is analog or not
        """
        with self._lock:
            facility = self._facilities_index.get(
                (self._dma_mapping[dma], call_sign))
            if facility:
                return {
                    "channel": facility['tv_virtual_channel'] or facility['fac_channel'],
                    "analog": facility['tv_virtual_channel'] == None
                }

    def _run(self):
        """Start the process of downloading, caching and processing of FCC data

        This method checks if a facilities file exists and how old it is. If it doesn't exist
        or is older than 24 hours, it will redownload the file and cache it.
        """

        data = None

        if not os.path.exists(self.cache_file) or datetime.now().timestamp() - os.path.getmtime(self.cache_file) > MAX_FILE_AGE:
            data = self._download()
            self._write_cache_file(data)
        elif not self._facilities_index:
            self.log.info(f"Using cached file: {self.cache_file}")
            data = self._read_cache_file()

        if data:
            self._process(self._unzip(data))
            self._load_dma_mapping()
            self.log.info("Done loading..")

        threading.Timer(CHECK_INTERVAL, self._run).start()

    def _download(self) -> bytes:
        """Download facilities zipfile from the FCC.

        Returns:
            bytes: contents of the facilities zip file (compressed)
        """

        self.log.info("Downloading FCC facilities..")
        # Disabling weak dh check. FCC should update their servers.
        ciphers = requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
        r = requests.get(FACILITIES_URL)
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = ciphers
        r.raise_for_status()
        return r.content

    def _write_cache_file(self, data):
        """Write the contents of `data` to `self.cache_file`

        Args:
            data ([bytes]): bytes of data to be written
        """

        with open(self.cache_file, mode='wb') as f:
            f.write(data)

        self.log.info(f"Cached facilities at {self.cache_file}")

    def _read_cache_file(self) -> bytes:
        """Read the contents of `self.cache_file`

        Returns:
            bytes: bytes of data
        """
        with open(self.cache_file, 'rb') as file:
            return file.read()

    def _unzip(self, data: bytes) -> str:
        """Unzip a bytes array

        Args:
            data (bytes): String of ZIP compressed bytes

        Returns:
            str: Decoded bytes as a utf-8 string
        """

        self.log.info("Unzipping facilities...")
        z = zipfile.ZipFile(io.BytesIO(data))
        return z.read('facility.dat').decode('utf-8')

    def _process(self, facilities: str):
        """Process FCC facilities string and store FCC DMAs and FCC facilities in memory

        Args:
            facilities (str): Uncompressed facilities file contents
        """
        # The FCC file has one facility per line and is column separated by a "|".
        # The columns in the file are the following
        COLUMNS = ["comm_city", "comm_state", "eeo_rpt_ind", "fac_address1", "fac_address2", "fac_callsign",
                   "fac_channel", "fac_city", "fac_country", "fac_frequency", "fac_service", "fac_state", "fac_status_date",
                   "fac_type", "facility_id", "lic_expiration_date", "fac_status", "fac_zip1", "fac_zip2", "station_type",
                   "assoc_facility_id", "callsign_eff_date", "tsid_ntsc", "tsid_dtv", "digital_status", "sat_tv",
                   "network_affil", "nielsen_dma", "tv_virtual_channel", "last_change_date", "end_of_record"]

        with self._lock:
            # Reset everything before processing
            self._fcc_dmas = set()
            self._dma_mapping = {}

            for line in facilities.split("\n"):
                if not line:
                    continue

                line = line.strip()
                facility = {}
                cells = line.split("|")

                # Map the line into a dict, so it's easier to work with
                for i, col in enumerate(COLUMNS):
                    facility[col] = cells[i]

                # Only care about specific facilities
                if facility["lic_expiration_date"] and \
                        facility["fac_status"] == 'LICEN' and \
                        facility['fac_service'] in ('DT', 'TX', 'TV', 'TB', 'LD', 'DC'):

                    # Only care about non expired licence facilities
                    lic_expiration_date = datetime.strptime(
                        facility["lic_expiration_date"], '%m/%d/%Y') + \
                        timedelta(hours=23, minutes=59, seconds=59)

                    # Add the facility to the index, keyed by nielsen_dma and fac_callsign
                    if lic_expiration_date > datetime.now():
                        nielsen_dma = facility['nielsen_dma']
                        fac = facility['fac_callsign'].split("-")[0]
                        self._facilities_index[(nielsen_dma, fac)] = facility

                    if facility['nielsen_dma']:
                        self._fcc_dmas.add(facility['nielsen_dma'])

    def _load_dma_mapping(self):
        """Load locast DMA ID's and map them to Nielsen DMAs. This uses fuzzy name matching.

        Raises:
            SystemExit: if no FCC DMA can be found for a locast DMA
            HTTPError: if the request for DMAs to locast fails
        """
        r = requests.get(DMA_URL)
        r.raise_for_status()
        for locast_dma in r.json():
            fcc_dma = None
            for dma in self._fcc_dmas:
                # Tampa Bay and Tampa don't match directly, so we force a match
                if locast_dma["id"] == 539:
                    test_string = locast_dma['name'].split()[0].lower()
                else:
                    test_string = locast_dma['name'].lower()

                ratio = fuzz.partial_ratio(test_string, dma.lower())

                if ratio == 100:
                    fcc_dma = dma
                    break
            if not fcc_dma:
                raise SystemExit(
                    f"Can't find FCC DMA for {locast_dma['id']}, {locast_dma['name']}")

            self._dma_mapping[locast_dma["id"]] = fcc_dma
