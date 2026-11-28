# AI-Powered Workflow Story: DraftMind AI

DraftMind is a draft room for League of Legends coaches, built on the official GRID hackathon data with Cloud9 Kia as the default team. This page explains how AI and JetBrains tools were used to build it: which tool did what, and where the evidence is. Every claim below can be checked in the repository and its commit history.

## Who did what

| Tool | Role in the build | Evidence |
|---|---|---|
| **Claude Code** (Anthropic's coding agent) | Wrote most of the code from our instructions, including the backend, the frontend, the GRID data adapter, the model fitting, and the deployment. It also ran the tests and checked the app in a browser. We set the direction, reviewed the work, and made the calls on product, data licensing and hosting. | Commits carry `Co-Authored-By: Claude` |
| **Junie** (in PyCharm) | Wrote one API test from our prompt and ran the suite. | `test_dashboard_ban_plan` in [`backend/tests/test_api.py`](backend/tests/test_api.py), commit *"Add dashboard ban-plan test (written by Junie)"* |
| **PyCharm** | Project setup: the Python interpreter, the pytest runner, and shared run configurations for the API, tests and UI. Also the place where Junie ran. | [`.idea/`](.idea), [`.run/`](.run) |
| **Qodana** | Static analysis of the backend. It found 22 problems, 4 of them high severity; all 4 are fixed. | [`qodana.yaml`](qodana.yaml), commit *"Fix Qodana findings in the backend"* |
| **HTTP Client** | 11 API checks with assertions, run against the deployed API (11/11 passed). | [`http/api.http`](http/api.http) |

We want to be upfront: a general-purpose coding agent did most of the coding. The JetBrains tools did the quality and verification work, plus one Junie-written test. If we did it again, we would run the agent work inside the IDE through **JetBrains Air**, so that the coding and the review happen in one place.

## Junie in PyCharm

We opened the repository in PyCharm and gave Junie this prompt:

> Add a pytest test in backend/tests/test_api.py that checks /api/dashboard?our=NMB&opp=IWF returns a ban_plan with at most 5 entries, and that each entry has a non-empty "champion" field. Follow the style of the existing tests (use the existing `client` fixture). Then run the backend tests.

Junie read the existing tests and reused the `client` fixture. It added a six-line test and ran the suite, which went from 30 to 31 passing tests. We accepted the diff.

## Qodana and the HTTP Client: quality checks

- **Qodana** (`qodana-python-community:2025.3`) flagged two kinds of high-severity problem. First, `datetime.utcnow()` is deprecated and slated for removal; we switched to timezone-aware `datetime.now(timezone.utc)` in two places. Second, `set([...])` calls should be set literals. In the same pass we narrowed a bare `except Exception` in the backtest to `DraftError`, so real errors are no longer swallowed. We then re-ran the scan: no high-severity problems remain.
- **HTTP Client.** `http/api.http` runs a full coaching flow: create a Bo3 fearless series, start a game, read the ranked suggestions, lock in the top pick, undo it, and clean up. Each step has assertions. It has `local` and `prod` environments. For the password-protected demo, it reads the password from a git-ignored private env file. We used it as the smoke test for the deployed API.

## Where AI changed the outcome

**1. Reading raw GRID feeds.** The data comes as compressed event streams, up to about 1 GB per match uncompressed. The agent sampled one Cloud9 match and found the `team-banned/picked-character` events that give the exact draft order. It then wrote an adapter that streams all 745 series in about 45 seconds.

GRID has no player roles, so roles are inferred from champion fit plus each player's usual role. The result for Cloud9 Kia is Thanatos top, Blaber jungle, Loki mid, Tactical bot and Vulcan support. The first run crashed on players who switched teams, or played two roles, mid-season. The agent traced that to the data and fixed the roster logic.

**2. Finding the First Selection rule in the data.** While checking drafts, the agent noticed that in 237 games the red side drafted first. That is the 2026 First Selection rule, where a team takes either a side or the first draft turn. It would have broken our draft engine, which assumed blue always goes first. The rule became a feature instead. Across the 439 First Selection games, blue side wins 54% and the team drafting first wins 51%. So for Cloud9 against Team Liquid the advice is "take blue side" (about 62% expected, even after Team Liquid's best reply).

**3. Being honest about model quality.** On the real data, the first backtest showed our hand-tuned opponent model was no better than a meta-only baseline. Instead of tuning against the test set:

- We changed the evaluation to walk-forward, which matches what a coach knows on match day.
- We added new signals, such as presence over the last 80 games and the role a team usually fills with its n-th pick.
- We fitted the weights by conditional logit on an earlier slice of games.

On 420 untouched games, pick top-5 accuracy went from 33.5% to **40.6%** and ban top-5 from 34.9% to **48.5%**. The meta-only baseline scores 32.7% and 34.5%.

The live win-probability model got the same treatment, with a negative result. Draft features added nothing measurable over team strength (Elo) and side: 63.6% correct either way. We shipped it with that statement on screen rather than show draft "impacts" that are really noise.

**4. Working within the data license.** The GRID data may only be used for the hackathon, never redistributed, and shown only to judges and organizers. We handled that in four ways:

- The data lives outside the repo, and it is git-ignored. Staged files are checked before every commit.
- The hosted demo sits behind a password, which Render generates; neither we nor the agent typed it.
- The server deletes the raw feeds after building its cache.
- We turned off model training on our inputs in Claude's privacy settings, as the license requires, and we confirmed the hosting approach with the organizers before switching the data on.

## Takeaways

- An agent that can run code, read data and drive a browser is most valuable for **discovery**. Two examples: the First Selection drafts, and the roster bug that a quick read of the data would have missed.
- AI speeds up building, and it speeds up fooling yourself just as much. Walk-forward evaluation, a baseline next to every number, and stating negative results kept the product honest.
- The JetBrains tools were our checks on the AI's work: static analysis, repeatable API tests, and an IDE agent for focused, reviewable changes.
