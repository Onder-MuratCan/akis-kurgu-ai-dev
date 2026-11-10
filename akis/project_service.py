"""Versioned project document validation and atomic persistence."""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path

from akis.timeline_model import Timeline

CURRENT_VERSION = 2
MAX_PROJECT_BYTES = 20 * 1024 * 1024

# Expected JSON types for editor state fields (mirrors main.EditState). Unknown keys are
# ignored by the editor; known keys with the wrong type are rejected so a crafted project
# file cannot crash the UI or push unexpected values into the render pipeline.
STATE_TYPES = {
    'source': str, 'duration': float, 'start': float, 'end': float, 'aspect': str,
    'brightness': int, 'contrast': int, 'saturation': int, 'speed': float, 'effect': str,
    'fade': bool, 'export_profile': str, 'noise_reduction': bool, 'loudness_normalization': bool,
    'overlay_text': str, 'ai_title': str, 'ai_caption': str, 'ai_hashtags': str,
}
PUBLISH_KEYS = ('title', 'caption', 'hashtags')


def _check_type(value, expected, name):
    if expected is bool:
        ok = isinstance(value, bool)
    elif expected is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    else:
        ok = isinstance(value, str) and len(value) <= 20_000
    if not ok:
        raise ValueError(f'Invalid project field: {name}')


def validate_document(document):
    state = document.get('state', {})
    if not isinstance(state, dict):
        raise ValueError('Invalid project state')
    for key, expected in STATE_TYPES.items():
        if key in state:
            _check_type(state[key], expected, f'state.{key}')
    publish = document.get('publish', {})
    if not isinstance(publish, dict):
        raise ValueError('Invalid project publish data')
    for key in PUBLISH_KEYS:
        if key in publish:
            _check_type(publish[key], str, f'publish.{key}')
    if 'ai_prompt' in document:
        _check_type(document['ai_prompt'], str, 'ai_prompt')


def migrate(document):
    if not isinstance(document, dict) or document.get('format') != 'akis-kurgu-project':
        raise ValueError('Unsupported project format')
    version = document.get('version', 1)
    if not isinstance(version, int) or version < 1 or version > CURRENT_VERSION:
        raise ValueError('Unsupported project version')
    validate_document(document)
    result = dict(document)
    if version == 1:
        result['timeline'] = result.get('timeline') or Timeline.from_legacy(result.get('state', {})).to_dict()
    result['timeline'] = Timeline.from_dict(result['timeline']).to_dict()
    result['version'] = CURRENT_VERSION
    return result


def load(path):
    if Path(path).stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError('Project file is too large')
    with Path(path).open(encoding='utf-8') as stream:
        return migrate(json.load(stream))


def save(path, document):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = migrate(document)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def make_document(state, timeline, publish, ai_prompt):
    return {
        'format': 'akis-kurgu-project',
        'version': CURRENT_VERSION,
        'saved_at': datetime.now().astimezone().isoformat(),
        'state': dict(state),
        'timeline': timeline.to_dict(),
        'publish': dict(publish),
        'ai_prompt': ai_prompt,
    }


def save_with_snapshot(path, document, snapshot=False):
    target = Path(path)
    save(target, document)
    if snapshot:
        versions = target.parent / f'{target.name}.versions'
        versions.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        save(versions / f'{stamp}.json', document)


def load_with_source(path):
    document = load(path)
    source = document.get('state', {}).get('source', '')
    source_path = Path(source)
    if source and not source_path.is_absolute():
        source_path = (Path(path).parent / source_path).resolve()
        document.setdefault('state', {})['source'] = str(source_path)
    if not source or not source_path.exists():
        raise FileNotFoundError('Projede kullanılan kaynak video bulunamadı.')
    return document, str(source_path)
