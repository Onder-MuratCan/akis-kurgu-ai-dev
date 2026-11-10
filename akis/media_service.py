"""FFmpeg process boundary, injectable for tests and reusable by media workers."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# Media paths come from file dialogs *and* from project files, which may be shared by
# other people. Restrict FFmpeg to plain local files and to the container formats the
# editor actually supports. This blocks network/pipe protocols and "playlist" demuxers
# (concat, HLS, image sequences, ...) that can silently pull in other files from disk.
# Demuxer names: mov = mp4/mov/m4v/m4a, matroska = mkv/webm.
ALLOWED_PROTOCOLS = 'file'
ALLOWED_DEMUXERS = 'mov,matroska,avi,mp3,wav'


def input_args(path):
    """FFmpeg arguments that open one untrusted media file with the safe whitelists."""
    return ['-protocol_whitelist', ALLOWED_PROTOCOLS, '-format_whitelist', ALLOWED_DEMUXERS,
            '-i', str(path)]


class MediaService:
    def __init__(self, executable, runner=None):
        self.executable = str(executable)
        self.runner = runner or subprocess.run

    def run(self, arguments, *, text=False):
        return self.runner([self.executable, *map(str, arguments)], capture_output=True,
                           text=text, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def duration(self, path):
        result = self.run(['-hide_banner', *input_args(path)], text=True)
        match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', result.stderr)
        if not match:
            raise ValueError('Medya süresi okunamadı.')
        return int(match.group(1))*3600 + int(match.group(2))*60 + float(match.group(3))

    def has_audio(self, path):
        result = self.run(['-hide_banner', *input_args(path)], text=True)
        return bool(re.search(r'Stream #\S+.*Audio:', result.stderr))

    def dimensions(self, path):
        result = self.run(['-hide_banner', *input_args(path)], text=True)
        match = re.search(r'Stream #.*Video:.*?\b(\d{2,5})x(\d{2,5})\b', result.stderr)
        if not match:
            raise ValueError('Video boyutları okunamadı.')
        width, height = int(match.group(1)), int(match.group(2))
        return width - width % 2, height - height % 2

    def extract_frame(self, source, seconds, destination):
        return self.run(['-y', '-ss', str(seconds), *input_args(source), '-frames:v', '1',
                         '-vf', 'scale=640:-2', '-q:v', '3', destination])

    def extract_audio(self, source, destination):
        return self.run(['-y', *input_args(source), '-vn', '-ac', '1', '-ar', '16000',
                         '-b:a', '64k', destination])
