# Innie — training a personal AI that watches YouTube the way you would

| | |
|---|---|
| **Date** | May 2026 |
| **Github** | _(add link)_ |
| **Try it now!** | _(add link)_ |

## Problem statement

Every content recommendation system I use is optimizing for something that isn't me.

YouTube, TikTok, the feeds — they're all extraordinary pieces of engineering, but their objective function is engagement: watch time, sessions, clicks. That objective is correlated with what I want, but it is not the same thing. The gap between "what keeps me watching" and "what I'm actually glad I watched" is exactly where clickbait, doomscrolling, and the slow drift of my feed toward the lowest-common-denominator live.

There are three things I can't do with those systems, and all three bother me:

1. **I can't teach it.** I can thumbs-down a video, but I can't *say* "I want talks from this conference, but only the technical ones, and never the keynote fluff." My intent has to be squeezed through a like button.
2. **I can't see why.** The ranking is a black box. I have no idea why a video showed up, so I can't trust it and I can't correct it.
3. **I can't own it.** The model that decides what I see belongs to the platform and is tuned for the platform's goals, not mine.

So I asked a different question: **what if the recommender were an LLM-based agent that I explicitly train, that shows its reasoning, and that I actually own?** Not a black box optimizing for retention, but something closer to a little version of *me* — one that reads everything coming in, judges it the way I would, and pushes the good stuff to the top.

That framing is where the name comes from. In *Severance*, your "innie" is the version of you that exists at work and does the labor you don't want to spend your life doing. **Innie is that, for your media diet** — an AI that internalizes your taste and does the watching, sorting, and judging on your behalf, so your "outie" only sees what's worth its time.

This write-up is about the challenges I ran into trying to build that, and the lessons that came out of each one.

### What I built

Innie is a personalized YouTube curator. The user flow is three steps:

1. **Create a funnel.** A funnel is a topic you care about. You give it discovery sources (YouTube keywords and creator channels) and a description of what belongs in it.
2. **Review to teach your innie.** As videos flow in, you rate them (Not for me / It was okay / Enjoyed this!) and optionally leave written feedback. Every review is training data.
3. **Your innie scores your feed.** A personal model, trained on your reviews, learns what you actually want and helps the good content rise to the top.

Under the hood it's a monorepo of four services, and honestly each one became its own little research project:

- **`application`** — a Next.js app: the feed, the watch page, the funnel editor (a React Flow canvas), the review panel, and a per-video "idea graph."
- **`agents`** — LangGraph agents: a multi-model **classification swarm** that routes videos through a topic tree, and an idea-graph builder.
- **`orchestrator`** — a Prefect pipeline that discovers videos, fetches transcripts, summarizes, classifies, and evaluates them against your criteria.
- **`lab`** — the training stack: SFT and RLVR fine-tuning (on Tinker) that turns your reviews into a personal "innie" model, plus a server that trains and serves it.

Below are the five problems that took most of my time.

---

## Challenge 1 — How do you actually capture someone's taste?

This is the whole ballgame, and it's much harder than it sounds. Taste is mostly **tacit**: we know far more than we can say. I can tell you I like "good systems talks," but I can't write down the rule that separates the ones I love from the ones I bounce off. If I can't articulate it, how is a model supposed to?

I ended up collecting preference at several levels of explicitness, because no single one is enough.

**(1) Explicit structure — what you *can* say.** Each funnel has:
- **Criteria**: natural-language conditions, each tagged `Include`/`Exclude` and `Must Have`/`Nice to Have`. e.g. *"discusses enterprise use cases — Include, Must Have."*
- **Gold standards**: reference videos you mark as positive or negative examples. These double as few-shot examples for the LLM later.
- **Discovery config**: keywords and creator channels that define where content even comes from.

