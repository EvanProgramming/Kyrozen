"""Attachments: images and videos (feature 3.4, requirement #1).

The desktop client used to read PNG/JPEG/WebP/MP4/MOV as if they were text.
This module turns them into first-class artifacts:

* images  -> thumbnail (ffmpeg), visual analysis (ffprobe dims + average colour),
             and delete
* videos  -> duration (ffprobe), evenly-spaced keyframes (ffmpeg), an optional
             speech transcript (pluggable ASR), and a timestamped summary

Everything is backed by ``<workspace>/.kyrozen/attachments/`` and an index file
so attachments survive reloads and can be injected into a requirements
conversation (acceptance: image content participates in the requirements
dialogue).

ffmpeg/ffprobe are used for all media work so the engine is deterministic and has
no PIL dependency. When the binaries are missing the module degrades gracefully:
metadata that needs them is left empty and ``error`` records what was skipped.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
IMAGE_EXTS: tuple[str, ...] = ("png", "jpeg", "jpg", "webp")
VIDEO_EXTS: tuple[str, ...] = ("mp4", "mov")
OTHER_EXTS: tuple[str, ...] = ("pdf", "txt", "md", "csv", "json", "log")

DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
THUMBNAIL_WIDTH = 240
VIDEO_KEYFRAMES = 4

_MIME: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
}


class AttachmentError(Exception):
    """Raised when an attachment is rejected (size/format/not_found/analysis)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason  # 'size' | 'format' | 'not_found' | 'analysis_failed'


# --------------------------------------------------------------------------
# ffmpeg/ffprobe helpers
# --------------------------------------------------------------------------
_COMMON_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
)


def _find_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in _COMMON_BIN_DIRS:
        candidate = Path(d) / name
        if candidate.exists():
            return str(candidate)
    return None


def _run(cmd: Sequence[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


# --------------------------------------------------------------------------
# Analysis result objects
# --------------------------------------------------------------------------
@dataclass
class Keyframe:
    timestamp: float
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "path": self.path}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "text": self.text}


@dataclass
class ImageAnalysis:
    width: int | None = None
    height: int | None = None
    fmt: str | None = None
    average_color: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "format": self.fmt,
            "average_color": self.average_color,
            "description": self.description,
        }


@dataclass
class VideoAnalysis:
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    keyframes: list[Keyframe] = field(default_factory=list)
    transcript: str | None = None
    transcript_segments: list[TranscriptSegment] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "keyframes": [k.to_dict() for k in self.keyframes],
            "transcript": self.transcript,
            "transcript_segments": [s.to_dict() for s in self.transcript_segments],
            "summary": self.summary,
        }


# --------------------------------------------------------------------------
# Analyzers (pluggable; default implementations use ffmpeg/ffprobe)
# --------------------------------------------------------------------------
class ImageAnalyzer:
    """Default image analyzer using ffprobe + ffmpeg."""

    def __init__(self, thumbnail_width: int = THUMBNAIL_WIDTH) -> None:
        self.thumbnail_width = thumbnail_width

    def analyze(self, path: str | Path, thumbnail_dir: Path) -> ImageAnalysis:
        path = Path(path)
        ffprobe = _find_bin("ffprobe")
        ffmpeg = _find_bin("ffmpeg")
        analysis = ImageAnalysis()
        if ffprobe is None:
            analysis.description = "（未找到 ffprobe，无法分析图像元数据）"
            return analysis
        # Dimensions + format.
        proc = _run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name",
                "-of", "json", str(path),
            ]
        )
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout.decode("utf-8", "replace"))
                stream = (data.get("streams") or [{}])[0]
                analysis.width = _as_int(stream.get("width"))
                analysis.height = _as_int(stream.get("height"))
                analysis.fmt = stream.get("codec_name")
            except Exception:
                pass
        # Average colour via a 1x1 scale.
        if ffmpeg is not None:
            proc = _run(
                [
                    ffmpeg, "-loglevel", "error", "-y", "-i", str(path),
                    "-vf", "scale=1:1", "-frames:v", "1", "-pix_fmt", "rgb24",
                    "-f", "rawvideo", "-",
                ]
            )
            if proc.returncode == 0 and len(proc.stdout) >= 3:
                r, g, b = proc.stdout[0], proc.stdout[1], proc.stdout[2]
                analysis.average_color = f"#{r:02X}{g:02X}{b:02X}"
        analysis.description = self._describe(analysis)
        return analysis

    def _describe(self, a: ImageAnalysis) -> str:
        bits = []
        if a.fmt:
            bits.append(f"{a.fmt} 图像")
        if a.width and a.height:
            bits.append(f"尺寸 {a.width}×{a.height}")
        if a.average_color:
            bits.append(f"主色调 {a.average_color}")
        if not bits:
            return "图像文件（未提取到元数据）"
        return "；".join(bits) + "。"


