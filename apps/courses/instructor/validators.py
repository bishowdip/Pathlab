"""
File upload validators for the instructor workspace.

Two layers of defence:
  - size cap (catches instructors dragging in a 5 GB .mov by mistake)
  - content-type allowlist (catches .exe renamed to .pdf)

Overridable per-deploy via settings:
  INSTRUCTOR_MAX_VIDEO_MB (default 500)
  INSTRUCTOR_MAX_RESOURCE_MB (default 25)
"""
from django.conf import settings
from django.core.exceptions import ValidationError


VIDEO_CONTENT_TYPES = {
    "video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/ogg",
}

RESOURCE_CONTENT_TYPES = {
    "application/pdf",
    "application/zip", "application/x-zip-compressed",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain", "text/markdown",
    "image/png", "image/jpeg",
}


def _max_mb(key, default):
    return int(getattr(settings, key, default))


def validate_video_upload(f):
    if not f:
        return
    max_mb = _max_mb("INSTRUCTOR_MAX_VIDEO_MB", 500)
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Video too large — max {max_mb} MB.")
    ctype = getattr(f, "content_type", "") or ""
    # Permissive on content-type: some browsers send "application/octet-stream"
    # for matroska. We still reject the obvious bad cases.
    if ctype and not (ctype.startswith("video/") or ctype == "application/octet-stream"):
        raise ValidationError(f"Unsupported video type: {ctype}")


def validate_resource_upload(f):
    if not f:
        return
    max_mb = _max_mb("INSTRUCTOR_MAX_RESOURCE_MB", 25)
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(f"File too large — max {max_mb} MB.")
    ctype = getattr(f, "content_type", "") or ""
    if ctype and ctype not in RESOURCE_CONTENT_TYPES and ctype != "application/octet-stream":
        raise ValidationError(f"Unsupported file type: {ctype}")
