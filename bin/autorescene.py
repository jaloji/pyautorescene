#!/usr/bin/python

from __future__ import print_function
import argparse, os, sys, errno
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
from rescene.osohash import compute_hash, osohash_from
import utils.res

#list of processes releases
release_list = dict()
missing_files = []
compressed_release = []

def arg_parse():
    parser = argparse.ArgumentParser(
        description='automated rescening of unrarred/renamed scene files',
        usage=os.path.basename(sys.argv[0]) + ' [--opts] input1 [input2] ...')

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

    args = parser.parse_args()

    return vars(args)

def search_by_crc(crc):
    if len(crc) != 8:
        #crc must have 8 characters
        raise ValueError("CRC must have length of 8")

    crc_search = utils.res.srrdb_api + "archive-crc:" + crc

    try:
        response = s.retrieveContent(crc_search)
        data = response.json()
    except:
        raise

    if 'resultsCount' not in data or int(data['resultsCount']) < 1:
        return None

    return data['results']

def search_by_oso(hashfile):
    if not hashfile or hashfile == "":
        raise ValueError("Release must have a valid OSO hash")

    name_search = utils.res.srrdb_api + "isdbhash:" + hashfile

    try:
        response = s.retrieveContent(name_search)
        data = response.json()
    except:
        raise

    if 'resultsCount' not in data or int(data['resultsCount']) < 1:
        return None

    return data['results']

def calc_crc(fpath):
    if not os.path.isfile(fpath):
        return None

    prev = 0
    for line in open(fpath, "rb"):
        prev = zlib.crc32(line, prev)

    return "%08X"%(prev & 0xFFFFFFFF)

def calc_oso(fname):
    if not os.path.isfile(fname):
        return None

    (oso_hash, file_size) = compute_hash(fname)

    return oso_hash

def copy_file(finput, foutput):
    if not os.path.isfile(finput):
        raise ValueError("finput must be a file")
    if not os.path.isdir(foutput):
        raise ValueError("foutput must be a file")
    if not os.path.splitext(finput)[1][0] != ".":
        return None
    try:
        shutil.copy2(finput, foutput)
    except IOError as e:
        return (None, "Unable to rename file: " + e)

    return True

def find_file(startdir, fname, fcrc):
    if not os.path.isdir(startdir):
        raise ValueError("startdir must be a directory")

    for root, dirs, files in os.walk(startdir):
        if fname in files:
            if calc_crc(os.path.join(root, fname)) == fcrc.zfill(8):
                #sample found!
                return os.path.join(root, fname)

    return False

def search_srrdb_crc(crc, rlspath):
    #search srrdb for releases matching crc32
    verbose("\t - Searching srrdb.com for matching CRC", end="")
    try:
        results = search_by_crc(crc)
    except Exception as e:
        verbose("%s -> %s" % (utils.res.FAIL, e))
        return False

    if not results:
        verbose("%s -> %s" % (utils.res.FAIL, "No matching results"))
        return False
    else:
        verbose("%s" % utils.res.SUCCESS)

    #handle multiple releases having same crc32 
    # (this should only happen with dupe srr's being uploaded)
    if len(results) > 1:
        verbose("\t\t %s More than one release found matching CRC %s." % (utils.res.FAIL, crc))
        verbose("\t - Searching srrdb.com for matching release name", end="")
        try:
            rlsname = os.path.basename(rlspath)
            results = utils.res.search_by_name(rlsname, s, isdir = False)
        except Exception as e:
            verbose("%s -> %s" % (utils.res.FAIL, e))
            return False

        if not results or len(results) > 1:
            verbose("%s -> %s" % (utils.res.FAIL, "No matching results"))
            verbose("\t - Searching srrdb.com for matching OSO hash", end="")
            try:
                OSOhash = calc_oso(rlspath)
                results = search_by_oso(OSOhash)
            except Exception as e:
                verbose("%s -> %s" % (utils.res.FAIL, e))
                return False

            if not results:
                verbose("%s -> %s" % (utils.res.FAIL, "No matching results"))
                return False
            else:
                verbose("%s" % utils.res.SUCCESS)
        else:
            verbose("%s" % utils.res.SUCCESS)

    if len(results) > 1:
        verbose("\t\t %s More than one release found matching OSO hash %s. This is most likely an issue, please report it on IRC (#srrdb @ irc.efnet.net)." % (utils.res.FAIL, OSOhash))
        return False

    release = results[0]
    verbose("\t\t - Matched release: %s" % release['release'])

    return release

