# Topic Tree Architecture

## Overview

Innie organizes content into a **tree of topic nodes** rather than a flat list. Each node represents a progressively more specific sub-category of content. Videos are discovered at the root level and then classified down through the tree using a multi-model LLM voting agent (`classify_items_graph`) deployed on LangGraph.

```
Root Topic: "AI Content"
  ├── Child A: "LLM Tutorials"
  │     ├── Grandchild A1: "Beginner LLM Guides"
  │     └── Grandchild A2: "Advanced LLM Research"
  └── Child B: "AI Tools & Products"
        └── Grandchild B1: "Open Source AI Tools"
```

---

## 1. Data Model

### Topic Tree (Prisma Schema)

```
┌─────────────────────────────────────────────────────────────────┐
│  Topic                                                           │
│  ─────────────────────────────────────────────────────────────  │
│  id                    String  (cuid)                            │
│  name                  String                                    │
│  description           String?   ← used as LLM classification   │
│                                    prompt for this node          │
│  parentId              String?   ← null = root node             │
│  active                Boolean                                   │
│  pipelineIntervalHours Int                                       │
│  lastPipelineRunAt     DateTime?                                 │
│                                                                  │
│  parent         Topic?           (self-referential)              │
│  children       Topic[]          (self-referential)              │
│  criteria       Criterion[]      (own LLM-evaluated criteria)    │
│  criterionFilters CriterionFilter[] (routing rules)             │
│  goldStandards  GoldStandard[]   (few-shot examples per node)   │
│  keywords       TopicKeyword[]   (root only: discovery)         │
│  creators       TopicCreator[]   (root only: discovery)         │
│  videos         Video[]          (many-to-many)                  │
└─────────────────────────────────────────────────────────────────┘
```

The tree is stored as a **flat list with a `parentId` foreign key** — the same pattern used in `self_evolving_taxonomy_agent`. This makes BFS/DFS traversal straightforward in SQL.

### CriterionFilter

A child node can optionally declare explicit filter rules using criteria evaluated on the parent:

```
┌──────────────────────────────────────────────────────┐
│  CriterionFilter                                     │
│  ──────────────────────────────────────────────────  │
│  topicId        String   ← the child topic           │
│  criterionId    String   ← any ancestor's criterion  │
│  requiredResult PASS | FAIL | CANNOT_TELL            │
│                                                      │
│  @@unique([topicId, criterionId])                    │
└──────────────────────────────────────────────────────┘
```

**Example:** Child node "Enterprise AI" has the filter `{criterion: "discusses enterprise use cases", requiredResult: PASS}`. Only videos that received `PASS` for that criterion (evaluated on the parent) enter this child.

### Entity Relationship

```mermaid
erDiagram
    Topic {
        string id PK
        string parentId FK
        string name
        string description
        bool active
        int pipelineIntervalHours
    }
    Topic ||--o{ Topic : "children"
    Topic ||--o{ Criterion : "owns"
    Topic ||--o{ CriterionFilter : "has"
    Topic ||--o{ GoldStandard : "has"
    Topic ||--o{ TopicKeyword : "has"
    Topic ||--o{ TopicCreator : "has"
    Topic }o--o{ Video : "_TopicToVideo"
    Criterion ||--o{ CriterionResult : "produces"
    Criterion ||--o{ CriterionFilter : "referenced by"
    Video ||--o{ CriterionResult : "has"
    CriterionFilter {
        string topicId FK
        string criterionId FK
        enum requiredResult
    }
    Criterion {
        string topicId FK
        string condition
        bool include
        string level
    }
    GoldStandard {
        string topicId FK
        string videoUrl
        bool isPositive
    }
```

---

## 2. System Architecture

