# Data sources and provider behavior

## Exercise catalog

The catalog and photos are from [Free Exercise DB](https://github.com/yuhonas/free-exercise-db), which publishes its dataset under the [Unlicense](EXERCISE_DATA_LICENSE). The original repository credits [wrkout/exercises.json](https://github.com/wrkout/exercises.json). Retrieved November 9, 2026, from upstream commit `f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5`. Rebuild with `python3 scripts/refresh_exercises.py` (requires Pillow).

The upstream snapshot had 876 records. Three kettlebell records did not contain any image paths; this release excludes those records so every one of the **873** included exercises has a real photograph. The first photo for each movement is resized to at most 280 × 210 and encoded as WebP. Names, muscle groups, equipment, and instructions remain upstream data. The thumbnails and catalog are bundled; opening an exercise does not send a request to GitHub. Photos are movement references, not a substitute for individual technique assessment.

## Local Qwen coach

The coach runs an installed Qwen model through [Ollama](https://ollama.com/), at a loopback address on the user's computer. Qwen3 8B is the default. Remote models and non-loopback addresses are rejected. There are no hosted-model integrations, API keys or provider fallbacks.

Qwen returns structured proposals that the app validates independently. Workout quantities are grounded in the user's source notes, with batches of at most five movements. Ambiguous details remain visible in a partial preview. Meal estimates show assumptions and remain editable. Approval is an application action; the model cannot save a journal record by claiming it did so.

## Research

[Europe PMC REST API](https://europepmc.org/RestfulWebService) supplies at most five titles and abstracts per request. The query is visible in the manual research field or selected by the coach for a general training topic. Abstract text is stripped of HTML and bounded before being sent to the local Qwen model. Only exact retrieved source URLs are accepted in the structured citation field. The prose is still generated content and should be assessed alongside the source links. Retrieved does not mean high-quality, relevant, replicated, or causal.

A failed lookup is shown as unavailable. The coach is instructed to acknowledge missing evidence rather than claim it completed a search. No private journal contents should be included in public research queries; the prompt instructs the model to use general topics.

## YouTube

Exercise details provide an ordinary outbound YouTube search link using the catalog exercise name plus “exercise proper form tutorial”. Links open in a new tab only when selected. There is no YouTube API setup, API request, embedded player, remote thumbnail loading, or coach video search. The custom pull-up retains the user-supplied direct reference link. Legacy API credentials are removed from the local settings file.

## Additional exercise variations

`src/fitness_tracker/custom_exercises.json` extends the 873 upstream exercises without changing the upstream snapshot. The library currently has 874 entries. These additions survive rerunning the upstream refresh script.

**Wide-Grip Neutral Pull-Up** is also searchable as wide parallel-grip, wide V-bar, and semi-neutral/semi-supinated pull-up. The metadata describes the wider hand spacing requested by the user; general neutral/parallel-grip terminology is supported by [Pullup & Dip](https://www.pullup-dip.com/blogs/training-camp/pull-up-grip-position) and [REP Fitness](https://repfitness.com/blogs/training/11-different-hand-positions-on-the-pull-up-bar-and-the-muscle-groups-they-target). The user's [reference video](https://www.youtube.com/shorts/AVrTxMEgSBE) is linked in the exercise detail.

Its bundled photo reuses the public-domain `V-Bar_Pullup` image. The interface explicitly labels it as a reference photo of a narrower neutral grip, rather than representing it as the exact wide-grip movement. No third-party blog or YouTube image is redistributed.

## Training-group overlay

`src/fitness_tracker/anatomy.py` supplies the app's high-level body parts and detailed movement labels without rewriting the upstream dataset. At the user's request, the five reverse-curl variations use Forearms as their primary tally and retain Biceps as assisting. This is a training-focus classification, not a claim that other muscles are inactive or a measured ranking of activation. [Bowflex's exercise manual](https://download.bowflex.com/supportdocs/OM/Bowflex/BFX_Power_Pro_OM_web.pdf) describes forearm and upper-arm involvement in reverse curls.

## Coaching skills, web search and calculator

Eight versioned guides link to ACSM, WHO, ISSN/IUSCA, NIH and technique/recovery resources. [The skill index](COACH_SKILLS.md) records the sources, review date, scope and inference limits. Every research-mode coach turn attempts a generalized public web query using DDGS/Bing; official and primary sources are prioritized. If metasearch is unavailable, live Europe PMC search is labelled as a fallback. Query terms are restricted to general fitness vocabulary to avoid forwarding private names or numeric journal details. Both search failures and cached guide citations are labelled. The calculator evaluates a restricted numeric AST and cannot run Python code or access files.

## Food estimate references

The current app accepts typed coaching messages only.

The direct logging prompt includes a rough large-egg protein reference from [USDA FSIS](https://ask.fsis.usda.gov/article/What-is-the-cholesterol-content-of-eggs) (about 6.3 g per large whole egg). Actual product labels and portions take precedence; estimates are not measured nutrition.

## Body-map illustration

The front/back anatomy SVG is drawn in this project; it does not embed or copy the supplied reference image. Its group highlights use the existing exercise catalog classifications. The relative shading is a local visualization convention implemented in the app, not measured muscle activation.
