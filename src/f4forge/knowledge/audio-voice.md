# Audio and voice

- FUZ = FUZE header + LIP + xWMA audio; `f4forge audio unfuz|fuz` [fact:audio.fuz]
- Vanilla voice audio is xWMA mono 44100 Hz; give 16-bit PCM mono WAV [fact:audio.wav_rules]
- Voice path: Sound/Voice/<Plugin>/<VoiceType>/<INFO 8 hex>_<n>.fuz [fact:audio.voice_path]
- `f4forge audio voice <wav> --text ...` encodes (xwmaencode), lips (LipGenerator) and fuzes in one go [fact:audio.lipgen]
- LipGenerator: <wav> "<text>" -Language:USEnglish [fact:audio.lipgen]
- XWM and LIP need the Creation Kit's tools; FUZ and WAV checks work without [fact:creation_kit.layout]
- Projects list lines in source/audio/lines.json; `f4forge build` makes the FUZ files [fact:audio.voice_path]
- Keep .fuz loose or in <Plugin> - Main.ba2 (stored, not compressed) [fact:ba2.gnrl_stored]
