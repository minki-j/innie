# test_agi.py  (run from orchestrator/)
from models.schemas import Topic, TopicKeyword, Criterion, GoldStandard
from tasks.agi_search import search_videos_with_agi, _build_search_prompt

topic = Topic(
    id="test-123",
    name="AI code review tools",
    description="YouTube videos reviewing AI-powered code review and coding assistant tools",
    userId="fake-user",
    keywords=[
        TopicKeyword(id="k1", topicId="test-123", keyword="AI code review"),
        TopicKeyword(id="k2", topicId="test-123", keyword="cursor IDE review"),
    ],
    criteria=[
        Criterion(
            id="c1",
            topicId="test-123",
            condition="Video is in English",
            include=True,
            level="MUST_HAVE",
            order=0,
        ),
        Criterion(
            id="c2",
            topicId="test-123",
            condition="Video is a hands-on demo, not just news",
            include=True,
            level="NICE_TO_HAVE",
            order=1,
        ),
    ],
    gold_standards=[
        GoldStandard(
            id="g1",
            topicId="test-123",
            videoUrl="https://www.youtube.com/watch?v=example1",
            title="Great AI Review",
            isPositive=True,
            note="Thorough walkthrough",
        ),
    ],
)

# Inspect the prompt first (no API call)
print(_build_search_prompt(topic, max_results=5))
print("---")

# Actually call AGI (requires AGI_INC_API_KEY in .env)
results = search_videos_with_agi.fn(topic, max_results=5)
print(f"Found {len(results)} videos: {results}")
