Forked
------
Forked from [sticki](https://bitbucket.org/sticki/pyautorescene)  

pyautorescene 2.0
=============
pyautorescene automates the process of returning un-rarred scene releases back into their former glory.  It makes use of [PyReScene](https://github.com/srrDB/pyrescene) and [srrDB](http://srrdb.com) to make the whole process has hands off as possible.

With this fork, you can log into your srrDB account to bypass the daily download limit for .srr files. The redirection for srrxx is automatic, so you don't need to worry about it.

It is now also possible to add only NFO/SFV/Sample/Proof/Subs files if you already have scene releases but no longer have the unrarred .mkv files. You can rebuild missing files as long as they are in the same directory. 

Additionally, you can search unrarred files by CRC to check if an .srr file is available or if the CRC is valid, for example.

If the script crashes for any reason everything done is print inside `autorescene.txt` with and without `-v`.

Requirements on Windows
------------
The main requirement is to have already installed PyReScene from source as per the [instructions](https://web.archive.org/web/20190118053832/https://bitbucket.org/Gfy/pyrescene/src/).  This tool does not work with the pre-compiled .exes.

For compressed RAR, use these two WinRAR setup packs:
* [<=4.20 + betas](http://www.mediafire.com/?ooedhgdei3cm72u)
* [5.50b1 up to 7.00b4](https://www.mediafire.com/file/jvgoh37eq71d6og/RARSETUP-X64-511%252B550b1-to-700b4.rar)

Use this powershell script [preprardir.ps1](https://github.com/MRiCEQB/PS_preprardir), You just need to extract these packs and, with admin rights, run the following command in the directory you want (for x86, there are more versions available): `powershell -executionpolicy bypass -File .\preprardir.ps1`.

Installation on Windows
------------
1. Clone this repository to your local machine
2. Via terminal/command prompt navigate to the folder
3. Edit `utils/res.py`, fill `USERNAME/PASSWORD` to log into your srrdb account, 
4. Fill `RAR_VERSION` path to the WinRAR executables (ensure you run `preprardir.ps1` beforehand) and set `SRR_TEMP_FOLDER` who is just a temp folder for the recompressing process.
5. Fill `SRS_NET_EXE` because we need an absolute path and maybe you haven't the same path until `pyautorescene-master\utils\srs.exe`.
6. Run `python setup.py install`

Requirements on Linux (Debian)
------------
The main requirement is to have already installed PyReScene from source as per the [instructions](https://web.archive.org/web/20190118053832/https://bitbucket.org/Gfy/pyrescene/src/) and use Python 3.9.

For compressed RAR files (to run old RAR binaries) and ReSample .NET 1.2, you will need the following libraries:
```
dpkg --add-architecture i386
apt-get update
apt-get install libc6-i386 libstdc++5 libstdc++5:i386 lib32stdc++6 lib32z1 lib32ncurses6 mono-complete
wget http://archive.debian.org/debian/pool/main/g/gcc-2.95/libstdc++2.10-glibc2.2_2.95.4-27_i386.deb
dpkg -i libstdc++2.10-glibc2.2_2.95.4-27_i386.deb
```
You can install UnRAR via `apt-get install unrar`, but it's recommended to compile it from source for the latest version:
```
wget https://www.rarlab.com/rar/unrarsrc-7.0.9.tar.gz
tar xzf unrarsrc-7.0.9.tar.gz
cd unrar
make
make install
```
Use this RAR setup pack [x86](https://github.com/jaloji/rarlinux/tree/master/x86) or [x64](https://github.com/jaloji/rarlinux/tree/master/x64) and use `python3 /app/pyrescene-master/bin/preprardir.py -b /rarlinux/x86 /app/rarv`.

If something is missing you can check in my Dockerfile.

Installation on Linux (Debian)
------------
1. Clone this repository to your local machine
2. Via terminal/command prompt navigate to the folder
3. Edit `utils/res.py`, fill `USERNAME/PASSWORD` to log into your srrdb account, 
4. Set `RAR_VERSION` with the path that you have the RAR executables (you must run `preprardir.py -b` before) and set `SRR_TEMP_FOLDER` who is just a temp folder for the recompressing process.
5. Fill `SRS_NET_EXE` because we need an absolute path and maybe you haven't the same path until `pyautorescene-master/utils/srs.exe`.
6. Run `python setup.py install`

And MacOS ?
------------
Ask to Apple.

Usage
-----
Currently, the best and most tested method of executing this script is:
```autorescene.py -vaf -o /path/to/output /path/to/input```

It is **seriously** recommended to output to a completely separate folder that you're happy to delete.


If you already have releases in scene format but no longer the unrarred .mkv and you want to search against srrdb if you have missing files like nfo/sfv/Sample/Proof/Subs do:
```autorescene.py -vc /path/to/input```

If you want to do te same with check CRC:
```autorescene.py -vc --check-crc /path/to/input```

If you want to search files against srrdb to know if they are corrupt or if they have a .srr available do:
```autorescene.py -vs /path/to/input```

```
jaloji$ autorescene.py --help
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
  -s, --search-srrdb    check crc against srrdb and print release name
```

If you have a dynamic IP or you encounter a disconnection which causes an error like this:

```
- Connecting srrdb.com...  [FAIL]  -> ValueError() takes no keyword arguments
- Searching srrdb.com for matching Release: release.name  [FAIL]  -> name 's' is not defined
```

Then use the .bat/.sh file and relaunch the script **but before you need to edit .bat/.sh and change the username in the path by your own!**

NEW IN V2.0
-----
* Completely rewritten, optimized, simplified, and modernized code
* Fixed many crashes and bugs, such as:
  - Crashes when multiples proof or .srs inside .srr
  - Crashes without any reason except bad code
  - Didn't case sensitive for file extension or path
  - Not a good exclusion method for subdirs of a release for -vc (check extras) with or without --check-crc
  - Not a good method for subrar check or reconstruction
  - Skipping a file if a release have already been checked didn't work well
* Fixed counters for scanned release and success release
* Fixed multiple different print style when Sample, Proof, Subs rar or release rar is missing
* Fixed subtitles rebuild for:
  - Single Subs .rar: idx and sub in the same .rar file
  - Double Subs .rar: a .rar file with .idx or .sub inside a rar with .idx or .sub too
  - Multiple Subs .rar: multiple .rar with .idx and .sub inside a .rar (many of cd1/cd2 release use this one) 
* Added feature to search files against srrdb with CRC to know if .srr exist or if CRC is valid
* Added feature to check anomalies in the release, like double nfos, sfv missing, multiple Proof or Sample dir and many other things...
* Added a counter for no matched result
* Added orange color highlighting when a RAR reconstruction is using compression method
* Added retrocompatibility with ReSample .NET 1.2 for very old .srs files that PyRescene-0.7 cannot rebuild
* Added support for rebuild compressed RARs with Linux
* Added support for multiple .rar subs in Subs dir
* Added skip extracting stored files in SRR if already exist
* Fixed get_srs() to directly exctract .srs if .srr contain .srs but already present on the disk so not extracted the first time
* Fixed some subs stuff...
* Fixed rls_check is now after each release only the result is print at the end to prevent any data loose if the script crashes
* Added custom logger, works if -v is set or not
* Added a progress bar and final stats when -v is not set
* Maybe more but I don't remember...

To Do
-----
* Get feedback on bugs for Windows and Linux

docker-pyautorescene
=============
A docker version is available here: [docker-pyautorescene](https://github.com/jaloji/docker-pyautorescene)
