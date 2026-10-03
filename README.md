# hack-yeah

HackYeah 2026 project repository.

## yt-fact-checker

A Chrome/Chromium extension that checks factual claims made in YouTube videos. It reads the video's captions, pulls out the checkable claims, gathers evidence from the open web, Wikipedia and the academic literature, decides each claim against that evidence, and then fetches every cited page to confirm the quoted passage is actually on it.

- **[SETUP.md](./SETUP.md)** — getting it running on a new machine
- **[yt-fact-checker/README.md](./yt-fact-checker/README.md)** — how the pipeline works and why each stage exists
- **[verifier_script.py](./verifier_script.py)** — command-line check for a single video

```bash
git clone git@github.com:ramszaj513/hack-yeah.git && cd hack-yeah
# then follow SETUP.md
```

Needs Python 3.11+, Node 18+, and an OpenAI API key.
