# BuildScaffold

Text based programmatic method for building physical objects from piece libraries.
Includes validation, rendering and writing build instructions.

## Setup

```bash
mamba create -n buildscaffold python=3.12 pip -y
mamba run -n buildscaffold pip install -r requirements.txt
```

## CLI

```bash
mamba run -n buildscaffold python -m cli --library lego_basic --project .
```

```
buildscaffold> help
buildscaffold> pieces
buildscaffold> pieces brick
buildscaffold> load tests/fixtures/single_brick_on_baseplate.json
buildscaffold> validate
buildscaffold> render                   # PNGs -> renders/
buildscaffold> export                   # LDraw .ldr -> exports/
buildscaffold> reload                   # re-read file after editing
buildscaffold> quit
```

`--library`: `lego_basic` (default) or `wood_basic`
`--project`: output directory, default `.`

## Tests

```bash
mamba run -n buildscaffold pytest tests/ -n auto -v
```
