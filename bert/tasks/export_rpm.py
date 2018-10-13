
import collections
from enum import IntEnum
import gzip
import hashlib
import io
import os
import re
import tarfile
import tempfile
import shutil
import struct

try:
    import bz2
except ImportError:
    bz2 = None

try:
    import lzma
except ImportError:
    lzma = None

from . import Task
from ..utils import IOFromIterable

# This is derived from arch_canon entries in rpmrc
# (We don't include the uname equiv portion)
ARCH_CANON = {
    "aarch64": 19, "alpha": 2, "alphaev5": 2, "alphaev56": 2,
    "alphaev6": 2, "alphaev67": 2, "alphapca56": 2, "amd64": 1, "armv3l": 12,
    "armv4b": 12, "armv4l": 12, "armv5tejl": 12, "armv5tel": 12,
    "armv5tl": 12, "armv6hl": 12, "armv6l": 12, "armv7hl": 12, "armv7hnl": 12,
    "armv7l": 12, "athlon": 1, "em64t": 1, "geode": 1, "i370": 14,
    "i386": 1, "i486": 1, "i586": 1, "i686": 1, "ia32e": 1, "ia64": 9,
    "m68k": 6, "m68kmint": 13, "mips": 4, "mips64": 11, "mips64el": 11,
    "mips64r6": 21, "mips64r6el": 21, "mipsel": 4, "mipsr6": 20,
    "mipsr6el": 20, "noarch" : 1, "pentium3": 1, "pentium4": 1, "ppc32dy4": 5, "ppc": 5,
    "ppc64": 16, "ppc64iseries": 16, "ppc64le": 16, "ppc64p7": 16,
    "ppc64pseries": 16, "ppc8260": 5, "ppc8560": 5, "ppciseries": 5,
    "ppcpseries": 5, "riscv64": 22, "rs6000": 8, "s390": 14, "s390x": 15,
    "sgi": 7, "sh": 17, "sh3": 17, "sh4": 17, "sh4a": 17, "sparc": 3,
    "sparc64": 2, "sparc64v": 2, "sparcv8": 3, "sparcv9": 3, "sparcv9v": 3,
    "x86_64": 1, "xtensa": 18
}

# This is derived from os_canon entries in rpmrc
# (We don't include the uname equiv portion)
OS_CANON = {
    "Linux": 1, "Irix": 2, "solaris": 3, "SunOS": 4, "AmigaOS": 5, "AIX": 5,
    "hpux10": 6, "osf1": 7, "FreeBSD": 8, "SCO_SV3.2v5.0.2": 9, "Irix64": 10,
    "NextStep": 11, "bsdi": 12, "machten": 13, "cygwin32": 14, "cygwin32": 15,
    "MP_RAS:": 16, "FreeMiNT": 17, "OS/390": 18, "VM/ESA": 19, "OS/390": 20,
    "VM/ESA": 20, "darwin": 21, "macosx": 21
}

class RPMSense(IntEnum):
    Less = 0x02
    Greater = 0x04
    Equal = 0x08
    PreReq = 0x40
    Interp = 0x100
    ScriptPre = 0x200
    ScriptPost = 0x400
    ScriptPreUn = 0x800
    ScriptPostUn = 0x1000
    RPMLib = 0x1000000

#
# RPM Tag Types
#

def _rpm_tag_multiple(type_tag, alignment, struct_type, val):
    if isinstance(val, list):
        return type_tag, alignment, len(val), b"".join(struct.pack(struct_type, v) for v in val)
    else:
        return type_tag, alignment, 1, struct.pack(struct_type, val)

def rpm_tag_null(name, value):
    return 0, 0, 0, b""

def rpm_tag_char(name, value):
    return _rpm_tag_multiple(1, 0, '!c', value)

def rpm_tag_int8(name, value):
    return _rpm_tag_multiple(2, 0, '!B', value)

def rpm_tag_int16(name, value):
    return _rpm_tag_multiple(3, 2, '!H', value)

def rpm_tag_int32(name, value):
    return _rpm_tag_multiple(4, 4, '!I', value)

def rpm_tag_int64(name, value):
    return _rpm_tag_multiple(5, 8, '!Q', value)

