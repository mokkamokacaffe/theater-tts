# Theater TTS

Theater TTS is a local Python desktop application for turning multi-speaker theater/dialogue scripts into generated audio with ElevenLabs. It keeps the script, cast mapping, generated files, cache, and manifest on your computer. Tout reste local: pas de serveur, pas de compte, pas de bazar.

This repository is an incremental MVP. It already includes script parsing, recurring cast assignments, native ElevenLabs Text-to-Dialogue generation, provider-aware chunking, deterministic caching, resumable generation, project save/load, voice previews, cancellation between API calls, and full-play ffmpeg concatenation.


## Current ElevenLabs integration

The integration was checked against the current ElevenLabs documentation on 2026-09-25 and the stable Python SDK 2.x line.

The application uses:

- `ElevenLabs(api_key=...)`
- `client.voices.search(...)` for the current v2 voice list
- `client.text_to_dialogue.with_raw_response.convert(...)` for native multi-speaker dialogue
- `client.text_to_speech.with_raw_response.convert(...)` as the provider-level single-line primitive

Provider-specific constraints are isolated in `app/providers/elevenlabs_provider.py`. The current Text-to-Dialogue API recommends keeping all input text at or below 2,000 characters per request and currently allows up to 10 unique voice IDs in one dialogue request. Theater TTS automatically splits around those limits.

Official references:

- https://elevenlabs.io/docs/eleven-api/guides/cookbooks/text-to-dialogue
- https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert
- https://elevenlabs.io/docs/api-reference/voices/search
- https://github.com/elevenlabs/elevenlabs-python

## Requirements

- Python 3.11+
- Windows, macOS, or Linux with a PySide6-supported desktop environment
- An ElevenLabs API key for voice loading/generation
- Internet access for ElevenLabs API requests
- Optional: `ffmpeg` on `PATH` for full-play export

Python 3.13 is supported by current PySide6 releases. The code itself avoids Python-version-specific features beyond Python 3.11.

## Install, sans usine à gaz

Create and activate a virtual environment:

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configure the ElevenLabs key

Preferred: copy `.env.example` to `.env` and fill in the key:

```text
ELEVENLABS_API_KEY=your_key_here
```

`.env` is ignored by Git. The API key is never written to `project.json`.

You can also leave the environment variable unset and enter the key in the GUI for the current run. The GUI field is not saved with the project.

## Run

```bash
python main.py
```

## Basic workflow, tout simplement

1. Open or paste a script.
2. Click **Parse Script**.
3. Click **Load Voices**.
4. Assign one ElevenLabs voice to every character you want generated.
5. Pick how stage directions should behave.
6. Choose a project folder and save the project.
7. Click **Generate** and review the preflight summary.
8. Re-run generation after edits: unchanged chunks come from cache.
9. Click **Export Full Play** if ffmpeg is installed.

The preflight shows chunk count, total text characters, cached chunks, and how many chunks actually require ElevenLabs API calls. The app deliberately does not invent a money estimate because pricing depends on the user's current ElevenLabs plan/model.

## Supported plain-text script forms

The MVP parser recognizes common forms including:

```text
ROMEO:
Where are you?

JULIET: I'm here.


JULIET
I'm here.
```

It recognizes `ACT ...` and `SCENE ...` headings, preserves the original source text, records source line ranges, and parses leading performance directions such as:

```text
ALICE:
[whispering] Did you hear that?
```

or:

```text
ALICE: (whispering) Did you hear that?
```

The parser is intentionally conservative. It is implemented behind `ScriptParser`, so FDX, DOCX, PDF, screenplay formats, or project-specific parsers can be added later without changing the GUI/provider layers.

## Stage-direction modes

**Performance instructions** converts a leading direction into an Eleven v3 audio tag, e.g. `(whispering)` becomes `[whispering]`, while standalone theatrical directions are not spoken.

**Do not speak stage directions** omits stage directions from generated input.

**Narrate stage directions** turns stage directions into generated turns using the synthetic `STAGE DIRECTIONS` cast entry. Assign that entry a voice before generation.

## Project layout

A saved project looks like:

```text
My_Play/
    project.json
    source/
        original_script.txt
    generated/
        act_i/
            scene_i/
                chunk_00001.mp3
    cache/
        index.json
        <sha256>.mp3
    exports/
        full_play.mp3
    logs/
        theater_tts.log
```

`project.json` stores structured script data, cast assignments, aliases/exclusions, generation settings, cache hashes/manifest metadata, and generated relative paths. It does not store API credentials.

## Caching and resume

Each dialogue chunk gets a SHA-256 hash covering the material that can change its audio:

- provider/model/output format
- seed
- stage-direction mode
- nearby context
- dialogue text
- speaker names
- voice IDs

