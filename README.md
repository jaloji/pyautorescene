Forked
------
Forked from [sticki](https://bitbucket.org/sticki/pyautorescene)  

pyautorescene
=============
pyautorescene automates the process of returning un-rarred scene releases back into their former glory.  It makes use of [PyReScene](https://github.com/srrDB/pyrescene) and [srrDB](http://srrdb.com) to make the whole process has hands off as possible. 
With this fork, it is possible to log in your srrdb account to bypass the daily download limit of srr.
Now it is also possible to add only nfo/sfv/Sample/Proof/Subs if you already have releases in scene format but no longer the unrarred .mkv.

Requirements
------------
The main requirement is that you have already installed PyReScene from source as per the [instructions](https://web.archive.org/web/20190118053832/https://bitbucket.org/Gfy/pyrescene/src/).  This tool does not work with the pre-compiled .exes.

Installation
------------
1. Clone this repository to your local machine
2. Via terminal/command prompt navigate to the folder
3. Edit `utils/res.py`, fill `username/password` to login your srrdb account, 
4. Fill `rar_version` with the path that you have the WinRAR executables (you must run `preprardir.py` before) and fill `srr_temp_foder` who is just a temp folder for the recompressing process. (**Doesn't work under linux...**)
5. Run `python setup.py install`

Usage
-----
Currently, the best and most tested method of executing this script is `autorescene.py -vaf -o /path/to/output /path/to/input`

It is **seriously** recommended to output to a completely separate folder that you're happy to delete.


If you already have releases in scene format but no longer the unrarred .mkv and you want to search against srrdb if you have missing files like nfo/sfv/Sample/Proof/Subs do `autorescene.py -vc /path/to/input`

```
stick$ autorescene.py --help
usage: autorescene.py [--opts] input1 [input2] ...

automated rescening of unrarred/renamed scene files

positional arguments:
  input                 file or directory of files to be parsed

optional arguments:
  -h, --help            show this help message and exit
  -a, --auto-reconstruct
                        full auto rescene - this will scan directories, locate
                        files, check srrdb, and a release into a release dir
                        with original rars and nfo/sfv/etc and sample, if srs
                        exists - this is the same as -jkx
  -j, --rescene         recreate rars from extracted file/srr
  -k, --resample        recreate sample from original file/srs
  -f, --find-sample     if sample creation fails, look for sample file on disk
  -g, --resubs          look for sub rar if file is missing
  -o OUTPUT, --output OUTPUT
                        set the directory for all output
  -v, --verbose         verbose output for debugging purposes
  --rename              rename scene releases to their original scene
                        filenames
  -x, --extract-stored  extract stored files from srr (nfo, sfv, etc)
  -e EXTENSION, --extension EXTENSION
                        list of extensions to check against srrdb (default:
                        .mkv, .avi, .mp4, .iso)
  -c, --check-extras    check missing Sample/Proof, this will scan directories, 
                        check srrdb, and add into a release dir with original rars 
                        nfo/sfv/proof and recreate sample
  --check-crc           check crc in sfv file when using --check-extras
  --keep-srr            keep srr in output directory
  --keep-srs            keep srs in output directory
```
If you have a dynamic IP or you encounter a disconnection which causes an error like connect fail unknow (s) something then just double click on the bat file and relaunch the script **but before you need to edit it and change the username in the path by your own!**

To Do
-----
Make a better code for Subs reconstruction/check -> Working but little bugged, I'm not sure that will work with all subbed releases.
