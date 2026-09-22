# sample-strands-approval-gate

This is a sample for experiments, not production code. It accompanies the blog post
"Gate the Tool, Not the Prompt: Strands Approval Hooks (With Traces)" and shows one thing:
a before-tool hook in Strands Agents that pauses the agent with an interrupt until a human
approves a destructive tool call, and cancels the call otherwise.

## What it does

- `approval_gate.py` registers an `ApprovalHook` on `BeforeToolCallEvent`.
- When the model asks for `delete_files`, the hook calls `event.interrupt(...)` and the agent
  returns with `stop_reason == "interrupt"`.
- The caller answers the interrupt (from the `APPROVE` environment variable so the script runs
  unattended) and resumes the agent.
- On resume the same `event.interrupt(...)` call returns the answer. Anything other than `y`
  or `yes` sets `event.cancel_tool`, and the tool never executes.

The `delete_files` tool is a fake: it prints `TOOL EXECUTED` and removes nothing.

## Run it

Requires Python 3.13, [uv](https://docs.astral.sh/uv/), AWS credentials with Amazon Bedrock
access, and a model you have verified in your own account:

```bash
aws bedrock list-inference-profiles --region eu-central-1 \
  --query 'inferenceProfileSummaries[].inferenceProfileId' --output text
```

Edit `MODEL_ID` and `REGION` in `approval_gate.py` if yours differ, then:

```bash
uv sync
APPROVE=y uv run python approval_gate.py   # tool runs once
APPROVE=n uv run python approval_gate.py   # tool never runs
```

Look for the `TOOL EXECUTED` line. It appears in the approved run and is absent in the denied run.

## Checks

```bash
uv run ruff check approval_gate.py
uv run ruff format --check approval_gate.py
uv run mypy --strict approval_gate.py
```

## Links

- [Strands Agents interrupts](https://strandsagents.com/docs/user-guide/sdk/interrupts/)
- [Strands Agents hooks](https://strandsagents.com/docs/user-guide/sdk/agents/hooks/)
- [Hook events](https://strandsagents.com/docs/user-guide/sdk/agents/hooks-events/)
