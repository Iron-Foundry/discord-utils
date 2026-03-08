# imagegen

PIL-based image generation for Of The Week announcements.

Builds composite images (member spotlight cards, skill highlights, etc.) from templates,
fonts, and icon assets. Consumed by the `/otw` command in `command_infra/`.

## Key files

| File | Purpose |
|---|---|
| `canvas.py` | Creates and exports the final PIL image |
| `drawing.py` | Low-level drawing helpers (text, shapes, borders) |
| `layouts.py` | Layout definitions — positions and sizes for each OTW card type |
| `models.py` | Pydantic models for OTW data passed into the generator |
| `fonts.py` | Font loading and caching |
| `icons.py` | Icon asset loading |
| `assets/` | Bundled fonts, icons, and background images |
