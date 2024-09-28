#!/usr/bin/python

from __future__ import print_function
import argparse
import re
import os
import sys
import errno
from colorama import init
import shutil
import zlib
import json
import tempfile
import requests
import time

from utils.connect import SRRDB_LOGIN
from utils.srr import SRR
from utils.srs import SRS
# Pyrescene source need to be installed
from rescene.osohash import compute_hash
import utils.res
import utils.check_rls

# Globals variables
release_list = dict()
missing_files = []
compressed_release = []
scanned_nothing_found = []
rls_check = []
missing_rar = 0

def arg_parse():
    parser = argparse.ArgumentParser(
        description='automated rescening of unrarred/renamed scene files',
        usage=f'{os.path.basename(sys.argv[0])} [--opts] input1 [input2] ...')

    parser.add_argument('input', nargs='*',
                        help='file or directory of files to be parsed', default='')
    parser.add_argument('-a', '--auto-reconstruct', action='store_true',
                        dest="auto_reconstruct",
                        help='full auto rescene - this will scan directories, locate files, '
                        'check srrdb, and a release into a release dir with original rars and '
                        'nfo/sfv/etc and sample, if srs exists - this is the same as -jkx')
    parser.add_argument('-j', '--rescene', action='store_true',
                        help='recreate rars from extracted file/srr')
    parser.add_argument('-k', '--resample', action='store_true',
                        help='recreate sample from original file/srs')
    parser.add_argument('-f', '--find-sample', action='store_true',
                        help='if sample creation fails, look for sample file on disk')
    parser.add_argument('-g', '--resubs', action='store_true',
                        help='look for sub rar if file is missing')
    parser.add_argument('-o', '--output', help='set the directory for all output')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='verbose output for debugging purposes')
    parser.add_argument('--rename', action='store_true',
                        help='rename scene releases to their original scene filenames')
    parser.add_argument('-x', '--extract-stored', action='store_true',
                        help='extract stored files from srr (nfo, sfv, etc)')
    parser.add_argument('-e', '--extension', action='append', default=[],
                        help='list of extensions to check against srrdb '
                        '(default: .mkv, .avi, .mp4, .iso)')
    parser.add_argument('-m', '--min-filesize', help='set a minimum filesize in MB of a file to '
                        'check')
    parser.add_argument('-c', '--check-extras', action='store_true',
                        help='check missing Sample/Proof, this will scan directories, '
                        'check srrdb, and add into a release dir with original rars '
                        'nfo/sfv/proof and recreate sample')
    parser.add_argument('--check-crc', action='store_true',
                        help='check crc in sfv file when using --check-extras')
    parser.add_argument('--keep-srr', action='store_true',
                        help='keep srr in output directory')
    parser.add_argument('--keep-srs', action='store_true',
                        help='keep srs in output directory')
    parser.add_argument('-s', '--search-srrdb', action='store_true',
                        help='check crc against srrdb and print release name')

    return vars(parser.parse_args())

def progress_bar(current, total, bar_length=None):
    # Get terminal width
    if bar_length is None:
        terminal_size = shutil.get_terminal_size()
        # Adjust for files count display
        bar_length = terminal_size.columns - 20

    progress = current / total
    block = int(bar_length * progress)
    bar = '█' * block + '-' * (bar_length - block)

    sys.stdout.write(f'\r|{bar}| {current}/{total} files')
    sys.stdout.flush()

def search_by(search_type, value):
    # Use search type by OSO hash or by CRC
    if search_type == "archive-crc:" and len(value) != 8:
        raise ValueError("CRC must have a length of 8")
    if search_type == "isdbhash:" and not value:
        raise ValueError("Release must have a valid OSO hash")

    search_url = utils.res.SRRDB_API + f"{search_type}{value}"

    try:
        response = s.retrieve_content(search_url)
        data = response.json()
    except Exception as e:
        raise e

    # Check if the search returned any results
    if 'resultsCount' not in data or int(data['resultsCount']) < 1:
        return None

    return data['results']

def calc_crc(fpath):
    # Calculate CRC32 checksum
    if not os.path.isfile(fpath):
        return None

    prev = 0
    with open(fpath, "rb") as file:
        for line in file:
            prev = zlib.crc32(line, prev)

    return f"{prev & 0xFFFFFFFF:08X}"

def calc_oso(fname):
    # Compute OSO hash
    if not os.path.isfile(fname):
        return None

    oso_hash, _ = compute_hash(fname)
    return oso_hash

def copy_file(finput, foutput):
    # Use to copy/rename file or dir
    if not os.path.isfile(finput):
        raise ValueError("finput must be a file")
    if not os.path.isdir(foutput):
        raise ValueError("foutput must be a directory")
    if not os.path.splitext(finput)[1][0] != ".": # Ensure the input has a valid file extension
        return None

    try:
        shutil.copy2(finput, foutput)
    except IOError as e:
        return None, f"Unable to copy/rename file: {e}"

    return True

def find_file(startdir, fname, fcrc):
    # Use to find a file by CRC
    if not os.path.isdir(startdir):
        raise ValueError("startdir must be a directory")

    for root, dirs, files in os.walk(startdir):
        if fname in files:
            file_path = os.path.join(root, fname)
            if calc_crc(file_path) == fcrc.zfill(8): # Sample or Proof found
                return file_path

    return False

def search_srrdb_crc(crc, rlspath):
    # Search srrdb API for releases matching the provided CRC32
    global scanned_nothing_found

    utils.res.verbose("\t - Searching srrdb.com for matching CRC", end="")
    try:
        results = search_by("archive-crc:", crc)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return False

    if not results:
        utils.res.verbose(f"{utils.res.FAIL} -> No matching results")
        scanned_nothing_found.append(rlspath)
        return False
    else:
        utils.res.verbose(f"{utils.res.SUCCESS}")

    # Handle multiple releases having the same CRC32
    if len(results) > 1:
        utils.res.verbose(f"\t\t {utils.res.FAIL} More than one release found matching CRC {crc}.")
        utils.res.verbose("\t - Searching srrdb.com for matching release name", end="")
        try:
            rlsname = os.path.basename(rlspath)
            results = utils.res.search_by_name(rlsname, s, isdir = False)
        except Exception as e:
            utils.res.verbose(f"{utils.res.FAIL} -> {e}")
            return False

        if not results or len(results) > 1: # Handle multiple or 0 releases having the same name, can be the filename used with -vaf or -vs
            utils.res.verbose(f"{utils.res.FAIL} -> No matching results")
            utils.res.verbose("\t - Searching srrdb.com for matching OSO hash", end="")
            try:
                OSOhash = calc_oso(rlspath)
                results = search_by("isdbhash:", OSOhash)
            except Exception as e:
                utils.res.verbose(f"{utils.res.FAIL} -> {e}")
                return False

            if not results or len(results) > 1: # Handle multiple or 0 releases having the same OSO hash
                utils.res.verbose(f"\t\t {utils.res.FAIL} Nothing found or more than one release found matching OSO hash {OSOhash}. Maybe no SRR available on srrdb or you need to check it manually.")
                scanned_nothing_found.append(rlsname)
                return False
            else:
                utils.res.verbose(f"{utils.res.SUCCESS}")
        else:
            utils.res.verbose(f"{utils.res.SUCCESS}")

    release = results[0]
    utils.res.verbose(f"\t\t - Matched release: {release['release']}")

    return release

