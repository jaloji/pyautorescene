import os
import sys
import re
import subprocess
import utils.res

def get_files_in_directory(root_dir):
    # This function returns a list of all files in the given directory and its subdirectories
    return [os.path.join(dirpath, filename) for dirpath, _, filenames in os.walk(root_dir) for filename in filenames]

def get_file_list(path, rlsname, mindepth=1, maxdepth=None, type_filter='f'):
    results = []
    for root, dirs, files in os.walk(path):
        # Calculate the current depth
        depth = root[len(path):].count(os.sep) + 1
    
        # Filter by depth
        if mindepth and depth < mindepth:
            continue
        if maxdepth and depth > maxdepth:
            dirs[:] = []  # Don't descend further
            continue
    
        # Filter by file type and get relative paths
        if type_filter == 'f':
            for f in files:
                full_path = os.path.normpath(os.path.join(root, f))
                # Make path relative to rlsname
                if rlsname in full_path:
                    rel_path = full_path.split(rlsname, 1)[1].lstrip(os.sep)
                    results.append(os.path.join(rlsname, rel_path))
        elif type_filter == 'd':
            for d in dirs:
                full_path = os.path.normpath(os.path.join(root, d))
                # Make path relative to rlsname
                if rlsname in full_path:
                    rel_path = full_path.split(rlsname, 1)[1].lstrip(os.sep)
                    results.append(os.path.join(rlsname, rel_path))

    return results
    
def normalize(paths):
    return [os.path.normpath(d).replace(os.path.sep, '/') for d in paths]

def get_release_type(rlsname):
    if re.search(r'dir.?fix', rlsname, re.IGNORECASE):
        release_type = "DIRFIX"
    elif re.search(r'nfo.?fix', rlsname, re.IGNORECASE):
        release_type = "NFOFIX"
    elif re.search(r'proof.?fix', rlsname, re.IGNORECASE):
        release_type = "PROOFFIX"
    elif re.search(r'sample.?fix', rlsname, re.IGNORECASE):
        release_type = "SAMPLEFIX"
    elif re.search(r'rar.?fix', rlsname, re.IGNORECASE):
        release_type = "RARFIX"
    elif re.search(r'sfv.?fix', rlsname, re.IGNORECASE):
        release_type = "SFVFIX"
    elif (re.search(r'\-([xh]26[45]|dvix|xvid)\-[0-9]{4}\-', rlsname, re.IGNORECASE) and
          any(re.search(r'\.(mkv|avi)$', f, re.IGNORECASE) for f in os.listdir(rlsname) if os.path.isfile(os.path.join(rlsname, f)))):
        release_type = "MVID"
    elif any(re.search(r'\.(rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3})$', f, re.IGNORECASE) for f in get_files_in_directory(rlsname)):
        release_type = "RAR"
    elif any(re.search(r'\.zip$', f, re.IGNORECASE) for f in os.listdir(rlsname) if os.path.isfile(os.path.join(rlsname, f))):
        release_type = "ZIP"
    elif any(re.search(r'\.mp3$', f, re.IGNORECASE) for f in os.listdir(rlsname) if os.path.isfile(os.path.join(rlsname, f))):
        release_type = "MP3"
    elif any(re.search(r'\.flac$', f, re.IGNORECASE) for f in os.listdir(rlsname) if os.path.isfile(os.path.join(rlsname, f))):
        release_type = "FLAC"
    else:
        release_type = "UNKNOWN"
    
    return release_type