def rpm_tag_str(name, value):
    if not isinstance(value, (str, bytes)):
        value = str(value)
    if isinstance(value, str):
        value = value.encode('utf-8')
    return 6, 0, 1, value + b'\x00'

def rpm_tag_bin(name, value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return 7, 0, len(value), value

def rpm_tag_str_array(name, value):
    if not isinstance(value, list):
        value = [value]

    encoded_values = [v.encode('utf-8') if isinstance(v, str) else v for v in value]
    return 8, 0, len(value), b"".join(v + b'\x00' for v in encoded_values)

#
# RPM Tag Names
#

class RPMTag(object):
    def __init__(self, id_, name, type_func):
        self.name = name
        self.id = id_
        self.type_func = type_func

# This is derived from lib/rpmtag.h
RPM_TAGS = [RPMTag(*a) for a in [
    # sig
    (1000, 'sig_size', rpm_tag_int32),
    (1001, 'sig_md5', rpm_tag_bin),

    # Header
    (1000, 'name', rpm_tag_str),
    (1001, 'version', rpm_tag_str),
    (1002, 'release', rpm_tag_str),
    (1003, 'epoch', rpm_tag_int32),
    (1004, 'summary', rpm_tag_str),
    (1005, 'description', rpm_tag_str),
    (1009, 'size', rpm_tag_int32),
    (1010, 'distribution', rpm_tag_str),
    (1011, 'vendor', rpm_tag_str),
    (1014, 'license', rpm_tag_str),
    (1015, 'packager', rpm_tag_str),
    (1020, 'url', rpm_tag_str),
    (1021, 'os', rpm_tag_str),
    (1022, 'arch', rpm_tag_str),
    (1023, 'prein', rpm_tag_str),
    (1024, 'postin', rpm_tag_str),
    (1025, 'preun', rpm_tag_str),
    (1026, 'postun', rpm_tag_str),
    (1028, 'filesizes', rpm_tag_int32),
    (1030, 'filemodes', rpm_tag_int16),
    (1033, 'filerdevs', rpm_tag_int16),
    (1034, 'filemtimes', rpm_tag_int32),
    (1035, 'filemd5s', rpm_tag_str_array),
    (1036, 'filelinktos', rpm_tag_str_array),
    (1037, 'fileflags', rpm_tag_int32),
    (1039, 'fileusername', rpm_tag_str_array),
    (1040, 'filegroupname', rpm_tag_str_array),
    (1047, 'providename', rpm_tag_str_array),
    (1048, 'requireflags', rpm_tag_int32),
    (1049, 'requirename', rpm_tag_str_array),
    (1050, 'requireversion', rpm_tag_str_array),
    (1053, 'conflictflags', rpm_tag_int32),
    (1054, 'conflictname', rpm_tag_str_array),
    (1055, 'conflictversion', rpm_tag_str_array),
    (1085, 'preinprog', rpm_tag_str),
    (1086, 'postinprog', rpm_tag_str),
    (1087, 'preunprog', rpm_tag_str),
    (1088, 'postunprog', rpm_tag_str),
    (1090, 'obsoletename', rpm_tag_str_array),
    (1095, 'filedevices', rpm_tag_int32),
    (1096, 'fileinodes', rpm_tag_int32),
    (1097, 'filelangs', rpm_tag_str_array),
    (1112, 'provideflags', rpm_tag_int32),
    (1113, 'provideversion', rpm_tag_str_array),
    (1114, 'obsoleteflags', rpm_tag_int32),
    (1115, 'obsoleteversion', rpm_tag_str_array),
    (1116, 'dirindexes', rpm_tag_int32),
    (1117, 'basenames', rpm_tag_str_array),
    (1118, 'dirnames', rpm_tag_str_array),
    (1124, 'payloadformat', rpm_tag_str),
    (1125, 'payloadcompressor', rpm_tag_str),
    (1126, 'payloadflags', rpm_tag_str),
]]

RPM_TAGS_BY_NAME = {tag.name : tag for tag in RPM_TAGS}

#
#
#

def _align_data(data, data_offset, data_align):
    if data_offset % data_align != 0:
        add_bytes = data_align - (data_offset % data_align)
        data.append(b'\x00'*add_bytes)
        data_offset += add_bytes
    return data_offset

def _align_padding(bs, align, padding=b'\x00'):
    if bs % align != 0:
        add_bytes = align - (bs % align)
        return padding*add_bytes
    return b''

def make_rpm_header(header, version=1):
    data = []
    data_offset = 0
    index = []

    # build out chunks of index and data
    for name, value in header.items():
        rpm_tag = RPM_TAGS_BY_NAME[name]
        type_id, data_align, count, new_data = rpm_tag.type_func(name, value)

        if data_align != 0:
            data_offset = _align_data(data, data_offset, data_align)

        index.append(struct.pack('!iiii', rpm_tag.id, type_id, data_offset, count))
        data.append(new_data)
        data_offset += len(new_data)

    # finish making header
    index_bytes = b"".join(index)
    data_bytes = b"".join(data)

    return b'%s%s%s'%(
        struct.pack('!3sBxxxxII', b'\x8e\xad\xe8', version, len(index), data_offset),
        index_bytes,
        data_bytes
    )

class RPMFileItem(object):
    def __init__(self, filename, size=0, mode=0o644, rdev=0, mtime=0, md5=None,
            nlink=1, linkto=None, flags=0, user="root", group="group", inode=0, device=0, lang=""):
        self.filename = filename
        self.basename = os.path.basename(filename)
        self.dirname = os.path.join(os.path.dirname(filename), "")
        self.size = size
        self.mode = mode
        self.rdev = rdev
        self.mtime = mtime
        self.md5 = md5 or hashlib.md5()
        self.nlink = nlink
        self.linkto = linkto
        self.flags = flags
        self.user = user
        self.group = group
        self.inode = inode
        self.device = device
        self.lang = lang

class RPMDep(object):
    RE_VERSIONED = re.compile(r'^(?P<name>.*?)\s*(?P<cmp>=|>=|<=|>|<)\s*(?P<version>\d.*?)$')

    CMP_TO_FLAG = {
        '=' : RPMSense.Equal,
        '>=' : RPMSense.Equal | RPMSense.Greater,
        '>' : RPMSense.Greater,
        '<=' : RPMSense.Equal | RPMSense.Less,
        '<' : RPMSense.Less
    }

    def __init__(self, name, version=None, flags=0):
        m = self.RE_VERSIONED.match(name)
        if m:
            name = m.group("name")
            version = m.group("version")
            flags |= self.CMP_TO_FLAG[m.group("cmp")]

        if name.startswith("rpmlib("):
            flags |= RPMSense.RPMLib

        self.name = name
        self.version = version
        self.flags = flags

class RPMBuild(object):
    def __init__(self, job, value):
        self.name = job.template(value["name"])
        self.epoch = job.template(value.get("epoch", None))
        self.version = job.template(value.get("version", "0.0"))
        self.release = job.template(value.get("release", "0"))
        self.arch = job.template(value.get("arch", "noarch"))
        self.rpm_os = job.template(value.get("os", "Linux"))
        self.url = job.template(value.get("url"))
        self.summary = job.template(value.get("summary"))
        self.description = job.template(value.get("description"))
        self.header = {k.lower(): v for k,v in job.template(value.get("header", {})).items()}
        self.compress_type = job.template(value.get("compress-type", "bzip2"))

        self.provides = []
        self.requires = [
            RPMDep("rpmlib(PayloadFilesHavePrefix) <= 4.0-1"),
            RPMDep("rpmlib(CompressedFileNames) <= 3.0.4-1")
        ]
        self.conflicts = []
        self.obsoletes = []

        self.payload_flags = 0
        if not self.compress_type:
            self.compress_type = "gzip"

        if self.compress_type == "gzip":
            self.payload_flags = self.compress_level = 9
            self.compressor = lambda f: gzip.GzipFile(filename='', fileobj=f, compresslevel=self.compress_level)
        elif self.compress_type == "bzip2":
            if bz2 is None:
                raise RuntimeError("bzip2 compression not available")
            self.payload_flags = self.compress_level = 9
            self.compressor = lambda f: bz2.BZ2File(f, mode='a', compresslevel=self.compress_level)
            self.requires.append(RPMDep("rpmlib(PayloadIsBzip2) <= 3.0.5-1"))
        elif self.compress_type == "xz":
            if lzma is None:
                raise RuntimeError("LZMA compression not available")
            self.payload_flags = 7 # XXX Sometimes this is 2?  Why?
            self.compressor = lambda f: lzma.LZMAFile(f, mode='a', preset=self.payload_flags, check=lzma.CHECK_SHA256)
            self.requires.append(RPMDep("rpmlib(PayloadIsXz) <= 5.2-1"))
        else:
            raise RuntimeError("Unknown compressor")

        if self.epoch is not None:
            self.name_full = "{0.name}-{0.epoch}:{0.version}-{0.release}".format(self)
        else:
            self.name_full = "{0.name}-{0.version}-{0.release}".format(self)

        try:
            dest = job.template(value["dest"])
        except KeyError:
            dest = None

        dest_dir = "."
        if dest:
            if dest.endswith("/") or os.path.isdir(dest):
                dest_dir = dest
                dest = None

        if "dest-dir" in value:
            dest_dir = job.template(value["dest-dir"])

        if dest is None:
            self.dest = os.path.join(dest_dir, "{}.{}.rpm".format(self.name_full, self.arch))
        else:
            self.dest = dest

        # allow either
        self.paths = value.get('paths', [])
        install_path = value.get('install-path')
        if install_path:
            self.paths.append(paths)

        if not self.paths:
            raise RuntimeError("Need a path")

        self._add_to_header("name", self.name)
        self._add_to_header("epoch", self.epoch)
        self._add_to_header("url", self.url)
        self._add_to_header("summary", self.summary)
        self._add_to_header("description", self.description)
        self._add_to_header("version", self.version)
        self._add_to_header("release", self.release)
        self._add_to_header("arch", self.arch)
        self._add_to_header("os", self.rpm_os)

        self._reset()

    def _reset(self):
        self.path_idx = 0
        self.install_size = 0
        self.files = []
        self.contents_md5 = hashlib.md5()

    def _add_to_header(self, name, value, override=False):
        if name in self.header and not override:
            return
        if value is None:
            return
        self.header[name.lower()] = value

    def _put_deps(self, header, items, namefield, versionfield, flagfield):
        if not items:
            return

        names = []
        versions = []
        flags = []

        for item in items:
            names.append(item.name)
            versions.append(item.version)
            flags.append(int(item.flags))

        header[namefield] = names
        header[versionfield] = versions
        header[flagfield] = flags

    def build(self, job):
        lead = struct.pack("!4sBBhh65sxhh16x",
            # unsigned char magic[4]
            b'\xed\xab\xee\xdb',
            # unsigned char major, minor
            3, 0,
            # short type (binary)
            0,
            # short archnum
            ARCH_CANON.get(self.arch, -1),
            # char name[66]
            self.name_full.encode('ascii', errors='replace'),
            # short osnum
            OS_CANON.get(self.rpm_os, -1),
            # short signature_type (RPMSIGTYPE_HEADERSIG)
            5
        )

        self._reset()

        container = job.create({})
        with tempfile.TemporaryFile() as contents_f, tempfile.TemporaryFile() as header_f:
            for path in self.paths:
                self._copy_data(container, contents_f, path)
            self._write_cpio_trailer(contents_f)

            all_dirnames = sorted(set(f.dirname for f in self.files))
            all_dirnames_lookup = {val:idx for idx,val in enumerate(all_dirnames)}

            header = dict(self.header)
            self._put_deps(header, self.requires, 'requirename', 'requireversion', 'requireflags')
            self._put_deps(header, self.provides, 'providename', 'provideversion', 'provideflags')
            self._put_deps(header, self.conflicts, 'conflictname', 'conflictversion', 'conflictflags')
            self._put_deps(header, self.obsoletes, 'obsoletename', 'obsoleteversion', 'obsoleteflags')
            header['dirnames'] = all_dirnames
            header['dirindexes'] = [all_dirnames_lookup[f.dirname] for f in self.files]
            header['basenames'] = [f.basename for f in self.files]
            header['filesizes'] = [f.size for f in self.files]
            header['filemodes'] = [f.mode&0xffff for f in self.files]
            header['filerdevs'] = [f.rdev&0xffff for f in self.files]
            header['filemtimes'] = [f.mtime for f in self.files]
            header['filemd5s'] = [f.md5.hexdigest() for f in self.files]
            header['filelinktos'] = [(f.linkto or "") for f in self.files]
            header['fileflags'] = [f.flags for f in self.files]
            header['fileusername'] = [f.user for f in self.files]
            header['filegroupname'] = [f.group for f in self.files]
            header['fileinodes'] = [f.inode for f in self.files]
            header['filedevices'] = [f.device for f in self.files]
            header['filelangs'] = [f.lang for f in self.files]
            header['size'] = self.install_size
            header['payloadformat'] = "cpio"
            header['payloadcompressor'] = self.compress_type
            header['payloadflags'] = self.payload_flags
            rpm_header = make_rpm_header(header)

            header_f.write(rpm_header)
            self.contents_md5.update(rpm_header)

            contents_f.seek(0)
            while True:
                chunk = contents_f.read(2**14)
                if not chunk:
                    break
                self.contents_md5.update(chunk)

            sig_header = make_rpm_header({
                'sig_size' : contents_f.tell() + header_f.tell(),
                'sig_md5' : self.contents_md5.digest()
            })

            with open(self.dest+".tmp", "wb") as f:
                f.write(lead)

                f.write(sig_header)
                f.write(_align_padding(f.tell(), 8))

                header_f.seek(0)
                shutil.copyfileobj(header_f, f)

                contents_f.seek(0)
                with self.compressor(f) as comp_f:
                    shutil.copyfileobj(contents_f, comp_f)

        os.rename(self.dest+".tmp", self.dest)

    def _copy_data(self, container, cpiof, path):
        dirname = os.path.dirname(path)
        tstream, tstat = container.get_archive(path)
        tf = IOFromIterable(tstream)

        with tarfile.open(fileobj=tf, mode="r|") as tin:
            while True:
                ti = tin.next()
                if ti is None:
                    break

                self.path_idx += 1
                tdata = tin.extractfile(ti) if ti.isreg() else None
                filename = os.path.join(dirname, ti.name)
                nlink = (2 if ti.isdir() else 1)

                user = "root"
                if ti.uname:
                    user = ti.uname
                elif ti.uid != 0:
                    user = str(ti.uid)
                group = "root"
                if ti.gname:
                    group = ti.gname
                elif ti.gid != 0:
                    group = str(ti.gid)

                # cpio header
                filename_utf8 = os.path.join(".", os.path.relpath(filename, "/")).encode('utf-8') + b'\x00'
                cpiof.write(b"".join((
                    b"070701",
                    b"%08x"%self.path_idx,
                    b"%08x"%ti.mode,
                    b"%08x"%ti.uid,
                    b"%08x"%ti.gid,
                    b"%08x"%nlink,
                    b"%08x"%ti.mtime,
                    b"%08x"%ti.size,
                    b"%08x"%0,
                    b"%08x"%0,
                    b"%08x"%0,
                    b"%08x"%0,
                    b"%08x"%(len(filename_utf8)-1),
                    b"%08x"%0
                )))

                # cpio filename
                cpiof.write(filename_utf8)
                cpiof.write(_align_padding(cpiof.tell(), 4))

                # cpio contents
                sz = 0
                md5hash = hashlib.md5()
                while True:
                    chunk = tdata.read(2**14)
                    if not chunk:
                        break
                    sz += len(chunk)
                    md5hash.update(chunk)
                    cpiof.write(chunk)

                self.install_size += sz
                cpiof.write(_align_padding(cpiof.tell(), 4))

                self.files.append(RPMFileItem(
                    filename,
                    size=ti.size,
                    mode=ti.mode,
                    mtime=ti.mtime,
                    md5=md5hash,
                    nlink=nlink,
                    linkto=ti.linkname,
                    user=user,
                    group=group,
                    inode=self.path_idx,
                ))

    def _write_cpio_trailer(self, cpiof):
        cpiof.write(
            b"07070100000000000000000000000000000000000000010000000000000000000"
            b"000000000000000000000000000000000000b00000000TRAILER!!!\x00\x00\x00\x00"
        )

class TaskExportRpm(Task, name="export-rpm"):
    def run(self, job):
        build = RPMBuild(job, self.value)

        if os.path.exists(build.dest) and not job.changes:
            return

        build.build(job)
