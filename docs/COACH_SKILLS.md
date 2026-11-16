# Coaching skills and evidence

Quick chat uses a concise safety and coaching prompt. Optional **Research** loads **Form, safety & listening**, then up to three topic guides relevant to the question and the user's focus. These are versioned application instructions, not a claim that the bot is a certified trainer. They distinguish public-health guidance, research syntheses, individual inference and uncertainty. The app exposes them through **AI coach → Options → Coaching skills**.

| Guide | Scope | Primary reference |
| --- | --- | --- |
| [Form, safety & listening](../src/fitness_tracker/coach_skills/safety.md) | Clear cues, feedback, limits of text-only form advice, pain modifications | [Mayo Clinic weight-training technique](https://www.mayoclinic.org/healthy-lifestyle/fitness/in-depth/weight-training/art-20045842) |
| [Strength & progression](../src/fitness_tracker/coach_skills/strength.md) | Repeatable performance, appropriate load, measurable milestones | [2026 ACSM position stand](https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/) |
| [Cardio & endurance](../src/fitness_tracker/coach_skills/cardio.md) | Aerobic activity, gradual progression, individualized capacity | [WHO physical-activity guidelines](https://www.who.int/europe/publications/i/item/9789240014886) |
| [Full-body routines](../src/fitness_tracker/coach_skills/full_body.md) | Major movement patterns, practical schedules, shorter alternatives | [ACSM evidence review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/) |
| [Muscle priorities](../src/fitness_tracker/coach_skills/muscle_focus.md) | Exercise selection, regional emphasis, overlapping fatigue | [IUSCA hypertrophy position stand](https://journal.iusca.org/index.php/Journal/article/view/81) |
| [Protein & food estimation](../src/fitness_tracker/coach_skills/nutrition.md) | Portion uncertainty, dietary preferences, calculator-based totals | [ISSN protein and exercise position stand](https://pubmed.ncbi.nlm.nih.gov/28642676/) |
| [Supplement literacy](../src/fitness_tracker/coach_skills/supplements.md) | Creatine evidence, product units, limits and interactions | [NIH Office of Dietary Supplements](https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/) |
| [Recovery & accountability](../src/fitness_tracker/coach_skills/recovery.md) | Breaks, sleep, manageable returns, supportive review | [ACSM muscle-recovery guide](https://www.acsm.org/docs/default-source/files-for-resource-library/a-road-map-to-effective-muscle-recovery.pdf) |

Sources were checked on November 10, 2026. These short paraphrased guides are maintained in the repository; they are not automatically rewritten by search results. They are included in the same context budget as tool definitions, user input, journal context and retrieved evidence. A cached guide is labelled separately from freshly retrieved evidence.

With Research enabled, the coach searches before a final response. Normal chat uses one direct generation without web search. It prefers official/primary sources, can search Europe PMC abstracts, and directs users to exercise-library details for optional YouTube tutorials. Web metasearch uses a public, generalized query with names and private numeric journal details removed. If metasearch fails, it tries a live Europe PMC search and labels that fallback; if both fail, the failure is visible. Snippets and abstracts are not equivalent to reading a full paper or assessing evidence quality.

Research arithmetic is requested through a numeric-only AST calculator. Quick-chat meal draft totals are checked locally with the same calculator, without another model call; ordinary conversational estimates remain model estimates. It supports bounded arithmetic and basic numeric functions, without variables, imports, filesystem access or arbitrary code execution. Explicit arithmetic questions cannot finish with an unverified numeric answer if the model ignores the calculator requirement. A model's qualitative advice still requires human judgment.

## Runtime and budget

The optional Research workflow uses LangGraph `StateGraph` nodes, not a label on a fixed single call: model → conditional tool execution → model → finish. It allows four model calls and eight tool observations per turn, with no provider switching. A short quota rejection from either provider may retry once per call after a reported wait of at most 30 seconds; daily/zero-quota errors do not retry. [Provider limits](PROVIDER_LIMITS.md) describes free-tier pacing and local guards. The graph has no entry-writing tool. A final proposal becomes a validated pending SQLite draft; approval remains a separate user action.

Qwen uses a JSON decision envelope for answers, tools and reviewable proposals. The graph executes only the allowed tools and validates proposals separately. Food-draft totals are checked with the local calculator. The default input budget is 5,000 tokens per call; the local transport reserves output space, checks the selected context size and rejects truncated model replies. Token estimates are conservative; Ollama's reported prompt and output counts are also checked.

See [development and setup](DEVELOPMENT.md) for local configuration and [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/quickstart) for the graph library.
