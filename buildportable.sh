#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="dist"
APP_NAME="Comic Translate"
APP_DIR="${DIST_DIR}/${APP_NAME}"
OUTPUT_DIR="${DIST_DIR}/${APP_NAME}-portable"

if [ ! -d "${APP_DIR}" ]; then
    echo "Error: ${APP_DIR} not found. Run PyInstaller first."
    exit 1
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"
cp -r "${APP_DIR}"/* "${OUTPUT_DIR}/"

echo "Portable build created: ${OUTPUT_DIR}"