def search_srrdb_dirname(rlspath):
    # Search srrdb API for release matching the directory name
    global scanned_nothing_found

    utils.res.verbose("\t - Searching srrdb.com for matching release name", end="")
    try:
        rlsname = os.path.basename(rlspath)
        results = utils.res.search_by_name(rlsname, s, isdir = True)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return False

    if not results or len(results) > 1:
        utils.res.verbose(f"{utils.res.FAIL} -> No matching results")
        scanned_nothing_found.append(rlsname)
        return False
    else:
        utils.res.verbose(f"{utils.res.SUCCESS}")

    release = results[0]
    utils.res.verbose(f"\t\t - Matched release: {release['release']}")

    return release

def is_valid_file(args, fpath):
    # Check if the file is in a Sample directory or has an invalid extension etc...
    if os.path.basename(os.path.split(fpath)[0].lower()) == "Sample".lower():
        return False
    if os.path.splitext(fpath)[1].lower() not in args['extension']:
        return False
    if args['min_filesize'] and os.path.getsize(fpath) < args['min_filesize']:
        return False
    return True

def process_crc(args, fpath):
    # This function is used only for potential release to rescene not Sample/Proof CRC calc
    global scanned_release

    utils.res.verbose(f"{utils.res.DARK_YELLOW}* Found potential file:{utils.res.RESET} {os.path.basename(fpath)}")
    utils.res.verbose(f"\t - Calculating crc for file: {fpath}", end="")
    scanned_release += 1
    release_crc = calc_crc(fpath)
    if not release_crc:
        utils.res.verbose(f"{utils.res.FAIL}")
    else:
        utils.res.verbose(f"{utils.res.SUCCESS} -> {release_crc}")
    return release_crc

def search_file(args, fpath):
    # When -vs command is called
    global success_release
    global scanned_release

    if not is_valid_file(args, fpath):
        return False

    release_crc = process_crc(args, fpath)
    if not release_crc:
        return False

    release = search_srrdb_crc(release_crc, fpath)
    if not release:
        return False
    else:
        #keep track of the releases we are processing
        if not release['release'] in release_list:
            release_list[release['release']] = dict()
            release_list[release['release']]['search'] = False
        elif release_list[release['release']]['search']:
            utils.res.verbose("\t - Skipping, already processed.")
            scanned_release -= 1
            return True

    release_list[release['release']]['search'] = True
    success_release += 1
    return True

def process_release_directory(args, release, doutput):
    # Ensure the output directory matches the release name
    if os.path.basename(doutput.lower()) != release['release'].lower():
        doutput = os.path.join(doutput, release['release'])
        if not os.path.isdir(doutput):
            utils.res.verbose(f"\t - Creating output directory: {doutput}", end="")
            try:
                utils.res.mkdir(doutput)
            except Exception as e:
                utils.res.verbose(f"{utils.res.FAIL} -> Unable to create directory: {e}")
                return False
            else:
                utils.res.verbose(f"{utils.res.SUCCESS}")
    utils.res.verbose(f"\t - Setting output directory to: {doutput}")
    return doutput

def download_srr(release):
    # Download .srr file from srrdb.com
    utils.res.verbose("\t - Downloading SRR from srrdb.com", end="")
    try:
        srr_path = utils.res.download_srr(release, s)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return None
    else:
        utils.res.verbose(f"{utils.res.SUCCESS}")
        return srr_path

def rename_file_if_needed(fpath, doutput, srr_finfo):
    # Only when --rename command is called
    if len(srr_finfo) != 1:
        return False
    if srr_finfo[0].file_name != os.path.basename(fpath):
        utils.res.verbose(f"\t\t - file has been renamed, renaming to: {srr_finfo[0].file_name}", end="")
        (ret, mesg) = copy_file(fpath, os.path.join(doutput, srr_finfo[0].file_name))
        if not ret:
            utils.res.verbose(f"{utils.res.FAIL} -> {mesg}")
        else:
            utils.res.verbose(f"{utils.res.SUCCESS}")

def extract_stored_files(release_srr, doutput, release, srr_finfo):
    # Extract stored files from .srr file based on regex filter
    utils.res.verbose("\t - Extracting stored files from SRR")
    regex = r"^(?i:(?:(.+\.)((?!txt$)[^.]*)|[^.]+))$" if srr_finfo else r"^(?i:(?:(.+\.)((?!srs$)[^.]*)|[^.]+))$"
    try:
        matches = release_srr.extract_stored_files_regex(doutput, regex=regex)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return False
    else:
        srs_path = None
        proof_path = None
        # Save path for Sample/Proof and fix crashed when multiple .srs or Proofs
        for match in matches:
            utils.res.verbose(f"\t\t - {os.path.relpath(match[0], doutput)}{utils.res.SUCCESS}")
            if srs_path is None and match[0].lower().endswith(".srs"):
                srs_path = match[0]
            if proof_path is None and match[0].lower().endswith((".jpg", ".jpeg", ".png")):
                proof_path = match[0]

        # Check if subtitle directories exist
        sub_dirs = ["Sub", "Subs", "Subpack", "Subtitles"]
        if not any(os.path.exists(os.path.join(doutput, sub_dir)) for sub_dir in sub_dirs):
            release_list[release['release']]['resubs'] = True

    release_list[release['release']]['extract'] = True
    return srs_path, proof_path

