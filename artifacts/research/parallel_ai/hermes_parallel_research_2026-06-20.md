# Hermes SOTA Model Stack Research — 2026-06-20

Source run: `trun_7f0d77aad14040b4980cca67c0a6d6f2`
Parallel result URL: <https://platform.parallel.ai/play/deep-research/trun_7f0d77aad14040b4980cca67c0a6d6f2>
Raw artifact: `artifacts/research/parallel_ai/hermes_parallel_research_2026-06-20.json`

## Bottom line

For a Hermes-style engineering agent that must be **fast, frontier-grade, and cost-effective**, the best overall stack from the Parallel research is:

- **Default workhorse:** `claude-sonnet-4.6`
- **Cheap fast subagent / tool loop model:** `claude-haiku-4.5`
- **OpenAI alternative / strong coding tier:** `gpt-5.4`
- **Fast OpenAI worker:** `gpt-5.4-mini`
- **Frontier escalation / hardest tasks:** `claude-opus-4.8`
- **Best open-weight / budget escape hatch:** `glm-5.2` via `Fireworks` or `OpenRouter`

## Recommended provider / inference paths

### Primary production stack
1. **Anthropic direct**
   - Use for `claude-haiku-4.5`, `claude-sonnet-4.6`, `claude-opus-4.8`
   - Reason: best first-party support, prompt caching, strongest Claude tool/coding workflow alignment

2. **OpenAI direct**
   - Use for `gpt-5.4` and `gpt-5.4-mini`
   - Reason: strong coding performance and reliable tool support; useful second workhorse family

3. **Fireworks** for `glm-5.2`
   - Best open-weight fallback path when cost ceilings matter
   - Research cites cache-hit economics as especially attractive

4. **OpenRouter**
   - Best meta-provider / control plane when you want one bill and fast fallback switching across vendors
   - Use as routing fabric, not as your only source of truth for evals

### Secondary / optional
- **Google AI Studio / Vertex** for `Gemini 2.5 Flash`, `Gemini 2.5 Pro`, `Gemini 3.1 Pro`
  - Good for cost-sensitive long-context or batch paths
  - Not the best default coding model per the research synthesis

## Best single-model choice

If Hermes must use **one model only**:

- **Pick:** `claude-sonnet-4.6`
- **Why:** best balance of coding quality, tool use, large-context handling, and cost for day-to-day engineering work

## Best multi-model stack

If Hermes can route intelligently:

- **Tier 0 / trivial classification:** `gpt-5.4-nano` or `gemini-2.5-flash-lite`
- **Tier 1 / fast worker:** `claude-haiku-4.5`
- **Tier 1b / OpenAI fast worker:** `gpt-5.4-mini`
- **Tier 2 / main workhorse:** `claude-sonnet-4.6`
- **Tier 2b / alternate coding workhorse:** `gpt-5.4`
- **Tier 3 / hardest tasks:** `claude-opus-4.8`
- **Budget fallback / open weights:** `glm-5.2` on `Fireworks`

## Best budget stack

If the main objective is strong quality at low cost:

- **Primary worker:** `claude-haiku-4.5`
- **Secondary workhorse:** `glm-5.2` on `Fireworks`
- **Escalation only when needed:** `claude-sonnet-4.6`
- **Rare frontier escalation:** `claude-opus-4.8`

## Where GLM fits

`GLM 5.2` is **not the best default primary model** for this repo or for general Hermes use, but it is highly valuable as:

- the **best open-weight escape hatch**
- a **budget-aware fallback**
- a strong option for **batch jobs**, **quota avoidance**, and **cost-capped routing**
- a good fit when you want **provider flexibility** or partial self-hosting patterns later

Best placement:
- **Tier 2 budget fallback**
- **Open-weight batch path**
- **backup when Anthropic/OpenAI spend or rate limits spike**

Not ideal as sole default because the research still points to Claude/OpenAI for more reliable day-to-day coding outcomes.

## Routing policy Hermes should implement

1. **Default every non-trivial engineering task to `claude-sonnet-4.6`.**
2. **Spawn subagents on `claude-haiku-4.5` by default.**
3. **If a task is specifically code-heavy and architecture/depth-sensitive, allow `gpt-5.4` as alternate Tier 2.**
4. **If a worker fails two tool calls in a row, escalate that task to `claude-sonnet-4.6` or `gpt-5.4`.**
5. **If Tier 2 fails twice, escalate to `claude-opus-4.8`.**
6. **If daily spend crosses a threshold, reroute budget-sensitive Tier 2 traffic to `glm-5.2` on Fireworks.**
7. **Use prompt caching on Anthropic paths whenever stable prefixes repeat.**
8. **Track outcomes by task type, not just by model, because harness quality materially changes real-world results.**

## What this means for this repo specifically

For the FUSMLE repo, the model priorities are slightly different from generic daily use because the work includes:

- multi-file repo reasoning
- retrieval-heavy evidence comparison
- deterministic artifact generation
- validation and parity QA
- occasional UI/backend debugging

### Best model for this repo
- **Primary:** `claude-sonnet-4.6`
- **Reviewer / hardest synthesis:** `claude-opus-4.8`
- **Fast parallel subtasks:** `claude-haiku-4.5`
- **Secondary alternate coding perspective:** `gpt-5.4`
- **Cheap large-scale batch fallback:** `glm-5.2`

## What this means for daily use

For general daily agent usage outside this repo:

- **Best overall default:** `claude-sonnet-4.6`
- **Best cheap fast worker:** `claude-haiku-4.5`
- **Best alternate coding model:** `gpt-5.4`
- **Best premium escalation:** `claude-opus-4.8`
- **Best open-weight budget option:** `glm-5.2`

## Confidence / caveats

Important caveat from the research:

- Some leaderboard claims are vendor-reported and likely inflated relative to standardized harnesses.
- The research itself explicitly warns that **harness matters as much as the model**.
- Therefore, the right conclusion is **not** “pick the highest benchmark model,” but “use a tiered router with measured escalation.”

That is why the recommended answer is a routing stack, not a single universal winner.

## Final recommendation

If I had to set Hermes up today for the best mix of **frontier quality, speed, and cost efficiency**:

- **Main model:** `claude-sonnet-4.6`
- **Subagents:** `claude-haiku-4.5`
- **Alternate coding path:** `gpt-5.4`
- **Premium escalation:** `claude-opus-4.8`
- **Budget/open fallback:** `glm-5.2` via `Fireworks`
- **Meta-routing / failover:** `OpenRouter`

That is the strongest all-around June 2026 stack supported by the Parallel research.
