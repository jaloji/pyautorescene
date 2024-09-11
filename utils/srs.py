import os
from resample.srs import main as srsmain
from resample.main import file_type_info, FileType, sample_class_factory

class SRS:
    def __init__(self, filename, binary=None):
        if not os.path.isfile(filename):
            raise AttributeError("srs must be a file")
        if not filename.endswith(".srs"):
            raise AttributeError("srs file must have the .srs extension")

        self.filename = filename
        if binary == None:
            if os.name == 'posix':
                self.binary = '/usr/bin/srs'
            elif os.name == 'nt':
                self.binary = 'srs'
            else:
                self.binary = binary

        self.sample = sample_class_factory(file_type_info(self.filename).file_type)
        self.srs_data, _ = self.sample.load_srs(self.filename)

    def recreate(self, finput, doutput):
        if not os.path.isfile(finput):
            raise AttributeError("input file must be a valid file")
        if not os.path.isdir(doutput):
            raise AttributeError("output directory must be a valid directory")

        try:
            srsmain([self.filename, "-y", "-o", doutput, finput], True)
        except Exception:
            raise

    def get_filename(self):
        return self.srs_data.name

    def get_filesize(self):
        return self.srs_data.size

    def get_crc(self):
        return f"{self.srs_data.crc32 & 0xFFFFFFFF:08X}"