def search_srrdb_dirname(rlspath):
    #search srrdb for release matching
    verbose("\t - Searching srrdb.com for matching release name", end="")
    try:
        rlsname = os.path.basename(rlspath)
        results = utils.res.search_by_name(rlsname, s, isdir = True)
    except Exception as e:
        verbose("%s -> %s" % (utils.res.FAIL, e))
        return False

    if not results or len(results) > 1:
        verbose("%s -> %s" % (utils.res.FAIL, "No matching results"))
        return False
    else:
        verbose("%s" % utils.res.SUCCESS)

    release = results[0]
    verbose("\t\t - Matched release: %s" % release['release'])

    return release

def check_file(args, fpath):
    spath = os.path.split(fpath)
    if os.path.basename(spath[0].lower()) == "Sample".lower():
        return False
    if not os.path.splitext(fpath)[1] in args['extension']:
        return False
    if args['min_filesize'] and os.path.getsize(fpath) < args['min_filesize']:
        return False

    if args['output']:
        doutput = args['output']
    else:
        doutput = os.path.dirname(fpath)

    global success_release
    global scanned_release

    verbose("* Found potential file: " + os.path.basename(fpath))
    scanned_release += 1
    #calculate crc32 of file
    verbose("\t - Calculating crc for file: %s" % fpath, end="")

    release_crc = calc_crc(fpath)
    if not release_crc:
        verbose("%s" % (utils.res.FAIL))
        return False
    else:
        verbose("%s -> %s" % (utils.res.SUCCESS, release_crc))

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
        elif release_list[release['release']]['rescene'] and release_list[release['release']]['resample'] and release_list[release['release']]['resubs']:
            verbose("\t - Skipping, already processed.")
            return True

    verbose("\t - Downloading SRR from srrdb.com", end="")
    # download srr
    try:
        srr_path = utils.res.download_srr(release['release'], s)
    except Exception as e:
        verbose("%s -> %s" % (utils.res.FAIL, e))
        return False
    else:
        verbose("%s" % utils.res.SUCCESS)

    release_srr = SRR(srr_path)
    srr_finfo = release_srr.get_archived_fname_by_crc(release_crc)
    if os.path.basename(doutput.lower()).lower() != release['release'].lower():
        #output dir is not specific to rls/doesnt match release
        doutput = os.path.join(doutput, release['release'])
        if not os.path.isdir(doutput):
            verbose("\t - Creating output directory: %s" % (doutput), end="")
            try:
                utils.res.mkdir(doutput)
            except Exception as e:
                verbose("%s -> Unable to create directory: %s" % (utils.res.FAIL, e))
                return False
            else:
                verbose("%s" % (utils.res.SUCCESS))

    verbose("\t - Setting output directory to: %s" % doutput)

    #rename file
    if args['rename']:
        if len(srr_finfo) != 1:
            return False

        if srr_finfo[0].file_name != os.path.basename(fpath):
            verbose("\t\t - file has been renamed, renaming to: %s" % srr_finfo[0].file_name, end="")
            (ret, mesg) = copy_file(fpath, os.path.join(doutput, srr_finfo[0].file_name))

            if not ret:
                verbose("%s -> %s", (utils.res.FAIL, mesg))
            else:
                verbose("%s" % (utils.res.SUCCESS))

    if (args['extract_stored'] or args['auto_reconstruct']) and not release_list[release['release']]['extract']:
        verbose("\t - Extracting stored files from SRR", end="")
        try:
            matches = release_srr.extract_stored_files_regex(doutput, regex="^(?:(.+\.)((?!txt$)[^.]*)|[^.]+)$")

        except Exception as e:
            verbose("%s -> %s" % (utils.res.FAIL, e))
            return False

        else:
            verbose("%s" % utils.res.SUCCESS)

            for match in matches:
                if match[0].endswith(".srs"):
                    srs_path = match[0]

                verbose("\t\t - %s" % os.path.relpath(match[0], doutput))

            release_list[release['release']]['extract'] = True
            if not os.path.exists(os.path.join(doutput, "Subs")):
                release_list[release['release']]['resubs'] = True

    if (args['rescene'] or args['auto_reconstruct']) and not release_list[release['release']]['rescene']:
        verbose("\t - Reconstructing original RARs from SRR", end="")

        rename_hints = {srr_finfo[0].file_name: os.path.basename(fpath)}
        try:
            if release_srr.get_is_compressed():
                verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

            release_srr.reconstruct_rars(os.path.dirname(fpath), doutput, rename_hints, utils.res.rar_version, utils.res.srr_temp_foder)
        except Exception as e:
            verbose("%s -> %s" % (utils.res.FAIL, e))
            if release_srr.get_is_compressed():
                compressed_release.append(release['release'])
        else:
            verbose("%s" % (utils.res.SUCCESS))
            release_list[release['release']]['rescene'] = True
            success_release += 1

    if (args['resample'] or args['auto_reconstruct']) and not release_list[release['release']]['resample']:
        if release['hasSRS'] == "yes":
            try:
                srs_path
            except NameError:
                srs_path = ""

                verbose("\t\t - Extracting SRS from SRR file for Sample reconstruction", end="")
                release_srs = release_srr.get_srs(doutput)

                if len(release_srs) != 1:
                    verbose("%s -> more than one SRS in this SRR.  Please reconstruct manually." % utils.res.FAIL)
                else:
                    srs_path = release_srs[0][0]

            if srs_path != "":
                sample = SRS(srs_path)
                verbose("\t - Recreating Sample .. expect output from SRS\n-------------------------------")

                try:
                    sample.recreate(fpath, os.path.dirname(srs_path))
                except Exception as e:
                    verbose("-------------------------------")
                    verbose("\t - %s -> failed to recreate sample: %s." % (utils.res.FAIL,e))

                    #sample reconstruction failed.. should we try check local disk for a sample?
                    if args['find_sample']:
                        verbose("\t - Searching for sample on local disk")
                        sample_file = find_file(os.path.dirname(fpath), sample.get_filename(), sample.get_crc())
                        if sample_file:
                            verbose("\t\t - %s - Found sample -> %s" % (utils.res.SUCCESS, sample_file))
                            try:
                                shutil.move(sample_file, os.path.dirname(srs_path))
                                release_list[release['release']]['resample'] = True
                            except Exception as e:
                                verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(srs_path), e))
                                missing_files.append(release['release']+"/Sample/"+sample.get_filename())
                        else:
                            missing_files.append(release['release']+"/Sample/"+sample.get_filename())
                    else:
                        missing_files.append(release['release']+"/Sample/"+sample.get_filename())
                else:
                    verbose("-------------------------------")
                    verbose("\t - %s -> sample recreated successfully" % (utils.res.SUCCESS))
                    release_list[release['release']]['resample'] = True
                    if not args['keep_srs']:
                        if os.path.exists(srs_path):
                            os.remove(srs_path)
                        else:
                            verbose("\t - Impossible to delete no SRS found %s" % (utils.res.FAIL))
            else:
                missing_files.append(release['release']+"/Sample/"+sample.get_filename())
        else:
            verbose("\t - No SRS found for sample recreation %s" % (utils.res.FAIL))

    if (args['resubs'] or args['auto_reconstruct']) and not release_list[release['release']]['resubs']:
        sub_srr = ""
        sub_file = ""
        idx_file = ""
        sub_srr_2 = ""
        rar_name = ""
        rar_name_2 = ""
        for root, dirs, files in os.walk(os.path.join(doutput, "Subs")):
            for file in files:
                if file.endswith(".sfv"):
                    sub_sfv = os.path.join(root, file)
                elif file.endswith(".srr"):
                    sub_srr = os.path.join(root, file)

        for root, dirs, files in os.walk(os.path.dirname(fpath)):
            for file in files:
                if file.endswith(".sub"):
                    sub_file = os.path.join(root, file)
                elif file.endswith(".idx"):
                    idx_file = os.path.join(root, file)

        verbose("\t - Reconstructing original RARs for Subs")
        if os.path.exists(sub_sfv) and sub_srr != "" and sub_file != "" and idx_file != "":
            subs_srr = SRR(sub_srr)
            subs_rar_name = subs_srr.get_rars_name()
            for rarn in subs_rar_name:
                if rarn.endswith(".rar"):
                    rar_name = rarn

            verbose("\t - Extracting stored files from Subs SRR", end="")
            try:
                matches = subs_srr.extract_stored_files_regex(os.path.dirname(sub_srr), regex="^(?:(.+\.)((?!diz$)[^.]*)|[^.]+)$")
            except Exception as e:
                verbose("%s -> %s" % (utils.res.FAIL, e))
                return False

            else:
                verbose("%s" % utils.res.SUCCESS)

                for match in matches:
                    if match[0].endswith(".srr"):
                        sub_srr_2 = match[0]

                    verbose("\t\t - %s" % os.path.relpath(match[0], sub_srr_2))

            if sub_srr_2 != "":
                subs_srr_2 = SRR(sub_srr_2)
                subs_rar_name_2 = subs_srr_2.get_rars_name()
                for rarn in subs_rar_name_2:
                    if rarn.endswith(".rar"):
                        rar_name_2 = rarn

                rename_hints_subs = {subs_srr_2.filename: os.path.basename(sub_file)}
                verbose("\t - Reconstructing first RAR for Subs", end="")
                try:
                    if subs_srr_2.get_is_compressed():
                        verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                    subs_srr_2.reconstruct_rars(os.path.dirname(sub_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                except Exception as e:
                    verbose("%s -> %s" % (utils.res.FAIL, e))
                    if subs_srr_2.get_is_compressed():
                        compressed_release.append(os.path.join(os.path.dirname(sub_file), rar_name_2))
                else:
                    verbose("%s" % (utils.res.SUCCESS))
                    rename_hints_subs = {subs_srr.filename: os.path.basename(idx_file)}
                    verbose("\t - Reconstructing second RAR for Subs", end="")
                    try:
                        if subs_srr.get_is_compressed():
                            verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                        subs_srr.reconstruct_rars(os.path.dirname(idx_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                    except Exception as e:
                        verbose("%s -> %s" % (utils.res.FAIL, e))
                        if subs_srr.get_is_compressed():
                            compressed_release.append(os.path.join(os.path.dirname(idx_file), rar_name))
                    else:
                        verbose("%s" % (utils.res.SUCCESS))                            
            else:
                rename_hints_subs = {subs_srr.filename: os.path.basename(idx_file)}
                verbose("\t - Reconstructing second RAR for Subs", end="")
                try:
                    if subs_srr.get_is_compressed():
                        verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                    subs_srr.reconstruct_rars(os.path.dirname(idx_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                except Exception as e:
                    verbose("%s -> %s" % (utils.res.FAIL, e))
                    if subs_srr.get_is_compressed():
                        compressed_release.append(os.path.join(os.path.dirname(idx_file), rar_name))
                else:
                    verbose("%s" % (utils.res.SUCCESS))   

        verbose("\t - Checking if RAR for Subs have good CRC in %s" % (os.path.dirname(sub_sfv)))
        try:
            sfv_f = open(sub_sfv, "r")
            sfv_p = os.path.dirname(sub_sfv)
        except Exception as e:
            verbose("\t\t - %s - Could not open sfv file %s -> %s" % (utils.res.FAIL, sub_sfv, e))

        for line in sfv_f:
            # Skip comments.
            if line[0] == ';': continue

            filename, _, crc = line.rstrip().rpartition(' ')

            if not (filename and crc): continue

            if not os.path.exists(os.path.join(fpath, os.path.join(sfv_p, filename))):
                verbose("\t\t - %s -> Be careful missing Subs file: %s" % (utils.res.FAIL, filename))
                verbose("\t - Searching for Subs on local disk")
                subs_file = find_file(os.path.dirname(fpath), filename, crc.upper())
                if subs_file:
                    verbose("\t\t - %s - Found Subs -> %s" % (utils.res.SUCCESS, subs_file))
                    try:
                        shutil.move(subs_file, os.path.dirname(sub_srr))
                        release_list[release['release']]['resubs'] = True
                        if not args['keep_srr']:
                            if os.path.exists(sub_srr):
                                os.remove(sub_srr)
                            if os.path.exists(sub_srr_2):
                                os.remove(sub_srr_2)
                            if os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
                    except Exception as e:
                        verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(sub_srr), e))
                        missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

                else:
                    verbose("\t\t - %s - Subs RAR not found" % (utils.res.FAIL))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))
                continue

            hash = calc_crc(os.path.join(fpath, os.path.join(sfv_p, filename)))
            if hash.lower() == crc.lower():
                verbose("\t\t - %s -> %s %s" % (utils.res.SUCCESS, filename, hash.upper()))
            else:
                verbose("\t\t - %s -> %s our hash %s does not match %s" % (utils.res.FAIL, filename, hash.upper(), crc.upper()))
                verbose("\t - Searching for Subs on local disk")
                subs_file = find_file(os.path.dirname(fpath), filename, crc.upper())
                if subs_file:
                    verbose("\t\t - %s - Found Subs -> %s" % (utils.res.SUCCESS, subs_file))
                    try:
                        shutil.move(subs_file, os.path.dirname(sub_srr))
                        release_list[release['release']]['resubs'] = True
                        if not args['keep_srr']:
                            if os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
                            if os.path.exists(sub_srr):
                                os.remove(sub_srr)
                            if os.path.exists(sub_srr_2):
                                os.remove(sub_srr_2)
                    except Exception as e:
                        verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(sub_srr), e))
                        missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

                else:
                    verbose("\t\t - %s - Subs RAR not found" % (utils.res.FAIL))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))
        sfv_f.close()
        if not args['keep_srr']:
            if sub_srr != "" and rar_name_2 != "" and os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
            if sub_srr != "" and os.path.exists(sub_srr):
                os.remove(sub_srr)
            if sub_srr_2 != "" and os.path.exists(sub_srr_2):
                os.remove(sub_srr_2)

    release_list[release['release']]['resubs'] = True

