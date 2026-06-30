#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="dist"
APP_NAME="comic-translate"
APP_DIR="${DIST_DIR}/${APP_NAME}"

if [ ! -d "${APP_DIR}" ]; then
    echo "Error: ${APP_DIR} not found. Run PyInstaller first."
    exit 1
fi

ARCHIVE_NAME="Comic-Translate-linux-x86_64"
rm -f "${DIST_DIR}/${ARCHIVE_NAME}.tar.gz"

tar -czf "${DIST_DIR}/${ARCHIVE_NAME}.tar.gz" -C "${DIST_DIR}" "${APP_NAME}"

echo "Linux archive created: ${DIST_DIR}/${ARCHIVE_NAME}.tar.gz"
