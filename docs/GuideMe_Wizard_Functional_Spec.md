# Guide Me Wizard Functional Specification

## Purpose

Guide Me is the prompt-construction and prompt-repair wizard inside HermanPrompt.

Its purpose is to:

- help the user create a prompt that accomplishes the task they want accomplished
- produce a properly formatted prompt that includes all required elements
- improve both structure and specificity so the prompt is likely to score at least `95`
- continue to target `100` when useful, but avoid frustrating the user by repeatedly asking for refinements in the same area without meaningful progress
- ingest a user's existing prompt when one exists
- identify what is missing or weak
- guide the user through a small number of targeted improvements
- compile a stronger labeled prompt
- return that improved prompt to the main composer

Guide Me is not intended to be a generic coaching chat. It is a guided workflow whose output is a reusable high-quality LLM prompt.

## Product Boundary

### Prompt Transformer responsibilities

- score the prompt
- evaluate `Who`, `Task`, `Context`, and `Output`
- return per-field status, scores, reason, and improvement hints
- return the consolidated prompt score

### HermanPrompt responsibilities

- launch and render the wizard
- ingest the source prompt and recent chat context
- decide which step or refinement state to show next
- compile the in-progress prompt draft
- request scoring after each user submission
- use AI to develop contextual suggestions that overcome the deficiencies identified by Prompt Transformer
- show suggestions and apply selected refinements
- return the compiled prompt to the composer

## Core Inputs

Guide Me can start with any combination of these inputs:

- source prompt text from the composer
- conversation ID
- current conversation history
- user profile / display name
- Prompt Transformer field scores and consolidated score

## Core Output

The functional output of the wizard is:

- a compiled prompt draft using labeled sections:
  - `Who:`
  - `Task:`
  - `Context:`
  - `Output:`
  - `Additional Information:`
- a completion state that allows the user to insert that prompt into the main composer

Secondary outputs:

- step-specific guidance
- prompt-ready rewrite suggestions
- requirement debug payload
- decision trace payload

## Guide Me State Model

Primary steps currently defined in the product:

- `intro`
- `describe_need`
- `who`
- `why`
- `how`
- `what`
- `refine`
- `complete`
- `cancelled`

Functional modes:

- `Collection mode`
  Purpose: gather missing structural prompt sections
- `Specificity mode`
  Purpose: improve prompt quality after structure is already complete

## High-Level Flow

1. User clicks `Guide Me`.
2. The wizard loads the current source prompt and recent chat context.
3. HermanPrompt sends the compiled draft to Prompt Transformer for scoring.
4. Based on the Prompt Transformer scoring, Guide Me decides whether the prompt needs:
   - section collection
   - targeted field repair
   - specificity refinement
   - completion
5. The user responds or selects a rewrite suggestion.
6. HermanPrompt updates the in-progress prompt draft.
7. HermanPrompt re-scores the compiled draft.
8. Based on the Prompt Transformer score, the wizard either:
   - moves to the next needed step
   - stays in targeted refinement
   - completes and enables insertion into the composer
   - if the same refinement area is being requested again without meaningful score improvement, the wizard should explain that the prompt is still suboptimal, present the current draft score clearly, and offer the user a choice to continue refining or use the prompt as-is

## Use Cases

### Use Case 1: Start With No Prompt Input

#### Starting condition

- composer is empty or does not contain a usable prompt
- user clicks `Guide Me`

#### Expected wizard behavior

A. Examine recent prompt history and available profile context to estimate the user's typical AI need
1. Start at `intro`
2. Ask whether the user's typical AI use matches today's need
3. If user answers `No`, route to `Describe Need`
4. If user answers `Yes`, use the likely typical AI use as an initial task seed and continue to the next needed step
5. Collect missing structural sections
6. Build a labeled prompt draft as the user responds
7. Re-score after each user submission
8. Once structure is complete, move to specificity mode if the score is still below threshold
8A. In specificity mode, if improvement is requested more than once for the same section or issue, the wizard should present a message that the prompt is still suboptimal and ask whether the user wants to continue refining or finalize the prompt as-is.
9. Complete when the prompt reaches the practical stop threshold, or when the user explicitly chooses to finalize the prompt as-is.

#### User inputs

- `Yes` or `No`
- freeform task description
- optional role/persona information
- optional instructions / constraints
- optional context
- desired output format
- optional refinement selection or freeform refinement

#### Expected final output

