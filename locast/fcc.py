import requests
import logging
import io
import zipfile
import datetime
from fuzzywuzzy import fuzz
from os import path

FACILITIES_URL = 'https://transition.fcc.gov/ftp/Bureaus/MB/Databases/cdbs/facility.zip'
DMA_URL = 'http://api.locastnet.org/api/dma'

COLUMNS = ["comm_city", "comm_state", "eeo_rpt_ind", "fac_address1", "fac_address2", "fac_callsign",
           "fac_channel", "fac_city", "fac_country", "fac_frequency", "fac_service", "fac_state", "fac_status_date",
           "fac_type", "facility_id", "lic_expiration_date", "fac_status", "fac_zip1", "fac_zip2", "station_type",
           "assoc_facility_id", "callsign_eff_date", "tsid_ntsc", "tsid_dtv", "digital_status", "sat_tv",
           "network_affil", "nielsen_dma", "tv_virtual_channel", "last_change_date", "end_of_record"]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)


class Facilities:
    __instance = None

    def __new__(cls):
        if Facilities.__instance is None:
            Facilities.__instance = Facilities.__Facilities()
        return Facilities.__instance

    class __Facilities:

        def __init__(self):
            self.facilities = []
            self.dmas = set()
            self.dma_mapping = {}

            self._process(self._unzip(self._download()))
            self._get_dma_mapping()

        def _get_dma_mapping(self):
            r = requests.get(DMA_URL)
            r.raise_for_status()
            for locast_dma in r.json():
                fcc_dma = None
                for dma in self.dmas:
                    if locast_dma["id"] == 539:  # Tampa bay hack
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

                self.dma_mapping[locast_dma["id"]] = fcc_dma

        def _download(self):
            cache_file = path.join(path.dirname(
                path.realpath(__file__)), 'facility.zip')
            if path.exists(cache_file):
                logging.info("Using cached facilities file")
                with open(cache_file, 'rb') as file:
                    data = file.read()
            else:
                logging.info("Downloading FCC facilities..")
                r = requests.get(FACILITIES_URL)
                r.raise_for_status()
                data = r.content
                logging.info("Caching facilities...")
                with open(cache_file, "wb") as file:
                    file.write(data)
            return data

        def _unzip(self, data):
            logging.info("Unzipping...")
            z = zipfile.ZipFile(io.BytesIO(data))
            return z.read('facility.dat').decode('utf-8')

        def _process(self, facilities):
            for line in facilities.split("\n"):
                if not line:
                    continue

                line = line.strip()
                facility = {}
                cells = line.split("|")
                for i, col in enumerate(COLUMNS):
                    try:
                        facility[col] = cells[i]
                    except:
                        print(line)
                        print(len(cells))

                if facility["lic_expiration_date"] and \
                        facility["fac_status"] == 'LICEN' and \
                        facility['fac_service'] in ('DT', 'TX', 'TV', 'TB', 'LD', 'DC'):

                    lic_expiration_date = datetime.datetime.strptime(
                        facility["lic_expiration_date"], '%m/%d/%Y') + datetime.timedelta(hours=23, minutes=59, seconds=59)

                    if lic_expiration_date > datetime.datetime.now():
                        self.facilities.append(facility)
                    if facility['nielsen_dma']:
                        self.dmas.add(facility['nielsen_dma'])