def reconstruct_rars(args, release_srr, fpath, doutput, srr_finfo, release):
    # Attempt to reconstruct original RARs from .srr only for releases not Subs
    global success_release
    global missing_rar

    utils.res.verbose("\t - Reconstructing original RARs from SRR", end="")
    rename_hints = {srr_finfo[0].file_name: os.path.basename(fpath)}

    try:
        if release_srr.get_is_compressed():
            utils.res.verbose(f"\n\t - {utils.res.WARNING} -> RAR Compression is used, reconstruction may not work")
        release_srr.reconstruct_rars(os.path.dirname(fpath), doutput, rename_hints, utils.res.RAR_VERSION, utils.res.SRR_TEMP_FOLDER)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        missing_rar += 1
        if release_srr.get_is_compressed():
            compressed_release.append(release['release'])
    else:
        utils.res.verbose(f"{utils.res.SUCCESS}")

    release_list[release['release']]['rescene'] = True
    if missing_rar == 0:
        success_release += 1
    missing_rar = 0

def recreate_sample(args, release, release_srr, fpath, doutput, srs_path):
    if not srs_path:
        # Extract .srs file if something going wrong when we save the path before
        utils.res.verbose("\t\t - Extracting SRS from SRR file for Sample reconstruction", end="")
        release_srs = release_srr.get_srs(doutput)
        if not release_srs:
            utils.res.verbose(f"\t - No SRS found for sample recreation {utils.res.FAIL}")
            return
        elif len(release_srs) > 1:
            utils.res.verbose(f"{utils.res.FAIL} -> more than one SRS in this SRR. Please reconstruct manually.")
            return None
        else:
            srs_path = release_srs[0]
            utils.res.verbose(f"{utils.res.SUCCESS}")

    sample = SRS(srs_path)
    utils.res.verbose("\t - Recreating Sample .. expect output from SRS\n-------------------------------")
    try:
        sample.recreate(fpath, os.path.dirname(srs_path))
    except Exception as e:
        utils.res.verbose("-------------------------------")
        utils.res.verbose(f"\t - {utils.res.FAIL} -> failed to recreate sample: {e}.")
        if os.path.exists(fpath):
            try:
                utils.res.verbose("\t We can try with ReSample .NET 1.2 sometimes it can work...")
                output, error, fail = utils.res.run_resample_net_executable(utils.res.SRS_NET_EXE, srs_path, fpath, "-o", os.path.dirname(srs_path))

                if fail == True:
                    utils.res.verbose(f"\t - {utils.res.FAIL} -> failed to recreate sample with ReSample .NET 1.2.")

            except Exception as e:
                utils.res.verbose(f"\t - {utils.res.FAIL} -> failed to recreate sample with ReSample .NET 1.2: {e}.")

        # Attempt to find the sample on local disk if recreation fails when -vaf or -f command is called
        if args['find_sample']:
            utils.res.verbose("\t - Searching for sample on local disk")
            sample_file = find_file(os.path.dirname(fpath), sample.get_filename(), sample.get_crc())
            if sample_file:
                utils.res.verbose(f"\t\t - {utils.res.SUCCESS} - Found sample -> {sample_file}")
                try:
                    shutil.move(sample_file, os.path.dirname(srs_path))
                    if not args['keep_srs'] and os.path.exists(srs_path):
                        os.remove(srs_path)
                except Exception as e:
                    utils.res.verbose(f"\t\t - {utils.res.FAIL} - Could not copy file to {os.path.dirname(srs_path)} -> {e}")
                    missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
                    if not args['keep_srs'] and os.path.exists(srs_path):
                        os.remove(srs_path)
            else:
                missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
                if not args['keep_srs'] and os.path.exists(srs_path):
                    os.remove(srs_path)
        else:
            missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
            if not args['keep_srs'] and os.path.exists(srs_path):
                os.remove(srs_path)
    else:
        utils.res.verbose("-------------------------------")
        utils.res.verbose(f"\t - {utils.res.SUCCESS} -> sample recreated successfully")
        if not args['keep_srs']:
            if os.path.exists(srs_path):
                os.remove(srs_path)
            else:
                utils.res.verbose("\t - Impossible to delete no SRS found %s" % (utils.res.FAIL))

    release_list[release['release']]['resample'] = True

def find_sub_files_by_extension(root_dir, extension):
    # Search for all files with a specific extension in a directory tree
    matching_files = []

    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(extension):
                matching_files.append(os.path.join(root, file))

    return matching_files

def get_first_rar_name(rar_names):
    # Get the first .rar file name inside .srr, needed if we have .rar inside .rar for Subs
    for rarn in rar_names:
        if rarn.lower().endswith(".rar"):
            return rarn
    return None

def get_second_srr(matches):
    # Get a list of all .srr files exctracted, needed if we have .rar inside .rar for Subs
    return [match[0] for match in matches if match[0].lower().endswith(".srr")]

def search_sub_by_archived_files(subs_srr_file, sub_file, idx_file):
    # Searches for Subs by comparing the file names in sub_file and idx_file
    # with the archived names from subs_srr_2. If no matches are found, the function
    # calculates the CRCs of sub_file and idx_file and searches for match in the archived_files of SRR.
    archived_name = []
    archived_names_to_search = []
    archived_name = subs_srr_file.get_archived_fname() # Will contains .idx/.sub filename

    # Loop through the list of .sub filenames to search for
    for archived_fname in archived_name:
        for full_path in sub_file:
            # Extract the the full path
            if archived_fname == os.path.basename(full_path):
                archived_names_to_search.append(full_path)

    # If no result search for .idx files
    if len(archived_names_to_search) == 0:
        for archived_fname in archived_name:
            for full_path in idx_file:
                if archived_fname == os.path.basename(full_path):
                    archived_names_to_search.append(full_path)

    # If still no results, search based on CRC
    if len(archived_names_to_search) == 0:
        crc_archived = subs_srr_file.get_archived_crc()
        matched_sub_files = []
        matched_idx_files = []
        for sub_file_paths, idx_file_paths in zip(sub_file, idx_file):
            sub_crc = calc_crc(sub_file_paths)
            idx_crc = calc_crc(idx_file_paths)
            if sub_crc in crc_archived:
                matched_sub_files.append(sub_file_paths)
            if idx_crc in crc_archived:
                matched_idx_files.append(idx_file_paths)

        archived_names_to_search = matched_sub_files + matched_idx_files

    return archived_names_to_search, archived_name

