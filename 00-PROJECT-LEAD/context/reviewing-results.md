# Reviewing returned work and experiment results

Load when: a handoff comes back, or Matt brings a result from the app.

## Returned work (a HANDOFF file)

1. Check each acceptance line in the prompt against evidence in the handoff. No evidence means not done.
2. Check deploy claims yourself: `/health` commit, frontend bundle hash, job image digest. A claim that something is deployed must name the SHA or digest.
3. Check `00-PROJECT-LEAD/QUESTIONS.md` for anything the worker left.
4. Update `00-PROJECT-LEAD/STATE.md`. Tell Matt first whether the goal was achieved.

If the returned work is wrong, don't review it in the same context that wrote the prompt and then argue it through. Write down what the spec required, what came back, and what differs.

## Experiment results

- **Performance is not your review topic unless Matt asks.** Your job is whether the platform ran the experiment correctly: right config, right seasons, right features, results recorded.
- **Leakage checks belong in the platform.** For a finished experiment run, the checks that apply are: the label convention verifier (`01-DATA-PIPELINE/scripts/verify_label_convention.py`), the train/test season split in the config, and the run's recorded features. If a check the platform needs doesn't exist, that is a platform gap: add it to `00-PROJECT-LEAD/STATE.md` as a build item. Don't run the check as a one-off script in chat, and don't raise it as a warning when Matt is asking about something else.
- **Read the run's Notes / Observations.** A run with no analysis goes back to MODELING as incomplete.
- **Voided runs are marked.** If a run is invalidated, check that the experiment log says so and links to the reason.
- **May 2026 runs are never evidence.** Don't compare against them.

## Data-only fixes are not fixes

Rebuilding a table without fixing the code that builds it gets undone by the next scheduled run. Every fix changes the code first, then rebuilds the data from the fixed code.

## When establishing a fact is hard

If checking what is running, what it was built from, or when it last succeeded takes more than one lookup, that difficulty is a defect. Add it to `00-PROJECT-LEAD/STATE.md` as a platform gap, then do the digging.
