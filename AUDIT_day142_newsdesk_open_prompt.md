# Day-142 — the news desk asked about the open: NULL (rejection #58)

**Registered** 2026-10-28 in `PREREGISTER_day142_newsdesk_open_prompt.md`
(baf7e8f), before any call was made. **Run** 2026-10-29 in the council lab's
slot by `replay_news_open.py`; summary `data/replay_day142_open_prompt.json`.
One look. Nothing live changes.

## The question

Day-139's pre-open news desk asks day-122's prompt, which asks for a side
"from 09:45 ET to the close" and says the open will already have priced the
release. It is scored from the open to the close against XIU (`w_day`). Does a
prompt that asks about the scored window, the open, earn anything?

## The population

* **420 events over 63 sessions** (2026-07-02 → 10-01), rebuilt today by
  `news_desk.events` on the committed wire archive. That is day-122's count.
* **Excluded by the rule:**

  | Reason | Events |
  |---|---:|
  | traded value under C$3M a day | 289 |
  | price under C$2 | 72 |
  | fewer than 21 prior sessions | 24 |
  | not quoted in CAD | 13 |
  | not an equity | 9 |
  | no chart today | 6 |

  The 6 come from 4 symbols that fail on every request, also one at a time:
  BY.TO, MPVD.TO, CIU-PR.TO and MIC-PR.TO.
* **Bodies.** All 446 release bodies were refetched from newswire.ca, with no
  failure.
* **Calls.** 132 DeepSeek requests (two wordings, 12 items a batch), none
  retried.
  * The open wording answered 418 of 420. Two answers gave a confidence
    outside 0.5–1, and the parser dropped them as registered.
  * Day-122's wording answered all 420.

## The verdict: NULL

| | Open wording (the test) |
|---|---:|
| Calls / sessions | 418 / 63 |
| Right | 205 (49%) |
| Mean `w_day`, open → close against XIU | +0.11% |
| Session-clustered t | 0.99 |
| Sign-flip placebo p (2,000 draws, seed 142) | 0.19 |
| Halves, by date | +0.06%, +0.16% |
| Net of the 0.13% round trip | −0.02% |

* **The bar** (day-139's `news_desk._preopen_bar`) needs a mean above 0.13%,
  t ≥ 3, a placebo p < 0.01 and both halves positive. Only the halves pass.
  The mean is positive, so it is not a FAIL; as registered it is NULL.
* **The planted control.** Every call was centred on the sample mean and
  0.5% added; the same t is 4.41, so the test could see an effect of that
  size. The smallest detectable effect at 80% power is 0.44% a call.
* **The contamination probe.** It asked 12 names' closing prices on their
  sessions. The median error was 48%, so the model does not remember the
  period. Not VOID.

## Beside the verdict (descriptive, never a verdict)

* **Day-122's own prompt, re-asked today on the same items:** +0.05% a call,
  t = 0.44 (420 calls, 50% right). Day-122's own run of it read +0.09%,
  t = 0.71. A re-ask of the same prompt moves the estimate by about that much.
* **The paired difference, open minus day-122, by event:** +0.06% a call,
  t = 0.46. The side changed on 99 of 418 calls (24%).
  * Re-asking one prompt also flips some calls. The old answers went with the
    10-26 reset, so the share due to the wording alone cannot be separated.
* **The gap (prior close → open)** under the open wording is +0.21% a call,
  t = 2.48 (day-122's wording today: +0.21%, t = 2.17). The desk still reads
  which way a release points, and the open still prices it, as day-122 found.
* **Long share:** 71% for the open wording, against 66%.
* **The splits:**

  | Split | Open wording | Day-122 wording |
  |---|---|---|
  | Material | 273 calls, +0.27%, t = 1.75 | +0.14%, t = 0.84 |
  | Routine | 145 calls, −0.18%, t = −0.95 | −0.11% |
  | Confidence ≥ 0.6 | 230 calls, +0.37%, t = 2.22 | +0.11%, t = 0.55 |

  These splits were registered as description only, and they were read after
  the verdict. With six split rows, one reaching t = 2.2 is well within what
  noise gives, and it is short of the bar. It is not a finding, and no rule is
  built on it.

## So

* **Rejection #58.** Asking about the window the desk is scored on does not
  change what it earns from the open: +0.11% against +0.05% for the old
  wording on the same releases, both inside the noise.
* **Day-139's disclosure has its answer.** The mismatch between its question
  (09:45 → close) and its measure (open → close) costs nothing measurable.
* **Nothing changes.** Day-139's pre-open arm runs on unchanged, with
  day-122's prompt byte for byte. No second pre-open arm is proposed, and the
  prompt is not re-worded against this replay.
* **Cost:** 133 DeepSeek calls (132 asks and the probe). No OpenRouter.