def reconstruct_rar(srr, file, alt_file, rename_hints=None):
    # Function used to reconstruct every Subs .rar
    if rename_hints is None:
        rename_hints = {srr.filename: os.path.basename(file[0])}

    utils.res.verbose("\t - Reconstructing RAR", end="")
    try:
        if srr.get_is_compressed():
            utils.res.verbose(f"\n\t - {utils.res.WARNING} -> RAR Compression is used, reconstruction may not work")

        srr.reconstruct_rars(os.path.dirname(file[0]), os.path.dirname(srr.filename), rename_hints, utils.res.RAR_VERSION, utils.res.SRR_TEMP_FOLDER)
        utils.res.verbose(f"{utils.res.SUCCESS}")
        return True
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return False

def reconstruct_rars_pair(subs_srr, sub_srr_2, sub_file, idx_file):
    # Function used to reconstruct in the good order Subs .rar inside Subs .rar
    success = False
    rar_name_2 = []

    # Reconstruct the .rar inside the .rar first if more than one .srr is found
    for all_srr_files in sub_srr_2:
        archived_names_to_search = []
        archived_name = []
        search_sub_by_archived_files
        subs_srr_2 = SRR(all_srr_files)
        rar_name_2.append(get_first_rar_name(subs_srr_2.get_rars_name()))
        archived_names_to_search, archived_name = search_sub_by_archived_files(subs_srr_2, sub_file, idx_file)

        rename_hints_subs = {os.path.basename(archived_names_to_search[0]): archived_name[0]}
        pair_success = reconstruct_rar(subs_srr_2, archived_names_to_search, idx_file, rename_hints_subs)
        success = success or pair_success

    if success:
        # Reconstruct the second RAR if we have multiple .rar inside the Subs .rar
        if len(sub_srr_2) > 1:
            utils.res.verbose("\t - Reconstructing second RAR for Subs")
            rename_hints_subs = {rar_name_2[0]: rar_name_2[0]}
            reconstruct_rar(subs_srr, [os.path.join(os.path.dirname(sub_srr_2[0]), rar_name_2[0])], sub_file, rename_hints_subs)
        # Reconstruct the second RAR if we have one .rar inside the Subs .rar
        else:
            archived_names_to_search = []
            archived_name = []
            archived_names_to_search, archived_name = search_sub_by_archived_files(subs_srr, sub_file, idx_file)

            rename_hints_subs = {archived_name[0]: archived_name[0]}
            utils.res.verbose("\t - Reconstructing second RAR for Subs")
            reconstruct_rar(subs_srr, archived_names_to_search, sub_file, rename_hints_subs)

    return rar_name_2, success

def extract_and_reconstruct_rars(sub_srr, sub_file, idx_file):
    # Initialize an SRR object for the first Subs .srr file
    subs_srr = SRR(sub_srr)
    rar_name = get_first_rar_name(subs_srr.get_rars_name())

    # Something is wrong
    if not rar_name:
        return False

    # Extract all stored files from the .srr with the regex filter, if we have Subs .rar inside .rar we will have one or multiple .rar exctracted
    utils.res.verbose("\t - Extracting stored files from Subs SRR", end="")
    try:
        matches = subs_srr.extract_stored_files_regex(os.path.dirname(sub_srr), regex=r"^(?i:(?:(.+\.)((?!diz$)[^.]*)|[^.]+))$")
        utils.res.verbose(f"{utils.res.SUCCESS}")
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")
        return False

    all_srr_files = get_second_srr(matches)
    success = False

    # If we there are .rar inside .rar we need to have the path of every others .srr files
    if all_srr_files:
        rar_name_2 = None

        rar_name_2, pair_success = reconstruct_rars_pair(subs_srr, all_srr_files, sub_file, idx_file)
        success = success or pair_success
        if not args['keep_srr']: # Clean every .srr and .rar who are inside .rar
            files_to_delete = [sub_srr] + all_srr_files + [os.path.join(os.path.dirname(sub_srr), file) for file in rar_name_2]
            for file in files_to_delete:
                if os.path.exists(file):
                    os.remove(file)

        return success
    else:
        # If no secondary SRR files are found, that mean that .sub and .idx files are inside it
        archived_names_to_search = []
        archived_name = []
        archived_names_to_search, archived_name = search_sub_by_archived_files(subs_srr, sub_file, idx_file)

        rename_hints_subs = {os.path.basename(archived_names_to_search[0]): archived_name[0]}
        return reconstruct_rar(subs_srr, archived_names_to_search, sub_file, rename_hints_subs)

def cleanup_files(args, release, sub_srr):
    if not args['keep_srr']:
        # Ensure sub_srr is a list; if it's a string, convert it to a list
        if isinstance(sub_srr, str):
            sub_srr = [sub_srr]

        for file in sub_srr:
            if file and os.path.exists(file):
                os.remove(file)

def generate_relative_path(fpath, sfv_p, filename):
    # Generate a relative path based on the given parameters, to print RELEASE\Sub(s)\subs_rar.rar or RELEASE\subs_rar.rar
    base_dir = os.path.basename(fpath)
    if sfv_p == base_dir:
        return os.path.relpath(os.path.join(fpath, filename), os.path.dirname(fpath))
    else:
        return os.path.relpath(os.path.join(fpath, sfv_p, filename), os.path.dirname(fpath))

def add_to_missing_files(fpath, sfv_p, filename):
    # Add the relative path to the missing files list if it's not already present
    global missing_rar
    global missing_files

    relative_path = generate_relative_path(fpath, sfv_p, filename)
    if relative_path.lower() not in [f.lower() for f in missing_files]:
        missing_files.append(relative_path)
        missing_files = list(dict.fromkeys(missing_files)) # Remove duplicates
        missing_rar += 1

def remove_from_missing_files(fpath, sfv_p, full_path):
    # Remove the relative path from the missing files list if we have successfully founded it or rebuilded it
    global missing_files

    relative_path = generate_relative_path(fpath, sfv_p, os.path.basename(full_path))
    missing_files[:] = [f for f in missing_files if f.lower() != relative_path.lower()]

def fix_missing_file(full_path, filename, crc, sfv_p, fpath, sub_srr, sfv_file, args, release):
    # Attempt to find the missing Subs .rar file on the local disk with CRC, can be in right place but not with good name
    utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Be careful missing Subs file: {filename}")
    utils.res.verbose("\t - Searching for Subs on local disk")

    subs_file = find_file(os.path.dirname(fpath), filename, crc.upper())
    if subs_file:
        utils.res.verbose(f"\t\t - {utils.res.SUCCESS} - Found Subs -> {subs_file}")
        try:
            shutil.move(subs_file, os.path.dirname(sfv_file))
            cleanup_files(args, release, sub_srr)
            return True
        except Exception as e:
            utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Could not copy file to {os.path.dirname(sfv_file)} -> {e}")
    else:
        utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Subs RAR not found")

    # Handling missing file scenario
    add_to_missing_files(fpath, sfv_p, filename)
    return False

