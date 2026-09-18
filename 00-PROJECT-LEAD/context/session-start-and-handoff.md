# Session start and handoff

Load when: a session starts, Matt says "handoff" or "pickup", or context is getting full.

## Start

1. Read `00-PROJECT-LEAD/instructions.md`, then `00-PROJECT-LEAD/STATE.md`.
2. Read `00-PROJECT-LEAD/QUESTIONS.md`. Anything open there goes to Matt before new work.
3. If a `00-PROJECT-LEAD/HANDOFF-*.md` is newer than the date at the top of `00-PROJECT-LEAD/STATE.md`, read it and update `00-PROJECT-LEAD/STATE.md` from it.
4. Re-check the live facts in `00-PROJECT-LEAD/STATE.md` if they are more than a day old. Run what you can yourself. If Matt has to run something, give one action block (see `00-PROJECT-LEAD/context/talking-to-matt.md`):

```
curl -s https://nfl-backend-api-rmaehdhzhq-uc.a.run.app/health
curl -s http://34.49.20.115/ | findstr /C:"assets/index-"
gcloud run jobs executions list --job nfl-production-refresh --region us-central1 --limit 3
```

5. If Matt opened with a request, work on it. Give a state summary only if he asks, or if the state conflicts with his request. If the state is unclear, ask before working.

## During the session

- **Corrections become rules.** When Matt corrects how you behave, add the fix to the right `context/` file now, and tell him which file in one line.
- **Decisions go on the board.** Any decision Matt makes either adds an item to `00-PROJECT-LEAD/STATE.md` or is recorded there with "no work follows from this."
- **Repeated work becomes a script or a template.** If you do the same thing three times in a session, write it down.
- **At about half your context**, write the handoff now. Don't wait until the end.

## Handoff ("handoff", or the session is ending)

1. Copy the current `00-PROJECT-LEAD/STATE.md` to `00-PROJECT-LEAD/archive/STATE-<date>.md` (don't overwrite an existing copy).
2. Rewrite `00-PROJECT-LEAD/STATE.md` using the template below. It describes what is true now, not what you did.
3. Check every file you changed this session for stale paths and contradictions.
4. Tell Matt it's done, and give him the resume prompt in a paste-only block.

## STATE.md template

```
# STATE — <date, NZ>

## Current state (verified <date/time> against <what>)
## Decisions (standing rulings — don't re-ask)
<"Chose X over Y because Z", dated>
## Open items
### Matt's current priority
### Waiting on Matt
### Background list (not the agenda — see handling-requests.md)
## Next action
## Resume prompt
```

## Pickup ("pickup")

Read `00-PROJECT-LEAD/STATE.md` and any newer handoff. Summarise current state, open items and next action in a few lines. Wait for Matt to confirm before starting work.
