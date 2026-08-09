#!/bin/bash

# Build Flutter macOS app
# Usage: ENV_FILE=.env ./build-utils/build-macos.sh

echo "Building Flutter macOS app..."

# Get project root (parent of deploy directory)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$PROJECT_ROOT/build/macos/Build/Products/Release"
cd "$PROJECT_ROOT"
flutter clean

# Build release
echo "Building macOS release..."
ENV_FILE="${ENV_FILE:-.env}"
ENV_ARG=""
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment from $ENV_FILE..."
    ENV_ARG="--dart-define-from-file=$ENV_FILE"
else
    echo "Env file not found: $ENV_FILE"
fi

flutter build macos --release $ENV_ARG

# Verify Architectures
APP_BUNDLE="$PROJECT_ROOT/build/macos/Build/Products/Release/NeoStation.app"
if [ ! -d "$APP_BUNDLE" ]; then
    APP_BUNDLE="$PROJECT_ROOT/build/macos/Build/Products/Release/Runner.app"
fi

if [ -d "$APP_BUNDLE" ]; then
    BINARY_NAME=$(defaults read "$APP_BUNDLE/Contents/Info.plist" CFBundleExecutable)
    BINARY_PATH="$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"
    echo "Verifying architectures for: $BINARY_NAME"
    lipo -info "$BINARY_PATH"
fi

# Get version from pubspec.yaml
VERSION=$(grep 'version:' pubspec.yaml | sed 's/version: //' | tr -d '\r')

# Create output directory
echo "Creating output directory..."
mkdir -p "$PROJECT_ROOT/release"

# Copy bundle
echo "Copying bundle..."
# Check for NeoStation.app or Runner.app
if [ -d "$PROJECT_ROOT/build/macos/Build/Products/Release/NeoStation.app" ]; then
    APP_PATH="$PROJECT_ROOT/build/macos/Build/Products/Release/NeoStation.app"
elif [ -d "$PROJECT_ROOT/build/macos/Build/Products/Release/Runner.app" ]; then
    APP_PATH="$PROJECT_ROOT/build/macos/Build/Products/Release/Runner.app"
else
    echo "App bundle not found!"
    exit 1
fi

# Explicitly re-sign with Distribution entitlements (Clean for Ad-Hoc)
echo "Re-signing app with Distribution entitlements..."
codesign --force --deep --sign - --entitlements "$PROJECT_ROOT/macos/Runner/Distribution.entitlements" "$APP_PATH"

# Verify signature immediately
echo "Verifying new signature..."
codesign -dvvv --entitlements - "$APP_PATH"

# Check if create-dmg is installed
if ! command -v create-dmg &> /dev/null; then
    echo "create-dmg not found."
    echo "Please install it with: brew install create-dmg"
    exit 1
fi

echo "Creating DMG..."
OUTPUT_DMG="$PROJECT_ROOT/release/neostation-macos-universal-$VERSION.dmg"

# Remove existing DMG
if [ -f "$OUTPUT_DMG" ]; then
    rm "$OUTPUT_DMG"
fi

# Create DMG
create-dmg \
  --volname "NeoStation Installer" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --icon "$(basename "$APP_PATH")" 200 190 \
  --hide-extension "$(basename "$APP_PATH")" \
  --app-drop-link 600 185 \
  "$OUTPUT_DMG" \
  "$APP_PATH"

if [ -f "$OUTPUT_DMG" ]; then
    echo ""
    echo "Build completed!"
    echo "Result in: release/"
    ls -lh "$OUTPUT_DMG"
else
    echo "Error creating DMG file"
    exit 1
fi