def validate_crc(full_path, fpath, sfv_p, expected_crc):
    # Final check after we try to rebuilt it or search it, exept with -vc or -vc --check-crc we try it first
    hash_crc = calc_crc(full_path)
    if not hash_crc:
        hash_crc = ""

    if hash_crc.lower() == expected_crc.lower():
        utils.res.verbose(f"\t\t - {utils.res.SUCCESS} -> {os.path.basename(full_path)} {hash_crc.upper()}")
        # Remove the relative path from missing_files if it exists or finally rebuilded or founded
        remove_from_missing_files(fpath, sfv_p, full_path)
        return True
    else:
        utils.res.verbose(f"\t\t - {utils.res.FAIL} -> {os.path.basename(full_path)} our hash {hash_crc.upper()} does not match {expected_crc.upper()}")
        # Add the relative path to missing_files if not already present
        add_to_missing_files(fpath, sfv_p, os.path.basename(full_path))
        return False

def check_crc_and_fix(sfv_file, fpath, sub_srr, sub_file, idx_file, args, release):
    # Open and read the Subs .sfv file line by line
    utils.res.verbose(f"\t - Checking if RAR for Subs have good CRC in {os.path.dirname(sfv_file)}")
    try:
        with open(sfv_file, "r") as sfv_f:
            sfv_p = os.path.dirname(sfv_file)
            for line in sfv_f:
                if line[0] == ';':
                    continue
                filename, _, crc = line.rstrip().rpartition(' ')
                if not filename or not crc:
                    continue
                full_path = os.path.join(fpath, os.path.join(sfv_p, filename))
                if not os.path.exists(full_path):
                    return fix_missing_file(full_path, filename, crc, sfv_p, fpath, sub_srr, sfv_file, args, release) # Subs .rar missing we try to find it
                else:
                    return validate_crc(full_path, fpath, sfv_p, crc) # Subs .rar exist we need to check his CRC

    except Exception as e:
        utils.res.verbose(f"\t\t - {utils.res.FAIL} - Could not open SFV file {sfv_file} -> {e}")
        return False

def find_sub_files(doutput, fpath):
    # Function to search and save the path of every .sub, .idx and .srr file
    sub_srr = []
    sub_file = []
    idx_file = []

    # List all directories in doutput
    all_dirs = [d for d in os.listdir(doutput) if os.path.isdir(os.path.join(doutput, d))]

    # Create a dictionary with lowercase names for case-insensitive lookup
    all_dirs_lower = {d.lower(): d for d in all_dirs}

    for sub_dir in ["Sub", "Subs", "Subpack", "Subtitles"]:
        sub_dir_lower = sub_dir.lower()

        # Check if there's a case-insensitive match
        if sub_dir_lower in all_dirs_lower:
            # Get the actual directory name with its original casing
            actual_sub_dir = all_dirs_lower[sub_dir_lower]
            sub_dir_path = os.path.join(doutput, actual_sub_dir)

            # Verify if the path exists
            if os.path.exists(sub_dir_path):
                sub_srr = find_sub_files_by_extension(sub_dir_path, ".srr")

    sub_file = find_sub_files_by_extension(os.path.dirname(fpath), ".sub")
    idx_file = find_sub_files_by_extension(os.path.dirname(fpath), ".idx")

    return sub_srr, sub_file, idx_file

def process_subtitles(args, fpath, doutput, release):
    # Function to manage the start of Subs reconstruction only with -vaf or --resubs
    sub_srr = []
    sub_file = []
    idx_file = []
    sub_srr, sub_file, idx_file = find_sub_files(doutput, fpath)

    if not all([sub_srr, sub_file, idx_file]):
        return False

    utils.res.verbose("\t - Reconstructing original RARs for Subs")
    # List all directories in doutput
    all_dirs = [d for d in os.listdir(doutput) if os.path.isdir(os.path.join(doutput, d))]

    # Create a dictionary with lowercase names for case-insensitive lookup
    all_dirs_lower = {d.lower(): d for d in all_dirs}

    # Search and save the path of the Subs .sfv file
    sub_sfv = []
    for sub_dir in ["Sub", "Subs", "Subpack", "Subtitles"]:
        sub_dir_lower = sub_dir.lower()

        # Check if there's a case-insensitive match
        if sub_dir_lower in all_dirs_lower:
            # Get the actual directory name with its original casing
            actual_sub_dir = all_dirs_lower[sub_dir_lower]
            sub_dir_path = os.path.join(doutput, actual_sub_dir)

            # Verify if the path exists
            if os.path.exists(sub_dir_path):
                sub_sfv = find_sub_files_by_extension(sub_dir_path, ".sfv")

    if not sub_sfv or not any(os.path.exists(sfv) for sfv in sub_sfv):
        utils.res.verbose(f"\t - SFV file not found: {sub_sfv}")
        return False

    for srr_file in sub_srr:
        extract_and_reconstruct_rars(srr_file, sub_file, idx_file) # We try to rebuild first

    for sfv_file in sub_sfv:
        check_crc_and_fix(sfv_file, fpath, sub_srr, sub_file, idx_file, args, release) # If rebuild success or failed can search or calc CRC

    cleanup_files(args, release, sub_srr) # Clean everything
    release_list[release['release']]['resubs'] = True

