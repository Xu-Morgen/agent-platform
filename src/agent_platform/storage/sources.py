"""可重建源码格式：只保存字节和摘要，不序列化 Python 可执行对象。"""
import base64
from hashlib import sha256
from pathlib import PurePosixPath
from types import MappingProxyType
from uuid import uuid4
import sys
from ..registry.snapshots import ContentSnapshot, _MemoryFinder


def encode_source(content, kind, symbol):
    return {'format': 1, 'kind': kind, 'symbol': symbol, 'digest': content.digest,
            'files': {name: base64.b64encode(value).decode('ascii') for name, value in content.files.items()}}


def decode_source(document):
    if document['format'] != 1:
        raise ValueError('源码快照格式不兼容')
    files = {}
    for name, value in sorted(document['files'].items()):
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('快照路径无效')
        files[name] = base64.b64decode(value, validate=True)
    if document['kind'] in ('block', 'contract'):
        if set(files) != {'block.py'}:
            raise ValueError('单文件资源快照无效')
        digest = sha256(files['block.py']).hexdigest()
    else:
        h = sha256()
        for name, content in files.items():
            encoded = name.encode('utf-8')
            h.update(len(encoded).to_bytes(8, 'big'))
            h.update(encoded)
            h.update(len(content).to_bytes(8, 'big'))
            h.update(content)
        digest = h.hexdigest()
    if digest != document['digest']:
        raise ValueError('源码快照摘要不一致')
    snapshot = ContentSnapshot(digest, f'_agent_restored_{digest}_{uuid4().hex}', MappingProxyType(files))
    sys.meta_path.insert(0, _MemoryFinder(snapshot))
    return snapshot
