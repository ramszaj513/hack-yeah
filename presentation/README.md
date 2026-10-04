# presentation — the HackYeah Defence deck

A Beamer deck built on a small custom theme, `admini`, that borrows the
extension's own visual language: dark surface, one blue, and verdict colour used
sparingly. Compiled with pdfLaTeX; no system fonts or `fontspec` are needed.

## Build

```bash
make demo    # theme-demo.pdf   — exercises every theme component
make deck    # main.pdf         — the 10-slide pitch
make notes   # main-notes.pdf   — the same slides with speaker notes
make all
make clean
```

All PDFs land in `build/`. TeX Live is required (`pdflatex`, `latexmk`).

## Layout

```
main.tex                 the deck (loads the theme, inputs sections/)
main-notes.tex           same deck with speaker notes switched on
theme-demo.tex           visual test bed for the theme
theme/
  beamerthemeadmini.sty        loads the four sub-themes
  beamercolorthemeadmini.sty   palette, taken from the extension's CSS
  beamerfontthemeadmini.sty    Roboto + Roboto Mono
  beamerouterthemeadmini.sty   telemetry bar, HUD brackets, scrubber footer
  beamerinnerthemeadmini.sty   claim cards, evidence, callouts, title page
sections/01-cover … 10-close  one file per slide
```

`main.tex` points Beamer at `theme/` with `\def\input@path{{theme/}}`, so
`\usetheme{admini}` resolves without any `TEXINPUTS` fiddling.

## The theme

Palette (from `yt-fact-checker/extension/src/sidepanel/styles.css`):

| token | hex | role |
| --- | --- | --- |
| bg / surface / line | `#0F0F0F` / `#181818` / `#2A2A2A` | surfaces |
| text / muted / faint | `#F1F1F1` / `#AAAAAA` / `#717171` | type hierarchy |
| link | `#3EA6FF` | accent |
| false / doubtful / misleading / supported | `#F05D5D` / `#E5A33D` / `#D9C04A` / `#5FBF8F` | verdict rules |
| signal | `#7C8FB5` | rhetorical pass |

Subtle "defence" framing: a telemetry bar and slide code, thin HUD corner
brackets, and a YouTube-style scrubber along the bottom that doubles as progress.
Body is Roboto; labels, timestamps and tags are Roboto Mono.

### Authoring macros

```tex
\adminikicker{innovation}                     % mono, uppercase, blue label
\adminilead{A short lead sentence.}           % muted lead paragraph
\adminipull{A large pull quote.}              % bold statement
\adminisource{a quiet source / disclaimer}    % small mono line

\begin{claimcard}{false}{02:13}               % verdict key + timestamp
  The claim text.
  \begin{evidence}
    \evidencerow{Publisher}{source type}{quoted span}{yes}  % yes | no | none
  \end{evidence}
\end{claimcard}

\administat{20--21/21}{labelled set}          % a statistic
\adminicallout[adminisupported]{body}         % left-ruled callout
\adminiplaceholder{[ screencast ]}{32mm}      % dashed image frame
```

Verdict keys: `false`, `doubtful`, `misleading`, `supported`, `neutral`,
`signal`.

## Speaker notes

The pitch script from `PITCH.md` is embedded as `\note{}` in each `sections/`
file. `make notes` renders them; `make deck` omits them.

## Assets

`04-demo`, and the measured numbers on `07-measurement`, use placeholders and
figures from `PITCH.md`. Replace the demo frame's `\adminiplaceholder` with a
real screenshot (drop the image into `assets/` and use
`\includegraphics[width=\linewidth]{…}`) once the extension UI is captured.
