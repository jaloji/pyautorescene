#!/usr/bin/python

"""
Forked from https://github.com/peps1/srrup
"""

import os
import sys
import argparse
from pathlib import Path
from colorama import init
import requests
import shutil
import time

from utils.connect import SRRDB_LOGIN
import utils.res

# Define global variables
VERSION = "2.1.1" # Use original script version as reference for any updates
MAX_UPLOAD_SIZE = 104857600  # 100 MiB

backfill_folder = os.path.join(utils.res.CONFIG_FOLDER, "backfill")
lockfile = Path(os.path.join(backfill_folder, "_srrup.lock"))

# Help text for the script
HELP_TEXT = """Usage: srrup.py file.srr <file2.srr> <file3.srr>
Upload one or more .srr files to srrdb.com, if no option is specified as listed below,
all parameters are expected to be .srr files and will be uploaded.
Output will be logged to ~/.config/srrdb/srrup.txt

Examples:
    srrup.py        -> Will use the current path
    srrup.py files/file1.srr more/file2.srr
    srrup.py /path/to/srr/files
Options:
    -b, --backfill  process files in backfill folder (~/.config/srrdb/backfill)
    -h, --help      show this help
    -v, --version   print the current version
"""

def arg_parse():
    parser = argparse.ArgumentParser(description="Upload .srr files to srrdb.com", add_help=False)
    parser.add_argument('files', nargs='*', help="Files to upload")
    parser.add_argument('-b', '--backfill', action='store_true', help="Process files in backfill folder")
    parser.add_argument('-h', '--help', action='store_true', help="Show this help message and exit")
    parser.add_argument('-v', '--version', action='store_true', help="Print the current version")
    
    return vars(parser.parse_args())
    
def verbose(string, end='\n'):
    filename = os.path.join(utils.res.CONFIG_FOLDER, "srrup.txt")
    # Print the string to the console
    print(string, end=end)
    
    # Open the file in append mode and write the string
    with open(filename, 'a') as file:
        file.write(utils.res.remove_ansi_escape_codes(string) + end)
        
def file_size_ok(file):
    # Check if the file size is within allowed limits
    try:
        stats = os.stat(file)
        return 0 < stats.st_size <= MAX_UPLOAD_SIZE
    except FileNotFoundError:
        verbose(f"{utils.res.FAIL} -> File not found: {file}")
        return False

def backup_srr(file):
    # Copy SRR to backup folder
    file_name = os.path.basename(file)
    backfill_file = os.path.join(backfill_folder, file_name)

    if not os.path.exists(backfill_file):
        try:
            shutil.copy2(file, backfill_file)
        except Exception as e:
            raise RuntimeError(f"Failed to copy {file_name} to backup folder: {e}")

def srr_upload(file):
    global scanned_release
    ret = False

    if not file.lower().endswith('.srr') or not file_size_ok(file):
        return False

    scanned_release += 1
    file_name = os.path.basename(file)

    try:
        with open(file, 'rb') as f:
            file_data = f.read()
    except Exception as e:
        verbose(f"{utils.res.FAIL} -> {e}")
        return False


    # Create a multipart form-data payload
    form_data = {'files[]': (file_name, file_data),}

    headers = {
        'User-Agent': f"srrup.py/{VERSION}",
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    verbose(f"\t - Uploading: {file}")
    try:
        response = s.retrieve_content(utils.res.SRRDB_UPLOAD, method="post", files=form_data, timeout=30, headers=headers)
    except Exception as e:
        verbose(f"\t\t - {utils.res.FAIL} -> {e}")
        backup_srr(file)
        ret = False

    if response.status_code == 200:
        response_data = response.json()

        if response_data['files'][0].get('message'):
            message = response_data['files'][0]['message'].strip()

        if response_data['files'][0]['color'] == 0:
            if "is a different set of rars" in message.lower():
                verbose(f"\t\t - {utils.res.SUCCESS} -> {message} when uploading file {file}")
                ret = True
            else:
                verbose(f"\t\t - {utils.res.FAIL} -> {message} when uploading file {file}")
                backup_srr(file)
                ret = False
                
        elif response_data['files'][0]['color'] in (1, 2):
            verbose(f"\t\t - {utils.res.SUCCESS} -> {response_data['files'][0]['message'].strip().lstrip('- ')}")
            ret = True
        else:
            verbose(f"\t\t - {utils.res.FAIL} -> Unknown response: {response.text} - please submit a bug report.")
            backup_srr(file)
            ret = False
    else:
        verbose(f"\t\t - {utils.res.FAIL} -> {response.status_code}")
        backup_srr(file)
        ret = False
                
    return ret

def check_lock_file():
    # Check if lock file exists and return its modification time or False
    if lockfile.exists():
        return lockfile.stat().st_mtime
    return False

def set_lock_file():
    locked = check_lock_file()
    if not locked:
        # Create empty lock file
        lockfile.touch()
        return True
    else:
        locked_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(locked))
        verbose(f"\t - {utils.res.FAIL} -> Lockfile found, cancelling backfill. Locked since {locked_time}.")
        return False

