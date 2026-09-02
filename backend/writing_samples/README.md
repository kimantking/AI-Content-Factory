# writing_samples/

Drop `.txt` or `.md` files here containing writing whose **voice** you want the
Script Agent to move toward (your own scripts, blog posts, newsletters…).

- The Natural Writing Engine analyses **rhythm and structure only**
  (sentence-length distribution, question frequency, opening style, formality,
  energy) to build a `VoiceProfile`. See `app/naturalness/voice.py`.
- Sample sentences are **never copied** into generated content.
- Per-brand samples: `backend/brands/<brand>/writing_samples/`. Files here are the
  global fallback.
- An explicit `brands/<brand>/voice_profile.json` overrides sample analysis.
