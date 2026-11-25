# PREREGISTER day-155b: the news desk's top two by its own score (owner, 2026-11-24 evening)

Registered 2026-11-24 at about 22:30 ET, before any return in the record was
split by confidence or by materiality. The script, `newsdesk_confidence.py`,
is committed in its own commit before it runs. It gets one look, tonight, and
reads the committed record only (`data/news_calls.csv`), so it costs nothing.

## The question

The owner, after 11-24: look at the confidence scores "to see the ones that
are actually tested to be the most correct … maybe the top two news desk picks
that will have a highest score".

* **The rule as the owner would see it.** The email already orders the news
  desk's calls by material first, then the model's own confidence, then ticker
  (`news_desk.lines`). So "the top two by score" are the table's first two
  rows. Do they beat the rest of the same morning's calls?
* **A second split:** the calls the model marks material against the ones it
  marks routine.

## What is already known

* **On the day-122 replay** (419 releases, the same prompt; `AUDIT_day122_releases.md`),
  09:45 → close against XIU:
  * all calls: +0.11% a call, t = 0.83;
  * confidence ≥ 0.6: 123/222 right (55%), +0.06%, t = 0.34;
  * material only: 129/256 right (50%), +0.04%, t = 0.20.

  Neither split did better than the whole.
* **On day-142's replay** (the open wording), the splits were descriptive and
  short of any bar: material +0.14% (day-122 wording), routine −0.11%.
* **Model confidence has not sorted outcomes elsewhere in this record:**
  * day-117: DeepSeek's desk confidence was not calibrated;
  * day-132b T1: the top-confidence pick did 0.20% worse than the rest;
  * day-145c: a model's first-named nomination was no better than its second;
  * day-154: Claude's confidence ≥ 0.50 leaned the wrong way.
* **Expect UNDERPOWERED.** The live record is short.

## The population

* **The FULL arm** of `data/news_calls.csv`, sessions 2026-10-02 → 2026-11-24.
  It is what the email prints, under prompt version `day122-v1`.
* **Counted at registration** (no return read): 221 calls over 35 sessions,
  208 with a 09:45 → close outcome. 141 are LONG and 80 SHORT; 131 are
  material and 90 routine. 32 sessions have three or more calls.
* **The outcome** is the ledger's `w945`: side × (the name's 09:45 → close
  minus XIU's), in %. It is the window the scoreboard's news desk line uses.

## H1 (primary): the top two against the rest of the morning

* **The order.** Each session's FULL calls, all of them whether scored or not,
  are sorted with the email's own key:
  * material first;
  * then confidence, highest first;
  * then ticker.

  The first two are the top two; the others are the rest.
* **The statistic.** For each session with at least one scored top-two call
  and one scored other call:
  `d = mean(w945 of the scored top two) − mean(w945 of the scored rest)`.
  The test is over the session series of d.
* **The machinery** is day-145's (`best_first.py`): a paired t over session
  means, a one-sided sign-flip placebo with 10,000 draws at seed 156, and the
  halves in session order.
* **TOP2_BETTER needs all of:**
  * mean d > 0 with t ≥ 3;
  * placebo p < 0.01, upper;
  * both halves positive;
  * the top two's own mean w945, over every scored top-two call, above the
    0.13% round trip.
* **TOP2_WORSE** is the mirror: t ≤ −3, the lower placebo p < 0.01, and both
  halves negative. It is reported to the owner.
* **The control.** Every d is centred on zero and 1.0% is added, then the same
  t is taken. If that t is below 3 the verdict is UNDERPOWERED. The smallest
  difference detectable at 80% power is printed: (3 + 0.84) × sd / √n.
* **Anything but TOP2_BETTER is rejection #71.** Rejection #70 is held by lab
  item 17, the faded gap, which was registered first and runs on 11-25.

## H2 (secondary): material against routine

* **The groups.** Every scored FULL call, labelled material or routine by the
  model, each in its session's cluster.
* **The test.** Day-140's arm A (`fixpack.arm_a`, seed 156, 2,000 label
  shuffles): material minus routine, a session-clustered t, the one-sided
  placebo, both halves in session order, and at least 10 calls in each group.
* **MATERIAL_BETTER needs:**
  * arm A to PASS;
  * the material calls' mean above the 0.13% round trip;
  * a planted 1.0% (each group centred, then 1.0% added to the material
    calls) to show at t ≥ 3. Without that the verdict is UNDERPOWERED.
* **Anything but MATERIAL_BETTER is rejection #72.**

## Beside the verdicts (descriptive, never a verdict)

* **Confidence:**
  * buckets (≥ 0.65, 0.60, 0.55, below 0.55);
  * the rank correlation of confidence with w945.
* **The same splits on other bases:**
  * the raw return, `w945_raw` (unhedged, the way the owner trades it);
  * the PREOPEN arm (asked at 09:20), on its own registered window, open →
    close against XIU (`w_day`);
  * the HEADLINE arm.
* **The market:**
  * LONG against SHORT, and the share of LONG calls;
  * each session's mean raw result against XIU's own 09:45 → close.
* **When the FULL and HEADLINE arms take opposite sides** (the email's "From
  the title alone" column): how often the FULL side was right, against the
  sessions where the two agree.
* **11-24 itself.**

## What a result changes

* **TOP2_BETTER** goes to the owner as a proposed "top two of the news desk"
  line. The owner has already asked for one, so it can ship as display, saying
  what the record shows and no more.
* **MATERIAL_BETTER** goes to the owner as a proposal to show material calls
  only.
* **Otherwise nothing is selected by score.** The table's order already puts
  the highest scores first, and the owner is told the record does not show
  that they are better.
* **The display fixes the owner asked for tonight do not depend on either
  verdict.** They are a clarity change, made for the high-stress morning, and
  are not a claim that any call is more accurate:
  * the conflicting second side column comes out of the email;
  * the releases the model itself calls routine ("no expected impact") get
    their own line rather than a row that looks like a call;
  * a call that contradicts a Top 2 pick on the same name is flagged.

## Not blind, said plainly

* **Known before this registration:**
  * the scoreboard's news desk total (106/208 right, +0.15% a call);
  * the replay's splits above;
  * 11-24's six calls and their results. The 11-24 top two were GIB-A.TO
    (−0.43%) and CM.TO (+0.42%); the rest were JWEL.TO +0.37%, SCR.TO
    −1.01%, DOL.TO (short) +0.28% and TOY.TO −1.50%.
* No other session's confidence or materiality split has been computed.

## Cost

* None: the committed ledger, no API call, no model.

## Amendment 1 (2026-11-24, after the verdict, before any session it covers): the forward look

* **The verdicts were NULL** (`AUDIT_day155b_newsdesk_confidence.md`). H1's top
  two minus the rest was +0.56% a session (t = 1.93). H2's material minus
  routine was +0.75% (t = 2.88). Both were powered for 1.0%.
* **A fresh sample decides.** H1 and H2 are judged again, unchanged, on
  sessions from 2026-11-25 only:
  * the same population rule, the same order, the same machinery, the same
    bar, the same controls and seed 156;
  * the look comes at the 60th new session with a scored FULL-arm call, and
    there is one look;
  * no session up to 2026-11-24 enters it.
* **Why 60.** At the live record's spread, a true 0.75% material edge reaches
  t = 3 with about 80% power near 60 sessions. A true 0.56% top-two edge needs
  about 130 sessions, so H1 may read UNDERPOWERED at the look.
* **What it changes.** A pass goes to the owner as a proposal: show only
  material calls, or mark the top two. Nothing live changes from it.