```mermaid
flowchart TB
    subgraph app [Next.js Application]
        UI["Topics Canvas\n(React Flow)"]
        Panel["Detail Panel\n(TopicPanels)"]
        API["REST API\n/api/topics/*"]
        DB[(PostgreSQL\nvia Prisma)]
    end

    subgraph orch [Orchestrator — Prefect]
        Flow["video_pipeline\n(Prefect Flow)"]
        DBTasks["tasks/db.py\n(raw psycopg2)"]
        EvalTask["evaluate_criterion\n(LangChain)"]
        YTTasks["tasks/youtube.py\n(yt-dlp)"]
    end

    subgraph agents [LangGraph Agent]
        Graph["classify_items\ngraph"]
        SubGraph["classify_an_item\nsubgraph"]
        LLMs["Multi-model LLM\nvoting (N parallel)"]
    end

    User --> UI
    UI --> Panel
    UI --> API
    API --> DB
    Panel --> API

    API -->|"POST /trigger/{topicId}"| Flow
    Flow --> DBTasks
    DBTasks --> DB
    Flow --> YTTasks
    Flow --> EvalTask
    Flow -->|"langgraph-sdk\nPOST /runs"| Graph
    Graph --> SubGraph
    SubGraph --> LLMs
    Graph -->|"classified_as\n[(topicId, confidence)]"| Flow
    Flow --> DBTasks
```

---

## 3. React Flow Canvas UI

The topics list page (`/settings/topics`) is a **React Flow canvas** with a right-side detail panel.

```mermaid
flowchart LR
    subgraph canvas [TopicFlowCanvas]
        direction TB
        RootNode["Root Node\n[ROOT badge]\nvideos · criteria"]
        ChildA["Child A\n2 filters · 3 criteria"]
        ChildB["Child B\n1 filter"]
        GrandA1["Grandchild A1"]
        AddRoot["+ New Root Topic\n(floating button)"]
        AddChild["+ (child button\non each node)"]

        RootNode --> ChildA
        RootNode --> ChildB
        ChildA --> GrandA1
    end

    subgraph panel [TopicDetailPanel]
        direction TB
        Overview["Overview\nname + description editor"]
        Classification["Classification tab\n(child nodes only)\nCriterionFilters editor"]
        Criteria["Criteria tab\nown LLM criteria"]
        GoldStd["Gold Standards\nfew-shot examples"]
        Keywords["Keywords tab\n(root only)"]
        Creators["Creators tab\n(root only)"]
        Videos["Videos tab\nwith criteria scores"]
        Pipeline["Pipeline tab\n(root only)\ntrigger + schedule"]
    end

    RootNode -->|click| panel
    ChildA -->|click| panel
```

### Node Card

Each node in the canvas displays:
- Node name
- `ROOT` or child badge
- Active/Paused status
- Video count
- Criteria count
- Filter count (child nodes)

Clicking **+** on any node creates a new child topic via `POST /api/topics` with `parentId`.

---

## 4. Pipeline Flow

### Triggering

```mermaid
flowchart TD
    Trigger["Trigger\ntopic_id = X\nor None"]
    IsRoot{parentId = null?}
    WalkUp["get_root_topic_id(X)\nwalk ancestor chain"]
    GetActive["get_active_topics()\nroot topics only\n(parentId IS NULL)"]
    ProcessTree["_process_topic_tree(root)"]

    Trigger --> IsRoot
    IsRoot -- "yes, X is root" --> ProcessTree
    IsRoot -- "no, X is child" --> WalkUp --> ProcessTree
    Trigger -- "None (scheduled)" --> GetActive --> ProcessTree
```

Triggering from any node (root or child) always processes from the **root downward**. Child-triggered runs skip updating `lastPipelineRunAt` on the root so the scheduler is not affected.

### Full Pipeline Execution

```mermaid
flowchart TD
    Start["_process_topic_tree(root)"]
    Skip{keywords + creators\n+ description empty?}
    Discover["discover_videos(root)\nkeyword search + yt-dlp creator scrape"]
    Filter["new_ids = discovered - existing_root_videos"]
    ProcessVid["process_video_for_topic(video_id, root)"]
    Save["1. fetch metadata / transcript / summary\n2. save_video to DB\n3. link_video_to_topic → root node\n4. evaluate_criterion for each root criterion"]
    LoadSubtree["get_topic_subtree(root)\n→ BFS flat list of all nodes"]
    HasChildren{child nodes\nexist?}
    GetAllVids["get_videos_for_topic(root)\nall root videos"]
    LangGraph["_classify_videos_via_langgraph()\nlanggraph-sdk API call"]
    SaveLinks["link_video_to_topic\nfor each (video, child_node) result"]
    EvalChildren["For each child node:\nevaluate_criterion on its linked videos\n(child's own criteria)"]
    UpdateRun["update_topic_last_run(root)"]
    Done["Done"]

    Start --> Skip
    Skip -- "yes → skip" --> Done
    Skip -- "no" --> Discover
    Discover --> Filter --> ProcessVid
    ProcessVid --> Save --> LoadSubtree
    LoadSubtree --> HasChildren
    HasChildren -- "no children" --> UpdateRun --> Done
    HasChildren -- "yes" --> GetAllVids --> LangGraph
    LangGraph --> SaveLinks --> EvalChildren --> UpdateRun --> Done
```