- a labeled high-scoring prompt with `Who`, `Task`, `Context`, `Output`, and optionally `Additional Information`
- a `Prompt Ready` state
- a `Use Prompt` action that inserts the completed prompt into the composer
- a `Use AS-IS` action that allows the user to accept the current draft before formal completion

#### Example output shape

```text
Who: You are an experienced recruiting strategist helping me improve hiring quality for a Customer Success Manager role.

Task: Recommend specific changes to reduce unqualified applicants by at least 30% over the next hiring cycle.

Context: We are receiving a high volume of applicants who lack SaaS customer success experience, renewal ownership, and cross-functional stakeholder management skills.

Output: Respond in this chat with a 3-sentence summary, 5 bullet points to improve the job description, 5 bullet points to strengthen screening criteria, 3 sourcing recommendations, and 3 immediate next steps.

Additional Information: Prioritize practical changes that can be implemented without increasing recruiter headcount.
```

### Use Case 2: Start With A Raw, Unstructured Prompt

#### Starting condition

- composer contains freeform text such as:
  - `We're hiring a Customer Success Manager but we're getting a lot of unqualified candidates`
- user clicks `Guide Me`

#### Expected wizard behavior

1. Ingest the raw prompt
2. Score it immediately
3. Infer what information is already present
4. Ask only for the missing or weak sections
5. Use one answer to improve multiple sections when appropriate
6. Re-score after each submission
7. Once all sections are structurally complete, switch to specificity mode
7A. In specificity mode, if the same issue is revisited without meaningful score improvement, the wizard should surface the current score and offer the user a choice to continue refining or finalize the prompt as-is.
8. Continue refining until the prompt reaches the practical stop threshold or no higher-value refinement remains

#### User inputs

- prompt repair answers
- selected suggestions
- freeform refinements

#### Expected final output

- a compiled labeled prompt that preserves the user's real objective
- no loss of core task intent during prompt assembly

### Use Case 3: Start With A Structurally Complete But Weak Prompt

#### Starting condition

- composer contains a labeled prompt with `Who`, `Task`, `Context`, and `Output`
- field structure may already score well
- consolidated score is still below threshold

#### Expected wizard behavior

1. Ingest and score the full prompt
2. Do not ask collection questions again
3. Enter specificity mode immediately
4. Identify one remaining issue at a time
5. Offer prompt-ready rewrites that directly address that issue
5A. In specificity mode, if the same issue is revisited without meaningful score improvement, the wizard should present the current score and ask whether the user wants to continue refining or finalize the prompt as-is.
6. Re-score after every selected or typed refinement
7. Change strategy if the same issue repeats without score improvement

#### User inputs

- numbered suggestion selections
- freeform typed refinements

#### Expected final output

- a more specific version of the original prompt
- the same labeled structure, but stronger task, context, output, or overall specificity
- a path for the user to accept the draft as-is if the score is good enough for their needs

### Use Case 4: Start With An Already Strong Prompt

#### Starting condition

- source prompt already meets the practical stop threshold

#### Expected wizard behavior

1. Do not send the user through repair steps
2. Show that the prompt is already strong
3. Offer:
   - review current prompt
   - start over

#### Expected final output

- existing prompt draft available for review and insertion into the composer

## Input Handling Rules

### Intro input

- `Yes` means continue using the likely typical AI use or the current prompt as the basis
- `No` means route directly to `Describe Need`
- intro input must not trigger completion

### Section answer input

- answers may improve more than one section
- answers should be interpreted against the whole prompt, not only the visible question label

### Refinement input

- numbered answers such as `1`, `1,2`, or `2 3` mean apply listed suggestions
- freeform refinements must be treated as actual prompt edits
- freeform refinements containing digits must not be mistaken for numbered option picks

## Prompt Draft Behavior

Guide Me should maintain an evolving compiled draft throughout the session.

Expected behavior:

- after every user submission, recompute the current best draft
- store that draft in session state
- show the draft in the wizard when the user chooses to view it
- submit the compiled draft for scoring after every user submission

## Completion Rule

Guide Me should not complete merely because all four core sections exist.

Functional completion rule:

- structure is complete
- the prompt has reached the practical stop threshold
- the prompt is ready to be inserted back into the composer
- or the user explicitly chooses to use the current draft as-is after being shown the achieved score

Current practical stop threshold:

- consolidated `final_score >= 95`
- and `final_llm_score >= 95` when LLM score is available
- if the same type of improvement is requested more than once without score improvement, the wizard should ask whether the user wants to keep refining or accept the prompt as-is

## Functional Requirements

