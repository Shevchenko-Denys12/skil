# Stage 2 checks of the three example topics

Checked against the live Wikipedia Action API on 2026-09-27. These checks verify article resolution only; no Pageviews were fetched. Article coverage and interlanguage links can change, so rerun before an analysis.

| Example | Requested editions and assumption | Verified result | Next step |
| --- | --- | --- | --- |
| Intermittent fasting | `pl`, `cs`; English article `Intermittent fasting` used as seed | [Czech `Přerušovaný půst`](https://cs.wikipedia.org/wiki/Přerušovaný_půst) is linked and selected. No Polish interlanguage link was returned. The guessed Polish title `Post przerywany` was checked separately and did not exist as an article. | Ask for a specific Polish Wikipedia page or state that this two-language comparison cannot yet proceed. |
| Astronomy | `uk`; explicit topic `Астрономія` | [Ukrainian `Астрономія`](https://uk.wikipedia.org/wiki/Астрономія) exists as a non-disambiguation article and was selected. | User can review the page before Pageviews fetch is implemented. |
| Learning English | Assumed `pl`, `cs`, `uk` because the original example leaves languages open; English article `English as a second or foreign language` used as seed | That English article had no matching interlanguage links for the chosen editions. The resolver returned no selected equivalent pages. A separate Polish phrase search suggested articles about English grammar, which the resolver left unconfirmed because grammar is narrower than learning English. | Ask which language editions and which precise article concept the user wants; accept explicit page overrides only after review. |

The results show why the resolver never treats a keyword match as proof of equivalent topics. The third example also requires user-selected languages before a real comparison.
