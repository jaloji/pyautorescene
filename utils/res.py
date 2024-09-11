import os
import errno
import tempfile
import json
from colorama import Fore, Style

SUCCESS = Fore.GREEN + "  [SUCCESS] " + Fore.RESET
FAIL = Fore.RED + "  [FAIL] " + Fore.RESET
ORANGE = '\033[38;5;208m'
RESET = Style.RESET_ALL
WARNING = f"{ORANGE}  [WARNING] {RESET}"

# YOU NEED TO EDIT WITH YOURS
USERNAME = ""
PASSWORD = ""
SITE = "https://www.srrdb.com/"
SRRDB_API = f"{SITE}api/search/"
SRRDB_DOWNLOAD = f"{SITE}download/srr/"

loginData = {"username": USERNAME, "password": PASSWORD}
loginUrl = f"{SITE}account/login"
loginTestUrl = SITE
loginTestString = USERNAME

# YOU NEED TO EDIT WITH YOURS
# DON'T RUN THIS SCRIPT WITHOUT USING preprardir.ps1 HERE: https://github.com/MRiCEQB/PS_preprardir EXCEPT IF YOU'RE UNDER LINUX
RAR_VERSION = "C:\\Python39\\pyrescene-master\\rarv"
SRR_TEMP_FOLDER = f"{RAR_VERSION}\\tmp"

# Create a directory if it doesn't exist
def mkdir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        if e.errno != errno.EEXIST or not os.path.isdir(path):
            raise OSError(e)
    return True

# Search for a release by name on srrdb
def search_by_name(name, s, isdir = False):
    if not name:
        raise ValueError("Release must have a valid name")

    name_search = f"{SRRDB_API}r:{name.rsplit('.', 1)[0] if not isdir else name}"

    try:
        response = s.retrieve_content(name_search)
        data = response.json()
    except Exception as e:
        raise RuntimeError("Failed to retrieve content") from e

    if 'resultsCount' not in data or int(data['resultsCount']) < 1:
        return None

    return data['results']

# Download an SRR file for the given release
def download_srr(rls, s, path=None):
    if not rls:
        raise ValueError("Release must have a valid name")

    srr_download = f"{SRRDB_DOWNLOAD}{rls}"

    if not path:
        path = tempfile.gettempdir()

    if not os.path.isdir(path):
        raise IOError(f'Output directory "{path}" does not exist.')

    #create path for file to be stored
    path = os.path.join(path, os.path.basename(f"{srr_download}.srr"))

    try:
        response = s.retrieve_content(srr_download)

        if response.text in [
            "The SRR file does not exist.",
            "You've reached your daily download limit.",
            "You have sent too many requests in a given amount of time."]:
            raise ValueError(response.text)

        with open(path, "wb") as local_file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    local_file.write(chunk)
                    local_file.flush()

    except Exception as e:
        raise RuntimeError("Failed to download SRR file") from e

    return path