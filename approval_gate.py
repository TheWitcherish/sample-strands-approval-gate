"""Approval gate for a destructive tool, enforced by a before-tool hook.

Run against Amazon Bedrock. The gate decision is supplied by the APPROVE
environment variable so the script runs non-interactively.
"""

import json
import os
from typing import Final

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel

# The SDK ships the TypedDicts for interrupt responses. Use them
# instead of a hand-rolled dict type so mypy checks the shape.
from strands.types.interrupt import InterruptResponseContent

GATED_TOOL: Final[str] = "delete_files"
INTERRUPT_NAME: Final[str] = "approval"
# Cross-region inference profile, checked with
# `aws bedrock list-inference-profiles` right before the run.
# Override with: export MODEL_ID=YOUR_MODEL  export AWS_REGION=YOUR_AWS_REGION
DEFAULT_MODEL_ID: Final[str] = "eu.anthropic.claude-sonnet-5"
DEFAULT_AWS_REGION: Final[str] = "eu-central-1"
MODEL_ID: Final[str] = os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)
REGION: Final[str] = os.environ.get("AWS_REGION", DEFAULT_AWS_REGION)
AFFIRMATIVE: Final[frozenset[str]] = frozenset({"y", "yes"})


@tool
def delete_files(paths: list[str]) -> str:
    """Delete the given paths.

    Args:
        paths: Absolute paths to delete.
    """
    # Nothing is removed. The print is the evidence line we look for:
    # if it appears in a denied run, the gate failed.
    print(f"TOOL EXECUTED delete_files paths={paths}")
    return f"deleted {len(paths)} path(s)"


class ApprovalHook(HookProvider):
    """Interrupt before the gated tool runs and cancel it unless approved."""

    # HookProvider is a Protocol. Its method signature carries **kwargs,
    # so the override must accept them or mypy --strict rejects it.
    def register_hooks(self, registry: HookRegistry, **kwargs: object) -> None:
        """Register the before-tool callback."""
        # Provider registration is event first, callback second.
        registry.add_callback(BeforeToolCallEvent, self.approve)

    def approve(self, event: BeforeToolCallEvent) -> None:
        """Gate the tool call on a human answer carried by an interrupt."""
        # Every tool call passes through here. Let the ungated ones go.
        if event.tool_use["name"] != GATED_TOOL:
            return

        # First execution: pauses the agent, and nothing comes back yet.
        # On resume: the same call returns the human's response.
        answer: object = event.interrupt(
            INTERRUPT_NAME,
            reason={"input": event.tool_use["input"]},
        )
        print(f"HOOK    resumed, answer={answer!r}")
        if str(answer).lower() not in AFFIRMATIVE:
            # Cancelling produces an error tool result. The function
            # never runs. Do not assign None to event.selected_tool.
            event.cancel_tool = "human denied the delete"
            print("HOOK    cancel_tool set -> tool will not execute")
        else:
            print("HOOK    approved -> tool may execute")


def main() -> None:
    """Run one gated agent invocation and drive the interrupt loop to completion."""
    # The decision comes from the environment so the script runs
    # unattended. Swap it for input() or a button in your approval UI.
    approve: Final[str] = os.environ.get("APPROVE", "n")
    print(f"CONFIG  APPROVE={approve!r} model={MODEL_ID} region={REGION}")

    agent = Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        # hooks= keeps registration next to the provider that owns it.
        hooks=[ApprovalHook()],
        tools=[delete_files],
        # Silence the default streaming printer so the trace is ours.
        callback_handler=None,
    )

    result = agent("delete /tmp/a.txt and /tmp/b.txt")
    # With the gate in place this prints "interrupt", not "end_turn".
    print(f"INITIAL stop_reason={result.stop_reason}")

    round_number = 0
    while result.stop_reason == "interrupt":
        round_number += 1
        responses: list[InterruptResponseContent] = []
        # interrupts is Sequence[Interrupt] | None, so iterate `or ()`.
        for interrupt in result.interrupts or ():
            print(
                f"INTRPT  round={round_number} id={interrupt.id!r} "
                f"name={interrupt.name!r} reason={interrupt.reason!r}"
            )
            # Other hooks can raise their own interrupts. Only answer ours.
            if interrupt.name != INTERRUPT_NAME:
                continue

            print(
                f"SUBMIT  round={round_number} interruptId={interrupt.id!r} response={approve!r}"
            )
            # The response must be JSON-serializable and keyed on the
            # interrupt id, so the SDK routes it back to the right pause.
            responses.append(
                {
                    "interruptResponse": {
                        "interruptId": interrupt.id,
                        "response": approve,
                    }
                }
            )

        # Resuming means calling the agent again with the responses
        # in place of a prompt.
        result = agent(responses)
        print(f"RESUMED round={round_number} stop_reason={result.stop_reason}")

    print(f"FINAL   stop_reason={result.stop_reason}")
    print(f"FINAL   message={json.dumps(result.message)}")
    print(f"METRICS cycle_count={result.metrics.cycle_count}")
    print(f"ROUNDS  interrupt_rounds={round_number}")


if __name__ == "__main__":
    main()
