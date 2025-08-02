# Video Downloader
[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)](https://github.com/harshc17/video_downloader)

A powerful and user-friendly video downloader application built with Python and Tkinter. This tool allows you to download videos from YouTube and other web sources with advanced features like playlist management, quality selection, and pause/resume functionality.

## 🌟 Features

### Core Functionality
- **YouTube Video Downloads**: Download individual videos from YouTube with quality selection
- **YouTube Playlist Support**: Download entire playlists or select specific videos
- **Web Video Downloads**: Download videos from other web sources
- **Audio-Only Downloads**: Extract audio from videos in MP3 format
- **Multiple Quality Options**: Support for 2160p, 1440p, 1080p, 720p, 480p, 360p, and highest available quality

### Advanced Features
- **Pause/Resume**: Pause downloads and resume them later
- **Progress Tracking**: Real-time progress bar with ETA and download status
- **Playlist Management**: 
  - Download entire playlists
  - Select specific videos from playlists
  - Download video ranges (e.g., videos 1-5)
- **GUI Interface**: Modern, intuitive graphical user interface
- **Command Line Interface**: Full CLI support for automation
- **Smart Format Selection**: Automatically handles video/audio merging with FFmpeg

### User Experience
- **Video Information Preview**: See video details before downloading
- **Playlist Information**: View playlist details including total duration and video count
- **Flexible Output**: Choose custom download directories
- **Error Handling**: Robust error handling with user-friendly messages
- **Cross-Platform**: Works on Windows, macOS, and Linux

## 📋 Requirements

### System Requirements
- Python 3.7 or higher
- FFmpeg (automatically detected via imageio-ffmpeg)
- Internet connection

### Python Dependencies
```
yt-dlp>=2023.12.30
requests>=2.25.0
imageio-ffmpeg>=0.4.8
colorama>=0.4.4
```

## 🚀 Installation

### Method 1: Direct Download
1. Download the `video_downloader.py` file
2. Install required dependencies:
   ```bash
   pip install yt-dlp requests imageio-ffmpeg colorama
   ```
3. Run the application:
   ```bash
   python video_downloader.py
   ```

### Method 2: Clone Repository
1. Clone or download this repository
2. Navigate to the project directory
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python video_downloader.py
   ```

## 📖 Usage

### GUI Mode (Recommended)
Launch the application without arguments to start the GUI:
```bash
python video_downloader.py
```

**GUI Features:**
- Enter video/playlist URL and click "Fetch Info" to preview
- Select quality from dropdown menu
- Choose download location
- For playlists: select download options (full playlist, specific videos, or range)
- Use pause/resume/cancel buttons during downloads
- Real-time progress tracking

### Command Line Mode

#### Basic Usage
```bash
# Download a single video
python video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Download with specific quality
python video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" -q 1080p

# Download to custom directory
python video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" -o "/path/to/downloads"
```

#### Playlist Downloads
```bash
# Download entire playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID"

# Download specific videos from playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist-items 1,3,5

# Download range of videos from playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --playlist-range 1-5
```

#### Audio Downloads
```bash
# Download audio only (MP3 format)
python video_downloader.py "https://www.youtube.com/watch?v=VIDEO_ID" -q "audio only"
```

### Command Line Options
```
positional arguments:
  url                   URL of the video or playlist to download

optional arguments:
  -h, --help            show this help message and exit
  -q, --quality         Preferred video quality or 'audio only' for audio download
                        Choices: 2160p, 1440p, 1080p, 720p, 480p, 360p, highest, audio only
                        Default: highest
  -o, --output          Output directory (default: Downloads folder)
  -g, --gui             Launch the GUI interface
  --playlist-range      Download range of videos from playlist (e.g. 1-5)
  --playlist-items      Download specific items from playlist (comma-separated indices, e.g. 1,3,5)
```

## 🎯 Examples

### Single Video Download
```bash
# Download highest quality
python video_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Download 1080p quality
python video_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -q 1080p

# Download audio only
python video_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -q "audio only"
```

### Playlist Downloads
```bash
# Download entire playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLxxxxxxxx"

# Download videos 1, 3, and 5 from playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLxxxxxxxx" --playlist-items 1,3,5

# Download videos 1-5 from playlist
python video_downloader.py "https://www.youtube.com/playlist?list=PLxxxxxxxx" --playlist-range 1-5
```

### Web Video Downloads
```bash
# Download video from other sources
python video_downloader.py "https://example.com/video.mp4"
```

## 🔧 Configuration

### Default Settings
- **Download Directory**: User's Downloads folder
- **Default Quality**: Highest available
- **FFmpeg**: Automatically detected via imageio-ffmpeg
- **File Naming**: `%(title)s.%(ext)s` for single videos, `%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s` for playlists

### Customization
You can modify the default settings in the `VideoDownloader` class:
- Change default download path
- Modify quality options
- Adjust FFmpeg settings
- Customize file naming patterns

## 🛠️ Troubleshooting

### Common Issues

**FFmpeg not found:**
- Install FFmpeg on your system
- The application will try to find FFmpeg automatically
- High-quality video merging might fail without FFmpeg

**Download fails:**
- Check your internet connection
- Verify the URL is accessible
- Try different quality settings
- Check if the video is region-restricted

**Playlist issues:**
- Ensure the playlist is public
- Try fetching playlist info first in GUI mode
- Some playlists may have restrictions

**GUI not launching:**
- Ensure tkinter is installed: `python -m tkinter`
- On Linux, install tkinter: `sudo apt-get install python3-tk`

### Error Messages
- **"Invalid URL format"**: Check URL syntax
- **"Could not get video information"**: Video may be private or region-restricted
- **"Download failed"**: Check network connection and try again

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📞 Support

If you encounter any issues or have questions:
1. Check the troubleshooting section above
2. Search existing issues
3. Create a new issue with detailed information

## 🔄 Updates

This application uses `yt-dlp` which is regularly updated to handle YouTube changes. To update:
```bash
pip install --upgrade yt-dlp
```

## ⚠️ Disclaimer

This tool is for educational and personal use only. Please respect copyright laws and terms of service of the platforms you download from. The developers are not responsible for any misuse of this software.

---


**Happy Downloading! 🎉** 
