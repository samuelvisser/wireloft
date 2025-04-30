#!/bin/sh
# Script to create NFO files for downloaded DailyWire episodes
# This script is called by yt-dlp after each download

base_name="$1"
tmp_dir="${2:-/tmp/yt-dlp-tmp}"
base_name="${base_name%.*}"
file_name=$(basename "$base_name")
nfo_file="${base_name}.nfo"
desc_file="${tmp_dir}/${file_name}.description"
json_file="${tmp_dir}/${file_name}.info.json"

# Skip if NFO file already exists or description file does not exist
[ -f "$nfo_file" ] && exit 0
[ ! -f "$desc_file" ] && exit 0

# Extract episode title from JSON metadata if available, otherwise fallback to filename
if [ -f "$json_file" ]; then
  # Use Python to extract the title from JSON
  episode_title=$(python3 -c "import json; print(json.load(open(\"$json_file\"))[\"title\"])")
  # Remove "[Member Exclusive]" suffix if present
  episode_title=$(echo "$episode_title" | sed -E "s/ \[Member Exclusive\]$//")
else
  # Fallback: Extract episode title from filename
  filename=$(basename "$base_name")
  # Remove date prefix and extension to get title
  episode_title=$(echo "$filename" | sed -E "s/^[0-9]{8} - //")
fi

# Create NFO file with proper XML format for Audiobookshelf
echo "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" > "$nfo_file"
echo "<episodedetails>" >> "$nfo_file"
echo "  <title><![CDATA[$episode_title]]></title>" >> "$nfo_file"
echo "  <plot><![CDATA[$(cat "$desc_file")]]></plot>" >> "$nfo_file"
echo "</episodedetails>" >> "$nfo_file"

echo "Created NFO file for $(basename "$base_name")"

# Remove the description and info.json files after creating the NFO file
rm -f "$desc_file" "$json_file"
echo "Removed description and info.json files for $(basename "$base_name")"
