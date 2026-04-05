"""
YouTube discovery and metadata tasks.

Discovery and metadata use the official YouTube Data API. Transcript fetching
uses youtube-transcript-api first and yt-dlp as a fallback.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from prefect import task
from prefect.states import State

from config import MAX_VIDEOS_PER_CREATOR, MAX_VIDEOS_PER_KEYWORD, YOUTUBE_API_KEY
from models.schemas import VideoData
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

_YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
_YOUTUBE_API_TIMEOUT_SECONDS = 30.0
_YOUTUBE_BATCH_SIZE = 50
_CHANNEL_ID_RE = re.compile(r"^/channel/(?P<channel_id>[^/?#]+)")
_CHANNEL_HANDLE_RE = re.compile(r"^/@(?P<handle>[^/?#]+)")
_ISO8601_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _should_retry_youtube(task, task_run, state: State) -> bool:
    """Retry only on transient YouTube request/download errors."""
    exc = state.result(raise_on_failure=False)
    transient = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    if isinstance(exc, httpx.TimeoutException | httpx.NetworkError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
    try:
        import yt_dlp  # type: ignore

        transient = transient + (yt_dlp.utils.DownloadError,)
    except ImportError:
        pass
    return isinstance(exc, transient)


# ── Shared helpers ────────────────────────────────────────────


def _get_yt_dlp():
    import yt_dlp  # type: ignore

    return yt_dlp


def _parse_yt_dlp_upload_date(date_str: str | None) -> datetime | None:
    """Parse YYYYMMDD date string from yt-dlp into a datetime."""
    if not date_str or len(date_str) < 8:
        return None
    try:
        return datetime.strptime(date_str[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _to_rfc3339(dt: datetime | None) -> str | None:
    """Format a datetime for the YouTube Data API."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _parse_iso8601_duration(value: str | None) -> int:
    if not value:
        return 0
    match = _ISO8601_DURATION_RE.fullmatch(value)
    if not match:
        return 0
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(tag) for tag in value if isinstance(tag, str)]


def _require_youtube_api_key() -> str:
    if not YOUTUBE_API_KEY:
        raise RuntimeError(
            "YOUTUBE_API_KEY (or GOOGLE_API_KEY) with YouTube Data API v3 enabled is required"
        )
    return YOUTUBE_API_KEY


def _youtube_api_get(
    client: httpx.Client,
    resource: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    api_key = _require_youtube_api_key()
    get_rate_limiter("youtube").acquire()
    response = client.get(
        f"{_YOUTUBE_API_BASE_URL}/{resource}",
        params={**params, "key": api_key},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"YouTube Data API returned malformed payload for {resource}")
    return payload


def _video_data_from_api_item(item: dict[str, Any]) -> VideoData | None:
    video_id = item.get("id")
    if not isinstance(video_id, str) or not video_id:
        return None

    snippet = item.get("snippet")
    content_details = item.get("contentDetails")
    statistics = item.get("statistics")
    if not isinstance(snippet, dict):
        snippet = {}
    if not isinstance(content_details, dict):
        content_details = {}
    if not isinstance(statistics, dict):
        statistics = {}

    return VideoData(
        video_id=video_id,
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        channel_title=str(snippet.get("channelTitle") or ""),
        channel_id=str(snippet.get("channelId") or ""),
        published_at=_parse_rfc3339(snippet.get("publishedAt")),
        view_count=_parse_int(statistics.get("viewCount")),
        like_count=_parse_int(statistics.get("likeCount")),
        comment_count=_parse_int(statistics.get("commentCount")),
        duration_seconds=_parse_iso8601_duration(content_details.get("duration")),
        tags=_normalize_tags(snippet.get("tags")),
    )


def _fetch_video_metadata_map_google_api(
    video_ids: list[str],
) -> dict[str, VideoData]:
    unique_video_ids = list(dict.fromkeys(video_id for video_id in video_ids if video_id))
    if not unique_video_ids:
        return {}

    videos: dict[str, VideoData] = {}
    with httpx.Client(timeout=_YOUTUBE_API_TIMEOUT_SECONDS) as client:
        for chunk in _chunked(unique_video_ids, _YOUTUBE_BATCH_SIZE):
            payload = _youtube_api_get(
                client,
                "videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(chunk),
                    "maxResults": len(chunk),
                },
            )
            items = payload.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                video = _video_data_from_api_item(item)
                if video is not None:
                    videos[video.video_id] = video

    missing_video_ids = [video_id for video_id in unique_video_ids if video_id not in videos]
    if missing_video_ids:
        logger.warning(
            "YouTube Data API returned no metadata for %d video(s): %s",
            len(missing_video_ids),
            ", ".join(missing_video_ids[:10]),
        )
    return videos


