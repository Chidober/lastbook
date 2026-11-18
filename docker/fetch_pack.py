#!/usr/bin/env python3
"""Download a Lastbook pack straight into a directory (the host mount).

The zip is saved under <dest>/.download and extracted there. Members live under
LastbookData/ inside the zip; that prefix is stripped so library-data/ and
derived/ are written in dest. Nothing is staged elsewhere and then copied.
"""
import fcntl
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = 'https://downloads.lastbook.org/manifest-v1.json'
# downloads.lastbook.org answers 403 to Python's default User-Agent.
UA = 'Lastbook-setup/1'


def die(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def open_url(url, headers=None, timeout=60):
    hdrs = {'User-Agent': UA, 'Accept-Encoding': 'identity'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read(200).decode('utf-8', 'replace').strip()
        die(f'下载服务器拒绝了请求（HTTP {e.code}）{": " + body if body else ""}。地址: {url}')
    except urllib.error.URLError as e:
        die(f'无法连接下载服务器（{e.reason}）。地址: {url}')


def manifest():
    with open_url(MANIFEST) as r:
        data = json.load(r)
    packs = {p['id']: p for p in data.get('packs') or [] if p.get('available')}
    return packs


def exclusive(path):
    """One download per zip. A second deploy must not open another connection to the same file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, 'a')
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        die(f'已有下载在写 {path.parent.name}/{path.name}，这次不再另开一路。')
    return fh


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for buf in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(buf)
    return digest.hexdigest()


def part_path(zip_path):
    return zip_path.with_suffix(zip_path.suffix + '.part')


def have_zip(zip_path, size, sha256):
    """A finished zip, or a .part that already has every byte. Verify it, then keep the zip and skip the network."""
    candidates = [p for p in (zip_path, part_path(zip_path)) if p.is_file()]
    for path in candidates:
        if size and path.stat().st_size != size:
            continue
        print(f'checking existing {path}', flush=True)
        if sha256 and sha256_file(path) != sha256:
            print(f'{path} is the right size but the checksum does not match; downloading again', flush=True)
            continue
        if path != zip_path:
            os.replace(path, zip_path)
        return True
    return False


def locate_zip(name, size, sha256, folders):
    """Look in the mount directory itself, then in its .download folder."""
    for folder in folders:
        zip_path = Path(folder) / name
        if have_zip(zip_path, size, sha256):
            return zip_path
    return None


def download(url, dest, size, sha256):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + '.part')
    got = part.stat().st_size if part.exists() else 0
    headers = {}
    if got and (not size or got < size):
        headers['Range'] = f'bytes={got}-'
    with open_url(url, headers, timeout=120) as r, open(part, 'ab' if got else 'wb') as f:
        if r.status == 200 and got:
            f.seek(0)
            f.truncate()
        while True:
            buf = r.read(8 * 1024 * 1024)
            if not buf:
                break
            f.write(buf)
            got += len(buf)
            print(f'\r  {dest.name}: {got / 1e9:.2f} GB', end='', file=sys.stderr, flush=True)
    print(file=sys.stderr)
    digest = hashlib.sha256()
    with open(part, 'rb') as f:
        for buf in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(buf)
    if sha256 and digest.hexdigest() != sha256:
        die(f'checksum mismatch for {dest.name}')
    os.replace(part, dest)
    return dest


def extract(zip_path, dest):
    dest = Path(dest)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename.replace('\\', '/')
            if name.startswith('/') or '..' in name.split('/'):
                die(f'refused path in zip: {name}')
            parts = [p for p in name.split('/') if p not in ('', '.')]
            if not parts:
                continue
            if parts[0] == 'LastbookData':
                parts = parts[1:]
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode and mode not in (0o100000, 0o040000):
                die(f'refused special file in zip: {name}')
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, 'wb') as out:
                while True:
                    buf = src.read(8 * 1024 * 1024)
                    if not buf:
                        break
                    out.write(buf)


def ready(dest, pack_id=None):
    """True when dest already holds a library. If pack.json names a pack, it must be this one."""
    root = Path(dest)
    catalog = root / 'library-data' / 'catalog.json'
    try:
        data = json.loads(catalog.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    if isinstance(data, list):
        if not data:
            return False
    elif isinstance(data, dict):
        if not data:
            return False
    else:
        return False
    try:
        name = json.loads((root / 'pack.json').read_text(encoding='utf-8')).get('name')
    except (OSError, ValueError):
        name = None
    if pack_id and isinstance(name, str) and name and name != pack_id:
        return False
    return True


def main():
    pack_id, dest, force, check = None, None, False, False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--pack':
            pack_id = args[i + 1]
            i += 2
        elif args[i] == '--dest':
            dest = args[i + 1]
            i += 2
        elif args[i] == '--force':
            force = True
            i += 1
        elif args[i] == '--check':
            check = True
            i += 1
        else:
            die(f'unknown argument {args[i]}')
    if not pack_id or not dest:
        die('usage: fetch_pack.py --pack small|medium|all --dest /path [--check] [--force]')
    dest = Path(dest)
    if ready(dest, pack_id) and not force:
        if not check:
            print(f'{dest} already has {pack_id}; skip')
        return
    if check:
        raise SystemExit(1)
    packs = manifest()
    pack = packs.get(pack_id)
    if not pack:
        die(f'pack {pack_id} is not in the manifest')
    cache = dest / '.download'
    for f in pack['files']:
        held = exclusive(cache / (f['name'] + '.lock'))
        zip_path = locate_zip(f['name'], f.get('size') or 0, f.get('sha256') or '', (dest, cache))
        if zip_path:
            print(f'{zip_path} already downloaded; extracting', flush=True)
        else:
            zip_path = cache / f['name']
            print(f'downloading {f["name"]} into {cache}', flush=True)
            download(f['url'], zip_path, f.get('size') or 0, f.get('sha256') or '')
        print(f'extracting {f["name"]} into {dest}', flush=True)
        extract(zip_path, dest)
        zip_path.unlink()
        held.close()
    try:
        cache.rmdir()
    except OSError:
        pass
    if not ready(dest):
        die(f'extract finished but {dest}/library-data/catalog.json is empty')
    print(f'ready: {dest}')


if __name__ == '__main__':
    main()