def check_file(args, fpath):
    # Main function for -vaf or every single --rename, --rescene, etc... commands
    global missing_rar
    global success_release
    global scanned_release
    global rls_check

    if not is_valid_file(args, fpath):
        return False

    if args['output']:
        doutput = args['output']
    else:
        doutput = os.path.dirname(fpath)

    missing_rar = 0
    release_crc = process_crc(args, fpath)
    if not release_crc:
        return False

    release = search_srrdb_crc(release_crc, fpath)
    if not release:
        return False
    else:
        #keep track of the releases we are processing
        if not release['release'] in release_list:
            release_list[release['release']] = dict()
            release_list[release['release']]['rescene'] = False
            release_list[release['release']]['resample'] = False
            release_list[release['release']]['extract'] = False
            release_list[release['release']]['resubs'] = False
        elif release_list[release['release']]['rescene'] and release_list[release['release']]['extract'] and release_list[release['release']]['resample'] and release_list[release['release']]['resubs']:
            utils.res.verbose("\t - Skipping, already processed.")
            scanned_release -= 1
            return True

    release_douput = process_release_directory(args, release, doutput)
    srr_path = download_srr(release['release'])
    if not srr_path:
        return False

    release_srr = SRR(srr_path)
    srr_finfo = release_srr.get_archived_fname_by_crc(release_crc)

    if args['rename']:
        rename_file_if_needed(fpath, release_douput, srr_finfo)

    if (args['extract_stored'] or args['auto_reconstruct']) and not release_list[release['release']]['extract']:
        srs, proof = extract_stored_files(release_srr, release_douput, release, release_srr.get_rars_name())

    if (args['rescene'] or args['auto_reconstruct']) and not release_list[release['release']]['rescene']:
        reconstruct_rars(args, release_srr, fpath, release_douput, srr_finfo, release)

    if (args['resample'] or args['auto_reconstruct']) and not release_list[release['release']]['resample']:
        if release['hasSRS'] != "yes":
            utils.res.verbose(f"\t - No SRS found for sample recreation {utils.res.FAIL}")
            release_list[release['release']]['resample'] = True
        else:
            recreate_sample(args, release, release_srr, fpath, release_douput, srs)

    if (args['resubs'] or args['auto_reconstruct']) and not release_list[release['release']]['resubs']:
        process_subtitles(args, fpath, release_douput, release)

    if missing_rar > 0:
        success_release -= 1

    chk = utils.check_rls.run_checks(release_douput)
    for c in chk:
        utils.res.verbose(c)
    rls_check.extend(chk)

def handle_rar_check(fpath, release_srr, release, srr_finfo):
    # Function if -vc command called, we check only the presence of every files inside the .srr
    global missing_rar
    global success_release

    # If its a RAR release
    if srr_finfo:
        utils.res.verbose(f"\t - Checking if all RAR are present in {fpath}")
        for match in srr_finfo:
            full_match_path = os.path.join(fpath, os.path.normpath(match))
            if not os.path.exists(full_match_path):
                utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Be careful missing RAR file: {os.path.normpath(match)}")
                missing_files.append(os.path.join(release['release'], os.path.normpath(match)))
                missing_rar += 1
            else:
                utils.res.verbose(f"\t\t - {utils.res.SUCCESS} -> {os.path.normpath(match)}")

    # If its a music/mvid release
    else:
        utils.res.verbose(f"\t - Checking if all files are present in {fpath}")
        srr_sfv_info = release_srr.get_sfv_entries_name()
        for match in srr_sfv_info:
            full_match_path = os.path.join(fpath, os.path.normpath(match))
            if not os.path.exists(full_match_path):
                utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Be careful missing file: {os.path.normpath(match)}")
                missing_files.append(os.path.join(release['release'], os.path.normpath(match)))
                missing_rar += 1
            else:
                utils.res.verbose(f"\t\t - {utils.res.SUCCESS} -> {os.path.normpath(match)}")

    release_list[release['release']]['rescene'] = True
    if missing_rar == 0:
        success_release += 1
    missing_rar = 0

def handle_crc_check(fpath, release_srr, release, srr_finfo):
    # Function if -vc --check-crc command called, we check CRC present inside the .sfv so we can handle both, RAR release or music/mvid release
    global missing_rar
    global success_release

    stored_files = release_srr.get_stored_files_name()
    sfv_paths = [os.path.join(fpath, os.path.normpath(fname)) for fname in stored_files if fname.endswith(".sfv")]

    utils.res.verbose(f"\t - Checking if all RAR have good CRC in {fpath}")
    for sfv in sfv_paths:
        try:
            with open(sfv, "r") as sfv_f:
                sfv_p = os.path.dirname(sfv)
                for line in sfv_f:
                    if line.startswith(';'):
                        continue
                    filename, _, crc = line.rstrip().rpartition(' ')
                    if not filename or not crc:
                        continue

                    full_file_path = os.path.join(sfv_p, filename)
                    if not os.path.exists(full_file_path):
                        utils.res.verbose(f"\t\t - {utils.res.FAIL} -> Be careful missing RAR file: {filename}")
                        add_to_missing_files(fpath, sfv_p, filename)
                        continue
                    hash = calc_crc(full_file_path)
                    if not hash:
                        hash = ""
                    if hash.lower() == crc.lower():
                        utils.res.verbose(f"\t\t - {utils.res.SUCCESS} -> {filename} {hash.upper()}")
                    else:
                        utils.res.verbose(f"\t\t - {utils.res.FAIL} -> {filename} our hash {hash.upper()} does not match {crc.upper()}")
                        add_to_missing_files(fpath, sfv_p, filename)

        except Exception as e:
            utils.res.verbose(f"\t\t - {utils.res.FAIL} - Could not open sfv file {sfv} -> {e}")
            continue

    release_list[release['release']]['rescene'] = True
    if missing_rar == 0:
        success_release += 1
    missing_rar = 0

