# Pitch — team admini, HackYeah Defence

Everything here is for the speaker, not the slides. Deck:
https://claude.ai/artifact/CzwLzYp9qA8U9B2TW2zmaS

Judging weights, and what each slide is doing about them:

| Criterion | Weight | Where it is earned |
| --- | --- | --- |
| Idea & Innovation | 30% | 5 (citation verification), 6 (rhetorical pass) |
| Relation to Category | 20% | 3 (why this is Defence) |
| Practical Applicability | 20% | 4 (demo), 9 (who pays) |
| Design | 20% | the deck itself, and the extension on screen |
| Completeness | 10% | 7 (measurement), 10 (shipped vs not) |

Design is 20% here, which is unusually high. The deck and the extension UI are
being scored, not just described — so do not apologise for either.

## Before you walk up

- [ ] Backend running, `CACHE_ENABLED=true` in `.env`
- [ ] **Demo video checked once already**, so it replays in ~3s instead of ~2min
- [ ] Extension reloaded, YouTube tab open and paused on the demo video
- [ ] Side panel closed — you want them to watch it open
- [ ] Laptop on the venue network *and* a phone hotspot ready
- [ ] Browser zoom at 125% so the panel is readable from the back

The single biggest risk is a cold run on a conference network. The cache
exists for this. Warm it, then do not clear it.

## The arc — 3 minutes

**0:00–0:10 · Cover.** "We are admini. We built a browser extension that
checks what a YouTube video claims, while you are watching it." Nothing else.

**0:10–0:35 · The gap.** Tell it as a person, not a statistic:

> "Someone watches a twenty-minute video tonight. If one claim in it is false,
> the correction — if it ever comes — lands about two weeks from now, and nine
> times out of ten it never lands at all. By then they have already repeated it
> at work."

Then point at the third card: "We move the check to the moment of exposure."

**0:35–0:55 · Why Defence.** The line that earns 20%:

> "Disinformation is not a content problem, it is a defence problem, because
> the target is a population rather than a system."

One sentence per card. Eye contact, not the screen.

**0:55–2:25 · DEMO.** The longest block. Roughly half your practical score.

1. Click **Check facts**. While it streams: "it is reading the captions,
   pulling out the checkable claims, and going to find sources for each one."
2. Point at markers appearing on the scrubber.
3. Scrub to a red marker. **Let the notice appear and say nothing** — let them
   read it.
4. Open one source link. Then the sentence that matters:
   > "That quoted line is on that page. We checked it was, before we showed
   > you this."
5. If there is time, open the panel and scroll to a rhetorical signal.

If anything stalls: keep talking, scrub to a marker already on the bar, never
apologise for the network.

**2:25–2:45 · Innovation.** Slide 5.

> "Every tool in this space, ours included, is built on a model that can
> fabricate a citation. The difference is that we go and look. If the sentence
> we quote is not on the page we linked, the verdict is downgraded before you
> see it — and that check is string matching, not another model, so it cannot
> be talked out of its answer."

**2:45–2:55 · Honesty.** Slide 7, said as a confession:

> "At one point this called two true statements false. We built the test set
> that catches that. We publish the variance, because the honest number is a
> range — none of the commercial tools publish accuracy at all."

**2:55–3:00 · Close.** Slide 10, then stop.

> "Everything on the left runs today and you just watched it. Everything on the
> right is what we would fix next. We are telling you because a tool that asks
> people to trust it has to go first."

Then silence. Let them ask.

## Things to know, not to say

**We are not first, and a judge may know it.** PopUpFactCheck, Facty,
DeepVerify and Live Fact Checker already do in-video fact-checking. Get in
front of it on slide 8 rather than being corrected. The narrow claim is
defensible: none of them verify that a cited page contains the quoted line,
and none publish an accuracy figure.

**Never claim**: first, only, real-time AI breakthrough, "solves
misinformation". Every one of those is checkable and wrong.

