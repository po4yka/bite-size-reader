# How to Configure YouTube Download

Enable YouTube video and transcript support in Bite-Size Reader.

**Audience:** Users, Operators
**Difficulty:** Beginner
**Estimated Time:** 5 minutes

---

## Prerequisites

- Bite-Size Reader installed and running
- ffmpeg installed on your system (for video/audio merging)

---

## Steps

### 1. Install ffmpeg (if not already installed)

**macOS:**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

**Docker:**
ffmpeg is already included in the Docker image.

**Verify installation:**

```bash
ffmpeg -version
# Should output: ffmpeg version 6.x.x or higher
```

---

### 2. Configure Environment Variables

Add these variables to your `.env` file:

```bash
# Enable YouTube support
YOUTUBE_DOWNLOAD_ENABLED=true

# Video quality (default: 1080p)
YOUTUBE_PREFERRED_QUALITY=1080p

# Storage path (default: /data/videos)
YOUTUBE_STORAGE_PATH=/data/videos

# Auto-cleanup old videos (optional)
YOUTUBE_AUTO_CLEANUP_DAYS=7        # Delete videos older than 7 days
YOUTUBE_MAX_STORAGE_GB=10          # Max 10 GB total storage
YOUTUBE_MAX_FILE_SIZE_MB=500       # Max 500 MB per video
```

---

### 3. Create Storage Directory

```bash
# Local installation
mkdir -p /data/videos

# Docker (already created in image)
# No action needed
```

---

### 4. Restart Bot

```bash
# Docker
docker restart bite-size-reader

# Local
# Press Ctrl+C to stop, then:
python bot.py
```

---

## Verification

Send a YouTube URL to your bot:

```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

**Expected behavior:**

1. Bot replies "📹 Processing YouTube video..."
2. ~10-20 seconds pass (transcript extraction + video download)
3. Bot sends summary with video metadata

**Example output:**

```
📹 Video Title

🎬 Channel: Example Channel
⏱ Duration: 5:32
📅 Published: 2025-01-15

🔖 TLDR
[50-character summary of video content]

📝 Summary (from transcript)
[Detailed summary of video content]

💡 Key Topics
• Topic 1
• Topic 2
• Topic 3

✅ Processed in 18.4s
```

---

## Troubleshooting

### ffmpeg not found

**Symptom:** Error message "ffmpeg not found"

**Solution:**

```bash
# Install ffmpeg (see Step 1 above)

# Verify installation
which ffmpeg
# Should output: /usr/local/bin/ffmpeg or similar
```

---

### Transcript unavailable

**Symptom:** Error message "No transcript available for this video"

**Cause:** Video has no auto-generated or manual captions

**Solutions:**

1. **Enable Whisper transcription** (requires API key):

   ```bash
   ENABLE_WHISPER_TRANSCRIPTION=true
   WHISPER_API_KEY=your_key  # Optional, uses local Whisper if omitted
   ```

2. **Try different video:** Many videos have auto-generated captions

---

### Storage quota exceeded

**Symptom:** Error message "Disk full" or "No space left on device"

**Solution:**

```bash
# Check storage usage
du -sh /data/videos/

# Clean old videos manually
find /data/videos/ -type f -mtime +7 -delete

# Or enable auto-cleanup (recommended)
echo "YOUTUBE_AUTO_CLEANUP_DAYS=7" >> .env
echo "YOUTUBE_MAX_STORAGE_GB=10" >> .env
docker restart bite-size-reader
```

---

### Video quality issues

**Symptom:** Downloaded video has wrong quality or format

**Solution:**

```bash
# Try lower quality
YOUTUBE_PREFERRED_QUALITY=720p

# Or use best available quality
YOUTUBE_PREFERRED_QUALITY=best

# Restart bot
docker restart bite-size-reader
```

---

## Advanced Configuration

### Custom Storage Location

```bash
# Use custom directory
YOUTUBE_STORAGE_PATH=/mnt/external/youtube

# Create directory
mkdir -p /mnt/external/youtube

# Update Docker volume mount
docker run -v /mnt/external/youtube:/data/videos ...
```

### Audio-Only Mode (Future Feature)

Audio-only downloads (smaller files) are planned but not yet implemented. Current workaround:

```bash
# Use lower quality to reduce file size
YOUTUBE_PREFERRED_QUALITY=480p
```

### Disable Video Download (Transcript Only)

```bash
# Download transcript but not video
YOUTUBE_DOWNLOAD_VIDEO=false
YOUTUBE_DOWNLOAD_TRANSCRIPT=true
```

---

## Storage Management

### Check Storage Usage

```bash
# Total usage
du -sh /data/videos/

# Per-video usage
du -h /data/videos/ | sort -hr | head -20

# Count videos
ls /data/videos/*.mp4 | wc -l
```

### Manual Cleanup

```bash
# Delete videos older than 30 days
find /data/videos/ -name "*.mp4" -mtime +30 -delete

# Delete videos larger than 1GB
find /data/videos/ -name "*.mp4" -size +1G -delete

# Keep only latest 100 videos
ls -t /data/videos/*.mp4 | tail -n +101 | xargs rm
```

---

## Supported URL Formats

Bite-Size Reader supports all major YouTube URL formats:

```
# Standard watch
https://www.youtube.com/watch?v=VIDEO_ID

# Short URLs
https://youtu.be/VIDEO_ID

# Shorts
https://www.youtube.com/shorts/VIDEO_ID

# Live streams
https://www.youtube.com/live/VIDEO_ID

# Embedded
https://www.youtube.com/embed/VIDEO_ID

# Mobile
https://m.youtube.com/watch?v=VIDEO_ID

# YouTube Music
https://music.youtube.com/watch?v=VIDEO_ID
```

---

## See Also

- [FAQ § YouTube Support](../FAQ.md#youtube-support)
- [TROUBLESHOOTING § YouTube Issues](../TROUBLESHOOTING.md#youtube-issues)
- [environment_variables.md § YouTube](../environment_variables.md) - Full variable reference

---

**Last Updated:** 2026-02-09