def handle_sample_reconstruction(args, release_srr, release, fpath, srs_path, doutput, srr_finfo):
    # When -vc is called with or without --check-crc we try to find the sample first but we need the .srs file to have his CRC
    if not srs_path:
        utils.res.verbose("\t\t - Extracting SRS from SRR file for Sample reconstruction", end="")
        release_srs = release_srr.get_srs(doutput)
        if not release_srs:
            utils.res.verbose(f"\t - No SRS found for sample recreation %s {utils.res.FAIL}")
            return None
        elif len(release_srs) != 1:
            utils.res.verbose(f"{utils.res.FAIL} -> more than one SRS in this SRR. Please reconstruct manually.")
            return None
        else:
            srs_path = release_srs[0]
            utils.res.verbose(f"{utils.res.SUCCESS}")

    if srs_path:
        sample = SRS(srs_path)
        utils.res.verbose("\t - Searching for sample on local disk")
        sample_file = find_file(os.path.dirname(fpath), sample.get_filename(), sample.get_crc())
        if sample_file:
            utils.res.verbose(f"\t\t - {utils.res.SUCCESS} - Found sample -> {sample_file}")
            if os.path.dirname(sample_file.lower()) != os.path.dirname(srs_path.lower()): # We found it but it can be rename or not in the good place
                try:
                    shutil.move(sample_file, os.path.dirname(srs_path))
                    release_list[release['release']]['resample'] = True
                    if not args['keep_srs'] and os.path.exists(srs_path):
                        os.remove(srs_path)
                except Exception as e:
                    utils.res.verbose(f"\t\t - {utils.res.FAIL} - Could not copy file to {os.path.dirname(srs_path)} -> {e}")
                    missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
                    if not args['keep_srs'] and os.path.exists(srs_path):
                        os.remove(srs_path)
            else:
                if not args['keep_srs'] and os.path.exists(srs_path):
                    os.remove(srs_path)
        else:
            utils.res.verbose(f"\t - Sample found have Bad CRC or no sample found {utils.res.FAIL}")
            utils.res.verbose("\t - Recreating Sample .. expect output from SRS\n-------------------------------")
            try:
                sample.recreate(os.path.join(fpath, srr_finfo[0]), os.path.dirname(srs_path))
            except Exception as e:
                utils.res.verbose(f"-------------------------------\n\t - {utils.res.FAIL} -> failed to recreate sample: {e}.")
                if os.path.exists(os.path.join(fpath, srr_finfo[0])):
                    try:
                        utils.res.verbose("\t We can try with ReSample .NET 1.2 sometimes it can work...")
                        output, error, fail = utils.res.run_resample_net_executable(utils.res.SRS_NET_EXE, srs_path, os.path.join(fpath, srr_finfo[0]), "-o", os.path.dirname(srs_path))

                        if fail == True:
                            utils.res.verbose(f"\t - {utils.res.FAIL} -> failed to recreate sample with ReSample .NET 1.2.")
                            missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
                            if not args['keep_srs'] and os.path.exists(srs_path):
                                os.remove(srs_path)

                    except Exception as e:
                        utils.res.verbose(f"\t - {utils.res.FAIL} -> failed to recreate sample with ReSample .NET 1.2: {e}.")
                        missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(srs_path)), sample.get_filename()))
                        if not args['keep_srs'] and os.path.exists(srs_path):
                            os.remove(srs_path)
                else:
                    if not args['keep_srs'] and os.path.exists(srs_path):
                        os.remove(srs_path)
            else:
                utils.res.verbose("-------------------------------")
                utils.res.verbose(f"\t - {utils.res.SUCCESS} -> sample recreated successfully")
                release_list[release['release']]['resample'] = True
                if not args['keep_srs'] and os.path.exists(srs_path):
                    os.remove(srs_path)

def check_proof_and_sample(args, release_srr, release, fpath, proof_path, srs_path, doutput, srr_finfo):
    # Function to search, check or find the Proof
    if proof_path:
        utils.res.verbose("\t - Searching for Proof on local disk")
        proof_crc = calc_crc(proof_path)
        proof_file = find_file(os.path.dirname(fpath), os.path.basename(*release_srr.get_proof_filename()), proof_crc) # We use CRC to find the .jpg
        if proof_file and proof_file.lower() == proof_path.lower():
            utils.res.verbose(f"\t\t - {utils.res.SUCCESS} - Found proof -> {proof_file}")
        if proof_file and proof_file.lower() != proof_path.lower(): # We found it but maybe the Proof is renamed or not in the right place
            utils.res.verbose(f"\t\t - {utils.res.SUCCESS} - Found proof -> {proof_file}")
            try:
                copy_file(proof_file, os.path.dirname(proof_path))
                if not args['keep_srs'] and os.path.exists(proof_file):
                    os.remove(proof_file)
            except Exception as e:
                utils.res.verbose(f"\t\t - {utils.res.FAIL} - Could not copy proof file to {os.path.dirname(proof_path)} -> {e}")
                missing_files.append(os.path.join(release['release'], os.path.basename(os.path.dirname(proof_path)), release_srr.get_proof_filename()))

    # We can know if the .srr file have .srs inside or not
    if release['hasSRS'] == "yes" and srr_finfo:
        handle_sample_reconstruction(args, release_srr, release, fpath, srs_path, doutput, srr_finfo)

def check_subtitles(args, fpath, doutput, release):
    # Function to manage the check of the Subs .rar
    sub_srr = []
    sub_file = []
    idx_file = []
    sub_srr, sub_file, idx_file = find_sub_files(doutput, fpath)

    # List all directories in doutput
    all_dirs = [d for d in os.listdir(doutput) if os.path.isdir(os.path.join(doutput, d))]

    # Create a dictionary with lowercase names for case-insensitive lookup
    all_dirs_lower = {d.lower(): d for d in all_dirs}

    sub_sfv = []
    for sub_dir in ["Sub", "Subs", "Subpack", "Subtitles"]:
        sub_dir_lower = sub_dir.lower()

        # Check if there's a case-insensitive match
        if sub_dir_lower in all_dirs_lower:
            # Get the actual directory name with its original casing
            actual_sub_dir = all_dirs_lower[sub_dir_lower]
            sub_dir_path = os.path.join(doutput, actual_sub_dir)

            # Verify if the path exists
            if os.path.exists(sub_dir_path):
                sub_sfv = find_sub_files_by_extension(sub_dir_path, ".sfv")

    # We can't know in an other way that find a .sfv file inside a Subs dir if the release have a Subs or not
    if not sub_sfv or not any(os.path.exists(sfv) for sfv in sub_sfv):
        release_list[release['release']]['resubs'] = True
        return # Maybe the release don't have a Subs .rar

    for sfv_file in sub_sfv:
        if not check_crc_and_fix(sfv_file, fpath, sub_srr, sub_file, idx_file, args, release): # Check CRC failed
            for _ in sub_srr:
                process_subtitles(args, fpath, doutput, release) # We launch the rebuild from the start function exactly like -vaf

    cleanup_files(args, release, sub_srr) # Clean .srr etc...

