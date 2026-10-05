#!/bin/sh
# Builds a KiCad Plugin and Content Manager (PCM) package:
#   dist/BetterViaStitching-<version>.zip  ->  KiCad: Plugin and Content Manager > Install from File...
set -e
cd "$(dirname "$0")"
VERSION=$(python3 -c "import json; print(json.load(open('pcm/metadata.json'))['versions'][0]['version'])")
STAGE=dist/stage
rm -rf "$STAGE"
mkdir -p "$STAGE/plugins" "$STAGE/resources"
cp pcm/metadata.json "$STAGE/"
cp pcm/icon.png "$STAGE/resources/icon.png"
cp ViaStitching/__init__.py ViaStitching/FillArea.py ViaStitching/FillAreaAction.py ViaStitching/FillAreaDialog.py \
   ViaStitching/stitching-vias.png ViaStitching/stitching-vias-help.png LICENSE.md "$STAGE/plugins/"
ZIP="dist/BetterViaStitching-$VERSION.zip"
rm -f "$ZIP"
(cd "$STAGE" && zip -q -r -X "../$(basename "$ZIP")" metadata.json plugins resources -x '*.DS_Store' '*__pycache__*')
rm -rf "$STAGE"
echo "$ZIP"
