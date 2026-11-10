"""Untrusted project files and media paths must not reach FFmpeg unchecked."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from akis import project_service
from akis.media_service import ALLOWED_DEMUXERS, MediaService, input_args
from akis.timeline_model import Clip, Timeline, Track
from akis.timeline_render import TimelineRenderer


def _timeline(**clip):
    data = {'source': 'a.mp4', 'start': 0, 'length': 30}
    data.update(clip)
    return {'fps_num': 30, 'fps_den': 1, 'tracks': [{'kind': 'video', 'name': 'V', 'clips': [data]}]}


class TimelineValidationTests(unittest.TestCase):
    def test_valid_roundtrip_and_integral_floats(self):
        timeline = Timeline.from_dict(_timeline(start=10.0, volume=1))
        clip = timeline.tracks[0].clips[0]
        self.assertEqual((clip.start, clip.volume), (10, 1.0))
        self.assertIsInstance(clip.start, int)
        original = Timeline(tracks=[Track('video', 'V', [Clip('a.mp4', 0, 10)])])
        self.assertEqual(Timeline.from_dict(original.to_dict()).to_dict(), original.to_dict())

    def test_rejects_filter_graph_injection_in_frame_rate(self):
        for fps in ('30:d=1,movie=secret.mp4', True, 0, 10 ** 9, 1.5):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                Timeline.from_dict({'fps_num': fps, 'tracks': []})
        with self.assertRaises(ValueError):
            Timeline.from_dict({'fps_num': 1, 'fps_den': 1000, 'tracks': []})

    def test_rejects_bad_clip_values(self):
        bad = [{'start': '0'}, {'start': True}, {'length': 0}, {'start': -1},
               {'volume': float('nan')}, {'volume': '1'}, {'volume': 2},
               {'source': 5}, {'source': 'a\0b'}, {'text': 'x' * 6000},
               {'unexpected': 1}, {'id': ''}, {'keyframes': {'opacity': [{'frame': 'x'}]}}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                Timeline.from_dict(_timeline(**change))

    def test_rejects_bad_structure(self):
        for data in ([], {'tracks': {}}, {'tracks': [{'kind': 'shell', 'name': 'x'}]},
                     {'tracks': [{'kind': 'video', 'name': 'x', 'muted': 'no'}]},
                     {'tracks': [{'kind': 'video', 'name': 'x'}] * 65},
                     {'markers': [{'frame': '1', 'label': 'a'}]}, {'markers': ['x']}):
            with self.subTest(data=str(data)[:60]), self.assertRaises(ValueError):
                Timeline.from_dict(data)

    def test_markers_are_normalised(self):
        timeline = Timeline.from_dict({'markers': [{'frame': 3, 'label': 'AI', 'extra': 'dropped'}]})
        self.assertEqual(timeline.markers, [{'frame': 3, 'label': 'AI'}])


class ProjectValidationTests(unittest.TestCase):
    def _document(self, **fields):
        document = project_service.make_document({'source': 'video.mp4'}, Timeline(), {}, '')
        document.update(fields)
        return document

    def test_rejects_wrong_state_and_publish_types(self):
        for fields in ({'state': {'brightness': '10'}}, {'state': {'speed': float('inf')}},
                       {'state': {'fade': 1}}, {'state': []}, {'publish': {'title': 3}},
                       {'ai_prompt': ['x']}, {'timeline': {'fps_num': 'x'}}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                project_service.migrate(self._document(**fields))

    def test_rejects_non_object_document(self):
        with self.assertRaises(ValueError):
            project_service.migrate(['akis-kurgu-project'])

    def test_rejects_oversized_project_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'big.akis.json'
            with path.open('wb') as stream:
                stream.truncate(project_service.MAX_PROJECT_BYTES + 1)
            with self.assertRaises(ValueError):
                project_service.load(path)


class FfmpegBoundaryTests(unittest.TestCase):
    def test_every_media_input_uses_whitelists(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', 'Duration: 00:00:01.00,'))
        service = MediaService('ffmpeg', runner)
        service.duration('clip.mp4')
        service.extract_frame('clip.mp4', 0.5, 'out.jpg')
        service.extract_audio('clip.mp4', 'out.wav')
        for call in runner.call_args_list:
            args = call.args[0]
            index = args.index('-i')
            self.assertEqual(args[index - 4:index + 2], input_args('clip.mp4'))

    def test_renderer_whitelists_clip_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'a.mp4'
            source.touch()
            media = Mock()
            media.has_audio.return_value = False
            media.run.return_value = subprocess.CompletedProcess([], 1, '', 'stop')
            timeline = Timeline(tracks=[Track('video', 'V', [Clip(str(source), 0, 10)])])
            with self.assertRaises(RuntimeError):
                TimelineRenderer(media, (160, 90)).export(timeline, Path(tmp) / 'out.mp4')
            args = media.run.call_args.args[0]
            index = args.index(str(source))
            self.assertEqual(args[index - 5:index + 1], input_args(source))

    def test_real_ffmpeg_blocks_playlist_inputs(self):
        ffmpeg = os.environ.get('AKIS_FFMPEG') or shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('FFmpeg not available')
        media = MediaService(ffmpeg)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / 'real.mp4'
            made = media.run(['-y', '-f', 'lavfi', '-i', 'testsrc=d=1:s=64x64:r=10',
                              '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video])
            self.assertEqual(made.returncode, 0)
            self.assertAlmostEqual(media.duration(video), 1.0, delta=0.2)
            # A concat playlist that references another local file. Without the
            # whitelist FFmpeg happily opens it and reads real.mp4 through it.
            playlist = root / 'evil.ffconcat'
            playlist.write_text("ffconcat version 1.0\nfile 'real.mp4'\n", encoding='utf-8')
            unsafe = media.run(['-hide_banner', '-i', playlist], text=True)
            self.assertIn('concat', unsafe.stderr)
            with self.assertRaises(ValueError):
                media.duration(playlist)
            with self.assertRaises(ValueError):
                media.duration('http://127.0.0.1:9/video.mp4')
        self.assertNotIn('concat', ALLOWED_DEMUXERS.split(','))


class LocalCaptionBoundaryTests(unittest.TestCase):
    def test_local_whisper_decodes_ffmpeg_output_not_source(self):
        from unittest.mock import patch
        from akis import caption_worker
        seen = {}

        def extract(self, source, destination):
            seen['source'] = source
            Path(destination).write_bytes(b'RIFF')
            return subprocess.CompletedProcess([], 0)

        def transcribe(path, model, **kwargs):
            seen['decoded'] = Path(path)
            return [{'start': 0, 'end': 1, 'text': 'merhaba'}]

        worker = caption_worker.LocalCaptionWorker('project/video.mp4', 'tiny', False, 'ffmpeg')
        results = []
        worker.completed.connect(results.append)
        with patch.object(MediaService, 'extract_audio', extract), \
                patch.object(caption_worker, 'local_transcribe', transcribe):
            worker.run()
        self.assertEqual(seen['source'], 'project/video.mp4')
        self.assertEqual(seen['decoded'].suffix, '.wav')
        self.assertEqual(results, [[{'start': 0, 'end': 1, 'text': 'merhaba'}]])


if __name__ == '__main__':
    unittest.main()