### process_video_for_topic Detail

```mermaid
flowchart LR
    V["video_id"]
    Exists{exists in DB?}
    FetchMeta["fetch_video_metadata\n(YouTube API)"]
    FetchTx["fetch_transcript\n(youtube-transcript-api)"]
    Summary["generate_summary\n(LLM: 3-5 sentences)"]
    SaveDB["save_video\nupsert Channel + Video"]
    Link["link_video_to_topic\n_TopicToVideo junction"]
    EvalCrit["evaluate_criterion × N\nfor each root criterion"]

    V --> Exists
    Exists -- "no" --> FetchMeta --> FetchTx --> Summary --> SaveDB
    Exists -- "yes (skip fetch)" --> Link
    SaveDB --> Link --> EvalCrit
```

---

## 5. classify_items LangGraph Agent

The agent lives in `agents/` and is deployed separately on LangGraph. The orchestrator calls it via `langgraph-sdk` after videos are discovered and saved.

### Input / Output Contract

```
Input (ClassifyItemsOverallState):
  taxonomy:           { id, name, aspect: root_topic.description }
  root_node_id:       root_topic.id
  nodes:              [ ClassNodeState × all topic nodes in subtree ]
  items:              [ ItemState × all videos in root topic ]
  models:             [ "gpt-4o", ... ]         # from CLASSIFY_MODELS env
  total_invocations:  3                          # from CLASSIFY_TOTAL_INVOCATIONS
  majority_threshold: 0.5                        # from CLASSIFY_MAJORITY_THRESHOLD
  is_for_single_batch: true

Output (items[].classified_as):
  [ { node_id: "child_topic_id", confidence_score: 0.83 }, ... ]
```

**ClassNodeState mapping:**

| Prisma `Topic` field | `ClassNodeState` field |
|---|---|
| `id` | `id` |
| `parentId` (or `""`) | `parent_node_id` |
| `name` | `label` |
| `description` | `description` |
| `goldStandards` video IDs | `items[].item_id` (few-shot examples) |

**ItemState mapping:**

| `VideoData` | `ItemState` |
|---|---|
| `video_id` | `id` |
| `"Title: {title}\nChannel: {channel}\nSummary: {summary}"` | `content` |

### Graph Structure

```mermaid
flowchart TD
    START --> spawn_next_batch

    subgraph outer [classify_items_graph]
        spawn_next_batch -->|"fan out: one Send per item"| classify_an_item_graph
        classify_an_item_graph -->|"item classified"| receive_classification_results
        receive_classification_results --> handle_classification_results
        handle_classification_results -->|"needs deeper classification"| classify_an_item_graph
        handle_classification_results -->|"all items fully classified"| interrupt_or_terminate
        interrupt_or_terminate -->|"is_for_single_batch = True"| END
        interrupt_or_terminate -->|"is_for_single_batch = False"| spawn_next_batch
    end

    subgraph inner [classify_an_item_graph subgraph]
        spawn_classifications -->|"fan out: one per model × invocation"| classify
        classify -->|"all complete: majority vote"| aggregate_item_classification
    end

    classify_an_item_graph --- inner
```

### Multi-Model Voting (classify_an_item subgraph)