def check_bad_files(rlsname, rel_path, release_type):
    release_status = "OK"

    # List of exclusion patterns from zipscript
    exclusion_patterns = [
    r'\[.*%.*incomplete.*\]',          # ex: [something%incomplete]
    r'\[.*-.*-.*\]',                   # ex: [foo-bar-baz]
    r'\[.*\].*\(.*\).*?\[.*\]',        # ex: [foo](bar)[baz]
    r'\[.*\].*\[.*\]',                 # ex: [foo][bar]
    r'\[.*\].*\[.*\].*\[.*\]',         # ex: [foo][bar][baz]
    r'\[100% complete\].*',            # ex: [100% complete] test
    r'\[complete\]',                   # ex: [complete]
    r'\[imdb\]=-.*-=\[imdb\]',         # ex: [imdb]=something-=[imdb]
    r'\[stream:.*',                    # ex: [stream:info
    r'^.*100\% COMPLETED.*$',          # ex: Done at 100% COMPLETED
    r'^.*DONE AT 100\%.*$',            # ex: Completed. DONE AT 100%
    r'^.*F - COMPLETE.*$',             # ex: F - COMPLETE
    r'\.message$']                     # ex: .message

    # Combine all patterns into a single pattern
    combined_pattern = re.compile(r'|'.join(exclusion_patterns), re.IGNORECASE)

    # Filter file lists
    release_rootfilelist = [f for f in get_file_list(rlsname, rel_path, maxdepth=1) if not combined_pattern.search(f)]
    release_filelist = [f for f in get_file_list(rlsname, rel_path) if not combined_pattern.search(f)]
    release_subdirs = [d for d in get_file_list(rlsname, rel_path, type_filter='d') if not combined_pattern.search(d)]

    normalized_rootfilelist = normalize(release_rootfilelist)
    normalized_filelist = normalize(release_filelist)
    normalized_subdirs = normalize(release_subdirs)

    # Check for directories deeper than maxdepth
    if len(get_file_list(rlsname, rel_path, mindepth=2, type_filter='d')) > 0:
        release_status = "BAD - too much sub dir: release/sub/sub/ exist"
        return release_status

    # Check for main regex issues
    notallowed_regex_result = [f for f in normalized_filelist if re.search(r'(.*\([0-9]?\)\.[a-z0-9]{3}$)|(\[|\]|\"|<|>|\*|%|\^|\+|\=|\{|\}|\:|\ |\;|\,|\?|\!)'
                                                                r'|(folder.jpg|rushchk.log|Thumbs.db|tvmaze.nfo|desktop.ini|albumartsmall.jpg|'
                                                                r'\.bad|\.missing|\.user|\.txt|\.pdf|\.requests|\.ok|\.debug|\.imdbdata|imdb.nfo|\.html|\.iso|\.bin)$', f, re.IGNORECASE)]
    if notallowed_regex_result:
        release_status = "BAD: not allowed file present"
        return release_status

    # Check specific filter for release type conditions
    if release_type in ["DIRFIX", "NFOFIX"]:
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if not re.search(r'\.nfo$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: nfo file missing"
        return release_status
    
    if release_type == "PROOFFIX":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.(jpg|jpeg|png)$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: jpg or jpeg or png file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|jpg|jpeg|png)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, jpg or jpeg, png present"
        return release_status

    if release_type == "SAMPLEFIX":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.(mkv|avi|wmv|mp4|ts|m2ts|vob)$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: mkv, avi, wmv, mp4, ts, m2ts, vob file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|mkv|avi|wmv|mp4|ts|m2ts|vob)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, mkv, avi, wmv, mp4, ts, m2ts, vob present"
        return release_status

    if release_type == "RARFIX":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple sfv"
        if len([f for f in normalized_filelist if re.search(r'\.(rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3})$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: rar archive file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv|rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3})$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, sfv, rar archive present"
        return release_status

    if release_type == "SFVFIX":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: sfv file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, sfv present"
        return release_status

    if release_type == "MVID":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple sfv"
        if len([f for f in normalized_filelist if re.search(r'\.(mkv|avi)$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: mkv, avi file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv|mkv|avi)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, sfv, mkv, avi present"
        return release_status

    if release_type == "RAR":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: sfv missing"
        if len([f for f in normalized_filelist if re.search(r'\.(rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3})$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: rar archive file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv|rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3}|mkv|avi|wmv|mp4|ts|m2ts|vob|jpg|jpeg|png)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: nfo, sfv, mkv, avi, wmv, mp4, ts, m2ts, vob, jpg or jpeg, png, rar archive file missing"
        if len([f for f in normalized_rootfilelist if not re.search(r'\.(nfo|sfv|rar|(r|s|t|u|v|w|x|y|z)[0-9]{2}|[0-9]{3})$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: nfo, sfv, rar archive file missing"
        if any(len([d for d in normalized_subdirs if re.search(pattern, d, re.IGNORECASE)]) > 1 for pattern in ['.*/samples?$', '.*/proofs?$', '.*/subs?$']):
            release_status = "BAD: more than one dir for sample, proof, subs"
        if len([d for d in normalized_subdirs if not re.search(r'.*/((dvd|cd|dis[ck])[0-9][0-9]?|samples?|proofs?|subs?)$', d, re.IGNORECASE)]) != 0:
            release_status = "BAD: other subdir than dvd, cd, disc or disk, sample, proof, subs"
        return release_status

    if release_type == "ZIP":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.zip$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: zip file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|zip|diz)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, zip, diz present"
        return release_status

    if release_type == "MP3":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: sfv file missing"
        if len([f for f in normalized_filelist if re.search(r'\.mp3$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: mp3 file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv|mp3|m3u|jpe?g|png|cue)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, sfv, mp3, m3u, jpg or jpeg, png, cue present"
        return release_status

    if release_type == "FLAC":
        if len([f for f in normalized_filelist if re.search(r'\.nfo$', f, re.IGNORECASE)]) != 1:
            release_status = "BAD: multiple nfo"
        if len([f for f in normalized_filelist if re.search(r'\.sfv$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: sfv file missing"
        if len([f for f in normalized_filelist if re.search(r'\.flac$', f, re.IGNORECASE)]) == 0:
            release_status = "BAD: flac file missing"
        if len([f for f in normalized_filelist if not re.search(r'\.(nfo|sfv|flac|m3u|jpe?g|png|cue|log)$', f, re.IGNORECASE)]) != 0:
            release_status = "BAD: other file than nfo, sfv, flac, m3u, jpg or jpeg, png, cue, log present"
        return release_status

    return release_status

def run_checks(rlsname):
    try:
        rls_type = get_release_type(os.path.normpath(rlsname))
        status = check_bad_files(os.path.normpath(rlsname), os.path.basename(rlsname), rls_type)
        if status == "OK":
            if rls_type == "UNKNOWN":
                print(f" - {utils.res.SUCCESS} -> {rlsname} -> {utils.res.WARNING}{rls_type} -> passed all checks.")
            else:
                print(f" - {utils.res.SUCCESS} -> {rlsname} -> {rls_type} -> passed all checks.")
        else:
            if rls_type == "UNKNOWN":
                print(f" - {utils.res.FAIL} -> {rlsname} -> {utils.res.WARNING}{rls_type} -> {status}")
            else:
                print(f" - {utils.res.FAIL} -> {rlsname} -> {rls_type} -> {status}")

    except Exception as e:
        print(f" - {utils.res.FAIL} -> {rlsname} -> Error: {str(e)}")
