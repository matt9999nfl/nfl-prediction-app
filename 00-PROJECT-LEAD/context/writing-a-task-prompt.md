# Writing a task prompt

Load when: Matt asks for a prompt, or work needs handing to a Claude Code session.

## How work is handed out

Work goes to a fresh Claude Code session on Matt's PC, started at the repo root. You write the prompt to `00-PROJECT-LEAD/PROMPT-<slug>.md` and give Matt a one-line paste that points to it. This is the standard way to hand out work. It replaces appending `## CURRENT TASK` to other agents' `instructions.md` files, and nothing else (`WORK-ORDER-*.md` files, subagents) is used.

You write the prompt. The Claude Code session writes the code. You never share a context with the worker.

The repo root `CLAUDE.md` loads automatically in every Claude Code session and carries the standing rules, deploy facts and handoff format. Prompts don't need to repeat it.

## Before writing

1. Write Matt's request as a numbered checklist, in his words (see `00-PROJECT-LEAD/context/handling-requests.md`).
2. Check the facts the prompt depends on (file paths, table names, what is deployed) against the code or live system. Old handoffs are not evidence.

## Size

- One prompt, one stage. If a request has several stages (build, analyse, test, automate), write one prompt per stage and list the order in `00-PROJECT-LEAD/STATE.md`.
- Target under 200 lines. Over that, split.
- A stage that produces analysis of another stage's output runs in a fresh session, not the one that built it.

## Template

```
# PROMPT-<slug> — <the outcome, one line>

Start in: C:\Users\OEM\OneDrive\Desktop\nfl-prediction-app
Written: <date> by PROJECT-LEAD. Stage <n> of <m>. Next stage: PROMPT-<slug>.

## Matt's request
<His words, quoted. Then the checklist item(s) this stage covers.>

## Task
<One paragraph: what is true when this is done.>

## Read first
- 00-PROJECT-LEAD/PROJECT-CHARTER.md
- 00-PROJECT-LEAD/STATE.md (Decisions section: standing rulings, don't re-ask)
- 00-PROJECT-LEAD/context/talking-to-matt.md (how to write to Matt)
- <each code file, with why it matters>

## Scope
Allowed to change: <list>
Must not change: <list>

## Kill-switch
Stop, write to 00-PROJECT-LEAD/QUESTIONS.md, and tell Matt if:
- <specific condition, e.g. reproduced probabilities differ from stored picks by more than 1e-6>
- <scope condition, e.g. the fix needs a change outside the allowed list>
- <anything that would change production without Matt's go-ahead>

## Acceptance (each line true or false)
- [ ] <measurable condition>
- [ ] <tests: N pass, previously M>
- [ ] <live check: exact command and expected output>

## Returns-with
Write 00-PROJECT-LEAD/HANDOFF-<date>-<slug>.md containing: goal achieved yes/no (first line), commit SHA(s), `/health` commit, frontend bundle hash, image digests, experiment/run IDs, test counts before and after, anything left open.
```

## Acceptance must be true/false

Not acceptable: "Matt has the week-1 analysis", "works as expected", "looks right".
Acceptable: "`reports/week_analysis_2026_wk01.md` exists and has a section for each of the 16 game_ids in week 1", "each game's contributions sum to its stored log-odds within 1e-4".

If you can't write acceptance this way, the stage isn't shaped yet. Reshape it before writing the prompt.

## Handing it to Matt

Say where the file is. Then give the paste text in its own block, containing only the text to paste:

```
Read 00-PROJECT-LEAD/PROMPT-<slug>.md in full and carry it out.
```

Put what to watch for (the kill-switch conditions) under the block, not inside it. Then say how Matt's checklist items are covered, including anything left for a later stage.
