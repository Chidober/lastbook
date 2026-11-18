"""Which mounted library the Docker server opens. Paths come only from libraries.json."""
import json
import os
import threading
from pathlib import Path

FILE = Path(os.environ.get('LASTBOOK_LIBRARIES') or '/data/config/libraries.json')


def load():
    try:
        data = json.loads(FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    libs = []
    for item in data.get('libraries') or []:
        if not isinstance(item, dict):
            continue
        lib_id, path = item.get('id'), item.get('path')
        if isinstance(lib_id, str) and isinstance(path, str) and lib_id and path.startswith('/'):
            libs.append({'id': lib_id, 'title': str(item.get('title') or lib_id), 'path': path})
    if not libs:
        return None
    active = data.get('active') if data.get('active') in {x['id'] for x in libs} else libs[0]['id']
    return {'active': active, 'libraries': libs}


def active_path():
    data = load()
    if not data:
        return None
    return next(x['path'] for x in data['libraries'] if x['id'] == data['active'])


def public():
    data = load()
    if not data:
        return {'active': None, 'libraries': []}
    out = []
    for item in data['libraries']:
        catalog = Path(item['path']) / 'library-data' / 'catalog.json'
        ready = False
        try:
            ready = bool(json.loads(catalog.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            ready = False
        out.append({'id': item['id'], 'title': item['title'], 'ready': ready})
    return {'active': data['active'], 'libraries': out}


def use(lib_id):
    data = load()
    if not data:
        return {'error': 'no libraries configured'}
    if lib_id not in {x['id'] for x in data['libraries']}:
        return {'error': 'unknown library'}
    if lib_id == data['active']:
        return {'ok': True, 'id': lib_id, 'restarting': False}
    raw = json.loads(FILE.read_text(encoding='utf-8'))
    raw['active'] = lib_id
    tmp = FILE.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(raw, indent=1), encoding='utf-8')
    os.replace(tmp, FILE)

    def _exit():
        os._exit(0)  # Docker restarts the container; entrypoint reads the new active library

    threading.Timer(0.4, _exit).start()
    return {'ok': True, 'id': lib_id, 'restarting': True}
