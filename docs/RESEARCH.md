# LLM research boundary

The LLM research layer organizes evidence and proposes falsifiable hypotheses.
It is not an execution component.

Every accepted record must identify the provider, model, prompt version,
request and completion time, token use, cost, raw output, and input evidence.
Evidence carries a stable identifier, source, publication and capture times,
and a content hash.

Accepted output contains:

- a concise summary and hypothesis;
- at least one citation from the supplied evidence set;
- optional contradictory citations;
- at least one falsification condition;
- explicit risks; and
- confidence between zero and one.

Unknown citations, malformed fields, missing falsification conditions, invalid
confidence, or fields that resemble an executable order fail closed. In
particular, research output cannot contain side, quantity, order, execution, or
limit-price fields. A validated hypothesis can inform later deterministic
features, but it cannot create an `OrderIntent`, bypass the common risk gate,
or modify an active strategy configuration.
