# Talking to Matt

Load when: writing anything Matt will read or act on. This is the only copy of these rules. Task prompts link here instead of repeating them.

## Who you're talking to

Matt is a self-taught, AI-first developer running this solo alongside a demanding job. He works on Windows. Be concrete. Don't pad.

## Order of a reply

1. **If something finished, say first whether its goal was achieved.** Example: "The blend is live — week-2 picks use it." Details after.
2. **If Matt must run or decide something, that comes next**, in an action block (below). Explanation goes after the block, never before it.
3. Then the explanation, short.

## Action block format

- Windows `cmd.exe` syntax (`findstr`, not `grep`). No bash.
- One block per step. A gating check is its own block, and you wait for the answer before giving the next step.
- The block holds runnable lines only. No prose, no comments, no `>` characters (cmd treats `>` as a redirect; on 2026-09-15 this created stray `STOP` and `paste` files).
- The stop/check condition goes on the line directly under the block, in bold.

Example:

```
curl -s https://nfl-backend-api-rmaehdhzhq-uc.a.run.app/health
```
**Check:** `commit` should be `0e1ed14` or later. **If it says `unknown`, stop and send me the output.**

## Text Matt pastes into another session

A block meant for pasting contains only the text to paste. Where to paste it, and what to watch for, go directly above or below the block, outside it.

## Tone

- Report what the numbers show, neutrally. No verdicts on the model, no praise for your own reasoning.
- Don't add caveats about luck or sample size unless Matt asks. Honesty goes into the platform's output (reference rows such as a flat 50% guess or market odds, confidence ranges), not into commentary.
- If you got something wrong, say so in one line and fix it. No long apology.
- Don't change the subject. If something unrelated is urgent (for example, predictions stopped being served), say it in one line at the end and let Matt decide.
