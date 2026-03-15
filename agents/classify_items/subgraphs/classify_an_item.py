from pydantic import BaseModel, Field, create_model
from typing import Annotated, Any
import asyncio
import operator
import re

from langchain_core.messages import HumanMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

from langgraph.graph import START, StateGraph
from langgraph.types import Command, Send
from langgraph.config import get_stream_writer

from agents.llm_factory import LLMFactory, AIModel
from agents.state import (
    ItemState,
    NodeAndConfidence,
    NodeVerdict,
    ClassifyItemsOverallState,
    ClassificationReturnState,
)
from agents.utils import (
    format_children_nodes_from_parent_node_ids,
    format_single_item,
    has_children_nodes,
    get_model_count_dict,
    filter_nodes_by_majority_threshold,
    abbreviate_node_ids,
)


class ClassifySubGraphState(ClassifyItemsOverallState):
    parent_node_id: str
    current_item: ItemState
    classification_results: Annotated[list[Any], operator.add] = Field(
        default_factory=list,
        description="A list of FinalJudge objects",
    )
    classified_node_ids: list[str] = Field(default_factory=list)


important_notes = [
    "An item can be classified into multiple nodes horizontally.",
    "If the item doesn't belong to any of the children nodes, don't try to shoehorn it into a node. Return an empty list.",
    "You should examine all the children nodes one by one, judging whether the item belongs to the node or not.",
]
important_notes = "- " + "\n- ".join(important_notes).strip()


def spawn_classifications(state: ClassifySubGraphState):
    model_count_dict = get_model_count_dict(state.models, state.total_invocations)
    return Command(
        goto=[
            Send(
                node=classify.__name__,
                arg=ClassifyInternalState(
                    **state.model_dump(),
                    model=model,
                ),
            )
            for model, count in model_count_dict.items()
            for _ in range(count)
        ],
    )


class ClassifyInternalState(ClassifySubGraphState):
    model: AIModel
    parent_node_id: str


async def classify(state: ClassifyInternalState):
    """
    This node classifies an item into one or more child nodes in a branch that has parent node with id `parent_node_id`. Note that it handles a single branch at a time. If there are multiple branches that need to be classified, this node may be called in parallel.
    """

    (
        abbreviated_nodes,
        abbreviated_id_to_original_map,
        original_id_to_abbreviated_map,
    ) = abbreviate_node_ids(state.nodes)

    abbreviated_parent_node_id = original_id_to_abbreviated_map[state.parent_node_id]

    formatted_nodes = await format_children_nodes_from_parent_node_ids(
        nodes=abbreviated_nodes,
        parent_node_ids=abbreviated_parent_node_id,
        all_items=state.items,
        num_examples=4,
        max_length=1000,
    )

    input_messages = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(
                """
You are a classification agent. You will be given an item and classify it into one or more child nodes in the taxonomy. 

This taxonomy is created for the following aspect:
{taxonomy_aspect}

Here are the child nodes you'll be classifying the item into. Note that there is a parent node in which the item is already classified into. You'll be classify the provided item into one or more children nodes. 

{nodes}

Important Notes!
{important_notes}
    """.strip()
            ),
            HumanMessagePromptTemplate.from_template(
                """
Here is the item you need to classify:
{item}

Important Notes!
{important_notes}
    """.strip()
            ),
        ]
    ).format_messages(
        taxonomy_aspect=state.taxonomy.aspect,
        nodes=formatted_nodes,
        item=format_single_item(state.current_item),
        important_notes=important_notes,
    )

    # Dynamically create Schema where each child node ID maps to RationaleAndVerdict
    children_nodes = [
        node
        for node in abbreviated_nodes
        if node.parent_node_id == abbreviated_parent_node_id
    ]

    class RationaleAndVerdict(BaseModel):
        rationale: str = Field(
            description="Think carefully whether the item belongs to this node or not."
        )
        verdict: bool = Field(
            description="True if the item belongs to this node, False otherwise."
        )

    # Anthropic requires property keys matching ^[a-zA-Z0-9_.-]{1,64}$
    # Sanitize labels into valid schema keys and keep a reverse mapping.
    def _sanitize_key(label: str) -> str:
        key = re.sub(r"[^a-zA-Z0-9_.\-]", "_", label)
        if key and key[0].isdigit():
            key = "_" + key
        return key[:64] or "_"

    # Build key → node mapping (deduplicate in case two labels sanitize identically)
    key_to_node: dict[str, Any] = {}
    for node in children_nodes:
        key = _sanitize_key(node.label)
        # Append index suffix to avoid collisions
        base_key = key
        i = 1
        while key in key_to_node:
            key = f"{base_key[:62]}_{i}"
            i += 1
        key_to_node[key] = node

    fields = {key: (RationaleAndVerdict, ...) for key in key_to_node}
    Schema = create_model("Schema", **fields, __base__=BaseModel)  # type: ignore

    llm = LLMFactory()
    classification_result: Schema = await llm.ainvoke(  # type: ignore
        model=state.model,
        prompts=input_messages,
        output_schema=Schema,
    )

    if classification_result is None:
        return Command(goto=aggregate_item_classification.__name__)

    # Collect per-node verdicts and map IDs back to originals
    correct_node_ids = []
    node_verdicts = []
    for key, child_node in key_to_node.items():
        node_result: RationaleAndVerdict = getattr(classification_result, key, None)
        if node_result is not None:
            original_id = abbreviated_id_to_original_map[child_node.id]
            node_verdicts.append(
                NodeVerdict(
                    model=state.model,
                    node_id=original_id,
                    node_label=child_node.label,
                    rationale=node_result.rationale,
                    verdict=node_result.verdict,
                )
            )
            if node_result.verdict:
                correct_node_ids.append(original_id)

    class ClassificationResult(BaseModel):
        node_ids: list[str]
        verdicts: list[NodeVerdict]

    return {
        "classification_results": [
            ClassificationResult(node_ids=correct_node_ids, verdicts=node_verdicts)
        ],
    }