def check_dir(args, fpath):
    # Main function for -vc and -vc --check-crc command
    global missing_rar
    global success_release
    global scanned_release
    global rls_check

    # We don't want to check these dirs
    pattern = r'(dvd|cd|dis[ck])[0-9][0-9]?|samples?|proofs?|subs?|subpacks?|subtitles?'
    if re.search(pattern, os.path.basename(fpath), re.IGNORECASE):
        return False

    if args['output']:
        doutput = args['output']
    else:
        doutput = os.path.dirname(fpath)

    utils.res.verbose(f"{utils.res.DARK_YELLOW}* Found potential release:{utils.res.RESET} {os.path.basename(fpath)}")
    scanned_release += 1
    release = search_srrdb_dirname(fpath)
    if not release:
        return False
    else:
        #keep track of the releases we are processing
        if not release['release'] in release_list:
            release_list[release['release']] = dict()
            release_list[release['release']]['rescene'] = False
            release_list[release['release']]['resample'] = False
            release_list[release['release']]['extract'] = False
            release_list[release['release']]['resubs'] = False
        elif release_list[release['release']]['rescene'] and release_list[release['release']]['extract'] and release_list[release['release']]['resample'] and release_list[release['release']]['resubs']:
            utils.res.verbose("\t - Skipping, already processed.")
            scanned_release -= 1
            return True

    release_douput = process_release_directory(args, release, doutput)
    srr_path = download_srr(release['release'])
    if not srr_path:
        return False

    release_srr = SRR(srr_path)
    srr_finfo = release_srr.get_rars_name()
    missing_rar = 0

    if args['check_extras']:
        if not args['check_crc']:
            handle_rar_check(fpath, release_srr, release, srr_finfo)
        else:
            handle_crc_check(fpath, release_srr, release, srr_finfo)

        srs_path, proof_path = extract_stored_files(release_srr, release_douput, release, srr_finfo)
        check_proof_and_sample(args, release_srr, release, fpath, proof_path, srs_path, release_douput, srr_finfo)
        check_subtitles(args, fpath, release_douput, release)

    if missing_rar > 0:
        success_release -= 1

    chk = utils.check_rls.run_checks(fpath)
    for c in chk:
        utils.res.verbose(c)
    rls_check.extend(chk)

def traverse_directories(input_paths, valid_extensions, process_file_func, use_progress_bar=False):
    # Function to traverse directories
    total_items = 0
    if use_progress_bar:
        for path in input_paths:
            if os.path.isfile(path):
                if os.path.splitext(path)[1].lower() in valid_extensions:
                    total_items += 1
            elif os.path.isdir(path):
                for _, _, files in os.walk(path):
                    total_items += sum(1 for f in files if os.path.splitext(f)[1].lower() in valid_extensions)

    current_item_count = 0
    for path in input_paths:
        if os.path.isfile(path):
            if os.path.splitext(path)[1].lower() in valid_extensions:
                process_file_func(path)
                if use_progress_bar:
                    current_item_count += 1
                    progress_bar(current_item_count, total_items)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if os.path.splitext(file)[1].lower() in valid_extensions:
                        process_file_func(os.path.join(root, file))
                        if use_progress_bar:
                            current_item_count += 1
                            progress_bar(current_item_count, total_items)

if __name__ == "__main__":
    args = arg_parse()
    # initialize pretty colours
    init()
    success_release = 0
    scanned_release = 0

    # Set the verbose flag to True to show srrdb connection
    utils.res.set_verbose_flag(True)

    if not args['extension']:
        args['extension'] = ['.mkv', '.avi', '.mp4', '.iso']
    if args['min_filesize']:
        #convert from MB to Bytes
        args['min_filesize'] = int(args['min_filesize']) * 1048576

    if args['output']:
        if not os.path.isdir(args['output']):
            sys.exit("output option needs to be a valid directory")
        utils.res.verbose(f"Setting output directory to: {args['output']}\n")

    utils.res.verbose("\t - Connecting srrdb.com...", end="")
    try:
        s = SRRDB_LOGIN(utils.res.loginUrl, utils.res.loginData, utils.res.loginTestUrl, utils.res.loginTestString)
    except Exception as e:
        utils.res.verbose(f"{utils.res.FAIL} -> {e}")

    if s and s.logged_in:
        utils.res.verbose(f"{utils.res.SUCCESS}")
    else:
        utils.res.verbose(f"{utils.res.WARNING}Login failed, continuing with daily download limit of srr.")

    # Set the verbose flag in the module
    utils.res.set_verbose_flag(args['verbose'])

    cwd = os.getcwd()

    # Ensure all extensions are lowercase
    valid_extensions = [ext.lower() for ext in args['extension']]

    if not args['verbose']:
        if args['check_extras']:
            # Process directories with progress bar
            traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: check_dir(args, p), use_progress_bar=True)
        else:
            if args['search_srrdb']:
                traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: search_file(args, p), use_progress_bar=True)
            else:
                traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: check_file(args, p), use_progress_bar=True)
    else:
        # No progress bar, process files with all verbose details
        if args['check_extras']:
            traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: check_dir(args, p), use_progress_bar=False)
        else:
            if args['search_srrdb']:
                traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: search_file(args, p), use_progress_bar=False)
            else:
                traverse_directories(valid_extensions=valid_extensions, input_paths=args['input'], process_file_func=lambda p: check_file(args, p), use_progress_bar=False)

    # Set the verbose flag to True to show the result
    utils.res.set_verbose_flag(True)

    if not args['search_srrdb']:
        # Verify weird inside releases
        utils.res.verbose(f"\n{utils.res.DARK_YELLOW}* Checking if releases are clean:{utils.res.RESET}")
        utils.res.verbose(f"Sometimes it was pred like that... sometimes there are extra weird things inside .srr...")
        utils.res.verbose(f"If you have{utils.res.FAIL}or{utils.res.WARNING}you will have to verify by yourself.")

    if len(rls_check) > 0:
        utils.res.verbose(f"\n".join(rls_check))

    # Print every failed things
    if len(missing_files) > 0:
        utils.res.verbose(f"\n{utils.res.DARK_YELLOW}* Rescene process complete, the following files need to be manually acquired:{utils.res.RESET}\n" + "\n".join(missing_files))

    if len(compressed_release) > 0:
        utils.res.verbose(f"\n{utils.res.DARK_YELLOW}* Rescene process complete, the following files were compressed and need to be manually acquired:{utils.res.RESET}\n" + "\n".join(compressed_release))

    if len(scanned_nothing_found) > 0:
        utils.res.verbose(f"\n{utils.res.DARK_YELLOW}* Rescene process complete, the following files were not found and need to be manually acquired:{utils.res.RESET}\n" + "\n".join(scanned_nothing_found))

    # Ensure success_release is non-negative (it mean that nothing has been reconstruct)
    success_release = max(0, success_release)
    utils.res.verbose(f"\n{utils.res.DARK_YELLOW}* Rescene process complete: {success_release} completed of {scanned_release} scanned{utils.res.RESET}")
