# Notes: the deep dive behind the post

The blog post keeps the story; this file keeps the detail that did not need to be in it: the
typing corrections, the limits, the `AfterToolsEvent` edge, and the two bets the post cut (the
cycle-count tie and the interrupt id shape). Everything below came from running
`approval_gate.py` against the real SDK and reading the traces in [TRACES.md](TRACES.md).

## Four typing corrections found by running the code

The first draft of `approval_gate.py` passed a read-through and failed `mypy --strict`. Running
it against strands-agents 1.56.0 fixed these:

1. `InterruptResponseContent` from `strands.types.interrupt` replaces a hand-rolled
   `list[dict[str, dict[str, str]]]`. The SDK ships the TypedDicts for interrupt responses, so
   use them and let mypy check the shape.
2. `HookProvider` is a `typing.Protocol` whose `register_hooks` takes `**kwargs`. The override
   must accept them, typed as `object`, or `mypy --strict` reports the signature as incompatible.
3. `registry.add_callback(BeforeToolCallEvent, callback)` is event first, callback second.
   `agent.add_hook(callback, BeforeToolCallEvent)` is callback first, event second. Both work;
   pick one order per codebase so the two do not get mixed up.
4. `AgentResult.interrupts` is typed `Sequence[Interrupt] | None`. Bare iteration fails under
   `mypy --strict`; iterate `result.interrupts or ()`.

One more that is not a typing error but bit the same way: `strands.__version__` does not exist.
Read the installed version with `importlib.metadata.version("strands-agents")`.

## Limits

- Interrupts are not supported on a direct tool call such as `agent.tool.delete_files(...)`.
  The gate only stands in the agent loop, where `BeforeToolCallEvent` fires.
- Interrupt state is session-managed. A stateless deployment that answers the interrupt in a
  later request needs a session manager so the resumed agent finds the pause it is answering.

## AfterToolsEvent edge

When an interrupt fires from `BeforeToolCallEvent`, `AfterToolCallEvent` does not fire for the
interrupted tool: the call never executed, so there is no after. `AfterToolsEvent` is different.
It fires once per event-loop cycle, not once per tool. A per-tool interrupt splits one batch of
tool calls across two cycles (the calls before the pause, then the resumed remainder), so
`AfterToolsEvent` fires twice for what the model produced as a single assistant message. A side
effect placed in `AfterToolsEvent` (a notification, a metric, a write) can therefore run twice
for one message. Keep each side effect at the boundary that owns it: per tool in
`AfterToolCallEvent`, per message somewhere that sees the whole message.

## Three things the traces showed

1. `cycle_count` is 3 in both the approved and the denied run. A cancelled call still produces
   a tool result with an error status, and the model still answers it, so a denial costs a full
   round rather than a short-circuit.
2. The interrupt id has the shape `v1:before_tool_call:<toolUseId>:<hash>`. The middle segment
   is the model's tool-use id and differs per run. The tail
   (`225d3982-9eb3-5ce9-93ca-f09a444307f7` in both traces) is byte-identical across separate
   processes, so it derives from the interrupt name rather than randomness. Key an approval
   queue on the whole id; the tail alone collides when two calls to the same tool are pending.
3. A `None` response re-raises the interrupt. In `strands/types/interrupt.py`, `interrupt()` returns
   the stored response only when it is not `None`, so a literal `null` from an approval UI never
   reaches the hook's check: the same interrupt rises again on resume and the caller's `while`
   loop spins. Deny with an explicit string, never with nothing.

## Model and versions

- strands-agents 1.56.0
- Model: `eu.anthropic.claude-sonnet-5`, a cross-region inference profile in `eu-central-1`,
  verified on 2026-09-22 with `aws bedrock list-inference-profiles` and
  `aws bedrock get-inference-profile`. Treat any model id in a blog post as perishable and check
  it in your own account before running.
