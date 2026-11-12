"""Bounded pronunciation playback without a shell or persistent audio files."""

import asyncio
from pathlib import Path
import shutil
import sys
import tempfile

from .translation import TranslationError, pronunciation


async def play(text, source="en", accent=None):
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 200:
        raise TranslationError("speech_too_long")
    process = None
    with tempfile.TemporaryDirectory(prefix="modu-audio-") as directory:
        if accent:
            data = await asyncio.to_thread(pronunciation, text, accent)
            path = Path(directory) / "voice.mp3"
            path.write_bytes(data)
            if sys.platform == "darwin":
                args = ["/usr/bin/afplay", str(path)]
            elif sys.platform == "win32":
                # Path is supplied as JSON on stdin, never interpolated as code.
                args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        "Add-Type -AssemblyName PresentationCore; "
                        "$p=New-Object System.Windows.Media.MediaPlayer; "
                        "$p.Open([Uri]([Console]::In.ReadToEnd() | ConvertFrom-Json)); "
                        "$p.Play(); Start-Sleep -Milliseconds 1000; "
                        "for($i=0;$i -lt 300 -and $p.Position.TotalSeconds -lt "
                        "$p.NaturalDuration.TimeSpan.TotalSeconds;$i++){Start-Sleep -Milliseconds 100}; $p.Close()"]
            elif shutil.which("ffplay"):
                args = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
            elif shutil.which("mpg123"):
                args = ["mpg123", "-q", str(path)]
            else:
                raise TranslationError("speech_unavailable")
        elif sys.platform == "darwin":
            # No voice override: use the system's configured pronunciation voice.
            args = ["/usr/bin/say", "--", text]
        elif sys.platform == "win32":
            args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$s.Speak(([Console]::In.ReadToEnd() | ConvertFrom-Json)); $s.Dispose()"]
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            args = [shutil.which("espeak-ng") or shutil.which("espeak"), "-v", source, "--", text]
        else:
            raise TranslationError("speech_unavailable")
        try:
            import json
            payload = json.dumps(str(path) if accent else text).encode() if sys.platform == "win32" else None
            process = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.PIPE if payload else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.communicate(payload), timeout=40)
            if process.returncode:
                raise TranslationError("speech_failed")
        except (OSError, TimeoutError) as error:
            raise TranslationError("speech_failed") from error
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
