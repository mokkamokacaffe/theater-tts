# Architecture notes -- plan de la plomberie

> The code stays explicit and local-first. Pas de magie distribuée, pas de serveur caché.

## Layers

- `app/models`: stable application data; no GUI/API dependencies.
- `app/parsers`: converts source text into structured script segments without mutating source.
- `app/providers`: provider contract and ElevenLabs implementation.
- `app/services`: provider-neutral orchestration (chunking, caching decisions, manifest updates).
- `app/project`: local JSON/filesystem persistence.
- `app/audio`: ffmpeg integration.
- `app/gui`: PySide6 presentation and background workers.

## Provider boundary -- la frontière propre

The app's native representation is `DialogueChunk -> DialogueTurn(speaker, voice_id, text)`.

`ElevenLabsProvider` translates this to the SDK's current `inputs=[{"text": ..., "voice_id": ...}]` request. A future Azure/OpenAI/Google/local provider can implement the same `TTSProvider` methods without changing parser or project files.

## Granularity trade-off -- le compromis, malheureusement

Native Text-to-Dialogue gives conversational context but returns one audio stream per request. Therefore the MVP cache/regeneration unit is a dialogue chunk rather than an independently stitchable line. The provider already exposes single-line generation so a later timeline/override layer can mix regenerated line clips without coupling that feature to ElevenLabs.

## Source preservation -- pas touche à l’original

`ParsedScript.source_text` and `source/original_script.txt` keep the imported/pasted source unchanged. Structured aliases/exclusions are stored separately in `project.json`.
