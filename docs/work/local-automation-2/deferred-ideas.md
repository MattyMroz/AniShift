# Deferred subtitle and translation ideas

Status: **DEFERRED — NOT AN IMPLEMENTATION PLAN**
Decision date: 2026-09-22
Authority: the user's explicit scope decision during acquisition research.

## Current priority

Focus on finding titles, choosing releases and episodes, downloading, and following ongoing series. Reduce maintained application code by assigning suitable responsibilities to existing tools. AniShift does not need to implement every step or own every interface; the complete user workflow matters more than preserving the current architecture.

For this iteration, the user considers the existing MKV processing workflow sufficient. This is a scope decision, not a claim that every processing scenario or P18 acceptance check has passed. TXT-to-audio behavior remains unverified and is not expanded here.

Preserve three user journeys when assessing acquisition tools:

- Local input: a file placed in a watched task folder enters its configured automatic processing flow.
- One-time acquisition: select available episodes, download them, observe progress, and automatically process them into library results.
- Subscription: choose existing episodes to acquire now and follow subsequent releases of an ongoing series without repeated intervention. For example, skip watched episodes 1–2, acquire available episode 3, and follow episode 4 onward.

Release-group selection, quality criteria, and fallback behavior remain unresolved research questions. Do not treat a fixed-group, automatic-ranking, or fallback policy as approved. The earlier workstream documents describe the previous design; they do not settle these reopened choices.

The three topics below are optional future directions. They are deferred, not rejected or promised. Reopening one requires a new user decision; none blocks acquisition work.

## 1. Published Polish subtitles and later updates

**Idea:** discover Polish subtitle releases or corrections announced by translation groups, including Discord release channels, and obtain their actual subtitle files. Lycoris was a concrete example with separate video and Polish-subtitle links.

Potential outcomes:

- Use suitable existing Polish dialogue subtitles instead of translating another language.
- Optionally prepare an improved result when a preferred Polish translation appears later.

Still unresolved:

- Whether announcements, a public website, or another supported interface should be the source.
- Access permissions, release/revision detection, matching episodes and video versions, and subtitle completeness.
- Whether to wait for Polish subtitles or generate an initial result and update it later.
- Whether updates replace only displayed subtitles or regenerate TTS and final media; changing subtitle text alone does not update recorded narration.
- Ownership of manual edits and safe replacement of existing results.

Reason deferred: a separate integration and update lifecycle would distract from acquisition and add maintenance responsibilities. Endpoint research was stopped; automation feasibility was not established.

## 2. Multiple subtitle languages as translation context

**Idea:** use an available primary dialogue track with additional language tracks as context for Polish translation, particularly speaker/addressee gender and ambiguous wording. This is contextual interpretation, not averaging translations or voting on endings.

Evidence from a small exploratory sample:

- Twenty ASS files were collected for the first episodes of Frieren and Shoushimin Series, comparing Erai-raws and SubsPlease releases.
- Each sampled Erai release provided nine tracks: English, Brazilian Portuguese, two Spanish variants, Arabic, French, German, Italian, and Russian. Polish was absent from these releases.
- Other languages provided concrete gender cues absent from English.
- Tracks differed in timing, segmentation, and screen-text events. Matching by line number is invalid; overlapping ASS layers can repeat text for visual effects.
- English subtitle events matched between the two release groups for each sampled episode; different group labels did not provide independent translations in these cases.

The samples support investigating the idea, not claiming better final Polish output or ranking release groups. No translation-quality benchmark, original-audio check, or rendered typesetting comparison was performed. Alignment metrics measured timing proximity, not semantic equivalence.

Research artifacts were saved outside the repository at `C:\Users\MATTYM~1\AppData\Local\Temp\opencode\subtitle-research-20260921-a7c4\` (`manifest.json`, ASS samples, `measurements.json`, and contexts). These are temporary evidence, not durable project dependencies; verify their existence before reuse.

Reason deferred: the quality gain is unmeasured, while additional context, alignment, and processing introduce cost and complexity. No multilingual alignment mechanism is approved.

## 3. Professional subtitling, typesetting, and song presentation

**Idea:** study how people prepare subtitles and reuse suitable open-source subtitle tools for the parts that benefit AniShift. Possible outcomes include polished Polish song translations, colored/styled song subtitles, and improved handling of signs and other on-screen text. Karaoke-style timing is a possible interpretation to clarify, not an agreed requirement.

Possible context sources include video, audio, screenshots, and existing speaker labels. They are research hypotheses, not selected mechanisms. A visible character is not necessarily the speaker, and no multimodal workflow has been validated.

Relevant findings to retain:

- Display timing, reading speed, subtitle segmentation, and spoken TTS duration are distinct concerns.
- Netflix's public guidance allows language-specific timing/segmentation adjustments and describes annotated translation templates carrying contextual information. Ordinary audience-facing English subtitles need not contain those annotations.
- ASS styling and positioning establish the presence of typesetting, not its visual quality or translation fidelity.
- No verified Netflix EN/PL episode pair was obtained. The Netflix findings concern delivery guidance, not measurements of actual paired tracks.

Reference starting points:

- [Netflix Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide)
- [Netflix Subtitle Timing Guidelines](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360051554394-Timed-Text-Style-Guide-Subtitle-Timing-Guidelines)
- [Netflix Subtitle Templates](https://partnerhelp.netflixstudios.com/hc/en-us/articles/219375728-Timed-Text-Style-Guide-Subtitle-Templates)

Reason deferred: this is a separate product-quality workstream. Do not introduce automatic retiming, song styling, visual speaker identification, or a new subtitle editor integration during acquisition work. No tool has been selected and no implementation schedule is committed.
