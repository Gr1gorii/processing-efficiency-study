---
layout: default
---

{% capture readme %}{% include_relative README.it.md %}{% endcapture %}
{{ readme | replace: "](README.md)", "](index.html)" | replace: "](docs/IMPLEMENTATION_ADDENDUM.md)", "](https://github.com/Gr1gorii/processing-efficiency-study/blob/main/docs/IMPLEMENTATION_ADDENDUM.md)" | replace: "](docs/METHODOLOGY.md)", "](https://github.com/Gr1gorii/processing-efficiency-study/blob/main/docs/METHODOLOGY.md)" | replace: "](docs/PILOT_DECISION.md)", "](https://github.com/Gr1gorii/processing-efficiency-study/blob/main/docs/PILOT_DECISION.md)" | replace: "](docs/PUBLIC_DATA.md)", "](https://github.com/Gr1gorii/processing-efficiency-study/blob/main/docs/PUBLIC_DATA.md)" | replace: "](docs/RUN_YOUR_OWN.md)", "](https://github.com/Gr1gorii/processing-efficiency-study/blob/main/docs/RUN_YOUR_OWN.md)" }}
