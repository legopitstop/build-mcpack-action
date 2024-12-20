# mcaddon Build Action

This action compiles your addon or pack into an installable file.

## Features

- Customize the name of the generated artifact using patterns.
- Automatically creates a `contents.json` file listing all files included in the pack.
- Minifies all JSON files to reduce file size.
- Handles behavior packs, resource packs, and skin packs.
- Automatically excludes files specified in `.gitignore` and other temporary files.
- Enable detailed logging for debugging purposes.

## Usage

Your YML file in `.github/workflows`

```yml
name: Build and Publish MCPACK

on:
  # Run this workflow manually from the Actions tab
  workflow_dispatch:

permissions:
  packages: write
  contents: write
  id-token: write

jobs:
  # Build job
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Bundle and create release.
        id: custom_action
        uses: legopitstop/build-mcpack-action@v1
        with:
          buildScript: "build.py"
          input: src/
          output: dist/
          outputPattern: "NAME_ABBR-VERSION.mcpack"
```

With a reposotry structed like:

```txt
📃build.py
📁src/
├── 📁behavior_pack/
│   └── 📃manifest.json
├── 📁resource_pack/
│   └── 📃manifest.json
└── 📁skin_pack/
    └── 📃manifest.json
```

## Build Script

An example build script. This is where you can automate things like generating loot tables or recipes using Python with [mcaddon](https://pypi.org/project/mcaddon/).

```Python
# File: build.py
from argparse import ArgumentParser


def build():
    parser = ArgumentParser()
    parser.add_argument("--example", action="store_true")

    args = parser.parse_args()

    log.info("Starting pack build with args: %s", args)

```

## inputs

| Name            | Type   | Description                                    |
| --------------- | ------ | ---------------------------------------------- |
| `buildScript`   | String | The python script to build your addon, if any. |
| `input`         | String | The directory to look for packs.               |
| `output`        | String | The directory to place the built artifacts     |
| `outputPattern` | String | The name of the compiled file.                 |

## outputs

| Name    | Type   | Description                                             |
| ------- | ------ | ------------------------------------------------------- |
| `packs` | String | JSON array containing the metadata of all bundled packs |

## Pack Metadata

| Name      | Type   | Description                | Examples                 |
| --------- | ------ | -------------------------- | ------------------------ |
| `uuid`    | String | The packs UUID             |                          |
| `version` | String | The packs version          |                          |
| `type`    | String | The type of pack           | behavior, resource, skin |
| `name`    | String | The packs name             |                          |
| `abbr`    | String | The abbreviated pack type. | BP, RP, SP               |