**Numbers you can use, all measured by us:**
- 20–21 of 21 on the labelled set, including a held-out set
- Rhetorical mirror test: 0/0 on neutral political opinion from either side,
  2/2 on the same manipulation from either side
- 8 techniques, 6 evidence sources
- Cache: 14.2s cold → 3.0s warm, identical output
- Signals reach the panel at ~4s; first verdicts at ~13s

**Numbers from research, cite as external:** Community Notes 14-day median,
90%+ never published (Harvard Misinformation Review, 2025).

## Questions you will get

**"How is this different from Community Notes?"**
Timing and traceability. Fourteen days versus now, and every verdict here
points at a line on a page we confirmed contains it.

**"How do you stop it being politically biased?"**
Slide 6, with the mirror test. Then the caveat yourself: constructed examples,
real speech is subtler, we would not overclaim.

**"What if the model hallucinates?"**
It does. That is the premise. Claims are anchored to a verbatim transcript line
or dropped; citations are fetched and string-matched or downgraded.

**"What does it cost to run?"**
Per video, a handful of model calls plus searches. Roughly a few cents for a
twenty-minute video; a local model removes that entirely.

**"Who pays?"**
Freemium for individuals, per-seat for newsrooms and schools, and the DSA /
AI Act reporting duties are the institutional wedge. Say plainly that it is
the wedge you would validate first, not a tested model.

**"Platforms should do this."**
They are going the other way — the European fact-checking network published on
the retreat from those commitments this year. Each step back on the platform
side raises the value of something on the viewer's side.

**"Why should we believe your accuracy?"**
Because we published the failures. Two true claims called false, the cause
found and fixed, and the variance reported as a range.

## The demo video — decided and tested

**https://www.youtube.com/watch?v=x5Ulx1VlnbA**
*Top Supplements for Energy, Detox & Digestion | Nutritional Podcast* — 13.9
min, 12 claims, 6–7 rhetorical signals. Apolitical, not a well-known presenter,
so a wrong call costs nothing on stage.

It was chosen because it makes both branches do visibly different work.

**The facts check out.** The composition of "Par 3", the aloe and senna in
"Bowel Mover", the cleanse tiers — all supported, verified against the
manufacturer's own pages, quotes confirmed. The tool is not flagging
everything.

**The second branch catches what is not said.** Four undisclosed_ad signals,
three of them high severity — a referral code and a discount delivered as
friendly advice:

| Time | Signal |
| --- | --- |
| 2:25 | `potentially_false` — "after 40 you don't produce enough stomach acid" (PubMed) |
| 6:38 | `undisclosed_ad`, high — referral code, commercial tie not disclosed |
| 11:52 | `undisclosed_ad`, high — sale with a discount tied to the presenter |
| 12:04 | `undisclosed_ad`, high — promotion through a personal discount code |

The line that sells the demo:

> "Everything this person says about the products is true — we checked it
> against the manufacturer. What they don't say is that there's a referral
> code. The second pass caught that four times."

That is slide 6's argument — a video can be factually spotless and still be an
operation — with a live example instead of an assertion.

Scrub to **2:25** for the amber claim marker, then **6:38** for the hidden-ad
signal, then open the panel to show the product facts holding up.

### Why not the others

Four candidates were run and rejected, each for a reason worth remembering:

- **Myth-debunking videos** quote falsehoods in order to correct them, so the
  tool argues with the correction. One marked "hair and nails do not grow after
  death" as false — siding with the myth.
- **Videos about their own presenter** produce claims like "he worked at the
  Washington Post": dull and half unverifiable.
- **A liver-cleanse video** worked but left 4 of 11 claims unresolved.

The shape to look for: confident factual claims about the world, dense with
numbers and dates, from someone with an incentive.

### Before the demo

`CACHE_ENABLED=true` is already set and the cache is warm for this video:
59s cold, **8s warm**, identical output. Do not clear it. Without it, two runs
of the same video returned 12 and 8 claims — the retrieval variance is real,
and the cache is what makes the stage behave like the rehearsal.