For each video at each tree level, the subgraph runs **N parallel LLM calls** across configured models:

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant G as classify_items_graph
    participant S as spawn_classifications
    participant L1 as LLM call 1 (gpt-4o)
    participant L2 as LLM call 2 (gpt-4o)
    participant L3 as LLM call 3 (claude-sonnet)
    participant A as aggregate_item_classification

    O->>G: items=[v1,v2,...], nodes=[root, childA, childB, ...]
    G->>S: current_item=v1, parent_node_id=root_id
    S-->>L1: classify v1 at root level
    S-->>L2: classify v1 at root level
    S-->>L3: classify v1 at root level
    L1-->>A: node_ids=["childA"], rationale="..."
    L2-->>A: node_ids=["childA"], rationale="..."
    L3-->>A: node_ids=["childB"], rationale="..."
    Note over A: majority vote: childA = 2/3 = 0.67 confidence
    A-->>G: classified_as=[{node_id: childA, confidence: 0.67}]
    Note over G: childA has children → re-queue v1 at childA level
    G->>S: current_item=v1, parent_node_id=childA
    S-->>L1: classify v1 at childA level
    S-->>L2: classify v1 at childA level
    S-->>L3: classify v1 at childA level
    L1-->>A: node_ids=["grandchildA1"]
    L2-->>A: node_ids=["grandchildA1"]
    L3-->>A: node_ids=["grandchildA1"]
    A-->>G: classified_as=[{node_id: grandchildA1, confidence: 1.0}]
    Note over G: grandchildA1 has no children → stop
    G-->>O: items[v1].classified_as = [{childA, 0.67}, {grandchildA1, 1.0}]
```

The orchestrator then calls `link_video_to_topic(v1, childA)` and `link_video_to_topic(v1, grandchildA1)`.

### Recursive Depth Handling

The recursion is driven by the `handle_classification_results` node. After each round of classification, it checks `cases_need_further_classification` — a list of `{parent_node_id: item}` pairs where the classified node has its own children. These are re-dispatched via `Send` for the next level of classification. This continues until all videos reach leaf nodes or fail to match any child.

```
Round 1:  all items → classify at root level
Round 2:  items that landed on non-leaf nodes → classify at their level
Round 3:  items that landed on non-leaf nodes at level 2 → classify further
...until no cases_need_further_classification remain
```

---

## 6. CriterionFilters Editor (UI)

Child nodes can optionally have explicit routing rules that supplement LLM classification. The **Classification tab** in the detail panel (visible on child nodes only) lets users add `CriterionFilter` records:

```mermaid
flowchart LR
    subgraph AncestorCriteria["Available Ancestor Criteria\n(from GET /ancestor-criteria)"]
        CA["Criterion A: 'discusses enterprise use'\n(from Parent)"]
        CB["Criterion B: 'mentions GPT-4'\n(from Grandparent)"]
    end

    subgraph CurrentFilters["Current Filters on this Node"]
        F1["A = PASS ✕"]
        F2["B = FAIL ✕"]
    end

    CA -->|"select + PASS"| F1
    CB -->|"select + FAIL"| F2
```

The filters are stored in `CriterionFilter` and are currently used for UI documentation of intended routing logic. The actual runtime routing is performed by the LangGraph agent using the node descriptions.

---

## 7. Criteria Evaluation

Each topic node has its **own `Criterion[]`** evaluated independently by the existing `evaluate_criterion` task (LangChain, single LLM call). These are used for **scoring and display** in the Videos tab — they do not control routing.

```mermaid
flowchart LR
    Video["Video"]
    C1["Criterion: 'discusses fine-tuning'\n(MUST_HAVE, Include)"]
    C2["Criterion: 'is paywalled'\n(MUST_HAVE, Exclude)"]
    C3["Criterion: 'mentions benchmarks'\n(NICE_TO_HAVE, Include)"]

    Video --> C1 --> R1["PASS"]
    Video --> C2 --> R2["FAIL"]
    Video --> C3 --> R3["PASS"]

    R1 --> Score
    R2 --> Score["Score = 2/2 MUST_HAVE passed\n= 100%"]