def clear_lock_file():
    # Remove lock file after processing
    try:
        lockfile.unlink()
    except FileNotFoundError:
        verbose(f"\t - {utils.res.FAIL} -> Lockfile not found during cleanup.")

def process_backfill():
    # Process all files in the backfill folder
    global success_release
    files = [f for f in os.listdir(backfill_folder) if f.endswith(".srr")]

    if not files:
        return

    verbose(f"\t - {len(files)} .srr found in backfill folder, will process now...")

    # Set lock file
    locked_successful = set_lock_file()
    if locked_successful:
        for file in files:
            file_path = os.path.join(backfill_folder, file)
            upload_success = srr_upload(file_path)
            if upload_success:
                success_release += 1
                # Remove file if upload is successful
                try:
                    os.remove(file_path)
                except OSError as e:
                    verbose(f"{utils.res.FAIL} -> Error deleting: {file} -> {e}")
            else:
                # If upload fails, stop the backfill processing
                #verbose(f"{utils.res.FAIL} -> Last file upload failed, cancelling backfill.")
                #break
                verbose(f"{utils.res.FAIL} -> Skipping {file}")
                continue

        # Clear the lock file when done
        clear_lock_file()

if __name__ == '__main__':
    start_time = time.time()
    
    args = arg_parse()
    # initialize pretty colours
    init()
    
    success_release = 0
    scanned_release = 0
    
    # Ensure config and backfill folder are created
    utils.res.mkdir(utils.res.CONFIG_FOLDER)
    utils.res.mkdir(backfill_folder)

    # Use current directory if no directory is passed
    if not args.get('directory'):
        directory = os.getcwd()
    # Use the provided directory
    else:
        directory = args['directory']
        if not os.path.isdir(directory):
            print(f"Provided directory '{directory}' does not exist.")
            sys.exit(1)
    
    # Get .srr files in the specified or current directory
    args['files'] = [f for f in os.listdir(directory) if f.endswith(".srr")]

    # If no .srr files found or no arguments passed
    if not args['files']:
        print("No .srr files provided or found in the current directory.")
        sys.exit(1)

    if args['help']:
        print(HELP_TEXT)
        sys.exit(0)

    elif args['version']:
        print(VERSION)
        sys.exit(0)

    # Process backfill only
    elif args['backfill']:
        verbose("\t - Connecting srrdb.com...", end="")
        try:
            s = SRRDB_LOGIN(utils.res.loginUrl, utils.res.loginData, utils.res.loginTestUrl, utils.res.loginTestString)
        except Exception as e:
            verbose(f"{utils.res.FAIL} -> {e}")

        if s and s.logged_in:
            verbose(f"{utils.res.SUCCESS}")
            verbose(f"{utils.res.DARK_YELLOW}* Starting backfill upload:{utils.res.RESET}")
            process_backfill()
        else:
            verbose(f"{utils.res.WARNING} -> Login failed, upload will be anonymous")

    # Upload files
    elif args['files']:
        verbose("\t - Connecting srrdb.com...", end="")
        try:
            s = SRRDB_LOGIN(utils.res.loginUrl, utils.res.loginData, utils.res.loginTestUrl, utils.res.loginTestString)
        except Exception as e:
            verbose(f"{utils.res.FAIL} -> {e}")

        if s and s.logged_in:
            verbose(f"{utils.res.SUCCESS}")
            verbose(f"{utils.res.DARK_YELLOW}* Starting upload:{utils.res.RESET}")
            
            last_upload_successful = False

            for file in args['files']:
                file_path = os.path.join(directory, file)
                uploaded = srr_upload(file_path)
                if uploaded:
                    success_release += 1
                    last_upload_successful = True
                else:
                    last_upload_successful = False

            # If the most recent file upload succeeded, process backfill folder
            if last_upload_successful:
                process_backfill()            
        else:
            verbose(f"{utils.res.WARNING} -> Login failed, upload will be anonymous")

    end_time = time.time()
    elapsed_time = end_time - start_time
    formatted_time = utils.res.format_time(elapsed_time)

    verbose(f"\n{utils.res.DARK_YELLOW}* Upload process complete: {success_release} completed of {scanned_release} scanned in {formatted_time}{utils.res.RESET}")