def _search_videos_by_keyword_google_api(
    keyword: str,
    max_results: int,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> list[str]:
    """
    Search YouTube via the Google YouTube Data API.

    This path supports true server-side filtering by publication timestamp.
    """
    video_ids: list[str] = []
    seen_ids: set[str] = set()
    next_page_token: str | None = None

    with httpx.Client(timeout=_YOUTUBE_API_TIMEOUT_SECONDS) as client:
        while len(video_ids) < max_results:
            params = {
                "part": "snippet",
                "type": "video",
                "q": keyword,
                "maxResults": min(_YOUTUBE_BATCH_SIZE, max_results - len(video_ids)),
                "order": "viewCount",
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            if published_after:
                params["publishedAfter"] = _to_rfc3339(published_after)
            if published_before:
                params["publishedBefore"] = _to_rfc3339(published_before)

            payload = _youtube_api_get(client, "search", params)
            items = payload.get("items") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id") or {}
                if not isinstance(item_id, dict):
                    continue
                video_id = item_id.get("videoId")
                if not video_id or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                video_ids.append(str(video_id))
                if len(video_ids) >= max_results:
                    break

            next_page_token = payload.get("nextPageToken")
            if not next_page_token or not items:
                break

    return video_ids


# ── Keyword search ────────────────────────────────────────────


@task(
    name="search_videos_by_keyword_google_or_yt_dlp",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def search_videos_by_keyword_google_or_yt_dlp(
    keyword: str,
    max_results: int | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
) -> list[str]:
    """
    Search YouTube for videos matching a keyword.
    Returns a list of video IDs.

    Args:
        published_after: Filter videos published on or after this timestamp.
        published_before: Filter videos published on or before this timestamp.

    Discovery now always uses the official YouTube Data API. When a date window
    is provided, filtering happens server-side.
    """
    if max_results is None:
        max_results = MAX_VIDEOS_PER_KEYWORD

    try:
        video_ids = _search_videos_by_keyword_google_api(
            keyword,
            max_results,
            published_after=published_after,
            published_before=published_before,
        )
        logger.info(
            "Keyword '%s': found %d videos via YouTube Data API",
            keyword,
            len(video_ids),
        )
        return video_ids
    except httpx.HTTPStatusError as exc:
        logger.exception(
            "YouTube Data API search failed for keyword: %s",
            keyword,
        )
        raise RuntimeError(
            "Keyword search failed. Ensure YOUTUBE_API_KEY is valid and has "
            "YouTube Data API v3 enabled."
        ) from exc
    except httpx.HTTPError as exc:
        logger.exception(
            "YouTube Data API search failed for keyword: %s",
            keyword,
        )
        raise RuntimeError(
            "Keyword search failed due to a YouTube Data API request error."
        ) from exc


# ── Creator / Channel video fetch ─────────────────────────────


def _extract_channel_id_from_url(channel_url: str) -> str | None:
    parsed = urlparse(channel_url)
    match = _CHANNEL_ID_RE.match(parsed.path)
    if match is None:
        return None
    return match.group("channel_id")


def _extract_channel_handle(channel_url: str) -> str | None:
    parsed = urlparse(channel_url)
    match = _CHANNEL_HANDLE_RE.match(parsed.path)
    if match is None:
        return None
    return match.group("handle")


def _resolve_channel_id_from_url(
    client: httpx.Client,
    channel_url: str,
) -> str | None:
    if channel_url.startswith("@"):
        handle = channel_url[1:]
    else:
        handle = _extract_channel_handle(channel_url)
    if handle:
        payload = _youtube_api_get(
            client,
            "channels",
            {"part": "id", "forHandle": handle},
        )
        items = payload.get("items")
        if isinstance(items, list) and items:
            item = items[0]
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                return item["id"]
        logger.warning("No YouTube channel found for handle '%s'", handle)
        return None

    channel_id = _extract_channel_id_from_url(channel_url)
    if channel_id:
        return channel_id

    logger.warning(
        "Unsupported channel_url format '%s'. Only @handle or /channel/<id> URLs are supported.",
        channel_url,
    )
    return None


def _resolve_channel_id(
    client: httpx.Client,
    channel_id: str | None,
    channel_url: str | None,
) -> str | None:
    if channel_id:
        return channel_id
    if not channel_url:
        return None
    return _resolve_channel_id_from_url(client, channel_url)


def _fetch_uploads_playlist_id(client: httpx.Client, channel_id: str) -> str | None:
    payload = _youtube_api_get(
        client,
        "channels",
        {"part": "contentDetails", "id": channel_id, "maxResults": 1},
    )
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        logger.warning("No channel found for channel_id=%s", channel_id)
        return None
    item = items[0]
    if not isinstance(item, dict):
        return None
    content_details = item.get("contentDetails")
    if not isinstance(content_details, dict):
        return None
    related_playlists = content_details.get("relatedPlaylists")
    if not isinstance(related_playlists, dict):
        return None
    uploads_playlist_id = related_playlists.get("uploads")
    if not isinstance(uploads_playlist_id, str) or not uploads_playlist_id:
        logger.warning("Channel %s has no uploads playlist", channel_id)
        return None
    return uploads_playlist_id


def _fetch_playlist_video_ids(
    client: httpx.Client,
    playlist_id: str,
    max_results: int,
    cutoff: datetime | None = None,
) -> list[str]:
    video_ids: list[str] = []
    next_page_token: str | None = None

    while len(video_ids) < max_results:
        payload = _youtube_api_get(
            client,
            "playlistItems",
            {
                "part": "contentDetails,snippet",
                "playlistId": playlist_id,
                "maxResults": min(_YOUTUBE_BATCH_SIZE, max_results - len(video_ids)),
                **({"pageToken": next_page_token} if next_page_token else {}),
            },
        )
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            content_details = item.get("contentDetails")
            snippet = item.get("snippet")
            if not isinstance(content_details, dict):
                content_details = {}
            if not isinstance(snippet, dict):
                snippet = {}
            published_at = _parse_rfc3339(
                content_details.get("videoPublishedAt") or snippet.get("publishedAt")
            )
            if cutoff and published_at and published_at < cutoff:
                continue
            video_id = content_details.get("videoId")
            if isinstance(video_id, str) and video_id:
                video_ids.append(video_id)
                if len(video_ids) >= max_results:
                    break
        next_page_token = payload.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


@task(
    name="fetch_creator_videos",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_creator_videos(
    channel_id: str | None = None,
    channel_url: str | None = None,
    months_back: int = 1,
    max_results: int | None = None,
) -> list[str]:
    """
    Fetch recent video IDs from a YouTube channel.
    Filters to videos published within `months_back` months.
    """
    if max_results is None:
        max_results = MAX_VIDEOS_PER_CREATOR

    if not channel_id and not channel_url:
        logger.warning("No channel_id or channel_url provided")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)
    with httpx.Client(timeout=_YOUTUBE_API_TIMEOUT_SECONDS) as client:
        resolved_channel_id = _resolve_channel_id(client, channel_id, channel_url)
        if not resolved_channel_id:
            return []
        uploads_playlist_id = _fetch_uploads_playlist_id(client, resolved_channel_id)
        if not uploads_playlist_id:
            return []
        video_ids = _fetch_playlist_video_ids(
            client,
            uploads_playlist_id,
            max_results=max_results,
            cutoff=cutoff,
        )

    logger.info(
        "Channel %s: found %d recent videos via YouTube Data API",
        channel_url or resolved_channel_id,
        len(video_ids),
    )
    return video_ids


# ── Video metadata extraction ─────────────────────────────────


@task(
    name="fetch_video_metadata_batch",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_video_metadata_batch(video_ids: list[str]) -> dict[str, VideoData]:
    """Fetch video metadata in batches using the YouTube Data API."""
    return _fetch_video_metadata_map_google_api(video_ids)


@task(
    name="fetch_video_metadata",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_video_metadata(video_id: str) -> VideoData | None:
    """
    Fetch full video metadata using the YouTube Data API.
    Returns a VideoData model or None on failure.
    """
    video = _fetch_video_metadata_map_google_api([video_id]).get(video_id)
    if video is None:
        logger.warning(
            "Could not fetch metadata for video %s via YouTube Data API", video_id
        )
        return None
    logger.info(
        "Fetched metadata for video %s: '%s' by %s",
        video_id,
        video.title,
        video.channel_title,
    )
    return video


# ── Transcript fetching ──────────────────────────────────────


def _normalize_whitespace(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _is_plausible_transcript(text: str) -> bool:
    """Check if text looks like an actual transcript (not HTML/JS)."""
    text = text.strip()
    if not text or len(text) < 200:
        return False
    suspicious = ["window.ytcfg", "<!doctype html", "<html", "<script"]
    lower = text[:5000].lower()
    if any(m in lower for m in suspicious):
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    spaces = sum(1 for ch in text if ch.isspace())
    ratio = (letters + spaces) / max(1, len(text))
    return ratio > 0.65


def _strip_vtt(vtt: str) -> str:
    """Strip VTT formatting to plain text."""
    if not vtt.lstrip().startswith("WEBVTT"):
        return ""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = unescape(line)
        lines.append(line)
    return _normalize_whitespace(" ".join(lines))


def _select_transcript_yta(video_id: str):
    # We select the best youtube-transcript-api transcript once so both callers can
    # reuse the same language/fallback logic. One caller flattens it to plain text
    # for stored transcripts, while the idea-graph pipeline needs the original
    # timestamped parts to preserve start/end offsets for evidence grounding.
    """Select the best transcript candidate via youtube-transcript-api."""
    get_rate_limiter("youtube").acquire()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        from youtube_transcript_api._errors import (  # type: ignore
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
        )
    except ImportError:
        return None, "yta:import_error"

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        chosen = None
        status = "yta:none"

        for t in transcript_list:
            if getattr(t, "language_code", "").startswith("en") and not getattr(
                t, "is_generated", False
            ):
                chosen, status = t, "yta:en:manual"
                break

        if chosen is None:
            for t in transcript_list:
                if getattr(t, "language_code", "").startswith("en"):
                    chosen, status = t, "yta:en:generated"
                    break

        if chosen is None:
            for t in transcript_list:
                try:
                    chosen = t.translate("en")
                    status = f"yta:{getattr(t, 'language_code', '?')}:translated_en"
                    break
                except Exception:
                    continue

        if chosen is None:
            for t in transcript_list:
                chosen = t
                status = f"yta:{getattr(t, 'language_code', '?')}:fallback"
                break

        if chosen is None:
            return None, status

        return chosen, status
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        return None, f"yta:{type(e).__name__}"
    except Exception as e:
        return None, f"yta:error:{type(e).__name__}"


def _fetch_transcript_yta(video_id: str) -> tuple[str | None, str]:
    """Fetch transcript via youtube-transcript-api."""
    chosen, status = _select_transcript_yta(video_id)
    if chosen is None:
        return None, status

    try:
        parts = chosen.fetch()
        text = " ".join(p.get("text", "") for p in parts if p.get("text"))
        text = _normalize_whitespace(text)

        if text and _is_plausible_transcript(text):
            return text, status
        return None, f"{status}:invalid"
    except Exception as e:
        return None, f"{status}:error:{type(e).__name__}"


def fetch_transcript_segments(video_id: str) -> tuple[list[dict[str, Any]] | None, str]:
    """Fetch transcript segments with timestamps for idea-graph grounding."""
    chosen, status = _select_transcript_yta(video_id)
    if chosen is None:
        return None, status

    try:
        parts = chosen.fetch()
        segments = []
        for part in parts:
            text = _normalize_whitespace(part.get("text", ""))
            if not text:
                continue
            start = float(part.get("start", 0))
            duration = float(part.get("duration", 0))
            segments.append(
                {
                    "text": text,
                    "start_sec": start,
                    "end_sec": start + max(duration, 0),
                }
            )
        if not segments:
            return None, f"{status}:no_segments"
        return segments, status
    except Exception as e:
        return None, f"{status}:error:{type(e).__name__}"


def _fetch_transcript_ytdlp(video_id: str) -> tuple[str | None, str]:
    """Fallback: fetch transcript via yt-dlp subtitle extraction."""
    get_rate_limiter("youtube").acquire()
    yt_dlp = _get_yt_dlp()
    import urllib.request

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return None, f"ytdlp:error:{type(e).__name__}"

    # Try manual subs first, then auto
    for subs_key in ("subtitles", "automatic_captions"):
        subs = info.get(subs_key) or {}
        for lang in ("en", "en-US", "en-GB"):
            fmts = subs.get(lang)
            if not isinstance(fmts, list):
                continue
            for fmt in fmts:
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    try:
                        req = urllib.request.Request(
                            fmt["url"],
                            headers={"User-Agent": "Mozilla/5.0"},
                        )
                        with urllib.request.urlopen(req, timeout=20) as resp:
                            raw = resp.read().decode("utf-8", errors="replace")
                        text = _strip_vtt(raw)
                        if text and _is_plausible_transcript(text):
                            return text, f"ytdlp:{lang}:vtt"
                    except Exception:
                        continue

    return None, "ytdlp:no_subtitles"


@task(
    name="fetch_transcript",
    retries=3,
    retry_delay_seconds=[10, 30, 90],
    retry_jitter_factor=0.2,
    retry_condition_fn=_should_retry_youtube,
)
def fetch_transcript(video_id: str) -> tuple[str | None, str]:
    """
    Fetch the best available transcript for a video.
    Tries youtube-transcript-api first, then falls back to yt-dlp.
    """
    text, status = _fetch_transcript_yta(video_id)
    if text is not None:
        logger.info("Transcript for %s: %s (%d chars)", video_id, status, len(text))
        return text, status

    text, status = _fetch_transcript_ytdlp(video_id)
    if text is not None:
        logger.info("Transcript for %s: %s (%d chars)", video_id, status, len(text))
    else:
        logger.warning("No transcript found for %s: %s", video_id, status)
    return text, status
