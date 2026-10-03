"""Hand-labelled transcripts for evaluating the pipeline.

Each segment carries an expectation so a run can be scored automatically:

* ``supported``      — well-established and should be confirmed
* ``refuted``        — false; any of false/potentially_false/misleading counts
* ``misleading``     — literally defensible but omits what changes its meaning
* ``context_needed`` — unanswerable as stated (no country, no period)
* ``dropped``        — opinion, prediction or narration that must NOT become a claim

The transcripts are written without punctuation, in the style of YouTube's
auto-generated captions, because that is the input the real pipeline gets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Expectation:
    start: float
    duration: float
    text: str
    expect: str
    note: str = ""


@dataclass
class Script:
    id: str
    title: str
    segments: list[Expectation] = field(default_factory=list)


HEALTH = Script(
    id="evalhealth1",
    title="5 Health Myths You Still Believe",
    segments=[
        Expectation(0, 4, "hey everyone welcome back to the channel today we are busting health myths", "dropped", "narration"),
        Expectation(4, 5, "first up taking vitamin c prevents you from catching the common cold", "refuted",
                    "Reviews find no prevention in the general population"),
        Expectation(9, 4, "the adult human body is about sixty percent water", "supported", "textbook physiology"),
        Expectation(13, 5, "eating sugar makes children hyperactive that is why birthday parties are chaos", "refuted",
                    "Controlled trials repeatedly fail to find the effect"),
        Expectation(18, 4, "honestly i think everyone should just go vegan it is the best choice", "dropped", "opinion"),
        Expectation(22, 5, "and of course we only use ten percent of our brains which is why meditation unlocks the rest", "refuted",
                    "classic neuromyth"),
        Expectation(27, 4, "drinking water is important for staying hydrated", "supported", "trivially true"),
    ],
)


HISTORY = Script(
    id="evalhistory1",
    title="History Facts That Are Actually Wrong",
    segments=[
        Expectation(0, 4, "today we are going through history facts that most people get wrong", "dropped", "narration"),
        Expectation(4, 4, "the berlin wall fell in nineteen eighty nine", "supported", "9 November 1989"),
        Expectation(8, 5, "the great wall of china is visible from the moon with the naked eye", "refuted",
                    "not visible from the Moon"),
        Expectation(13, 5, "mount everest is the highest mountain on earth measured above sea level", "supported",
                    "true with the stated measure"),
        Expectation(18, 5, "napoleon bonaparte was unusually short for his time which is where the complex comes from", "refuted",
                    "about average for a Frenchman of the period"),
        Expectation(23, 5, "i predict that in twenty years nobody will study history in schools anymore", "dropped", "prediction"),
        Expectation(28, 5, "vikings wore horned helmets into battle", "refuted", "19th-century invention"),
    ],
)


SCIENCE = Script(
    id="evalscience1",
    title="Science Facts Explained Simply",
    segments=[
        Expectation(0, 4, "welcome back lets talk about some science", "dropped", "narration"),
        Expectation(4, 5, "light travels at about three hundred thousand kilometres per second in a vacuum", "supported",
                    "299,792 km/s"),
        Expectation(9, 5, "humans and dinosaurs lived at the same time which is where dragon myths come from", "refuted",
                    "66 million years apart"),
        Expectation(14, 5, "carbon dioxide in the atmosphere has risen above four hundred parts per million", "supported",
                    "passed 400 ppm in the 2010s"),
        Expectation(19, 4, "lightning never strikes the same place twice", "refuted", "it frequently does"),
        Expectation(23, 5, "the unemployment rate is currently five percent which is quite low", "context_needed",
                    "no country and no period given"),
        # Labelled supported, not misleading: the pressure qualifier is implied
        # by convention and every reference work states it this way. Demanding
        # it would make the checker pedantic about ordinary simplification.
        Expectation(28, 5, "water boils at one hundred degrees celsius", "supported",
                    "standard simplification, true at sea-level pressure"),
    ],
)


SCRIPTS = [HEALTH, HISTORY, SCIENCE]


# Held-out set, written after the pipeline was tuned on the three above and
# deliberately not used to adjust it. It targets the failure mode that matters
# most: a checker that calls surprising-but-true things false, and waves
# through falsehoods that merely sound sensible.
ADVERSARIAL = Script(
    id="evaladversarial1",
    title="Facts That Sound Fake But Are Real",
    segments=[
        Expectation(0, 4, "right lets get into some facts that sound completely made up", "dropped", "narration"),
        Expectation(4, 6, "oxford university was already teaching students before the aztec empire existed", "supported",
                    "teaching from c.1096, Tenochtitlan founded 1325 — true but sounds absurd"),
        Expectation(10, 6, "cleopatra lived closer in time to the moon landing than to the building of the great pyramid", "supported",
                    "pyramid c.2560 BC, Cleopatra d.30 BC, Apollo 1969 — true"),
        Expectation(16, 5, "bats are completely blind which is why they use echolocation", "refuted",
                    "all bats can see; plausible-sounding falsehood"),
        Expectation(21, 6, "the coriolis effect is what decides which way water spins when your toilet flushes", "refuted",
                    "too small at that scale; very widely believed"),
        Expectation(27, 5, "there are more trees on earth than there are stars in the milky way", "supported",
                    "~3 trillion trees vs ~100-400 billion stars"),
        Expectation(32, 5, "i reckon most of these will get debunked in a few years anyway", "dropped", "prediction"),
    ],
)

SCRIPTS.append(ADVERSARIAL)