async def _summarize_rationales(
    rationales: list[str],
    state: ClassifySubGraphState,
) -> str | None:
    if not rationales:
        return None
    rationale_text = "\n".join(f"- {r}" for r in rationales)
    prompt = HumanMessage(
        content=(
            "You are given a set of rationales from different AI models explaining why a content item "
            "belongs (or doesn't belong) to a classification node.\n\n"
            f"Rationales:\n{rationale_text}\n\n"
            "Write a single concise 1-2 sentence explanation summarizing why this item belongs to this node."
        )
    )
    llm = LLMFactory()
    result = await llm.ainvoke(
        model=state.models[0],
        prompts=[prompt],
    )
    if result is None:
        return None
    return result.content if hasattr(result, "content") else str(result)


async def aggregate_item_classification(state: ClassifySubGraphState):
    writer = get_stream_writer()
    selected_node_and_confidence_score = filter_nodes_by_majority_threshold(
        state.classification_results, state.majority_threshold
    )

    all_verdicts = [v for r in state.classification_results for v in r.verdicts]

    # Concurrently generate explanation summaries for all winning nodes
    explanations = await asyncio.gather(
        *[
            _summarize_rationales(
                rationales=[v.rationale for v in all_verdicts if v.node_id == node_id],
                state=state,
            )
            for node_id, _ in selected_node_and_confidence_score
        ]
    )

    new_parent_node_ids = [
        node_id
        for node_id, _ in selected_node_and_confidence_score
        if has_children_nodes(state.nodes, node_id)
    ]
    cases_need_further_classification = [
        {parent_node_id: state.current_item} for parent_node_id in new_parent_node_ids
    ]

    writer(
        {
            "update_data": {
                "item_id": state.current_item.id,
                "new_parent_ids": new_parent_node_ids,
            }
        }
    )

    updated_current_item = ItemState(
        id=state.current_item.id,
        content=state.current_item.content,
        classified_as=[
            NodeAndConfidence(
                node_id=node_id,
                confidence_score=confidence_score,
                explanation=explanation,
            )
            for (node_id, confidence_score), explanation in zip(
                selected_node_and_confidence_score, explanations
            )
        ],
        verdicts=all_verdicts,
    )

    return Command(
        graph=Command.PARENT,
        goto=Send(
            node="receive_classification_results",
            arg=ClassificationReturnState(
                classified_item=updated_current_item,
                cases_need_further_classification=cases_need_further_classification,
            ),
        ),
    )


g = StateGraph(ClassifySubGraphState)
g.add_edge(START, spawn_classifications.__name__)

g.add_node(spawn_classifications, destinations=(classify.__name__,))

g.add_node(classify)
g.add_edge(classify.__name__, aggregate_item_classification.__name__)

g.add_node(aggregate_item_classification, defer=True)

g = g.compile()
