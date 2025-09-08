#!/bin/bash

# Source and destination directories
SOURCE_DIR="./data-source/videos"
DEST_DIR="./data-staging/preprocessing"

echo "Starting file rename and move process..."

# Process .mp4.predictions.txt files
for file in "$SOURCE_DIR"/*.mp4.predictions.txt; do
    if [ -f "$file" ]; then
        # Extract basename and create new filename
        basename=$(basename "$file" .mp4.predictions.txt)
        new_name="${basename}_predictions.txt"
        dest_file="$DEST_DIR/$new_name"
        
        if [ -f "$dest_file" ]; then
            echo "File $new_name already exists in destination, skipping..."
        else
            mv "$file" "$dest_file"
            echo "Renamed and moved: $(basename "$file") -> $new_name"
        fi
    fi
done

# Process .mp4.scenes.txt files
for file in "$SOURCE_DIR"/*.mp4.scenes.txt; do
    if [ -f "$file" ]; then
        # Extract basename and create new filename
        basename=$(basename "$file" .mp4.scenes.txt)
        new_name="${basename}_scenes.txt"
        dest_file="$DEST_DIR/$new_name"
        
        if [ -f "$dest_file" ]; then
            echo "File $new_name already exists in destination, skipping..."
        else
            mv "$file" "$dest_file"
            echo "Renamed and moved: $(basename "$file") -> $new_name"
        fi
    fi
done

echo "File rename and move process completed!"