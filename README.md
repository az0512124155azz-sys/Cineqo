# Cineqo

Cineqo is an open-source-first AI music-video creation platform.

## Current phase

Phase 1 only: establish the vetted open-source foundation and automated source-import workflow.

No production UI, authentication, Google integration, email integration, or deployed backend is being added in this phase.

## Product boundary

Cineqo does **not** generate songs. Artists provide their own music. Cineqo is intended to research the artist, help plan the creative concept, generate and edit music-video visuals, synchronize visible singing, and export a finished music video with the supplied song.

## Open-source policy

Every AI component accepted into Cineqo must pass a license review. Preference is given to OSI-style permissive licenses such as Apache-2.0 and MIT. Components with non-commercial, territory-restricted, hosted-service-restricted, or otherwise custom restrictive model licenses are excluded from the approved set.

Model weights are not committed to this Git repository. Large checkpoints will be downloaded later by explicit deployment/runtime scripts from their official upstream source after their licenses are verified.

## Repository layout

- `third_party/` - imported upstream source code only
- `open_source/manifest.json` - approved components and pinned upstream references
- `scripts/` - source import and verification helpers
- `.github/workflows/` - GitHub Actions automation
- `docs/licenses/` - license review notes and provenance

## Initial approved candidates

- Wan 2.2 - video generation - Apache-2.0
- MuseTalk - lip synchronization - MIT code license
- Whisper - speech recognition/transcription - MIT
- Mistral Small 4 - director/research/planning model - Apache-2.0 (weights remain external)
- FFmpeg - media processing; source is mainly LGPL with optional GPL components. Cineqo will treat FFmpeg as an external system dependency instead of vendoring it into the application source until the final distribution strategy is defined.

## Explicitly excluded for now

- HunyuanVideo - excluded because its model license is a custom community license with territorial restrictions and does not meet Cineqo's current "100% open-source" policy.
- FLUX.1 dev-family models - excluded because their model licenses include non-commercial restrictions. Only clearly permissive variants can be reconsidered later.

## Next milestone

After the open-source foundation is imported and verified, Cineqo will move to a standalone HTML design prototype. The real application will only be wired after the design is approved.
