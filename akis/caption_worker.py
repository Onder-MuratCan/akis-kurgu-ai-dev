import tempfile
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from akis.ai_service import local_transcribe
from akis.media_service import MediaService

class LocalCaptionWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)
    status = Signal(str)
    def __init__(self, video, model, download, executable=None):
        super().__init__()
        self.video, self.model, self.download, self.executable = video, model, download, executable
    def run(self):
        try:
            if self.executable is None:
                self.status.emit('Yerel model yükleniyor ve konuşma çözümleniyor…')
                self.completed.emit(local_transcribe(self.video, self.model, download=self.download, timed=True))
                return
            # Decode through the whitelisted FFmpeg boundary first; the Whisper decoder
            # (PyAV) would otherwise open the user/project supplied path without limits.
            self.status.emit('Ses parçası hazırlanıyor…')
            with tempfile.TemporaryDirectory(prefix='akis_caption_') as temp:
                audio = Path(temp) / 'audio.wav'
                result = MediaService(self.executable).extract_audio(self.video, audio)
                if result.returncode != 0 or not audio.is_file():
                    raise RuntimeError('Videodan ses parçası çıkarılamadı.')
                self.status.emit('Yerel model yükleniyor ve konuşma çözümleniyor…')
                self.completed.emit(local_transcribe(audio, self.model, download=self.download, timed=True))
        except Exception as exc:
            self.failed.emit(str(exc))