class AIImageAnalyzer(ImageAnalyzer):
    """Wraps base ImageAnalyzer and enriches description with AI vision analysis.

    Uses the multi-provider system (OmniRoute auto/vision > Gemini > Groq)
    to produce a natural-language description of image content. Falls back
    to the base description if no AI provider is available.
    """

    def __init__(self, chat_fn: Callable | None = None, thumbnail_width: int = THUMBNAIL_WIDTH) -> None:
        super().__init__(thumbnail_width=thumbnail_width)
        self._chat_fn = chat_fn

    def analyze(self, path: str | Path, thumbnail_dir: Path) -> ImageAnalysis:
        analysis = super().analyze(path, thumbnail_dir)
        if self._chat_fn is None:
            return analysis
        try:
            path = Path(path)
            image_bytes = path.read_bytes()
            b64 = base64.b64encode(image_bytes).decode("ascii")
            ext = path.suffix.lstrip(".").lower()
            mime = _MIME.get(ext, "image/png")
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "用一句中文简短描述这张图片的内容（不超过50字），只输出描述本身。"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }]
            response = self._chat_fn(messages, model="auto/vision")
            desc = (response.get("content") or "").strip()
            if desc:
                analysis.description = desc
        except Exception:
            pass  # best-effort: keep base description on failure
        return analysis


