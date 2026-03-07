from langgraph.graph import START, END, StateGraph
from langgraph.types import Command, interrupt, Send
from langgraph.config import get_stream_writer

from agents.common import get_checkpointer
from agents.state import (
    ClassNodeState,
    ClassificationReturnState,
    ClassifyItemsOverallState,
    InterruptType,
)
from agents.classify_items.subgraphs.classify_an_item import (
    g as classify_an_item_graph,
    ClassifySubGraphState,
)


def spawn_next_batch(state: ClassifyItemsOverallState):
    if not state.items:
        # There will be no items when initializing the graph.
        return Command(goto=END)

    # TODO: we need a rate limiter in case there are too many items in a batch
    return Command(
        goto=[
            Send(
                node="classify_an_item_graph",
                arg=ClassifySubGraphState(
                    **state.model_dump(),
                    current_item=item,
                    parent_node_id=state.root_node_id,
                ),
            )
            for item in state.items
        ],
    )


def receive_classification_results(state: ClassificationReturnState):
    # This node is necessary to update the state with the results from the classify subgraph
    # We need this node separately from the handle_classification_results node because that node uses Command with Send which makes it complicated to update the state.
    # When using Send, you have to pass the state manually.
    # When using Command, the state update is not applied to the goto nodes immediately.
    writer = get_stream_writer()

    if state.classified_item and state.classified_item.classified_as:
        classified_nodes = [
            {
                "node_id": node_and_confidence.node_id,
                "confidence_score": node_and_confidence.confidence_score,
            }
            for node_and_confidence in state.classified_item.classified_as
        ]
        writer(
            {
                "update_data": {
                    "item_id": state.classified_item.id,
                    "classified_as": classified_nodes,
                }
            }
        )

    return {
        "items": state.classified_item,
        "cases_need_further_classification": state.cases_need_further_classification,
    }


def handle_classification_results(state: ClassifyItemsOverallState):
    if not state.cases_need_further_classification:
        return Command(goto=interrupt_or_terminate.__name__)

    return Command(
        goto=[
            Send(
                node="classify_an_item_graph",
                arg=ClassifySubGraphState(
                    **state.model_dump(),
                    current_item=item,
                    parent_node_id=parent_node_id,
                ),
            )
            for case in state.cases_need_further_classification
            for parent_node_id, item in case.items()
        ],
        update={
            "cases_need_further_classification": "RESET",
        },
    )


def interrupt_or_terminate(state: ClassifyItemsOverallState):
    if state.is_for_single_batch:
        return Command(goto=END)

    # When we want to keep classifying more items with next batch, we interrupt the graph here until we get new batch of items.
    interrupt(
        {
            InterruptType.NEXT_BATCH: "Items are all classified. Please provide next batch."
        }
    )
    return Command(goto=spawn_next_batch.__name__)


g = StateGraph(ClassifyItemsOverallState)
g.add_edge(START, spawn_next_batch.__name__)

g.add_node(
    spawn_next_batch,
    defer=True,
    destinations=("classify_an_item_graph", END),
)

g.add_node(
    "classify_an_item_graph",
    classify_an_item_graph,
    destinations=(receive_classification_results.__name__,),
)

g.add_node(receive_classification_results, defer=True)
g.add_edge(
    receive_classification_results.__name__, handle_classification_results.__name__
)

g.add_node(
    handle_classification_results,
    defer=True,
    destinations=("classify_an_item_graph", interrupt_or_terminate.__name__),
)

g.add_node(
    interrupt_or_terminate,
    defer=True,
    destinations=(
        spawn_next_batch.__name__,
        END,
    ),
)

g = g.compile(checkpointer=get_checkpointer())


def _annotate_edges(mermaid: str) -> str:
    # Remove spurious edge: xray=True incorrectly links the subgraph's exit node to
    # interrupt_or_terminate because handle_classification_results declares it as a
    # destination. aggregate_item_classification only ever routes to receive_classification_results.
    mermaid = mermaid.replace(
        "classify_an_item_graph\\3aaggregate_item_classification -.-> interrupt_or_terminate;\n",
        "",
    )

    replacements = {
        # Relabel classify node to make parallelism explicit
        "classify_an_item_graph\\3aclassify(classify)": (
            "classify_an_item_graph\\3aclassify(\"classify (× N in parallel)\")"
        ),
        "classify_an_item_graph\\3aspawn_classifications -.-> classify_an_item_graph\\3aclassify;": (
            "classify_an_item_graph\\3aspawn_classifications -.->|fan out: one per model × invocation| classify_an_item_graph\\3aclassify;"
        ),
        "classify_an_item_graph\\3aclassify --> classify_an_item_graph\\3aaggregate_item_classification;": (
            "classify_an_item_graph\\3aclassify -->|all complete: majority vote| classify_an_item_graph\\3aaggregate_item_classification;"
        ),
        "spawn_next_batch -.-> __end__;": (
            "spawn_next_batch -.->|no items| __end__;"
        ),
        "spawn_next_batch -.-> classify_an_item_graph\\3aspawn_classifications;": (
            "spawn_next_batch -.->|fan out items| classify_an_item_graph\\3aspawn_classifications;"
        ),
        "classify_an_item_graph\\3aaggregate_item_classification -.-> receive_classification_results;": (
            "classify_an_item_graph\\3aaggregate_item_classification -.->|item classified| receive_classification_results;"
        ),
        "handle_classification_results -.-> classify_an_item_graph\\3aspawn_classifications;": (
            "handle_classification_results -.->|needs deeper classification| classify_an_item_graph\\3aspawn_classifications;"
        ),
        "handle_classification_results -.-> interrupt_or_terminate;": (
            "handle_classification_results -.->|all items fully classified| interrupt_or_terminate;"
        ),
        "interrupt_or_terminate -.-> __end__;": (
            "interrupt_or_terminate -.->|is_for_single_batch = True| __end__;"
        ),
        "interrupt_or_terminate -.-> spawn_next_batch;": (
            "interrupt_or_terminate -.->|is_for_single_batch = False| spawn_next_batch;"
        ),
    }
    for old, new in replacements.items():
        mermaid = mermaid.replace(old, new)
    return mermaid


if __name__ == "__main__":
    from langchain_core.runnables.graph_mermaid import draw_mermaid_png

    mermaid = g.get_graph(xray=True).draw_mermaid()
    mermaid = _annotate_edges(mermaid)
    with open("./agents/diagrams/classify_items.png", "wb") as f:
        f.write(draw_mermaid_png(mermaid_syntax=mermaid))