**(2) Implicit signal — what you *do*.** The reviews. A three-way rating keeps friction low (a 1–5 star scale makes people freeze), and an optional free-text box captures the nuance the rating can't. I added **voice input** to the feedback box because the easiest way to get someone to explain *why* they liked something is to let them ramble out loud for ten seconds instead of typing.

**(3) The cold-start problem.** A personal model needs data, but nobody wants to review 200 videos before the thing works. So before a user has reviewed enough (I gate training at a small minimum), I bootstrap with **synthetic personas** — e.g. a *principal engineer who cares about inference*, a *junior engineer doing side projects*, an *executive thinking about AI strategy*. An LLM role-plays each persona to generate plausible reviews, which gives the personal model a sane starting point that the user's real reviews then pull toward their own taste.

The thing I keep relearning here: **the structured fields capture what the user can articulate; the reviews capture what they can't.** You need both, and the product's job is to make giving the implicit signal as effortless as possible. Most of my UI effort went into shaving seconds off the act of leaving a review.

> **Key lesson:** Taste is tacit knowledge. Don't try to make the user specify it — make it cheap for them to *demonstrate* it, and design the system to learn from demonstration.

---

## Challenge 2 — Making LLM judgment robust, transparent, and controllable

Once content is flowing in, something has to decide what each video *is* and whether it belongs. I deliberately did **not** want a single LLM call making an opaque yes/no. I wanted judgment that's hard to fool, easy to inspect, and easy to override.

**Robust: a classification swarm, not a single judge.** Each video is classified by **N parallel LLM calls across multiple models and providers** (e.g. GPT-4o and Claude), and the result is a majority vote. If every model says a video belongs in a node, confidence is 1.0; if half do, it's 0.5. This is the same collective-decision idea I explored in my earlier *Classification swarm agent* project — reliability and model-agnosticism come from aggregating many cheap, independent judgments rather than trusting one expensive one. A flaky or biased single model gets outvoted.

**Transparent: a hierarchy, with receipts.** Videos don't get one flat label. They cascade down a **tree of topic nodes** — discovered at the root, then routed into progressively more specific children until they hit a leaf (the recursion is driven by re-dispatching any video that lands on a node that still has children). Every node evaluation produces a `PASS` / `FAIL` / `CANNOT_TELL` with a confidence score *and* a plain-language explanation summarizing the models' rationales. In the review panel you can click "see detail" and read **each individual model's verdict and reasoning**. Nothing is hidden.

**Controllable: the human is always in the loop.** Any verdict is a button. You can toggle a `PASS` to a `FAIL`, and when you disagree the UI asks you *why* and stores your correction. That correction isn't just cosmetic — it's exactly the kind of signal that improves the system.

I started this part wanting a 100%-autopilot agent that would self-correct its own taxonomy. I gave up on that quickly, and it's the most important realization of the project: **classifying content by topic and quality is fundamentally subjective.** There is no objectively correct taxonomy or granularity — it depends entirely on the user's intent. So the goal isn't a perfect autonomous judge; it's a **transparent state the user can see and steer at any moment.** This is the same lesson my *Coding Interview Agent* taught me from the other direction: for subjective calls, the right move is usually to lean on a tiny bit of user interaction rather than to engineer the AI into omniscience.

> **Key lesson:** For subjective judgment, don't optimize for autonomy — optimize for *legibility and correction*. Aggregate many models for robustness, show the work, and make every decision a one-click override.

---

## Challenge 3 — Prompt-based vs model-weight (RL) based personalization

This is the most interesting tension in the project, and I built both sides to feel the difference.

**The prompt-based approach** is everything in Challenge 2: criteria in the prompt, gold standards as few-shot examples, multi-model voting. Its virtues are huge — it's transparent, you can change behavior by editing text, and there's no training loop. But it has a ceiling:

- It can only act on what you wrote down, which (see Challenge 1) is the small, articulable part of your taste.
- Few-shot context is finite. You can't paste a year of someone's viewing history into a prompt.
- Running N frontier models on every incoming video is **expensive and slow** at feed scale.

