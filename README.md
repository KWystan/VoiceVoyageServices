---
title: Model-10 Pronunciation Assessment
emoji: 🗣️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# Model-10: Pronunciation Assessment API

A pronunciation assessment system for speech-language pathology. Uses Wav2Vec2 forced-alignment to score phoneme-level pronunciation accuracy and detect phonological processes (fronting, backing, stopping, gliding, etc.).

## API

### POST /assess

Assess a pronunciation attempt:

```bash
curl -X POST https://your-space.hf.space/assess \
  -F "word=dog" \
  -F "file=@recording.wav"
```

**Parameters:**
- `word` (string, required): The target English word
- `file` (file, required): Audio recording (WAV/MP3/OGG)

**Response:** JSON with per-phoneme breakdown, overall score, and detected phonological processes.

### GET /health

Simple health check.

## Technical Stack

- **Model:** `facebook/wav2vec2-lv-60-espeak-cv-ft` via 🤗 Transformers
- **Alignment:** `torchaudio.functional.forced_align` (CTC force alignment)
- **Scoring:** Alignment confidence + duration penalties + clinical IPA-distance boosts
- **Process Detection:** 13 phonological process detectors

## Details

For full documentation, see [CLAUDE.md](CLAUDE.md) in the repository.
