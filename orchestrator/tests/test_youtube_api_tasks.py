from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from flows.video_pipeline import (
    _filter_prefetched_videos_by_engagement,
    process_video_for_funnel,
)
from models.schemas import FunnelWithRelations, VideoData
from tasks.youtube import (
    _fetch_video_metadata_map_google_api,
    _parse_iso8601_duration,
    _resolve_channel_id_from_url,
    _video_data_from_api_item,
    fetch_creator_videos,
)


def _build_video_item(video_id: str) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": f"title-{video_id}",
            "description": f"description-{video_id}",
            "channelTitle": "Channel Name",
            "channelId": "UC123",
            "publishedAt": "2025-01-02T03:04:05Z",
            "tags": ["alpha", "beta"],
        },
        "contentDetails": {
            "duration": "PT1H2M3S",
        },
        "statistics": {
            "viewCount": "123",
            "likeCount": "45",
            "commentCount": "6",
        },
    }


class YouTubeApiTaskTests(unittest.TestCase):
    def test_parse_iso8601_duration(self) -> None:
        self.assertEqual(_parse_iso8601_duration("PT1H2M3S"), 3723)
        self.assertEqual(_parse_iso8601_duration("P1DT5S"), 86405)
        self.assertEqual(_parse_iso8601_duration(None), 0)
        self.assertEqual(_parse_iso8601_duration("not-a-duration"), 0)

    def test_video_data_from_api_item_maps_fields(self) -> None:
        video = _video_data_from_api_item(_build_video_item("video-123"))

        self.assertIsNotNone(video)
        assert video is not None
        self.assertEqual(video.video_id, "video-123")
        self.assertEqual(video.title, "title-video-123")
        self.assertEqual(video.description, "description-video-123")
        self.assertEqual(video.channel_title, "Channel Name")
        self.assertEqual(video.channel_id, "UC123")
        self.assertEqual(video.published_at, datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
        self.assertEqual(video.view_count, 123)
        self.assertEqual(video.like_count, 45)
        self.assertEqual(video.comment_count, 6)
        self.assertEqual(video.duration_seconds, 3723)
        self.assertEqual(video.tags, ["alpha", "beta"])

    @patch("tasks.youtube._youtube_api_get")
    def test_resolve_channel_id_from_handle_url(self, youtube_api_get: MagicMock) -> None:
        youtube_api_get.return_value = {"items": [{"id": "UC_HANDLE"}]}

        channel_id = _resolve_channel_id_from_url(
            MagicMock(),
            "https://www.youtube.com/@creator",
        )

        self.assertEqual(channel_id, "UC_HANDLE")
        youtube_api_get.assert_called_once_with(
            unittest.mock.ANY,
            "channels",
            {"part": "id", "forHandle": "creator"},
        )

    @patch("tasks.youtube.httpx.Client")
    @patch("tasks.youtube._youtube_api_get")
    def test_fetch_video_metadata_map_batches_requests(
        self,
        youtube_api_get: MagicMock,
        httpx_client: MagicMock,
    ) -> None:
        httpx_client.return_value.__enter__.return_value = MagicMock()
        first_page_ids = [f"video-{index}" for index in range(50)]
        second_page_ids = ["video-50"]
        youtube_api_get.side_effect = [
            {"items": [_build_video_item(video_id) for video_id in first_page_ids]},
            {"items": [_build_video_item(video_id) for video_id in second_page_ids]},
        ]

        videos = _fetch_video_metadata_map_google_api(first_page_ids + second_page_ids)

        self.assertEqual(len(videos), 51)
        self.assertEqual(youtube_api_get.call_count, 2)
        self.assertEqual(videos["video-50"].title, "title-video-50")

    @patch("tasks.youtube.httpx.Client")
    def test_fetch_creator_videos_rejects_legacy_channel_urls(
        self,
        httpx_client: MagicMock,
    ) -> None:
        httpx_client.return_value.__enter__.return_value = MagicMock()

        video_ids = fetch_creator_videos.fn(
            channel_url="https://www.youtube.com/user/legacy-name",
            months_back=1,
            max_results=5,
        )

        self.assertEqual(video_ids, [])


class VideoPipelinePrefetchTests(unittest.TestCase):
    @patch("flows.video_pipeline.MIN_VIDEO_LIKE_COUNT", 10)
    @patch("flows.video_pipeline.MIN_VIDEO_VIEW_COUNT", 1000)
    def test_filter_prefetched_videos_by_engagement(self) -> None:
        logger = MagicMock()
        low = VideoData(video_id="low", title="Low", view_count=50, like_count=2)
        high = VideoData(video_id="high", title="High", view_count=5000, like_count=300)

        filtered = _filter_prefetched_videos_by_engagement(
            {"low": low, "high": high},
            logger,
        )

        self.assertEqual(list(filtered.keys()), ["high"])
        logger.info.assert_called_once()

    @patch("flows.video_pipeline.get_run_logger")
    @patch("flows.video_pipeline.link_video_to_funnel")
    @patch("flows.video_pipeline.save_video")
    @patch("flows.video_pipeline.generate_summary")
    @patch("flows.video_pipeline.fetch_transcript")
    @patch("flows.video_pipeline.fetch_video_metadata")
    @patch("flows.video_pipeline.video_exists")
    def test_process_video_for_funnel_uses_prefetched_video_data(
        self,
        video_exists: MagicMock,
        fetch_video_metadata: MagicMock,
        fetch_transcript: MagicMock,
        generate_summary: MagicMock,
        save_video: MagicMock,
        link_video_to_funnel: MagicMock,
        get_run_logger: MagicMock,
    ) -> None:
        video_exists.return_value = False
        fetch_transcript.return_value = ("transcript body", "ok")
        generate_summary.return_value = "summary body"
        get_run_logger.return_value = MagicMock()
        funnel = FunnelWithRelations(
            id="funnel-123",
            name="My Funnel",
            description=None,
            userId="user-123",
            active=True,
            pipelineIntervalHours=6,
            lastPipelineRunAt=None,
            maxVideosPerKeyword=20,
            maxVideosPerCreator=30,
            createdAt=None,
            updatedAt=None,
            keywords=[],
            creators=[],
            class_nodes=[],
        )
        prefetched_video = VideoData(
            video_id="video-123",
            title="Title",
            description="Description",
            channel_title="Channel",
            channel_id="UC123",
            published_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            view_count=10,
            like_count=2,
            comment_count=1,
            duration_seconds=120,
            tags=["alpha"],
        )

        result = process_video_for_funnel(
            video_id="video-123",
            funnel=funnel,
            model_name="gpt-test",
            prefetched_video_data=prefetched_video,
        )

        fetch_video_metadata.assert_not_called()
        save_video.assert_called_once()
        link_video_to_funnel.assert_called_once_with("video-123", "funnel-123")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.summary, "summary body")
        self.assertEqual(result.transcript_status, "ok")


if __name__ == "__main__":
    unittest.main()