So for the *personalization* layer I went to **model weights**: train a small per-funnel "innie" model that learns to react to a video the way you would. The target is your own feedback. I implemented two methods on top of Tinker (LoRA on Llama-3.1-8B-Instruct):

**SFT (supervised fine-tuning).** Straightforward cross-entropy: given the video's title/summary/transcript, predict the user's review text. Cheap, stable, a great baseline. The limitation is that it optimizes token-level imitation — it learns to sound like your reviews, not necessarily to *mean* what you mean.

**RLVR (RL with a verifiable reward).** This is where it gets fun. The problem: how do you give a "reward" for an open-ended, subjective review? My answer was to make the reward **semantic similarity** — I embed the model's generated review and the target review, and the reward is their **cosine similarity**. A few details that mattered:

- **GRPO-style advantage**: I sample a group of completions per datapoint and use the group's *mean reward as the baseline* (advantage = reward − mean). This kills a ton of gradient variance and stabilizes learning without a separate value network.
- **KL penalty against the base model**, folded in as an advantage adjustment, so the policy doesn't drift off into reward-hacking gibberish that happens to embed nearby.
- **A length penalty**, because the model quickly discovered that rambling for 500 tokens nudges the embedding around; I penalize completions over ~400 tokens.

The tangible artifact of all this is the **"Ask your innie"** button on the review panel: it streams a review *in your voice* for a video you haven't seen yet. It's oddly personal to watch — it's the clearest window into what your model has actually absorbed about you, and it's the same signal I want to eventually use to **score and rank the feed** instead of just sorting by recency.

The honest takeaway on prompt-vs-weights is that it's **not** either/or — they're good at different layers:

- **Prompt-based judgment** for *classification and routing*, where I want transparency and instant steerability.
- **Weight-based learning** for *personal taste*, where the signal is tacit, high-volume, and impossible to fit in a prompt — and where a small fine-tuned model is far cheaper at inference than repeatedly polling frontier models.

> **Key lesson:** Prompting is how you encode the rules you can state; training is how you capture the preferences you can't. Use prompts for the parts of the system that must stay legible and steerable, and use weights for the parts that are tacit and high-volume.

---

## Challenge 4 — Building a reliable pipeline

A recommender that only works when you're watching is a demo. Innie has to run on its own, on a schedule, forever, without me babysitting it. This is the part that most resembled my *long-running agent reliability* work, and the lessons rhymed.

**Be vertical and break the work into fixed, idempotent steps.** The Prefect pipeline runs per funnel on an interval: discover videos → fetch metadata/transcript → summarize → classify (via the LangGraph swarm) → evaluate criteria → link to the tree. Each `FunnelVideo` carries an explicit status (`PENDING` → `PROCESSING` → `COMPLETED`, with `PENDING_RETRY`/`FAILED`), so a crash mid-run doesn't double-process or lose work — the next run just picks up where it left off. Discovery dedupes against what's already stored, so re-running is safe.

**Expect failure and handle it gracefully.** A retry policy with a failed-queue, a Redis-based rate limiter to stay under YouTube/LLM limits, and webhook callbacks so long-running training jobs report back instead of blocking. Training itself runs as a cancellable background task that writes its status to the DB at every transition.

**Streaming reliability is its own problem.** The per-video idea graph generates live in front of the user, and naive streaming breaks the moment the connection hiccups. The architecture I landed on cleanly separates concerns:

- LangGraph emits a custom event for every mutation (node added, edge added, etc.).
- The orchestrator writes those events into an **append-only Redis replay log**, then relays them to the browser over SSE.
- On reconnect, the client replays missed events from Redis — nothing is lost.
- When generation finishes, the final graph is written to **Postgres exactly once**, which becomes the durable source of truth.

