#!/usr/bin/env python3

import argparse
import boto3
import hashlib
import json
import mimetypes
import os
import posixpath
import sys
import tarfile

def is_valid_doc_version(v):
    if not v:
        return False
    if v == "latest":
        return True
    return re.search(r'^\d+\.\d+$', v) is not None

def get_mimetype(filename):
    filename = posixpath.basename(filename)
    mime_type, encoding = mimetypes.guess_type(filename)
    if mime_type is not None:
        return mime_type
    return "application/octet-stream" 

def s3_items(s3, bucket, prefix):
    s3 = boto3.client('s3')
    req = {
        'Bucket': bucket,
        'Prefix' : prefix
    }

    while True:
        resp = s3.list_objects_v2(**req)
        for obj in resp['Contents']:
            yield obj['Key']

        try:
            req['ContinuationToken'] = resp['NextContinuationToken']
        except KeyError:
            break

def s3_metadata(s3, bucket, key):
    resp = s3.head_object(Bucket=bucket, Key=key)
    return resp.get("Metadata", {})

def hash_fileobj(f, name):
    h = hashlib.new(name)
    while True:
        chunk = f.read()
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", "-b", required=True)
    parser.add_argument("--tag", "-t")
    parser.add_argument("--strip-dir", default=1)
    parser.add_argument("--src", "-s", default="dist/bert-docs.tar.bz2")

    args = parser.parse_args()

    tag = args.tag
    if tag is None:
        # Infer tag from CI environment
        tag = os.environ.get("CI_COMMIT_TAG", "latest")

    if "." in tag:
        version_major = ".".join(tag.split(".")[:2])
    else:
        version_major = tag
    
    if not is_valid_doc_version(version_major):
        print("Invalid version to publish as!  Expect single number or 'latest'")
        sys.exit(1)

    s3 = boto3.client('s3')

    previous_items = set(s3_items(s3, args.bucket, version_major))

    with tarfile.open(args.src, "r") as tf:
        for titem in tf.getmembers():
            path_split = titem.name.split("/")
            if len(path_split) < args.strip_dir + 1:
                continue
            name = posixpath.join(version_major, *path_split[1:])

            tdata = tf.extractfile(titem)
            if tdata is None:
                continue

            has_item_already = name in previous_items
            previous_items.discard(name)

            sha256 = hash_fileobj(tdata, 'sha256')
            if has_item_already:
                metadata = s3_metadata(s3, args.bucket, name)
                sha256_previous = metadata.get('sha256')
                if sha256 == sha256_previous:
                    print("Skip: %s"%name)
                    continue

            tdata.seek(0)

            print("Upload: %s"%name)
            s3.upload_fileobj(tdata, args.bucket, name, {
                'ContentType' : get_mimetype(name),
                'CacheControl' : "max-age=86400",
                'Metadata' : {
                    'sha256' : sha256
                }
            })

    for item in previous_items:
        print("Delete: %s"%item)
        s3.delete_object(Bucket=args.bucket, Key=item)

if __name__=='__main__':
    main()
