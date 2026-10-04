# Verifact — business model

A reference one-pager behind the deck's *Business model: subscription* and
*The wedge* slides.

## Value proposition

Verifact checks factual claims at the moment of exposure and shows the evidence
behind every verdict. Each verdict is traceable to a line on a page the tool has
confirmed contains it. It also checks selected text anywhere, and reads the
nature and tone of the speech beside whether its facts are right.

That traceability is the product. It is what a viewer needs to trust a verdict,
and it is what an institution needs to prove one.

## Model: subscription

One product, three subscription tiers.

| Tier | Who | Billing | What the subscription includes |
| --- | --- | --- | --- |
| Personal | Viewers | Monthly / annual | Unlimited checking, saved history, private local mode |
| Team | Newsrooms & schools | Per seat, monthly / annual | Shared, traceable, exportable checks; admin |
| Institution | Regulators, compliance teams | Annual enterprise | Audit-grade check logs, API, DSA / AI Act reporting |

**Why subscription.** Checking is a recurring need, not a one-off purchase:
every new video, article and claim is another reason to keep the tool. Recurring
revenue also smooths the variable cost of retrieval, and a buyer running a local
model raises the gross margin toward software levels. Price is anchored to the
cost of a human verification hour, not to model tokens.

**Why these tiers.** The personal tier is the wedge for adoption; teams pay
because a check in a newsroom or classroom has to be defensible; institutions
pay for the audit artifact, not the chat feature. The free trial is the on-ramp
and converts on the first video a user actually checks.

## Cost structure

- **Variable:** a handful of model calls plus searches per check — a few cents
  for a twenty-minute video.
- **Removable:** a buyer can run a local model, which drives marginal cost to
  near zero and keeps their data on their side.
- **Fixed:** backend hosting and retrieval integrations.

## Go-to-market

1. **Wedge:** the compliance/reporting duty (DSA, AI Act) — institutional
   willingness to pay, validated first.
2. **Design partners:** newsrooms and schools, where traceability already
   matters, give credibility and product feedback.
3. **Distribution:** a free trial converts on the first video checked; the paid
   tiers sit behind it.

## Defensibility

- Citation verification: every quote is fetched and string-matched, so a
  fabricated citation is downgraded before it is shown.
- An auditable check log that a consumer fact-checker does not produce — and
  what a subscription renews on.
- Uncertainty is surfaced honestly: *unverified* is split by reason, so "nobody
  has published on this" is never confused with "a provider timed out".

## Honesty / risks

- **Not a tested market.** Say plainly that the institutional wedge is the thing
  we would validate first.
- **Platform retreat.** European platforms are stepping back from some
  fact-checking commitments; each step back raises the value of a viewer-side
  tool.
- **Accuracy liability.** The tool is a decision aid; sources are always shown,
  and failures are published rather than hidden.
- **Retrieval reliability.** Results move between runs because open-web
  retrieval returns different sources; the cache steadies demos and costs.