def check_dir(args, fpath):
    if os.path.basename(fpath.lower()) == "Proof".lower():
        return False
    if os.path.basename(fpath.lower()) == "Sample".lower():
        return False
    if os.path.basename(fpath.lower()) == "Sub".lower():
        return False
    if os.path.basename(fpath.lower()) == "Subs".lower():
        return False
    if os.path.basename(fpath.lower()) == "CD1".lower():
        return False
    if os.path.basename(fpath.lower()) == "CD2".lower():
        return False
    if os.path.basename(fpath.lower()) == "CD3".lower():
        return False

    if args['output']:
        doutput = args['output']
    else:
        doutput = os.path.dirname(fpath)

    global success_release
    global scanned_release

    verbose("* Found potential release: " + os.path.basename(fpath))
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
            verbose("\t - Skipping, already processed.")
            return True

    verbose("\t - Downloading SRR from srrdb.com", end="")
    # download srr
    try:
        srr_path = utils.res.download_srr(release['release'], s)
    except Exception as e:
        verbose("%s -> %s" % (utils.res.FAIL, e))
        return False
    else:
        verbose("%s" % utils.res.SUCCESS)

    release_srr = SRR(srr_path)
    srr_finfo = release_srr.get_rars_name()
    missing_rar = missing_files
    if not args['check_crc']:
        if len(srr_finfo) > 0:
            verbose("\t - Checking if all RAR are present in %s" % (fpath))
            for match in srr_finfo:
                if not os.path.exists(os.path.join(fpath, os.path.normpath(match))):
                    verbose("\t\t - %s -> Be careful missing RAR file: %s" % (utils.res.FAIL, match))
                    missing_files.append(release['release']+"/"+os.path.normpath(match))
                else:
                    verbose("\t\t - %s -> %s" % (utils.res.SUCCESS, match))

            release_list[release['release']]['rescene'] = True
            if len(missing_files) == len(missing_rar):
                success_release += 1
        else:
            verbose("\t - Checking if all files are present in %s" % (fpath))
            srr_sfv_info = release_srr.get_sfv_entries_name()
            for match in srr_sfv_info:
                if not os.path.exists(os.path.join(fpath, match)):
                    verbose("\t\t - %s -> Be careful missing file: %s" % (utils.res.FAIL, match))
                    missing_files.append(release['release']+"/"+match)
                else:
                    verbose("\t\t - %s -> %s" % (utils.res.SUCCESS, match))

            release_list[release['release']]['rescene'] = True
            if len(missing_files) == len(missing_rar):
                success_release += 1

    elif args['check_crc']:
        stored_files = release_srr.get_stored_files_name()
        sfv_path = []
        for fname in stored_files:
            if fname.endswith(".sfv"):
                sfv_path.append(os.path.join(fpath, os.path.normpath(fname)))

        verbose("\t - Checking if all RAR have good CRC in %s" % (fpath))
        for sfv in sfv_path:
            try:
                sfv_f = open(sfv, "r")
                sfv_p = os.path.dirname(sfv)
            except Exception as e:
                verbose("\t\t - %s - Could not open sfv file %s -> %s" % (utils.res.FAIL, sfv, e))

            for line in sfv_f:
                # Skip comments.
                if line[0] == ';': continue

                filename, _, crc = line.rstrip().rpartition(' ')

                if not (filename and crc): continue

                if not os.path.exists(os.path.join(fpath, os.path.join(sfv_p, filename))):
                    verbose("\t\t - %s -> Be careful missing RAR file: %s" % (utils.res.FAIL, filename))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

                    continue

                hash = calc_crc(os.path.join(fpath, os.path.join(sfv_p, filename)))
                if hash.lower() == crc.lower():
                    verbose("\t\t - %s -> %s %s" % (utils.res.SUCCESS, filename, hash.upper()))
                else:
                    verbose("\t\t - %s -> %s our hash %s does not match %s" % (utils.res.FAIL, filename, hash.upper(), crc.upper()))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

            sfv_f.close()
        release_list[release['release']]['rescene'] = True
        if len(missing_files) == len(missing_rar):
            success_release += 1

    if os.path.basename(doutput.lower()).lower() != release['release'].lower():
        #output dir is not specific to rls/doesnt match release
        doutput = os.path.join(doutput, release['release'])
        if not os.path.isdir(doutput):
            verbose("\t - Creating output directory: %s" % (doutput), end="")
            try:
                utils.res.mkdir(doutput)
            except Exception as e:
                verbose("%s -> Unable to create directory: %s" % (utils.res.FAIL, e))
                return False
            else:
                verbose("%s" % (utils.res.SUCCESS))

    verbose("\t - Setting output directory to: %s" % doutput)

    if (args['check_extras']) and not release_list[release['release']]['extract']:
        verbose("\t - Extracting stored files from SRR", end="")
        if len(srr_finfo) > 0:
            rar_path = os.path.join(fpath, srr_finfo[0])

        try:
            if len(srr_finfo) > 0:
                matches = release_srr.extract_stored_files_regex(doutput, regex="^(?:(.+\.)((?!txt$)[^.]*)|[^.]+)$")
            else:
                matches = release_srr.extract_stored_files_regex(doutput, regex="^(?:(.+\.)((?!srs$)[^.]*)|[^.]+)$")

        except Exception as e:
            verbose("%s -> %s" % (utils.res.FAIL, e))
            return False

        else:
            verbose("%s" % utils.res.SUCCESS)
            proof_path = ""
            for match in matches:
                if match[0].endswith(".srs"):
                    srs_path = match[0]
                if match[0].endswith(".jpg") or match[0].endswith(".jpeg") or match[0].endswith(".png"):
                    proof_path = match[0]
                verbose("\t\t - %s" % os.path.relpath(match[0], doutput))
            release_list[release['release']]['extract'] = True
            if not os.path.exists(os.path.join(doutput, "Subs")):
                release_list[release['release']]['resubs'] = True

    if (args['check_extras']) and not release_list[release['release']]['resample']:
        proof_path = ""
        if proof_path != "":
            #we try check if proof on local disk is good
            verbose("\t - Searching for Proof on local disk")
            proof_crc = calc_crc(proof_path)
            proof_file = find_file(os.path.dirname(fpath), os.path.basename(*release_srr.get_proof_filename()), proof_crc)
            if proof_file and proof_file.lower() != proof_path.lower():
                verbose("\t\t - %s - Found proof -> %s" % (utils.res.SUCCESS, proof_file))
                try:
                    copy_file(proof_file, os.path.dirname(proof_path))
                    if not args['keep_srs']:
                        if os.path.exists(proof_file):
                            os.remove(proof_file)
                except Exception as e:
                    verbose("\t\t - %s - Could not copy proof file to %s -> %s" % (utils.res.FAIL, os.path.dirname(proof_path), e))
                    missing_files.append(release['release']+release_srr.get_proof_filename())
        if release['hasSRS'] == "yes" and len(srr_finfo) > 0:
            try:
                srs_path
            except NameError:
                srs_path = ""

                verbose("\t\t - Extracting SRS from SRR file for Sample reconstruction", end="")
                release_srs = release_srr.get_srs(doutput)

                if len(release_srs) != 1:
                    verbose("%s -> more than one SRS in this SRR.  Please reconstruct manually." % utils.res.FAIL)
                else:
                    srs_path = release_srs[0][0]

            if srs_path != "":
                sample = SRS(srs_path)
                #we try check if sample on local disk is good
                verbose("\t - Searching for sample on local disk")
                sample_file = find_file(os.path.dirname(fpath), sample.get_filename(), sample.get_crc())
                if sample_file:
                    verbose("\t\t - %s - Found sample -> %s" % (utils.res.SUCCESS, sample_file))
                    if os.path.dirname(sample_file.lower()) != os.path.dirname(srs_path.lower()):
                        try:
                            shutil.move(sample_file, os.path.dirname(srs_path))
                            release_list[release['release']]['resample'] = True
                            if not args['keep_srs']:
                                if os.path.exists(srs_path):
                                    os.remove(srs_path)
                                else:
                                    verbose("\t - Impossible to delete no SRS found %s" % (utils.res.FAIL))
                        except Exception as e:
                            verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(srs_path), e))
                            missing_files.append(release['release']+"/Sample/"+sample.get_filename())
                    
                    release_list[release['release']]['resample'] = True
                    if not args['keep_srs']:
                        if os.path.exists(srs_path):
                            os.remove(srs_path)
                        else:
                            verbose("\t - Impossible to delete no SRS found %s" % (utils.res.FAIL))
                else:
                    #we try sample reconstruction
                    verbose("\t - Sample found have Bad CRC or no sample foud %s" % (utils.res.FAIL))
                    verbose("\t - Recreating Sample .. expect output from SRS\n-------------------------------")
                    try:
                        sample.recreate(rar_path, os.path.dirname(srs_path))
                    except Exception as e:
                        verbose("-------------------------------")
                        verbose("\t - %s -> failed to recreate sample: %s." % (utils.res.FAIL,e))
                        missing_files.append(release['release']+"/Sample/"+sample.get_filename())

                    else:
                        verbose("-------------------------------")
                        verbose("\t - %s -> sample recreated successfully" % (utils.res.SUCCESS))
                        release_list[release['release']]['resample'] = True
                        if not args['keep_srs']:
                            if os.path.exists(srs_path):
                                os.remove(srs_path)
                            else:
                                verbose("\t - Impossible to delete no SRS found %s" % (utils.res.FAIL))
            else:
                missing_files.append(release['release']+"/Sample/"+sample.get_filename())
        else:
            verbose("\t - No SRS found for sample recreation %s" % (utils.res.FAIL))

    if (args['check_extras']) and not release_list[release['release']]['resubs']:
        sub_srr = ""
        sub_file = ""
        idx_file = ""
        sub_srr_2 = ""
        rar_name = ""
        rar_name_2 = ""
        for root, dirs, files in os.walk(os.path.join(doutput, "Subs")):
            for file in files:
                if file.endswith(".sfv"):
                    sub_sfv = os.path.join(root, file)
                elif file.endswith(".srr"):
                    sub_srr = os.path.join(root, file)

        for root, dirs, files in os.walk(os.path.dirname(fpath)):
            for file in files:
                if file.endswith(".sub"):
                    sub_file = os.path.join(root, file)
                elif file.endswith(".idx"):
                    idx_file = os.path.join(root, file)

        verbose("\t - Reconstructing original RARs for Subs")
        if os.path.exists(sub_sfv) and sub_srr != "" and sub_file != "" and idx_file != "":
            subs_srr = SRR(sub_srr)
            subs_rar_name = subs_srr.get_rars_name()
            for rarn in subs_rar_name:
                if rarn.endswith(".rar"):
                    rar_name = rarn

            verbose("\t - Extracting stored files from Subs SRR", end="")
            try:
                matches = subs_srr.extract_stored_files_regex(os.path.dirname(sub_srr), regex="^(?:(.+\.)((?!diz$)[^.]*)|[^.]+)$")
            except Exception as e:
                verbose("%s -> %s" % (utils.res.FAIL, e))
                return False

            else:
                verbose("%s" % utils.res.SUCCESS)

                for match in matches:
                    if match[0].endswith(".srr"):
                        sub_srr_2 = match[0]

                    verbose("\t\t - %s" % os.path.relpath(match[0], sub_srr_2))

            if sub_srr_2 != "":
                subs_srr_2 = SRR(sub_srr_2)
                subs_rar_name_2 = subs_srr_2.get_rars_name()
                for rarn in subs_rar_name_2:
                    if rarn.endswith(".rar"):
                        rar_name_2 = rarn

                rename_hints_subs = {subs_srr_2.filename: os.path.basename(sub_file)}
                verbose("\t - Reconstructing first RAR for Subs", end="")
                try:
                    if subs_srr_2.get_is_compressed():
                        verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                    subs_srr_2.reconstruct_rars(os.path.dirname(sub_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                except Exception as e:
                    verbose("%s -> %s" % (utils.res.FAIL, e))
                    if subs_srr_2.get_is_compressed():
                        compressed_release.append(os.path.join(os.path.dirname(sub_file), rar_name_2))
                else:
                    verbose("%s" % (utils.res.SUCCESS))
                    rename_hints_subs = {subs_srr.filename: os.path.basename(idx_file)}
                    verbose("\t - Reconstructing second RAR for Subs", end="")
                    try:
                        if subs_srr.get_is_compressed():
                            verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                        subs_srr.reconstruct_rars(os.path.dirname(idx_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                    except Exception as e:
                        verbose("%s -> %s" % (utils.res.FAIL, e))
                        if subs_srr.get_is_compressed():
                            compressed_release.append(os.path.join(os.path.dirname(idx_file), rar_name))
                    else:
                        verbose("%s" % (utils.res.SUCCESS))                            
            else:
                rename_hints_subs = {subs_srr.filename: os.path.basename(idx_file)}
                verbose("\t - Reconstructing second RAR for Subs", end="")
                try:
                    if subs_srr.get_is_compressed():
                        verbose("\n\t - WARNING ! RAR Compression is used, reconstruction may not work", end="")

                    subs_srr.reconstruct_rars(os.path.dirname(idx_file), os.path.dirname(sub_srr), rename_hints_subs, utils.res.rar_version, utils.res.srr_temp_foder)
                except Exception as e:
                    verbose("%s -> %s" % (utils.res.FAIL, e))
                    if subs_srr.get_is_compressed():
                        compressed_release.append(os.path.join(os.path.dirname(idx_file), rar_name))
                else:
                    verbose("%s" % (utils.res.SUCCESS))   

        verbose("\t - Checking if RAR for Subs have good CRC in %s" % (os.path.dirname(sub_sfv)))
        try:
            sfv_f = open(sub_sfv, "r")
            sfv_p = os.path.dirname(sub_sfv)
        except Exception as e:
            verbose("\t\t - %s - Could not open sfv file %s -> %s" % (utils.res.FAIL, sub_sfv, e))

        for line in sfv_f:
            # Skip comments.
            if line[0] == ';': continue

            filename, _, crc = line.rstrip().rpartition(' ')

            if not (filename and crc): continue

            if not os.path.exists(os.path.join(fpath, os.path.join(sfv_p, filename))):
                verbose("\t\t - %s -> Be careful missing Subs file: %s" % (utils.res.FAIL, filename))
                verbose("\t - Searching for Subs on local disk")
                subs_file = find_file(os.path.dirname(fpath), filename, crc.upper())
                if subs_file:
                    verbose("\t\t - %s - Found Subs -> %s" % (utils.res.SUCCESS, subs_file))
                    try:
                        shutil.move(subs_file, os.path.dirname(sub_srr))
                        release_list[release['release']]['resubs'] = True
                        if not args['keep_srr']:
                            if os.path.exists(sub_srr):
                                os.remove(sub_srr)
                            if os.path.exists(sub_srr_2):
                                os.remove(sub_srr_2)
                            if os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
                    except Exception as e:
                        verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(sub_srr), e))
                        missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

                else:
                    verbose("\t\t - %s - Subs RAR not found" % (utils.res.FAIL))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))
                continue

            hash = calc_crc(os.path.join(fpath, os.path.join(sfv_p, filename)))
            if hash.lower() == crc.lower():
                verbose("\t\t - %s -> %s %s" % (utils.res.SUCCESS, filename, hash.upper()))
            else:
                verbose("\t\t - %s -> %s our hash %s does not match %s" % (utils.res.FAIL, filename, hash.upper(), crc.upper()))
                verbose("\t - Searching for Subs on local disk")
                subs_file = find_file(os.path.dirname(fpath), filename, crc.upper())
                if subs_file:
                    verbose("\t\t - %s - Found Subs -> %s" % (utils.res.SUCCESS, subs_file))
                    try:
                        shutil.move(subs_file, os.path.dirname(sub_srr))
                        release_list[release['release']]['resubs'] = True
                        if not args['keep_srr']:
                            if os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
                            if os.path.exists(sub_srr):
                                os.remove(sub_srr)
                            if os.path.exists(sub_srr_2):
                                os.remove(sub_srr_2)
                    except Exception as e:
                        verbose("\t\t - %s - Could not copy file to %s -> %s" % (utils.res.FAIL, os.path.dirname(sub_srr), e))
                        missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))

                else:
                    verbose("\t\t - %s - Subs RAR not found" % (utils.res.FAIL))
                    missing_files.append(os.path.join(fpath, os.path.join(sfv_p, filename)))
        sfv_f.close()
        if not args['keep_srr']:
            if sub_srr != "" and rar_name_2 != "" and os.path.exists(os.path.join(os.path.dirname(sub_srr), rar_name_2)):
                os.remove(os.path.join(os.path.dirname(sub_srr), rar_name_2))
            if sub_srr != "" and os.path.exists(sub_srr):
                os.remove(sub_srr)
            if sub_srr_2 != "" and os.path.exists(sub_srr_2):
                os.remove(sub_srr_2)

    release_list[release['release']]['resubs'] = True

