# PRE-REGISTRATION — day-78: two tests of a different KIND

**Written and committed BEFORE either result is computed.**

Thirty-seven rejections stand behind this, and every one of them tested a
function of price history predicting price. Both tests below deliberately do
not: one tests BEHAVIOUR (insiders buying with their own money), the other
tests CONDITIONING (does a sponsor's own history change its rejection rate).

---

## TEST A — does insider open-market buying precede FDA outcomes?

### The premise

Company insiders are the only people with genuine private information about a
drug under review. A Form 4 transaction code **P** — an officer or director
buying on the open market at a real price — is the most expensive signal a
person can send, because they pay for it. Awards (code A, price $0) and option
exercises (code M) carry no such commitment and are excluded.

### The data, confirmed available before writing this

SEC bulk "Insider Transactions Data Sets", one ZIP per quarter, free:
`NONDERIV_TRANS.tsv` gives TRANS_CODE / TRANS_DATE / TRANS_SHARES /
TRANS_PRICEPERSHARE; `SUBMISSION.tsv` gives ISSUERCIK and **FILING_DATE**.
2025Q1 alone contains 5,681 code-P transactions.

### The look-ahead trap, closed by construction

A Form 4 is filed up to **two business days after** the trade. The transaction
date is therefore NOT public when it happens. **This test uses FILING_DATE
only.** Using TRANS_DATE would credit a trader with information nobody had, and
would be the single easiest way to manufacture a false positive here.

### The signal

For each FDA decision event, sum the dollar value (shares x price) of code-P
purchases whose **FILING_DATE** falls in the 90 calendar days strictly before
the event's own filing date. Scale by market cap where available; report raw
dollars where not.

### The two questions, tested separately

- **A1 OUTCOME:** does insider buying precede APPROVALS more than REJECTIONS?
  Measured as AUC of buy-dollars against the outcome label.
- **A2 RETURN:** does insider buying predict the event-window return
  (close t-2 -> close t+1), the same window as day-77?

### Bar, fixed now

ADOPT only if ALL of:
- the effect clears **|t| >= 3.0** (A2) or **AUC z >= 3.0** (A1), event-clustered;
- a **positive control** detects a planted effect of the size claimed;
- a **placebo** — the same 90-day window ending at a RANDOM date on the same
  tickers — shows nothing.

Two questions are asked, so the bar rises to **|z| >= 3.3** for either to count.

REJECT otherwise. UNDERPOWERED is a distinct third outcome, declared when the
minimum detectable effect exceeds what would be tradeable.

### Biases named in advance

- **Rarity.** Insider buying is uncommon in small-cap biotech. If most events
  have zero P-buying the test is about a small subsample and will likely be
  underpowered. That is a real possible outcome, not a failure to report.
- **Reverse causality.** A company whose stock has already collapsed is where
  insiders buy. Any effect may be a value/reversal signal wearing an insider
  costume. Control for the prior 90-day return.
- **Survivorship.** Same as always: names that delist lose price history.

---

## TEST B — is the base rate conditional on the sponsor's own history?

### The premise

Every rate this repo prints is labelled UNCONDITIONAL, which is honest and is
also its largest weakness. The harvest already contains what is needed to
condition one of them: whether the same sponsor has been rejected before.

### The signal

For each decision in the harvest, look ONLY at that sponsor's strictly earlier
decisions. Compute:

    P(CRL | the sponsor has a prior CRL)   vs   P(CRL | no prior CRL)

### Bar, fixed now

This is a descriptive conditional rate, not a trading rule, so the bar is
different and lower: **report it with Wilson intervals, and adopt it into the
report only if the two intervals do not overlap.** Overlapping intervals means
the conditioning adds nothing and the unconditional rate stands.

### Biases named in advance

- **Survivorship, and it runs one way.** A sponsor rejected once may never file
  again, so "has a prior CRL" over-selects companies that survived a rejection.
  This biases the conditional rate DOWN relative to truth.
- **Look-ahead:** only strictly-earlier events may be used. A sponsor's later
  rejections must not inform its earlier ones.
- **n will be small** on the prior-CRL arm. Report it and let the interval
  speak.

---

## What each outcome changes in the morning report

| result | change to `brief.py` |
|---|---|
| A adopted | a new INSIDER line per catalyst name, with the measured effect and its bar |
| A rejected | nothing ships; rejection #38 recorded |
| B adopted | `screen.py` uses the conditional rate for names with a prior CRL, and says which rate it used |
| B rejected | the unconditional rate stands, and the report says the conditioning was tested and added nothing |