class VideoAnalyzer:
    """Default video analyzer using ffprobe (duration/dims) + ffmpeg (keyframes).

    ``asr_fn`` is an optional callable ``(path) -> (text, [TranscriptSegment])``
    used for speech-to-text. When absent, the summary still carries keyframe
    timestamps (acceptance: short videos produce a timestamped summary).
    """

    def __init__(
        self,
        thumbnail_width: int = THUMBNAIL_WIDTH,
        keyframe_count: int = VIDEO_KEYFRAMES,
        asr_fn: Callable[[str | Path], tuple[str | None, list[TranscriptSegment]]] | None = None,
    ) -> None:
        self.thumbnail_width = thumbnail_width
        self.keyframe_count = keyframe_count
        self.asr_fn = asr_fn

    def analyze(self, path: str | Path, thumbnail_dir: Path) -> VideoAnalysis:
        path = Path(path)
        ffprobe = _find_bin("ffprobe")
        ffmpeg = _find_bin("ffmpeg")
        analysis = VideoAnalysis()

        if ffprobe is None:
            analysis.summary = "（未找到 ffprobe，无法分析视频）"
            return analysis

        proc = _run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=width,height",
                "-of", "json", str(path),
            ]
        )
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout.decode("utf-8", "replace"))
                fmt = data.get("format") or {}
                analysis.duration = _as_float(fmt.get("duration"))
                streams = data.get("streams") or []
                for s in streams:
                    analysis.width = _as_int(s.get("width")) or analysis.width
                    analysis.height = _as_int(s.get("height")) or analysis.height
            except Exception:
                pass

        if ffmpeg is not None and analysis.duration:
            analysis.keyframes = self._extract_keyframes(path, ffmpeg, thumbnail_dir, analysis.duration)

        if self.asr_fn is not None:
            try:
                text, segments = self.asr_fn(path)
                analysis.transcript = text
                analysis.transcript_segments = list(segments)
            except Exception:
                analysis.transcript = None

        analysis.summary = self._summarize(analysis)
        return analysis

    def _extract_keyframes(
        self, path: Path, ffmpeg: str, thumbnail_dir: Path, duration: float
    ) -> list[Keyframe]:
        frames: list[Keyframe] = []
        count = max(1, self.keyframe_count)
        interval = duration / (count + 1)
        for i in range(1, count + 1):
            ts = round(interval * i, 2)
            out = thumbnail_dir / f"keyframe_{i}.png"
            proc = _run(
                [
                    ffmpeg, "-loglevel", "error", "-y",
                    "-ss", str(ts), "-i", str(path),
                    "-frames:v", "1",
                    "-vf", f"scale={self.thumbnail_width}:-1",
                    str(out),
                ]
            )
            if proc.returncode == 0 and out.exists():
                frames.append(Keyframe(timestamp=ts, path=str(out)))
        return frames

    def _summarize(self, a: VideoAnalysis) -> str:
        parts: list[str] = []
        if a.duration is not None:
            parts.append(f"视频时长 {a.duration:.1f}s")
        if a.width and a.height:
            parts.append(f"分辨率 {a.width}×{a.height}")
        if a.keyframes:
            stamps = "、".join(f"{k.timestamp:.1f}s" for k in a.keyframes)
            parts.append(f"关键帧 {len(a.keyframes)} 张（{stamps}）")
        if a.transcript:
            segs = "；".join(
                f"[{s.start:.1f}s-{s.end:.1f}s] {s.text}" for s in a.transcript_segments
            ) or a.transcript
            parts.append(f"语音转写：{segs}")
        else:
            parts.append("（未配置语音转写）")
        return "，".join(parts) + "。"


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Attachment record
# --------------------------------------------------------------------------
@dataclass
class Attachment:
    id: str
    kind: str  # 'image' | 'video' | 'other'
    filename: str
    path: str
    size_bytes: int
    mime: str
    created_at: float
    thumbnail_path: str | None = None
    analysis: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "filename": self.filename,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mime": self.mime,
            "created_at": self.created_at,
            "thumbnail_path": self.thumbnail_path,
            "analysis": self.analysis,
            "metadata": self.metadata,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Attachment":
        return cls(
            id=d["id"],
            kind=d["kind"],
            filename=d["filename"],
            path=d["path"],
            size_bytes=d["size_bytes"],
            mime=d["mime"],
            created_at=d["created_at"],
            thumbnail_path=d.get("thumbnail_path"),
            analysis=d.get("analysis"),
            metadata=d.get("metadata", {}) or {},
            error=d.get("error"),
        )


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------
class AttachmentsManager:
    """Stores, analyzes, and deletes attachments for one workspace."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        image_analyzer: ImageAnalyzer | None = None,
        video_analyzer: VideoAnalyzer | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.dir = self.workspace / ".kyrozen" / "attachments"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.workspace / ".kyrozen" / "attachments.json"
        self.max_bytes = max_bytes
        self._image_analyzer = image_analyzer or ImageAnalyzer()
        self._video_analyzer = video_analyzer
        self._all = self._load_index()

    # -- persistence -------------------------------------------------------
    def _load_index(self) -> list[Attachment]:
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            return [Attachment.from_dict(d) for d in raw.get("attachments", [])]
        except Exception:
            return []

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(
                {"attachments": [a.to_dict() for a in self._all]}, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    # -- validation --------------------------------------------------------
    def validate(self, src: str | Path) -> None:
        src = Path(src)
        if not src.exists():
            raise AttachmentError("not_found", f"文件不存在：{src}")
        ext = src.suffix.lstrip(".").lower()
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS and ext not in OTHER_EXTS:
            raise AttachmentError(
                "format", f"不支持的格式：.{ext}（支持 {', '.join(IMAGE_EXTS + VIDEO_EXTS)} 等）"
            )
        size = src.stat().st_size
        if size > self.max_bytes:
            raise AttachmentError(
                "size",
                f"文件过大：{size} 字节（上限 {self.max_bytes} 字节）",
            )

    # -- add / delete ------------------------------------------------------
    def add(
        self,
        src: str | Path,
        *,
        copy: bool = True,
    ) -> Attachment:
        src = Path(src)
        self.validate(src)
        ext = src.suffix.lstrip(".").lower()
        if ext in IMAGE_EXTS:
            kind = "image"
        elif ext in VIDEO_EXTS:
            kind = "video"
        else:
            kind = "other"

        attachment_id = f"att_{uuid.uuid4().hex[:10]}"
        dest_name = f"{attachment_id}_{src.name}"
        dest = self.dir / dest_name
        if copy:
            dest.write_bytes(src.read_bytes())
        else:
            dest = src

        att = Attachment(
            id=attachment_id,
            kind=kind,
            filename=src.name,
            path=str(dest),
            size_bytes=dest.stat().st_size,
            mime=_MIME.get(ext, "application/octet-stream"),
            created_at=time.time(),
            metadata={"ext": ext},
        )

        # Analyze (best-effort; failures are recorded, not fatal).
        try:
            if kind == "image":
                analysis = self._image_analyzer.analyze(dest, self.dir)
                att.analysis = analysis.to_dict()
                att.thumbnail_path = self._make_thumbnail(dest, attachment_id)
            elif kind == "video":
                analyzer = self._video_analyzer or VideoAnalyzer()
                analysis = analyzer.analyze(dest, self.dir)
                att.analysis = analysis.to_dict()
                if analysis.keyframes:
                    att.thumbnail_path = analysis.keyframes[0].path
        except Exception as exc:  # pragma: no cover - defensive
            att.error = f"分析失败：{type(exc).__name__}: {exc}"

        self._all.append(att)
        self._save_index()
        return att

    def _make_thumbnail(self, image_path: Path, attachment_id: str) -> str | None:
        ffmpeg = _find_bin("ffmpeg")
        if ffmpeg is None:
            return None
        out = self.dir / f"thumb_{attachment_id}.png"
        proc = _run(
            [
                ffmpeg, "-loglevel", "error", "-y", "-i", str(image_path),
                "-vf", f"scale={THUMBNAIL_WIDTH}:-1",
                "-frames:v", "1", str(out),
            ]
        )
        if proc.returncode == 0 and out.exists():
            return str(out)
        return None

    def delete(self, attachment_id: str) -> bool:
        att = self.get(attachment_id)
        if att is None:
            return False
        # Remove stored files: original, thumbnail, keyframes.
        for p in (att.path, att.thumbnail_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
        if att.analysis and att.kind == "video":
            for kf in att.analysis.get("keyframes", []):
                try:
                    Path(kf.get("path", "")).unlink(missing_ok=True)
                except Exception:
                    pass
        self._all = [a for a in self._all if a.id != attachment_id]
        self._save_index()
        return True

    # -- queries -----------------------------------------------------------
    def get(self, attachment_id: str) -> Attachment | None:
        return next((a for a in self._all if a.id == attachment_id), None)

    def list(self) -> list[Attachment]:
        return list(self._all)

    def by_kind(self, kind: str) -> list[Attachment]:
        return [a for a in self._all if a.kind == kind]

    def analysis_text(self, attachment_id: str) -> str:
        att = self.get(attachment_id)
        if att is None or not att.analysis:
            return ""
        if att.kind == "image":
            return att.analysis.get("description", "")
        if att.kind == "video":
            return att.analysis.get("summary", "")
        return ""

    def requirements_context(self) -> str:
        """Return analyzed attachment content to inject into a requirements dialogue.

        Acceptance: image/video content participates in the requirements
        conversation rather than being silently dropped.
        """
        parts: list[str] = []
        for att in self._all:
            if not att.analysis:
                continue
            if att.kind == "image":
                text = att.analysis.get("description", "")
                if text:
                    parts.append(f"[图片附件 {att.filename}] {text}")
            elif att.kind == "video":
                text = att.analysis.get("summary", "")
                if text:
                    parts.append(f"[视频附件 {att.filename}] {text}")
        return "\n".join(parts)
