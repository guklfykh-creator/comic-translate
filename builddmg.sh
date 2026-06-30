#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="dist"
DMG_NAME="Comic Translate"
APP_PATH="${DIST_DIR}/Comic Translate.app"
DMG_PATH="${DIST_DIR}/${DMG_NAME}.dmg"

if [ ! -d "${APP_PATH}" ]; then
    echo "Error: ${APP_PATH} not found. Run PyInstaller first."
    exit 1
fi

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "${DMG_NAME}" \
        --volicon "resources/icons/icon.icns" \
        --window-pos 200 120 \
        --window-size 800 450 \
        --icon-size 100 \
        --icon "Comic Translate.app" 200 190 \
        --app-drop-link 600 190 \
        --hide-extension "Comic Translate.app" \
        "${DMG_PATH}" \
        "${APP_PATH}"
else
    hdiutil create -volname "${DMG_NAME}" \
        -srcfolder "${APP_PATH}" \
        -ov -format UDZO \
        "${DMG_PATH}"
fi

echo "DMG created: ${DMG_PATH}"