```

`NICE_TO_HAVE` criteria are evaluated but excluded from the score. `include=false` criteria invert the pass condition (a video passes if the criterion result is `FAIL`).

---

## 8. Gold Standards (Few-Shot Examples)

Each topic node can have `GoldStandard` records — YouTube URLs marked as positive or negative examples. These serve a dual purpose:

1. **Criterion evaluation:** Prepended as few-shot human/AI message pairs in the `evaluate_criterion` prompt (positive → expected `PASS`, negative → expected `FAIL`).
2. **LangGraph classification:** Gold standard video IDs are attached to each `ClassNodeState.items` as `used_as_few_shot_example: true`. The `format_single_node` formatter includes their content (title + summary) in the LLM prompt under "Exemplary Items".

Gold standards are **per-node**, meaning each child node can have its own examples that define what content belongs there.

---

## 9. Environment Variables

| Variable | Where Used | Description |
|---|---|---|
| `LANGGRAPH_API_URL` | `orchestrator/config.py` | LangGraph server URL (default `http://localhost:2024`) |
| `LANGGRAPH_API_KEY` | `orchestrator/config.py` | LangGraph Cloud API key (optional for local) |
| `CLASSIFY_MODELS` | `orchestrator/config.py` | Comma-separated model names, e.g. `gpt-4o,claude-3-5-sonnet-latest` |
| `CLASSIFY_TOTAL_INVOCATIONS` | `orchestrator/config.py` | Total LLM calls per item per level (default `3`) |
| `CLASSIFY_MAJORITY_THRESHOLD` | `orchestrator/config.py` | Fraction of votes needed to include a node (default `0.5`) |
| `DEFAULT_LLM_MODEL` | `orchestrator/config.py` | Model for `evaluate_criterion` and `generate_summary` |
| `POSTGRES_URL` | both `orchestrator` and `agents` | Neon PostgreSQL connection string |

---

## 10. Running Locally

### LangGraph Agent (development)

```bash
cd agents
uv run langgraph dev
# Serves at http://localhost:2024
# Studio UI at https://smith.langchain.com/studio
```

### Orchestrator

```bash
cd orchestrator
uv run uvicorn server:app --port 8200
# Trigger manually: POST /trigger/{topicId}
```

Or via Prefect:

```bash
cd orchestrator
uv run python flows/video_pipeline.py
```

### Application

```bash
cd application
npm run dev
# http://localhost:3000
# Topics canvas: /settings/topics
```

---

## 11. File Map

```
innie/
├── agents/                          # LangGraph agent (deployed separately)
│   ├── langgraph.json               # deployment config → classify_items graph
│   ├── pyproject.toml               # langgraph, langchain-openai, langchain-anthropic
│   ├── state.py                     # ClassifyItemsOverallState, ClassNodeState, ItemState
│   ├── llm_factory.py               # LLMFactory: parallel async multi-model calls
│   ├── utils.py                     # node/item formatting, majority vote logic
│   ├── common.py                    # MemorySaver checkpointer, retry policy
│   └── classify_items/
│       ├── classify_items_graph.py  # outer graph: batch dispatch + result handling
│       └── subgraphs/
│           └── classify_an_item.py  # inner subgraph: N parallel LLM calls + voting
│
├── orchestrator/                    # Prefect pipeline
│   ├── config.py                    # env vars incl. LANGGRAPH_API_URL
│   ├── server.py                    # FastAPI trigger server
│   ├── flows/
│   │   └── video_pipeline.py        # main pipeline: discover → eval → classify
│   ├── tasks/
│   │   ├── db.py                    # psycopg2 SQL: get_topic_subtree, link_video_to_topic, ...
│   │   ├── evaluate.py              # LangChain: evaluate_criterion, generate_summary
│   │   └── youtube.py               # yt-dlp: search, fetch metadata, transcript
│   └── models/
│       ├── _generated.py            # auto-generated from schema.prisma
│       └── schemas.py               # enriched Topic (with children, criterion_filters)
│
└── application/                     # Next.js app
    ├── prisma/schema.prisma         # Topic tree: parentId, CriterionFilter model
    ├── app/api/topics/
    │   ├── route.ts                 # GET (flat list + parentId), POST (accepts parentId)
    │   └── [topicId]/
    │       ├── route.ts             # includes children, criterionFilters
    │       ├── criterion-filters/
    │       │   ├── route.ts         # GET + POST criterion filters
    │       │   └── [filterId]/route.ts  # DELETE
    │       └── ancestor-criteria/
    │           └── route.ts         # GET all ancestor criteria (for filter editor)
    └── components/topic/
        ├── TopicFlowCanvas.tsx      # React Flow + dagre auto-layout
        ├── TopicNode.tsx            # custom React Flow node card (not yet extracted)
        ├── TopicDetailPanel.tsx     # right-side panel (fetches topic on click)
        ├── TopicPanels.tsx          # tab bar: Classification/Criteria/Videos/Pipeline/...
        └── CriterionFiltersEditor.tsx  # ancestor criteria selector + filter CRUD
```
