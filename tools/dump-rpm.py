#!/usr/bin/env python3

import click
import struct

def header_read_str(data, offset):
    end = data.find(b'\0', offset)
    return data[offset:end]

def header_read_str_multiple(data, offset, count):
    rv = []
    for i in range(count):
        end = data.find(b'\0', offset)
        rv.append(data[offset:end])
        offset = end + 1
    return rv

def header_unpack(data, offset, fmt, count):
    sz = struct.calcsize(fmt)
    if count > 1:
        return [struct.unpack(fmt, data[offset+i*sz:offset+(i+1)*sz])[0] for i in range(count)]
    else:
        return struct.unpack(fmt, data[offset:offset+sz])[0]

def skip_align(fileobj, align):
    here = fileobj.tell()
    if here % align != 0:
        add_bytes = align - (here % align)
        fileobj.seek(here+add_bytes)

def dump_rpm_lead(fileobj):
    fmt = "!4sBBhh65sxhh16x"
    data = fileobj.read(struct.calcsize(fmt))
    magic, major, minor, rpm_type, archnum, name, osnum, sig_type = struct.unpack(fmt, data)
    name = name.rstrip(b'\0').decode('utf-8')
    click.secho(f"RPM v{major}.{minor} {name} os={osnum} arch={archnum} sig={sig_type}", fg="blue")

def dump_rpm_header(fileobj, header_name):
    fmt = '!3sBxxxxII'
    header_magic, header_version, length, data_size = struct.unpack(fmt, fileobj.read(struct.calcsize(fmt)))
    click.secho(f"-- {header_name} v{header_version} n={length} data_size={data_size}", fg="blue")

    index = [struct.unpack('!iiii', fileobj.read(16)) for i in range(length)]
    data = fileobj.read(data_size)

    for tag_id, type_id, offset, count in index:
        if type_id == 0:
            txt_prefix = f"{tag_id}:"
        else:
            txt_prefix = f"{tag_id}: @{offset}:{count}"

        if tag_id in (62, 63):
            txt_value = ",".join(map(str, struct.unpack('!iiii', data[offset:offset+count])))
        elif type_id == 0:
            txt_value = "null"
        elif type_id == 1:
            value = header_unpack(data, offset, '!c', count)
            txt_value = f"(c) {value!r}"
        elif type_id == 2:
            value = header_unpack(data, offset, '!B', count)
            txt_value = f"(i8) {value}"
        elif type_id == 3:
            value = header_unpack(data, offset, '!H', count)
            txt_value = f"(i16) {value}"
        elif type_id == 4:
            value = header_unpack(data, offset, '!I', count)
            txt_value = f"(i32) {value}"
        elif type_id == 5:
            value = header_unpack(data, offset, '!Q', count)
            txt_value = f"(i64) {value}"
        elif type_id == 6:
            value = header_read_str(data, offset).decode('utf-8')
            txt_value = f"(s) {value}"
        elif type_id == 7:
            value = data[offset:offset+count]
            txt_value = f"(x) {value!r}"
        elif type_id == 8:
            value = [s.decode('utf-8') for s in header_read_str_multiple(data, offset, count)]
            txt_value = f"(s) {value}"
        else:
            txt_value = f"unknown type {type_id}"

        click.echo(f"{txt_prefix} {txt_value}")

def dump_rpm(fileobj):
    dump_rpm_lead(fileobj)

    dump_rpm_header(fileobj, "Sig")
    skip_align(fileobj, 8)
    dump_rpm_header(fileobj, "Header")


@click.command()
@click.argument('target')
def cli(target):
    with open(target, "rb") as f:
        dump_rpm(f)

if __name__=='__main__':
    cli()
