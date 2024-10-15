import os
import errno
import tempfile
           
import subprocess
import json
import re
import time
from pathlib import Path
from colorama import Fore, Style

SUCCESS = Fore.GREEN + "  [SUCCESS] " + Fore.RESET
FAIL = Fore.RED + "  [FAIL] " + Fore.RESET
ORANGE = '\033[38;5;208m'
DARK_YELLOW = '\033[38;5;3m'
RESET = Style.RESET_ALL
WARNING = f"{ORANGE}  [WARNING] {RESET}"
verbose_flag = False 

# YOU NEED TO EDIT WITH YOURS
USERNAME = ""
PASSWORD = ""
SITE = "https://www.srrdb.com/"
SRRDB_API = f"{SITE}api/search/"
SRRDB_DOWNLOAD = f"{SITE}download/srr/"
SRRDB_UPLOAD = f"{SITE}release/upload"

loginData = {"username": USERNAME, "password": PASSWORD}
loginUrl = f"{SITE}account/login"
loginTestUrl = SITE
loginTestString = USERNAME

# YOU NEED TO EDIT WITH YOURS
# DON'T RUN THIS SCRIPT WITHOUT USING preprardir.ps1 HERE: https://github.com/MRiCEQB/PS_preprardir 
# EXCEPT IF YOU'RE UNDER LINUX USE preprardir.py in pyrescene source

RAR_VERSION = ""
SRR_TEMP_FOLDER = f"{RAR_VERSION}"
if os.name == 'nt':
    SRS_NET_EXE = "C:\\Python39\\pyautorescene-master\\utils\\srs.exe"
else:
    # You need mono-complete package to run this
    SRS_NET_EXE = "/app/pyautorescene-master/utils/srs.exe"

# Logs folder
CONFIG_FOLDER = os.path.join(Path.home(), ".config", "srrdb")

def set_verbose_flag(flag):
    global verbose_flag
    verbose_flag = flag

def remove_ansi_escape_codes(text):
    ansi_escape = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def verbose(string, end='\n'):
    filename = os.path.join(CONFIG_FOLDER, "autorescene.txt")
    if verbose_flag:
        # Print the string to the console
        print(string, end=end)
    
    # Open the file in append mode and write the string
    with open(filename, 'a') as file:
        file.write(remove_ansi_escape_codes(string) + end)

def format_time(seconds):
    # Format the time into hours, minutes, and seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours)} hours, {int(minutes)} minutes, {int(seconds)} seconds"
    elif minutes > 0:
        return f"{int(minutes)} minutes, {int(seconds)} seconds"
    else:
        return f"{int(seconds)} seconds"
        
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

def run_resample_net_executable(executable_path, *args):
    fail = False  # Initialize the fail variable inside the function
    try:
        # Prepare the command with arguments
        if os.name == 'nt':
            command = [executable_path] + list(args)
        else:
            command = ['mono', executable_path] + list(args)

        # Run the .NET executable and capture output incrementally
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Read output in real-time
        stdout_lines = []
        stderr_lines = []
        for stdout_line in iter(process.stdout.readline, ''):
            stdout_lines.append(stdout_line)
            verbose(stdout_line, end='')
            if (stdout_line.startswith("Unable to") or
                stdout_line.startswith("Could not locate") or
                stdout_line.startswith("No A/V data was found") or
                stdout_line.startswith("Operation aborted") or
                stdout_line.startswith("Rebuild failed") or
                stdout_line.startswith("Corruption detected") or
                stdout_line.startswith("Unexpected Error")):
                fail = True

        for stderr_line in iter(process.stderr.readline, ''):
            stderr_lines.append(stderr_line)
            verbose("Error:", stderr_line, end='')

        process.stdout.close()
        process.stderr.close()
        process.wait()

        # Return the captured output and the fail status
        return ''.join(stdout_lines), ''.join(stderr_lines), fail

    except subprocess.CalledProcessError as e:
        verbose(f"Error occurred: {e}")
        return None, e.stderr, True

    except subprocess.TimeoutExpired as e:
        verbose(f"Process timed out: {e}")
        process.kill()
        return None, None, True
