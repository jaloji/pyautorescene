import os
import re
from rescene import info, extract_files, reconstruct
from rescene.srr import display_info
from utils.srs import SRS

class SRR:
    def __init__(self, filename, binary=None):
        if not os.path.isfile(filename):
            raise AttributeError("srr must be a file")

        if not filename.endswith(".srr"):
            raise AttributeError("srr file must have the .srr extension")

        self.filename = filename
        if binary is None:
            if os.name == 'posix':
                self.binary = '/usr/bin/srr'
            elif os.name == 'nt':
                self.binary = 'srr'
            else:
                self.binary = binary

    # display info about this SRR
    def d_info(self):
        return display_info(self.filename)

    # check if compression method is used for RAR file
    def get_is_compressed(self):
        return bool(info(self.filename)['compression'])

    # search an srr for all rar-files presents
    # returns array of FileInfo's
    def get_rars_name(self):
        return [sfile.file_name for sfile in info(self.filename)['rar_files'].values()]

    def get_rar_crc(self):
        return [sfile.crc32 for sfile in info(self.filename)['rar_files'].values()]

    def get_rars_nb(self):
        return len(info(self.filename)['rar_files'])

    def get_rars_size(self):
        return sum(sfile.file_size for sfile in info(self.filename)['rar_files'].values())

    # search an srr for all non RAR files presents in all sfv file
    # returns array of FileInfo's
    def get_sfv_entries_name(self):
        return [str(sfile).split()[0] for sfile in info(self.filename)['sfv_entries']]

    def get_sfv_entries_nb(self):
        return len(self.get_sfv_entries_name())

    # search an srr for all files presents in srr
    # returns array of FileInfo's
    def get_stored_files_name(self):
        return [sfile for sfile in info(self.filename)['stored_files'].keys() if not sfile.lower().endswith(".srs")]

    def get_archived_fname(self):
        return list(info(self.filename)['archived_files'].keys())

    # search an srr for all archived-files that match given crc
    # returns array of FileInfo's matching the crc
    def get_archived_fname_by_crc(self, crc):
        return [value for value in info(self.filename)['archived_files'].values() if crc == value.crc32.zfill(8)]

    # search an srr for all archived-files that much a given filename
    # returns an array of FileInfo's matching the fname
    def get_archived_crc_by_fname(self, fname):
        return [k.crc32 for k in info(self.filename)['archived_files'].values() if k.file_name == fname]

    def get_srs(self, path):
        if not os.path.isdir(path):
            raise AttributeError("path must be a valid directory")

        srs_files = [sfile for sfile in info(self.filename)['stored_files'].keys() if sfile.lower().endswith(".srs")]
        return [extract_files(self.filename, path, extract_paths=True, packed_name=sfile) for sfile in srs_files]

    def get_srs_size(self, path):
        if not os.path.isdir(path):
            raise AttributeError("path must be a valid directory")

        matches = self.get_srs(path)
        return sum(SRS(srs_path).get_filesize() for match in matches for srs_path in match)

    def get_proof_filename(self):
        return [sfile for sfile in info(self.filename)['stored_files'].keys() if sfile.lower().endswith(('.jpg', '.jpeg', '.png'))]

    def extract_stored_files_regex(self, path, regex=".*"):
        if not os.path.isdir(path):
            raise AttributeError("path must be a valid directory")

        return [item for key in info(self.filename)["stored_files"].keys() if re.search(regex, key)
            for item in extract_files(self.filename, path, extract_paths=True, packed_name=key)]

    def reconstruct_rars(self, dinput, doutput, hints, rarfolder, tmpfolder):
        if not os.path.isdir(dinput) or not os.path.isdir(doutput):
            raise AttributeError("input and output folders must be valid directories.")

        if not rarfolder or not os.path.isdir(rarfolder) or not tmpfolder or not os.path.isdir(tmpfolder):
            # Allow script to work without anything set in res.py
            res = reconstruct(self.filename, dinput, doutput, hints=hints, auto_locate_renamed=True, extract_files=False)
        else:
            res = reconstruct(self.filename, dinput, doutput, hints=hints, auto_locate_renamed=True,
                              rar_executable_dir=rarfolder, tmp_dir=tmpfolder, extract_files=False)

        if res == -1:
            raise ValueError(f"One or more of the original files already exist in {doutput}")

        return True