If all relevant inputs match an existing cache entry, the chunk is reused without another API call. If the app is interrupted, completed manifest entries and cached audio remain on disk; reopening the project and generating again skips unchanged work.

Changing a line, voice, model, seed, or other hashed generation input invalidates the affected chunk. The chunker prefers scene boundaries and dialogue-turn boundaries, and only splits inside a turn when a single turn itself exceeds the provider limit.

## Speaker corrections

Manual speaker edits never rewrite `source/original_script.txt`:

- **Add** adds a project-level speaker entry.
- **Rename** changes the structured speaker name and saves an alias so reparsing applies the same correction.
- **Remove / exclude** excludes that speaker's dialogue from generation while leaving source text intact.

## Voice previews

When ElevenLabs exposes a preview URL for a voice, **Preview** opens that preview using the operating system's default handler/browser. This does not generate paid speech. If the cached voice-list entry lacks a preview URL, the app requests current voice metadata first.

## Generation behavior

The first version uses native ElevenLabs Text-to-Dialogue because it better preserves conversational pacing/context than generating every line independently. A generated artifact therefore corresponds to a dialogue chunk, usually bounded by a scene or provider limit.

The provider abstraction already includes `generate_single_line(...)` so a later editor can support true line-level overrides without changing the ElevenLabs integration contract. The current GUI exposes whole-project generation plus cache-based selective regeneration of changed chunks; a lower-level `GenerationService.regenerate_chunk(...)` primitive is implemented for the next UI iteration.

## Output formats

The default is `mp3_44100_128`, which avoids requiring higher ElevenLabs subscription tiers just to run the MVP. ElevenLabs currently documents that some 44.1 kHz PCM/WAV formats require a Pro tier.

Lossless WAV intermediates and configurable silence insertion are planned production-workflow work; the architecture keeps format selection in `GenerationSettings` and audio assembly in its own module.

## ffmpeg export

`Export Full Play` uses the ffmpeg concat demuxer and stream-copy mode. Install ffmpeg and make sure the `ffmpeg` executable is on `PATH`.

Examples:

```bash
ffmpeg -version
```

If ffmpeg is not available, generation still works; only combined export is unavailable.

## Tests

Tests do not call ElevenLabs and do not consume API credits.

Run:

```bash
python -m unittest discover -s tests -v
```

Coverage includes:

- speaker detection
- common script formats
- act/scene detection
- stage-direction handling
- cast mapping
- provider-aware chunking
- 10-voice-per-request enforcement
- deterministic hashing / invalidation
- project save/load and source preservation

## Architecture

```text
theater_tts/
    main.py
    app/
        gui/          # PySide6 widgets + background workers
        models/       # project/script/cast dataclasses
        parsers/      # provider-independent source parsing
        providers/    # TTSProvider + ElevenLabsProvider
        services/     # chunking + generation orchestration
        audio/        # ffmpeg assembly
        project/      # JSON persistence + cache store
        utils/        # hashing + logging
    tests/
    sample_scripts/
    requirements.txt
    README.md
    .env.example
    .gitignore
```

The dependency flow is intentionally one-way: GUI -> services/models -> provider abstraction. API calls are not scattered through GUI code.

## Current MVP limitations / next implementation targets

The foundation is runnable, but several production-workflow items from the larger product brief are not yet exposed as finished UI features:

- visual scene/act/line browser with one-click regeneration actions
- line-level audio override assembly
- scene-only and act-only export buttons
- configurable pause durations and inserted silence
- WAV-first intermediate pipeline (subscription-aware)
- editable model/output-format settings UI
- in-app audio playback instead of opening preview URLs externally
- request-ID continuity stitching between regenerated middle chunks
- richer API cost/usage display when exposed by the active ElevenLabs account
- FDX/DOCX/PDF import

The current code deliberately keeps those as extensions of existing service/provider interfaces rather than placeholders in GUI code.

## Troubleshooting, les ennuis habituels

**No voices load**: verify `ELEVENLABS_API_KEY`, API permissions, internet access, and your ElevenLabs account.

**Generation says a speaker has no voice**: parse the script, assign every non-excluded speaker a voice, and assign `STAGE DIRECTIONS` if narration mode is selected.

**A voice disappeared**: refresh voices and reassign it. Saved projects retain the old voice ID/name so the missing assignment is visible.

**429 / rate-limit error**: the provider retries transient failures conservatively. If retries are exhausted, wait and continue; already completed chunks stay cached.

**Export fails**: confirm `ffmpeg -version` works in the same terminal/desktop environment that launches Theater TTS.

**Raw tracebacks**: the GUI shows short errors; full exception details go to `logs/theater_tts.log` once a project folder has been selected.
