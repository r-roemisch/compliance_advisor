# Query Translation searches every question in the Corpus's other language too

Before the search, one short model call translates the question into the Corpus's other language, English for a German question and German for an English one, in the terms the regulations use there. Both are searched with the chosen Search Strategy, and their rankings are merged by reciprocal rank fusion. The Corpus keeps every Source in its official language (ADR 0002), and the evaluation showed the price: a question finds an expected Provision in 93 % of cases when it shares the Source's language and in 73 % when it does not, the weakest kind of question on the Golden Set. The translation only steers the search. The Answer Model still answers the question as asked, and the translated query is kept in the Answer Trace. It runs on GPT-6 Luna, like the screening, and on the chosen model itself when that model is EU-hosted, so a question meant for an EU provider never reaches another one (ADR 0007). If the call fails, the question is searched alone. Decided on 2026-10-30, after review feedback asked for query translation.

## Considered Options

- **Multi-query rewriting** (several paraphrases in the question's language): helps vague questions, but stays in one language, where the search already does well.
- **HyDE** (searching with a drafted answer): the draft comes from the model's memory, so a plausible but wrong draft steers the search to the wrong Provision, and it costs a long model call per question.
- **Indexing translations of the Sources**: rejected in ADR 0002; unofficial translations lag behind amendments and are not what a supervisor cites.
- **Translating only when the question names a Source in the other language**: cheaper, but most cross-lingual questions name no Source ("When must a major ICT incident be reported?").

## Consequences

Every question costs one more short model call: in the first trials on 2026-10-30 the translation took about 2.5 seconds, and a whole question on GPT-6 Luna, screening and translation included, cost less than $0.002. In the first of them, a German question on reporting deadlines for major ICT incidents, the English translation brought in the article of the reporting standard that sets the deadlines, which the German question alone had left out of the six Passages. Vector search now merges two rankings, which can move a Passage in the question's own language down a place; the evaluation's `translated` set-up measures the gain on cross-lingual questions against any loss on same-language ones, and `QUERY_TRANSLATION=false` switches the translation off.
