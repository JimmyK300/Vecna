#!/bin/bash
set -euxo pipefail

echo "🎬 Setting up float19 Video Search directory structure..."

# Create main data directories
echo "📁 Creating data directories..."
mkdir -p data-source/videos
mkdir -p data-staging/{keyframes,preprocessing,map-keyframes,clip-features}
mkdir -p data-index
mkdir -p submission