if __name__ == "__main__":
    args = arg_parse()
    # initialize pretty colours
    init()
    success_release = 0
    scanned_release = 0

    #define verbose
    verbose = print if args['verbose'] else lambda *a, **k: None

    if not args['extension']:
        args['extension'] = ['.mkv', '.avi', '.mp4', '.iso']
    if args['min_filesize']:
        #convert from MB to Bytes
        args['min_filesize'] = int(args['min_filesize']) * 1048576

    if args['output']:
        if not os.path.isdir(args['output']):
            sys.exit("output option needs to be a valid directory")
        verbose("Setting output directory to: " + args['output'] + "\n")

    verbose("\t - Connecting srrdb.com...", end="")
    try:
        s = SRRDB_LOGIN(utils.res.loginUrl, utils.res.loginData, utils.res.loginTestUrl, utils.res.loginTestString)
    except Exception as e:
        verbose("%s -> %s" % (utils.res.FAIL, e))
    else:
        verbose("%s" % (utils.res.SUCCESS))

    cwd = os.getcwd()
    if args['check_extras']:
        for path in args['input']:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for dirname in dirs:
                        check_dir(args, os.path.join(root, dirname))
    else:
        for path in args['input']:
            if os.path.isfile(path):
                check_file(args, path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for sfile in files:
                        check_file(args, os.path.join(root, sfile))

    if len(missing_files) > 0:
        print("Rescene process complete, the following files need to be manually aquired:")
        print(*missing_files, sep='\n')

    if len(compressed_release) > 0:
        print("Rescene process complete, the following files were compressed and need to be manually aquired:")
        print(*compressed_release, sep='\n')
		
    print("Rescene process complete: %d completed of %d scanned" % (success_release, scanned_release))
