# anishift/tui

Textual presentation layer over `anishift.application.service.AppService`.

## Boundaries

- Keep product selection and validation in `application/`; screens only edit drafts and render application contracts.
- Call providers and filesystem workflows only through `AppService`. Never import concrete services here.
- Run blocking application work in a Textual thread worker. Only the UI timer drains `EventBuffer` and touches widgets.
- Keep the `CommandBar` and `StatusFooter` present on every main screen, including the small-terminal fallback.

## Verification

- Exercise interactions through Textual Pilot tests under `tests/tui/`; do not test widget internals by calling handlers directly.