| ID | Functionality | Description | Expected Behavior | Current State |
| --- | --- | --- | --- | --- |
| GM-01 | Launch from composer | User can start Guide Me from the composer | Wizard opens immediately with loading feedback | Implemented |
| GM-02 | Launch from coaching surfaces | User can start Guide Me from coaching dialogs / feedback surfaces | Guide Me opens using current prompt context | Implemented |
| GM-03 | Source prompt ingestion | Wizard reads the current composer prompt on launch | Prompt is ingested before any questions are asked | Implemented, still sensitive to prompt-state bugs |
| GM-04 | Chat-context ingestion | Wizard considers recent conversation context | Context should help interpret prompt meaning | Implemented, quality depends on prompt interpretation |
| GM-05 | Intro routing | `No` on intro routes to `Describe Need` | Must not jump to completion | Implemented after recent fix |
| GM-06 | Missing-section collection | Wizard asks only for missing structural sections | No unnecessary section prompts | Partially implemented |
| GM-07 | Multi-section answer merge | One user answer can populate more than one section | Whole-prompt interpretation | Partially implemented |
| GM-08 | Prompt draft persistence | Current compiled draft is stored after each step | Draft remains viewable and scorable | Implemented |
| GM-09 | Prompt draft preview | User can open and inspect evolving prompt | Draft shown in modal panel | Implemented |
| GM-10 | Re-score after every submission | Every answer triggers scoring on the compiled draft | Score should reflect latest compiled draft | Implemented |
| GM-11 | Prompt Transformer as scoring authority | HermanPrompt must not invent field scores | Display transformer-provided scores only | Implemented |
| GM-12 | Collection-to-specificity transition | Once structure is complete, wizard moves to specificity mode | No return to section prompts | Partially implemented; still unstable in edge flows |
| GM-13 | Single-issue specificity focus | Wizard focuses on one remaining issue at a time | Avoid cross-field suggestion drift | Partially implemented; recently improved |
| GM-14 | Suggestion quality | Suggestions should be task-aware, prompt-ready, and specific | Avoid generic filler like repeated `subject-matter expert` phrasing | Partially implemented |
| GM-15 | Freeform refinement handling | Typed refinements are applied as prompt edits | Freeform text must not be ignored | Implemented after recent fix |
| GM-16 | Numbered refinement handling | User can pick one or more numbered suggestions | Correct options are applied | Implemented |
| GM-17 | No-delta detection | Wizard detects repeated refinements with no score improvement | Change strategy instead of looping | Partially implemented |
| GM-18 | 95-point stop rule | Wizard stops at practical threshold instead of chasing perfect forever | Avoid over-refining last few points | Implemented |
| GM-19 | Already-strong prompt handling | Strong prompt on launch should not enter repair loop | Offer review or start over | Implemented |
| GM-20 | Completion handoff | Prompt Ready must display the final prompt and allow insert to composer | User can push final prompt back to main composer | Implemented |
| GM-20a | Use AS-IS handoff | User can accept the current draft before formal completion | Wizard shows achieved score, asks for confirmation, then moves the draft into the composer | Partially implemented |
| GM-21 | Requirement debug view | Show raw transformer requirement payload under `Show Details` | Aid debugging of score mismatches | Implemented |
| GM-22 | Decision trace | Show backend decision chain under `Show Details` | Aid debugging of routing/refine logic | Implemented |
| GM-23 | Scenario harness | Ability to run repeatable local prompt scenarios | Support deterministic bug reproduction | Implemented |
| GM-24 | Five-step usability target | Typical prompt-repair flow should complete in five steps or fewer | Avoid circular user experience | Not reliably met |
| GM-25 | Graceful repeated-refinement handling | If the same issue is raised more than once, the wizard should explain the lack of progress and offer a path out | Avoid user frustration and circular prompting | Partially implemented |

## Known Functional Gaps

These are the most important current gaps based on recent testing:

1. The wizard can still loop in `Refine` when structure is complete but the remaining specificity issue is not diagnosed cleanly enough.
2. Suggestion quality is improved but still not consistently specific enough for all domains.
3. When all field scores are maxed but consolidated score is still low, the whole-prompt diagnosis is still weaker than it needs to be.
4. The five-step completion target is not yet consistently achieved in real prompts.
5. Repeated asks for improvements in the same area still need a more graceful user-facing branch that clearly offers “continue refining” versus “use as-is.”

## Review Notes

This document is intended for markup and review.

It is a functional spec, not an implementation design. It describes:

- what the Guide Me Wizard is supposed to do
- what inputs it accepts
- what outputs it must produce
- which parts are working now versus still unstable