The boundary that made this robust: *the agent never pushes to the browser directly.* It writes to a buffer; the transport reads from the buffer. Live updates, disconnect recovery, and durable persistence each have a clearly assigned owner.

**Keep the agent's decision space narrow.** The classification graph looks intricate — fan-out with `Send`, deferred aggregation nodes, an `interrupt` for batching — but the complexity is all *structural* (it processes many items × many models × many tree levels in parallel), not decisional. Finding the right subgraph abstraction took trial and error, but once the engine was simple and the decision space was small, it became something I could actually trust to run unattended.

> **Key lesson:** Reliability comes from structure, not from cleverness. Fixed idempotent steps, explicit per-item state, an append-only buffer between the agent and the world, and a single durable source of truth — those are what let a long-running agent run without a human watching.

---

## Challenge 5 — Building the user interface

I've come to believe that for this kind of product **the UI *is* the system**, because everything subjective resolves at the interface. Two surfaces did most of the work.

**The funnel canvas.** The topic hierarchy is a **React Flow canvas** — a live, editable tree of nodes you can expand, add children to, and inspect. Each node shows its video count, criteria, and filters; a side panel lets you edit the description, criteria, gold standards, and discovery sources. Making the taxonomy a visual, direct-manipulation object (instead of nested forms) is what makes "steer the system" feel real.

**The review panel.** This is where judgment meets correction. It shows the classification results with confidence, lets you toggle and correct any verdict, exposes per-model rationales on demand, and combines the rating, the free-text/voice feedback, and "Ask your innie" in one place. Every interaction is designed to be a single gesture.

**The idea graph** is the one feature that isn't about curation at all — it turns a video's transcript into an argument map (claims, evidence, counterarguments, rebuttals…) so watching becomes active understanding rather than passive consumption. It started as a tangent and became one of my favorite parts.

The throughline across all of it: **surface the system's internal state, and make every piece of it inspectable and correctable.** That's the same conclusion I reached in earlier projects — UI/UX is criminally underrated by engineers, and for subjective tasks it's often the *first* place to look for a solution, not the last.

> **Key lesson:** When the task is subjective, the interface isn't a wrapper around the intelligence — it *is* the intelligence. Build for inspection and intervention first.

---

## Other things that turned out to be hard

A few challenges that don't get their own chapter but shaped the project:

- **Evaluating a subjective system.** There's no ground-truth accuracy for "good taste," which makes both RL reward design and "is this version better?" genuinely hard. The embedding-similarity reward is a pragmatic proxy, not a truth.
- **Cost and latency.** Multi-model voting on every video is expensive; the hierarchy prunes the search, and a small trained model is meant to eventually replace frontier-model polling for the personalization layer.
- **Orchestrating four heterogeneous services.** Next.js, LangGraph, Prefect, and a Tinker training server have to agree on a schema. I generate the Python models from the Prisma schema so the contract can't silently drift.
- **The model of the domain kept evolving.** "Topics" became "funnels" with an explicit `ClassNode` tree; the data model was refactored more than once as I understood the problem better. That churn is a feature of building toward something you don't fully understand yet — but it has a real cost, and naming things early-and-wrong slowed me down.

---

## Where it's going

The pieces are all in place: discovery, a transparent classification swarm, a human-in-the-loop review surface, and a personal model that learns your taste from your feedback. The next milestone is closing the loop end-to-end — using the trained innie's score to **rank the live feed**, so the promise on the landing page ("your innie scores your feed") is fully real rather than partly aspirational.

The bigger bet underneath all of this: recommendation shouldn't be a black box optimizing someone else's objective. It can be a transparent, steerable, *personal* model that you teach and own. Building Innie has mostly convinced me that the hard part isn't the ranking — it's capturing tacit preference, keeping judgment legible, and choosing the right tool (a prompt or a weight update) for each layer.

Thanks for reading this far. As always, everything's a work in progress and I'd love questions, pushback, or ideas — don't hesitate to reach out.
