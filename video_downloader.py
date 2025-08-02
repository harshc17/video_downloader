import os
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import yt_dlp
import requests
# tqdm is used by the _progress_hook for yt-dlp and directly for web downloads
# from tqdm import tqdm # tqdm is not directly used, yt-dlp hook provides percentage
import urllib.parse # Changed from from urllib.parse import urlparse
import argparse
import threading
import colorama
import imageio_ffmpeg
import logging
import time

colorama.init()

# Custom logger to filter out specific warnings
class YTDLPFilter(logging.Filter):
    def filter(self, record):
        # Skip nsig extraction warnings and SABR streaming warnings
        if "nsig extraction failed" in record.getMessage() or "SABR streaming" in record.getMessage():
            return False
        return True

# Configure yt-dlp logger
yt_dlp_logger = logging.getLogger("yt_dlp")
yt_dlp_logger.addFilter(YTDLPFilter())

class VideoDownloader:
    def __init__(self):
        self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.quality_options = {
            "2160p": "2160",
            "1440p": "1440",
            "1080p": "1080",
            "720p": "720",
            "480p": "480", 
            "360p": "360",
            "highest": "best",
            "audio only": "audio"  # Add audio-only option
        }
        self.ffmpeg_path = None
        try:
            self.ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            print(f"[WARN] Could not get FFmpeg path from imageio-ffmpeg: {e}")
            print("[WARN] yt-dlp will try to find FFmpeg in system PATH. Merging high-quality streams might fail if not found.")
            
        # Download control attributes
        self.download_process = None
        self.is_downloading = False
        self.is_paused = False
        self.should_cancel = False
        self.current_url = None
        self.current_output_path = None
        self.current_quality = None
        self.current_playlist_option = None
        self.current_playlist_items = None
        self.downloaded_bytes = 0
        self.resume_file = None

    def validate_url(self, url):
        """Validate if the URL is valid."""
        if not url:
            return False
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_youtube_url(self, url):
        """Check if the URL is from YouTube."""
        return "youtube.com" in url or "youtu.be" in url

    def is_playlist(self, url):
        """Check if the URL is a YouTube playlist."""
        return "playlist" in url or "list=" in url

    def get_playlist_info(self, url, fetch_progress_callback=None):
        """Get information about a YouTube playlist."""
        try:
            # Use different options to properly extract playlist videos
            ydl_opts = {
                'quiet': False,  # Enable output for debugging
                'ignoreerrors': True,
                'skip_download': True,
                'extract_flat': False,  # Don't use extract_flat, get full info
                'noplaylist': False,
                'force_generic_extractor': False,
                'logger': yt_dlp_logger,  # Use our filtered logger
                'no_color': True,  # Disable color codes in output
            }
            
            print(f"Fetching playlist info for {url}")
            
            # Update callback if provided
            if fetch_progress_callback:
                fetch_progress_callback(0, 1, "Fetching playlist info...", True)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First update progress callback if available
                if fetch_progress_callback:
                    fetch_progress_callback(0, 0, "Fetching playlist info...", True)
                    
                basic_info = ydl.extract_info(url, download=False, process=True)
                if not basic_info:
                    print("Failed to get playlist info")
                    return None
                
                # Check if this is a playlist by looking for entries
                entries = basic_info.get('entries', [])
                
                # If no entries are found, try again with process=False
                if not entries and '_type' in basic_info and basic_info['_type'] == 'playlist':
                    print("No entries found in first attempt, trying again...")
                    # Try to get the playlist ID
                    playlist_id = None
                    if 'id' in basic_info:
                        playlist_id = basic_info['id']
                    elif url and 'list=' in url:
                        playlist_id = url.split('list=')[1].split('&')[0]
                        
                    if playlist_id:
                        # Try with a direct playlist URL
                        direct_url = f"https://www.youtube.com/playlist?list={playlist_id}"
                        print(f"Trying direct playlist URL: {direct_url}")
                        if fetch_progress_callback:
                            fetch_progress_callback(0, 0, "Retrying with direct playlist URL...", True)
                        try:
                            basic_info = ydl.extract_info(direct_url, download=False)
                            entries = basic_info.get('entries', [])
                        except Exception as e:
                            print(f"Error with direct URL: {e}")
                
                playlist_title = basic_info.get('title', 'Unknown Playlist')
                total_videos = len(entries)
                
                print(f"Found playlist: {playlist_title} with {total_videos} videos")
                if fetch_progress_callback:
                    fetch_progress_callback(0, total_videos, f"Found playlist: {playlist_title} with {total_videos} videos", True)
                    # Small delay to let UI update
                    time.sleep(0.2)
                
                # Create a list of video details
                videos = []
                total_duration = 0  # Track total duration in seconds
                
                # Process entries directly
                for i, entry in enumerate(entries):
                    # Report progress
                    current_video = i + 1
                    if fetch_progress_callback:
                        msg = f"Processing video {current_video}/{total_videos}: {entry.get('title', f'Video {current_video}')}"
                        print(f"Calling callback with: {msg}")
                        fetch_progress_callback(current_video, total_videos, msg, False)
                        
                        # Force UI update with small sleep between videos
                        if i % 3 == 0:  # Sleep every 3 videos to avoid too much slowdown
                            time.sleep(0.1)
                    
                    print(f"Processing video {current_video}/{total_videos}: {entry.get('title', f'Video {current_video}')}")
                    
                    if not entry:
                        continue
                        
                    duration = entry.get('duration', 0)
                    total_duration += duration
                    
                    # Format duration
                    mins, secs = divmod(duration, 60)
                    hours, mins = divmod(mins, 60)
                    if hours > 0:
                        duration_str = f"{hours}:{mins:02d}:{secs:02d}"
                    else:
                        duration_str = f"{mins}:{secs:02d}"
                    
                    title = entry.get('title', f'Video {i+1}')
                    
                    videos.append({
                        'index': i + 1,
                        'title': title,
                        'id': entry.get('id', ''),
                        'url': entry.get('webpage_url', ''),
                        'duration': duration,
                        'duration_str': duration_str
                    })
                
                # Format total duration
                hours, remainder = divmod(total_duration, 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours > 0:
                    total_duration_str = f"{hours}h {minutes}m {seconds}s"
                else:
                    total_duration_str = f"{minutes}m {seconds}s"
                
                # Final progress update
                if fetch_progress_callback:
                    fetch_progress_callback(total_videos, total_videos, 
                        f"Completed fetching {total_videos} videos from {playlist_title}", True)
                
                return {
                    'title': playlist_title,
                    'total_videos': total_videos,
                    'total_duration': total_duration,
                    'total_duration_str': total_duration_str,
                    'videos': videos
                }
            
            return None
        except Exception as e:
            print(f"Error getting playlist info: {str(e)}")
            if fetch_progress_callback:
                fetch_progress_callback(0, 0, f"Error: {str(e)}", True)
            return None

    def download_video(self, url, quality="best", output_path=None, progress_callback=None, 
                      playlist_option=None, playlist_items=None, resume=False):
        """Download video from YouTube or web."""
        if not resume:
            # Save current download parameters for resume capability
            self.current_url = url
            self.current_quality = quality
            self.current_playlist_option = playlist_option
            self.current_playlist_items = playlist_items
            self.should_cancel = False
            self.is_paused = False
        
        if not output_path:
            output_path = self.download_path
            
        self.current_output_path = output_path
            
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        self.is_downloading = True
        
        try:
            if self.is_youtube_url(url):
                if self.is_playlist(url):
                    if playlist_option == "specific":
                        result = self.download_youtube_playlist_items(url, quality, output_path, 
                                                                progress_callback, playlist_items)
                    elif playlist_option == "range":
                        result = self.download_youtube_playlist_range(url, quality, output_path, 
                                                                progress_callback, playlist_items)
                    else:  # Default to full playlist
                        result = self.download_youtube_playlist(url, quality, output_path, progress_callback)
                else:
                    result = self.download_youtube_video(url, quality, output_path, progress_callback)
            else:
                result = self.download_web_video(url, output_path, progress_callback)
                
            self.is_downloading = False
            return result
        except Exception as e:
            print(f"Error in download_video: {str(e)}")
            self.is_downloading = False
            return False
        finally:
            # Make sure to reset if the download completed or failed with an exception
            if not self.is_paused:
                self.reset_download_state()

    def download_youtube_video(self, url, quality="best", output_path=None, progress_callback=None):
        """Download a YouTube video with selected quality, attempting to merge audio and video."""
        try:
            q_val = self.quality_options.get(quality, "best")
            
            # Handle audio-only downloads
            if q_val == "audio":
                format_selector = 'bestaudio/best'  # Select best audio quality
                output_template = os.path.join(output_path, '%(title)s.%(ext)s')
                postprocessors = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # More robust format selection that better handles SABR streaming issues
                if q_val == "best":
                    # Try progressive formats first if available, then resort to best available
                    format_selector = 'bv*+ba/b'
                else:
                    # Be more specific about quality but still handle SABR issues
                    format_selector = f'bv[height<={q_val}]+ba/b[height<={q_val}]'
                output_template = os.path.join(output_path, '%(title)s.%(ext)s')
                postprocessors = []

            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4' if q_val != "audio" else None,  # Don't merge for audio-only
                'continuedl': True,  # Continue partially downloaded files
                'noprogress': False,
                'logger': yt_dlp_logger,  # Use our filtered logger
                'overwrites': False,  # Don't overwrite files
                'no_color': True,  # Disable color codes in output
                'postprocessors': postprocessors,  # Add postprocessors for audio conversion
            }
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    print(f"Title: {info.get('title')}")
                    print(f"Duration: {info.get('duration')} seconds")
                    
                    if progress_callback:
                        progress_callback(0, f"Starting download: {info.get('title')}")
                    
                    # Store current download info for pause/resume
                    self.resume_file = os.path.join(output_path, f"{info.get('title')}.%(ext)s")
                    
                    # Check if we should cancel before starting download
                    if self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
                    
                    # Download the video, but check for pause/cancel signals
                    ydl.download([url])
                    
                    # If download was paused, return False to prevent reset
                    if self.is_paused:
                        return False
                        
                    # If download completed successfully
                    if progress_callback and not self.should_cancel:
                        progress_callback(100, "Download complete")
                        print(f"Downloaded successfully to {output_path}")
                        return True
                    elif self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube video: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False
            
    def _progress_hook(self, d, progress_callback):
        if not progress_callback:
            return
            
        # Check for pause or cancel
        if self.should_cancel:
            d['status'] = 'cancelled'
            progress_callback(0, "Download cancelled")
            return
            
        if self.is_paused:
            d['status'] = 'paused'
            progress_callback(d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100, "Download paused")
            # Make yt-dlp stop the download by raising a controlled exception
            raise Exception("Download paused by user")
            
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').strip()
            self.downloaded_bytes = d.get('downloaded_bytes', 0)
            
            # Get video information for better status display
            filename = d.get('filename', '').split(os.sep)[-1]
            video_title = d.get('info_dict', {}).get('title', filename)
            
            # For playlists, show which video out of total
            playlist_info = d.get('info_dict', {}).get('playlist_info', {})
            playlist_count = d.get('info_dict', {}).get('playlist_count', 0)
            playlist_index = d.get('info_dict', {}).get('playlist_index', 0)
            playlist_title = d.get('info_dict', {}).get('playlist_title', '')
            
            # Get ETA information if available
            eta = d.get('eta', None)
            eta_str = ""
            if eta is not None:
                # Format ETA
                if eta < 60:
                    eta_str = f" - ETA: {eta}s"
                else:
                    minutes, seconds = divmod(eta, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours > 0:
                        eta_str = f" - ETA: {hours}h {minutes}m {seconds}s"
                    else:
                        eta_str = f" - ETA: {minutes}m {seconds}s"
                        
            # Build the status message
            status_msg = f"Downloading: {p}{eta_str}"
            if video_title:
                if playlist_count > 0 and playlist_index > 0:
                    status_msg = f"Downloading video {playlist_index}/{playlist_count}: {video_title} - {p}{eta_str}"
                else:
                    status_msg = f"Downloading: {video_title} - {p}{eta_str}"
                    
            try:
                progress = int(float(p.replace('%', '')))
                progress_callback(progress, status_msg)
            except:
                progress_callback(0, status_msg)
        elif d['status'] == 'finished':
            # Get video information
            filename = d.get('filename', '').split(os.sep)[-1]
            video_title = d.get('info_dict', {}).get('title', filename)
            
            # For playlists, show which video out of total
            playlist_count = d.get('info_dict', {}).get('playlist_count', 0)
            playlist_index = d.get('info_dict', {}).get('playlist_index', 0)
            
            if playlist_count > 0 and playlist_index > 0:
                status_msg = f"Processing video {playlist_index}/{playlist_count}: {video_title}"
            else:
                status_msg = f"Processing file: {video_title}"
                
            progress_callback(100, status_msg)

    def get_video_info(self, url, fetch_progress_callback=None):
        """Get information about a YouTube video."""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
                'simulate': True,
                'logger': yt_dlp_logger,  # Use our filtered logger
                'no_color': True,  # Disable color codes in output
                'format': 'bv*+ba/b',  # Use the improved format selector
            }
            
            print(f"Fetching video info for {url}")
            
            # Update callback if provided
            if fetch_progress_callback:
                fetch_progress_callback(0, 1, "Fetching video information...", True)
                # Small delay to let UI update
                time.sleep(0.2)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if fetch_progress_callback:
                    fetch_progress_callback(0, 1, "Retrieving video details from YouTube...", True)
                
                info = ydl.extract_info(url, download=False)
                
                # Update callback for completion
                if fetch_progress_callback:
                    fetch_progress_callback(1, 1, "Video information retrieved", True)
                
                if not info:
                    print("Failed to get video info")
                    return None
                
                # Format duration into hours, minutes, seconds
                duration_seconds = info.get('duration', 0)
                hours, remainder = divmod(duration_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if hours > 0:
                    duration_formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_formatted = f"{minutes}:{seconds:02d}"
                
                return {
                    'title': info.get('title', 'Unknown Video'),
                    'channel': info.get('uploader', 'Unknown Channel'),
                    'duration': duration_seconds,
                    'duration_formatted': duration_formatted,
                    'thumbnail': info.get('thumbnail'),
                    'view_count': info.get('view_count'),
                    'upload_date': info.get('upload_date'),
                    'id': info.get('id', ''),
                    'is_live': info.get('is_live', False),
                }
            
            return None
        except Exception as e:
            print(f"Error getting video info: {str(e)}")
            if fetch_progress_callback:
                fetch_progress_callback(0, 0, f"Error: {str(e)}", True)
            return None

    def pause_download(self):
        """Pause the current download."""
        if self.is_downloading and not self.is_paused:
            self.is_paused = True
            # The actual pausing will be handled in the download loop
            print("Download paused")
            return True
        return False
    
    def resume_download(self, progress_callback=None):
        """Resume a paused download."""
        if self.is_paused:
            self.is_paused = False
            # If we have all the necessary info to resume
            if (self.current_url and self.current_output_path and 
                self.current_quality is not None):
                print("Resuming download...")
                # Resume download in a separate thread
                resume_thread = threading.Thread(
                    target=self.download_video,
                    args=(
                        self.current_url,
                        self.current_quality,
                        self.current_output_path,
                        progress_callback,
                        self.current_playlist_option,
                        self.current_playlist_items
                    ),
                    kwargs={"resume": True}
                )
                resume_thread.daemon = True
                resume_thread.start()
                return True
            else:
                print("Cannot resume download: missing information")
        return False
        
    def cancel_download(self):
        """Cancel the current download."""
        if self.is_downloading:
            self.should_cancel = True
            self.is_paused = False
            # The actual cancellation will be handled in the download loop
            print("Download cancelled")
            return True
        return False
    
    def reset_download_state(self):
        """Reset the download state variables."""
        self.is_downloading = False
        self.is_paused = False
        self.should_cancel = False
        self.current_url = None
        self.current_output_path = None
        self.current_quality = None
        self.current_playlist_option = None
        self.current_playlist_items = None
        self.downloaded_bytes = 0
        self.resume_file = None

    def download_youtube_playlist(self, url, quality="best", output_path=None, progress_callback=None):
        """Download all videos in a YouTube playlist, attempting to merge audio and video."""
        try:
            q_val = self.quality_options.get(quality, "best")

            # Handle audio-only downloads
            if q_val == "audio":
                format_selector = 'bestaudio/best'  # Select best audio quality
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # More robust format selection that better handles SABR streaming issues
                if q_val == "best":
                    # Try progressive formats first if available, then resort to best available
                    format_selector = 'bv*+ba/b'
                else:
                    # Be more specific about quality but still handle SABR issues
                    format_selector = f'bv[height<={q_val}]+ba/b[height<={q_val}]'
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = []

            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4' if q_val != "audio" else None,  # Don't merge for audio-only
                'continuedl': True,  # Continue partially downloaded files
                'logger': yt_dlp_logger,  # Use our filtered logger
                'overwrites': False,  # Don't overwrite files
                'no_color': True,  # Disable color codes in output
                'postprocessors': postprocessors,  # Add postprocessors for audio conversion
            }
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    playlist_title = info.get('title')
                    entries = info.get('entries', [])
                    total_videos = len(entries)
                    print(f"Playlist: {playlist_title}")
                    print(f"Total Videos: {total_videos}")
                    
                    if progress_callback:
                        progress_callback(0, f"Starting playlist download: {playlist_title} ({total_videos} videos)")
                    
                    # Check for cancel before starting
                    if self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
                    
                    # Download the playlist
                    ydl.download([url])
                    
                    # If download was paused, return False to prevent reset
                    if self.is_paused:
                        return False
                    
                    # If download completed successfully
                    if progress_callback and not self.should_cancel:
                        progress_callback(100, "Playlist download complete")
                        print(f"Downloaded playlist successfully to {output_path}")
                        return True
                    elif self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube playlist: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False

    def download_youtube_playlist_items(self, url, quality="best", output_path=None, 
                                      progress_callback=None, video_indices=None):
        """Download specific videos from a YouTube playlist by their indices."""
        try:
            if not video_indices:
                return False
                
            q_val = self.quality_options.get(quality, "best")
            
            # Handle audio-only downloads
            if q_val == "audio":
                format_selector = 'bestaudio/best'  # Select best audio quality
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # More robust format selection that better handles SABR streaming issues
                if q_val == "best":
                    # Try progressive formats first if available, then resort to best available
                    format_selector = 'bv*+ba/b'
                else:
                    # Be more specific about quality but still handle SABR issues
                    format_selector = f'bv[height<={q_val}]+ba/b[height<={q_val}]'
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = []
            
            # Convert indices to string format for yt-dlp (1-based)
            playlist_items = ','.join(map(str, video_indices))
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4' if q_val != "audio" else None,  # Don't merge for audio-only
                'playlist_items': playlist_items,
                'continuedl': True,  # Continue partially downloaded files
                'logger': yt_dlp_logger,  # Use our filtered logger
                'overwrites': False,  # Don't overwrite files
                'no_color': True,  # Disable color codes in output
                'postprocessors': postprocessors,  # Add postprocessors for audio conversion
            }
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    playlist_title = info.get('title')
                    selected_count = len(video_indices)
                    if progress_callback:
                        progress_callback(0, f"Starting download of {selected_count} selected videos from: {playlist_title}")
                    
                    # Check for cancel before starting
                    if self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
                    
                    # Download the videos
                    ydl.download([url])
                    
                    # If download was paused, return False to prevent reset
                    if self.is_paused:
                        return False
                    
                    # If download completed successfully
                    if progress_callback and not self.should_cancel:
                        progress_callback(100, "Download complete")
                        print(f"Downloaded selected videos successfully to {output_path}")
                        return True
                    elif self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube playlist items: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False
    
    def download_youtube_playlist_range(self, url, quality="best", output_path=None, 
                                      progress_callback=None, range_str=None):
        """Download a range of videos from a YouTube playlist."""
        try:
            if not range_str:
                return False
                
            # Parse range string (e.g., "1-5")
            try:
                start, end = map(int, range_str.split('-'))
                if start < 1:
                    start = 1
            except:
                print("Invalid range format. Use start-end (e.g., 1-5)")
                return False
                
            q_val = self.quality_options.get(quality, "best")
            
            # Handle audio-only downloads
            if q_val == "audio":
                format_selector = 'bestaudio/best'  # Select best audio quality
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # More robust format selection that better handles SABR streaming issues
                if q_val == "best":
                    # Try progressive formats first if available, then resort to best available
                    format_selector = 'bv*+ba/b'
                else:
                    # Be more specific about quality but still handle SABR issues
                    format_selector = f'bv[height<={q_val}]+ba/b[height<={q_val}]'
                output_template = os.path.join(output_path, '%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s')
                postprocessors = []
            
            # Format the range for yt-dlp
            playlist_items = f"{start}-{end}"
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': output_template,
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4' if q_val != "audio" else None,  # Don't merge for audio-only
                'playlist_items': playlist_items,
                'continuedl': True,  # Continue partially downloaded files
                'logger': yt_dlp_logger,  # Use our filtered logger
                'overwrites': False,  # Don't overwrite files
                'no_color': True,  # Disable color codes in output
                'postprocessors': postprocessors,  # Add postprocessors for audio conversion
            }
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    playlist_title = info.get('title')
                    total_in_range = end - start + 1
                    if progress_callback:
                        progress_callback(0, f"Starting download of videos {start}-{end} ({total_in_range} videos) from: {playlist_title}")
                    
                    # Check for cancel before starting
                    if self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
                    
                    # Download the videos
                    ydl.download([url])
                    
                    # If download was paused, return False to prevent reset
                    if self.is_paused:
                        return False
                    
                    # If download completed successfully
                    if progress_callback and not self.should_cancel:
                        progress_callback(100, "Download complete")
                        print(f"Downloaded videos {start}-{end} successfully to {output_path}")
                        return True
                    elif self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube playlist range: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False

    def download_web_video(self, url, output_path=None, progress_callback=None):
        """Download a video from a non-YouTube web URL."""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Extract filename from URL or Content-Disposition header
            if "Content-Disposition" in response.headers:
                content_disposition = response.headers["Content-Disposition"]
                filename = re.findall("filename=(.+)", content_disposition)[0].strip('"')
            else:
                filename = os.path.basename(urllib.parse.urlparse(url).path)
                
            if not filename:
                filename = "download.mp4"
            
            file_path = os.path.join(output_path, filename)
            
            # Create progress bar
            total_size = int(response.headers.get('content-length', 0))
            if progress_callback:
                progress_callback(0, f"Starting download: {filename}")
            
            # Check if file exists and we're resuming
            mode = 'ab' if os.path.exists(file_path) and self.is_paused else 'wb'
            downloaded = os.path.getsize(file_path) if mode == 'ab' else 0
            
            # If resuming, skip already downloaded chunks
            if downloaded > 0 and mode == 'ab':
                headers = {'Range': f'bytes={downloaded}-'}
                response = requests.get(url, stream=True, headers=headers)
            
            with open(file_path, mode) as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    # Check for cancel
                    if self.should_cancel:
                        if progress_callback:
                            progress_callback(0, "Download cancelled")
                        return False
                    
                    # Check for pause
                    if self.is_paused:
                        if progress_callback:
                            progress = int((downloaded / total_size) * 100) if total_size > 0 else 0
                            progress_callback(progress, "Download paused")
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            progress = int(downloaded * 100 / total_size)
                            progress_callback(progress, f"Downloading: {progress}%")
            
            if progress_callback and not self.should_cancel:
                progress_callback(100, "Download complete")
                print(f"Downloaded successfully to {file_path}")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error downloading web video: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False


class DownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        self.root.geometry("700x500")  # Larger window for more info
        self.root.resizable(True, True)
        
        self.downloader = VideoDownloader()
        self.playlist_info = None
        self.video_info = None
        self.playlist_option = tk.StringVar(value="full")
        self.selected_videos = []
        self.range_var = tk.StringVar()
        self.is_downloading = False
        
        self.setup_ui()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # URL input
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(url_frame, text="Video URL:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Add a "Fetch Info" button next to URL entry
        fetch_btn = ttk.Button(url_frame, text="Fetch Info", command=self.check_url)
        fetch_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind the entry to the check_url method when Enter key is pressed
        url_entry.bind("<Return>", self.check_url)
        
        # Video/Playlist info frame (initially hidden)
        self.info_frame = ttk.LabelFrame(main_frame, text="Media Information", padding=10)
        
        # Create widgets for the info frame
        self.info_title_var = tk.StringVar(value="")
        self.info_details_var = tk.StringVar(value="")
        self.info_duration_var = tk.StringVar(value="")
        
        # Title with larger font
        title_label = ttk.Label(self.info_frame, textvariable=self.info_title_var, 
                             font=('Helvetica', 12, 'bold'), wraplength=650)
        title_label.pack(fill=tk.X, pady=(0, 5), anchor=tk.W)
        
        # Details
        details_label = ttk.Label(self.info_frame, textvariable=self.info_details_var)
        details_label.pack(fill=tk.X, pady=2, anchor=tk.W)
        
        # Duration
        duration_label = ttk.Label(self.info_frame, textvariable=self.info_duration_var)
        duration_label.pack(fill=tk.X, pady=2, anchor=tk.W)
        
        # Quality selection
        quality_frame = ttk.Frame(main_frame)
        quality_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(quality_frame, text="Video Quality:").pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="highest")
        quality_combo = ttk.Combobox(
            quality_frame, 
            textvariable=self.quality_var,
            values=["2160p", "1440p", "1080p", "720p", "480p", "360p", "highest", "audio only"],
            state="readonly",
            width=10
        )
        quality_combo.pack(side=tk.LEFT, padx=5)
        
        # Store reference to quality_frame for later use
        self.quality_frame = quality_frame
        
        # Playlist options frame (initially hidden)
        self.playlist_frame = ttk.LabelFrame(main_frame, text="Playlist Options", padding=5)
        
        # Playlist radio buttons
        playlist_radio_frame = ttk.Frame(self.playlist_frame)
        playlist_radio_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Radiobutton(playlist_radio_frame, text="Download entire playlist", 
                      variable=self.playlist_option, value="full",
                      command=self.update_playlist_options).pack(anchor=tk.W)
        
        ttk.Radiobutton(playlist_radio_frame, text="Download specific videos", 
                      variable=self.playlist_option, value="specific",
                      command=self.update_playlist_options).pack(anchor=tk.W)
        
        ttk.Radiobutton(playlist_radio_frame, text="Download range of videos", 
                      variable=self.playlist_option, value="range",
                      command=self.update_playlist_options).pack(anchor=tk.W)
        
        # Range entry (initially hidden)
        self.range_frame = ttk.Frame(self.playlist_frame)
        ttk.Label(self.range_frame, text="Enter range (e.g. 1-5):").pack(side=tk.LEFT)
        ttk.Entry(self.range_frame, textvariable=self.range_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Video selection button (initially hidden)
        self.select_videos_frame = ttk.Frame(self.playlist_frame)
        self.select_btn = ttk.Button(self.select_videos_frame, text="Select Videos", 
                                  command=self.select_playlist_videos)
        self.select_btn.pack(pady=5)
        
        # Output path
        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(path_frame, text="Save to:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self.downloader.download_path)
        ttk.Entry(path_frame, textvariable=self.path_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Browse", command=self.browse_path).pack(side=tk.LEFT, padx=5)
        
        # Download and control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        self.download_btn = ttk.Button(button_frame, text="Download", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        
        # Pause, Resume, Cancel buttons (initially disabled)
        self.pause_btn = ttk.Button(button_frame, text="Pause", command=self.pause_download, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.resume_btn = ttk.Button(button_frame, text="Resume", command=self.resume_download, state=tk.DISABLED)
        self.resume_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.cancel_download, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar and status
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.status_var).pack(fill=tk.X, padx=5)
    
    def update_download_controls(self, downloading=False, paused=False):
        """Update the state of download control buttons based on current download state."""
        if downloading and not paused:
            # Download in progress
            self.download_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
            self.resume_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
            self.is_downloading = True
        elif downloading and paused:
            # Download paused
            self.download_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED)
            self.resume_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.NORMAL)
            self.is_downloading = True
        else:
            # No download in progress
            self.download_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.resume_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.DISABLED)
            self.is_downloading = False
    
    def pause_download(self):
        """Pause the current download."""
        if self.downloader.pause_download():
            self.status_var.set("Download paused")
            self.update_download_controls(downloading=True, paused=True)
    
    def resume_download(self):
        """Resume a paused download."""
        if self.downloader.resume_download(
            progress_callback=lambda p, s: self.root.after(0, self.update_progress, p, s)
        ):
            self.status_var.set("Resuming download...")
            self.update_download_controls(downloading=True, paused=False)
    
    def cancel_download(self):
        """Cancel the current download."""
        if self.downloader.cancel_download():
            self.status_var.set("Download cancelled")
            self.update_download_controls(downloading=False)
    
    def check_url(self, event=None):
        url = self.url_var.get().strip()
        if not url:
            return
            
        if not self.downloader.validate_url(url):
            self.status_var.set("Invalid URL format")
            return
        
        # Show loading message and disable download button
        self.status_var.set("Fetching information... Please wait. This may take a moment.")
        self.download_btn.config(state=tk.DISABLED)
        
        # Set progress bar to indeterminate mode for fetching
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(15)  # Start pulsing animation
        self.root.update_idletasks()
        
        # Clear previous info
        self.playlist_info = None
        self.video_info = None
        self.info_frame.pack_forget()
        self.playlist_frame.pack_forget()
        
        # Get info in a separate thread to prevent UI freeze
        if self.downloader.is_youtube_url(url) and self.downloader.is_playlist(url):
            threading.Thread(target=self._get_playlist_info, args=(url,), daemon=True).start()
        elif self.downloader.is_youtube_url(url):
            threading.Thread(target=self._get_video_info, args=(url,), daemon=True).start()
        else:
            # For non-YouTube URLs, just enable the download button
            self.progress_bar.stop()  # Stop the animation
            self.progress_bar.config(mode="determinate")  # Reset to determinate mode
            self.progress_var.set(0)  # Reset progress
            self.status_var.set("Ready to download web video")
            self.download_btn.config(state=tk.NORMAL)
    
    def update_progress(self, progress, status):
        """Update progress bar and status text."""
        self.progress_var.set(progress)
        self.status_var.set(status)
        
        # Update control buttons based on status text
        if "paused" in status.lower():
            self.update_download_controls(downloading=True, paused=True)
        elif "complete" in status.lower() or "cancelled" in status.lower() or "error" in status.lower():
            self.update_download_controls(downloading=False)
        elif progress > 0:
            self.update_download_controls(downloading=True, paused=False)
            
        self.root.update_idletasks()
    
    def start_download(self):
        url = self.url_var.get().strip()
        quality = self.quality_var.get()
        output_path = self.path_var.get()
        
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL")
            return
            
        if not self.downloader.validate_url(url):
            messagebox.showerror("Error", "Invalid URL format")
            return
        
        # Prepare playlist options if needed
        playlist_option = None
        playlist_items = None
        
        if self.downloader.is_youtube_url(url) and self.downloader.is_playlist(url):
            option = self.playlist_option.get()
            if option == "specific":
                if not self.selected_videos:
                    messagebox.showerror("Error", "Please select videos from the playlist")
                    return
                playlist_option = "specific"
                playlist_items = self.selected_videos
            elif option == "range":
                range_str = self.range_var.get().strip()
                if not range_str or not re.match(r'^\d+-\d+$', range_str):
                    messagebox.showerror("Error", "Please enter a valid range (e.g. 1-5)")
                    return
                playlist_option = "range"
                playlist_items = range_str
            else:  # "full"
                playlist_option = "full"
        
        # Update button states
        self.update_download_controls(downloading=True, paused=False)
        self.status_var.set("Preparing download...")
        self.progress_var.set(0)
        
        # Run download in a separate thread to prevent UI freeze
        download_thread = threading.Thread(
            target=self._download_thread,
            args=(url, quality, output_path, playlist_option, playlist_items)
        )
        download_thread.daemon = True
        download_thread.start()
    
    def _download_thread(self, url, quality, output_path, playlist_option=None, playlist_items=None):
        success = self.downloader.download_video(
            url, 
            quality, 
            output_path,
            progress_callback=lambda p, s: self.root.after(0, self.update_progress, p, s),
            playlist_option=playlist_option,
            playlist_items=playlist_items
        )
        
        def finish():
            if not self.downloader.is_paused:
                self.update_download_controls(downloading=False)
                if success:
                    messagebox.showinfo("Success", "Download completed successfully!")
                else:
                    messagebox.showerror("Error", "Failed to download. See console for details.")
        
        self.root.after(0, finish)

    def _get_video_info(self, url):
        try:
            # Start a timer for ETA
            start_time = time.time()
            
            # Set progress bar to indeterminate mode initially
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(15)  # Start pulsing animation
            
            # Create a label just for showing video fetch progress
            fetch_status_frame = ttk.Frame(self.root)
            fetch_status_frame.pack(fill=tk.X, padx=5, pady=5, before=self.progress_bar.master)
            fetch_status_label = ttk.Label(fetch_status_frame, text="", font=('Helvetica', 10))
            fetch_status_label.pack(fill=tk.X, padx=5)
            
            # Define a progress callback that will update the UI
            def fetch_progress_callback(current, total, status_text, force_update=False):
                # Calculate elapsed time
                elapsed = time.time() - start_time
                
                # If we have a total, show percentage progress
                if total > 0:
                    # Switch to determinate mode
                    if self.progress_bar['mode'] == 'indeterminate':
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="determinate")
                    
                    # Calculate and set progress percentage
                    percent = min(100, int((current / total) * 100))
                    self.progress_var.set(percent)
                    
                    # For videos, show count and percentage
                    if current > 0:
                        # Calculate estimated time remaining
                        if current > 1 and total > 0:
                            videos_left = total - current
                            time_per_video = elapsed / current
                            eta_seconds = videos_left * time_per_video
                            
                            # Format ETA
                            if eta_seconds < 60:
                                eta_text = f"ETA: {int(eta_seconds)}s"
                            else:
                                eta_minutes = int(eta_seconds // 60)
                                eta_secs = int(eta_seconds % 60)
                                eta_text = f"ETA: {eta_minutes}m {eta_secs}s"
                        else:
                            eta_text = "Calculating ETA..."
                        
                        # Main status shows progress percentage and ETA
                        main_status = f"Fetched {current} out of {total} videos ({percent}%) - {eta_text}"
                        self.status_var.set(main_status)
                        
                        # Status label shows the current video being processed
                        if "Processing video" in status_text:
                            # Split out just the video title
                            parts = status_text.split(": ", 1)
                            if len(parts) > 1:
                                video_title = parts[1]
                                fetch_status_label.config(text=f"Fetching: {video_title}")
                            else:
                                fetch_status_label.config(text=f"Fetching video {current} of {total}")
                        else:
                            fetch_status_label.config(text=f"Fetching video {current} of {total}")
                    else:
                        # Just show standard status
                        self.status_var.set(f"{status_text}")
                        fetch_status_label.config(text="Preparing to fetch videos...")
                else:
                    # Just show the status text
                    self.status_var.set(f"{status_text}")
                    fetch_status_label.config(text="Preparing to fetch videos...")
                
                # Force immediate UI update to ensure the status and progress are visible
                if force_update:
                    self.root.update()  # More aggressive update
                else:
                    self.root.update_idletasks()
                    
                # Log to console without the eta_text variable if it's not defined
                if current > 1 and total > 0:
                    print(f"Progress update: {status_text} - {eta_text if 'eta_text' in locals() else ''}")
                else:
                    print(f"Progress update: {status_text}")
            
            # Fetch the video info with our callback
            self.video_info = self.downloader.get_video_info(url, fetch_progress_callback)
            
            # Clean up the fetch status frame
            fetch_status_frame.destroy()
            
            # Stop the progress bar animation
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_var.set(0)
            
            # Immediately clear the "Fetching video info..." message
            self.status_var.set("")
            self.root.update_idletasks()
            
            if self.video_info:
                # Update info frame
                self.info_title_var.set(self.video_info.get('title', 'Unknown Video'))
                self.info_details_var.set(f"Channel: {self.video_info.get('channel', 'Unknown')}")
                self.info_duration_var.set(f"Duration: {self.video_info.get('duration_formatted', '0:00')}")
                
                # Show info frame - fix the placement by using quality_frame as reference
                self.info_frame.pack(fill=tk.X, padx=5, pady=5, after=self.quality_frame)
                
                # Update status - remove the fetching reference
                self.status_var.set(f"Ready to download: {self.video_info.get('title')}")
            else:
                self.status_var.set("Could not get video information. Try again.")
        except Exception as e:
            print(f"Error in _get_video_info: {str(e)}")
            self.status_var.set(f"Error getting video info: {str(e)}")
        finally:
            # Re-enable download button
            self.download_btn.config(state=tk.NORMAL)
            # Make sure progress bar is properly reset
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_var.set(0)
            # Remove fetch status frame if it exists
            if 'fetch_status_frame' in locals() and fetch_status_frame.winfo_exists():
                fetch_status_frame.destroy()
    
    def _get_playlist_info(self, url):
        try:
            # Start a timer for ETA
            start_time = time.time()
            
            # Set progress bar to indeterminate mode initially
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(15)  # Start pulsing animation
            
            # Create a label just for showing playlist fetch progress
            fetch_status_frame = ttk.Frame(self.root)
            fetch_status_frame.pack(fill=tk.X, padx=5, pady=5, before=self.progress_bar.master)
            fetch_status_label = ttk.Label(fetch_status_frame, text="", font=('Helvetica', 10))
            fetch_status_label.pack(fill=tk.X, padx=5)
            
            # Define a progress callback that will update the UI
            def fetch_progress_callback(current, total, status_text, force_update=False):
                # Calculate elapsed time
                elapsed = time.time() - start_time
                
                # If we have a total, show percentage progress
                if total > 0:
                    # Switch to determinate mode
                    if self.progress_bar['mode'] == 'indeterminate':
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="determinate")
                    
                    # Calculate and set progress percentage
                    percent = min(100, int((current / total) * 100))
                    self.progress_var.set(percent)
                    
                    # For videos, show count and percentage
                    if current > 0:
                        # Calculate estimated time remaining
                        if current > 1 and total > 0:
                            videos_left = total - current
                            time_per_video = elapsed / current
                            eta_seconds = videos_left * time_per_video
                            
                            # Format ETA
                            if eta_seconds < 60:
                                eta_text = f"ETA: {int(eta_seconds)}s"
                            else:
                                eta_minutes = int(eta_seconds // 60)
                                eta_secs = int(eta_seconds % 60)
                                eta_text = f"ETA: {eta_minutes}m {eta_secs}s"
                        else:
                            eta_text = "Calculating ETA..."
                        
                        # Main status shows progress percentage and ETA
                        main_status = f"Fetched {current} out of {total} videos ({percent}%) - {eta_text}"
                        self.status_var.set(main_status)
                        
                        # Status label shows the current video being processed
                        if "Processing video" in status_text:
                            # Split out just the video title
                            parts = status_text.split(": ", 1)
                            if len(parts) > 1:
                                video_title = parts[1]
                                fetch_status_label.config(text=f"Fetching: {video_title}")
                            else:
                                fetch_status_label.config(text=f"Fetching video {current} of {total}")
                        else:
                            fetch_status_label.config(text=f"Fetching video {current} of {total}")
                    else:
                        # Just show standard status
                        self.status_var.set(f"{status_text}")
                        fetch_status_label.config(text="Preparing to fetch videos...")
                else:
                    # Just show the status text
                    self.status_var.set(f"{status_text}")
                    fetch_status_label.config(text="Preparing to fetch videos...")
                
                # Force immediate UI update to ensure the status and progress are visible
                if force_update:
                    self.root.update()  # More aggressive update
                else:
                    self.root.update_idletasks()
                    
                # Log to console without the eta_text variable if it's not defined
                if current > 1 and total > 0:
                    print(f"Progress update: {status_text} - {eta_text if 'eta_text' in locals() else ''}")
                else:
                    print(f"Progress update: {status_text}")
            
            # Fetch the playlist info with our callback
            self.playlist_info = self.downloader.get_playlist_info(url, fetch_progress_callback)
            
            # Clean up the fetch status frame
            fetch_status_frame.destroy()
            
            # Stop the progress bar animation
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_var.set(0)
            
            # Immediately clear the "Fetching playlist info..." message
            self.status_var.set("")
            self.root.update_idletasks()
            
            if self.playlist_info and self.playlist_info.get('videos'):
                # Update info frame
                self.info_title_var.set(self.playlist_info.get('title', 'Unknown Playlist'))
                self.info_details_var.set(f"Videos: {self.playlist_info.get('total_videos', 0)}")
                self.info_duration_var.set(f"Total duration: {self.playlist_info.get('total_duration_str', '0:00')}")
                
                # Show info frame and playlist options - fix the placement
                self.info_frame.pack(fill=tk.X, padx=5, pady=5, after=self.quality_frame)
                self.playlist_frame.pack(fill=tk.X, padx=5, pady=5, after=self.info_frame)
                self.update_playlist_options()
                
                # Show playlist info in status with no mention of "fetching"
                video_count = len(self.playlist_info.get('videos', []))
                self.status_var.set(f"Ready to download: {self.playlist_info.get('title')} ({video_count} videos)")
            else:
                self.status_var.set("Could not get playlist information. Try again.")
        except Exception as e:
            print(f"Error in _get_playlist_info: {str(e)}")
            self.status_var.set(f"Error getting playlist info: {str(e)}")
        finally:
            # Re-enable download button
            self.download_btn.config(state=tk.NORMAL)
            # Make sure progress bar is properly reset
            self.progress_bar.stop()
            self.progress_bar.config(mode="determinate")
            self.progress_var.set(0)
            # Remove fetch status frame if it exists
            if 'fetch_status_frame' in locals() and fetch_status_frame.winfo_exists():
                fetch_status_frame.destroy()
    
    def update_playlist_options(self):
        # Hide all option-specific frames first
        self.range_frame.pack_forget()
        self.select_videos_frame.pack_forget()
        
        option = self.playlist_option.get()
        if option == "range":
            self.range_frame.pack(fill=tk.X, padx=5, pady=5)
        elif option == "specific":
            self.select_videos_frame.pack(fill=tk.X, padx=5, pady=5)
    
    def select_playlist_videos(self):
        if not self.playlist_info or not self.playlist_info.get('videos'):
            messagebox.showerror("Error", "No playlist information available")
            return
            
        # Create a dialog to select videos
        select_dialog = tk.Toplevel(self.root)
        select_dialog.title("Select Videos")
        select_dialog.geometry("800x600")  # Even larger dialog for better visibility
        select_dialog.transient(self.root)
        select_dialog.grab_set()
        select_dialog.resizable(True, True)  # Allow resizing
        
        # Create a frame with scrollable content
        frame = ttk.Frame(select_dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Add a heading
        ttk.Label(frame, text=f"Select videos to download from: {self.playlist_info.get('title', 'Playlist')}", 
                font=('Helvetica', 12, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        # Add playlist details
        details_frame = ttk.Frame(frame)
        details_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(details_frame, text=f"Total videos: {self.playlist_info.get('total_videos', 0)}").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(details_frame, text=f"Total duration: {self.playlist_info.get('total_duration_str', '0:00')}").pack(side=tk.LEFT)
        
        # Create a canvas with scrollbar for the video list
        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create header for columns
        header_frame = ttk.Frame(frame)
        header_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(header_frame, text="#", width=5, anchor=tk.W, font=('Helvetica', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header_frame, text="Title", anchor=tk.W, font=('Helvetica', 10, 'bold')).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(header_frame, text="Duration", width=10, anchor=tk.E, font=('Helvetica', 10, 'bold')).pack(side=tk.RIGHT)
        
        # Separator below header
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(5, 0))
        
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Add checkboxes for each video
        video_vars = []
        
        # Get the videos
        videos = self.playlist_info['videos']
        
        # Alternate row colors for better readability
        colors = ['#f0f0f0', 'white']
        
        for i, video in enumerate(videos):
            var = tk.BooleanVar(value=False)
            video_vars.append(var)
            
            # Create a frame for each video with alternating background color
            video_frame = ttk.Frame(scrollable_frame)
            video_frame.pack(fill=tk.X, pady=1, anchor=tk.W)
            
            # Get the video details
            index = video.get('index', i+1)
            title = video.get('title', f'Video {i+1}')
            duration_str = video.get('duration_str', '0:00')
            
            # Row content
            row_frame = ttk.Frame(video_frame)
            row_frame.pack(fill=tk.X, expand=True)
            
            # Set a different color for odd and even rows
            bg_color = colors[i % 2]
            
            # Index checkbox
            cb = ttk.Checkbutton(row_frame, text=f"{index}", variable=var, width=5)
            cb.pack(side=tk.LEFT, anchor=tk.W)
            
            # Title - use a fixed label instead of a StringVar for better compatibility
            title_text = title
            if len(title_text) > 60:
                title_text = title_text[:57] + "..."
                
            title_label = ttk.Label(row_frame, text=title_text, anchor=tk.W)
            title_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
            
            # Create tooltip for long titles
            def create_tooltip(widget, text):
                def show_tooltip(event):
                    x, y, _, _ = widget.bbox("all")
                    x += widget.winfo_rootx() + 25
                    y += widget.winfo_rooty() + 25
                    
                    # Create a toplevel window
                    tooltip = tk.Toplevel(widget)
                    tooltip.wm_overrideredirect(True)   
                    tooltip.wm_geometry(f"+{x}+{y}")
                    
                    label = ttk.Label(tooltip, text=text, wraplength=400, 
                                   background="#ffffe0", relief="solid", borderwidth=1)
                    label.pack()
                    
                    def hide_tooltip(event=None):
                        tooltip.destroy()
                    
                    widget.tooltip = tooltip
                    widget.bind("<Leave>", hide_tooltip)
                    
                if len(text) > 40:  # Only show tooltip for long titles
                    widget.bind("<Enter>", show_tooltip)
            
            create_tooltip(title_label, title)
            
            # Duration
            ttk.Label(row_frame, text=duration_str, width=10, anchor=tk.E).pack(side=tk.RIGHT)
            
            # Add a subtle separator between rows
            ttk.Separator(video_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(3, 0))
        
        # Configure the canvas to expand with the window
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Make sure the scrollable area adjusts when the window size changes
        canvas_frame.bind("<Configure>", lambda e: canvas.configure(width=e.width-20))
        
        # Allow mouse wheel scrolling - bind only to the canvas widget itself, not globally
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind mousewheel to the canvas only
        canvas.bind("<MouseWheel>", _on_mousewheel)
        
        # Selection controls
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        # Add Select All/None/Invert buttons
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        
        def select_all():
            for var in video_vars:
                var.set(True)
                
        def select_none():
            for var in video_vars:
                var.set(False)
                
        def invert_selection():
            for var in video_vars:
                var.set(not var.get())
                
        def select_range():
            try:
                range_input = simpledialog.askstring("Select Range", "Enter range (e.g. 1-5):",
                                                  parent=select_dialog)
                if not range_input:
                    return
                    
                # Parse range
                start, end = map(int, range_input.split('-'))
                if start < 1:
                    start = 1
                if end > len(video_vars):
                    end = len(video_vars)
                    
                # Select the range
                for i in range(len(video_vars)):
                    # +1 because range is 1-based, but our list is 0-based
                    is_in_range = start <= (i+1) <= end
                    video_vars[i].set(is_in_range)
            except:
                messagebox.showerror("Error", "Invalid range format. Use start-end (e.g., 1-5)", 
                                  parent=select_dialog)
        
        ttk.Button(btn_frame, text="Select All", command=select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Select None", command=select_none).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Invert Selection", command=invert_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Select Range...", command=select_range).pack(side=tk.LEFT, padx=5)
        
        # Selection info with a StringVar to update dynamically
        selection_info = tk.StringVar(value=f"Selected: 0/{len(video_vars)}")
        ttk.Label(btn_frame, textvariable=selection_info).pack(side=tk.RIGHT, padx=5)
        
        # Update selected count when checkbox state changes
        def update_selection_count(*args):
            selected = sum(1 for var in video_vars if var.get())
            selection_info.set(f"Selected: {selected}/{len(video_vars)}")
            
        # Bind checkboxes to update selection count
        for var in video_vars:
            var.trace_add("write", update_selection_count)
        
        # Add OK/Cancel buttons
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, pady=10)
        
        # Helper function to ensure cleanup when dialog is closed
        def cleanup_and_close():
            try:
                # Unbind mousewheel event to prevent errors after dialog closes
                canvas.unbind("<MouseWheel>")
            except Exception as e:
                print(f"Warning during cleanup: {e}")
            finally:
                select_dialog.destroy()
                
        def on_ok():
            # Get selected video indices (1-based for yt-dlp)
            self.selected_videos = [i+1 for i, var in enumerate(video_vars) if var.get()]
            cleanup_and_close()
            if self.selected_videos:
                self.status_var.set(f"Selected {len(self.selected_videos)} videos")
            else:
                self.status_var.set("No videos selected")
        
        def on_cancel():
            cleanup_and_close()
            self.status_var.set("Video selection cancelled")
        
        # Also handle window close event (X button)
        select_dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        ttk.Button(action_frame, text="Download Selected", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(action_frame, text="Cancel", command=on_cancel).pack(side=tk.RIGHT)
        
        # Wait for the dialog to close
        self.root.wait_window(select_dialog)
    
    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)


def main():
    parser = argparse.ArgumentParser(description="Video Downloader for YouTube and Web")
    parser.add_argument("url", nargs="?", help="URL of the video or playlist to download")
    parser.add_argument("-q", "--quality", 
                        choices=["2160p", "1440p", "1080p", "720p", "480p", "360p", "highest", "audio only"], 
                        default="highest", 
                        help="Preferred video quality or 'audio only' for audio download (default: highest)")
    parser.add_argument("-o", "--output", help="Output directory (default: Downloads folder)")
    parser.add_argument("-g", "--gui", action="store_true", help="Launch the GUI interface")
    parser.add_argument("--playlist-range", help="Download range of videos from playlist (e.g. 1-5)")
    parser.add_argument("--playlist-items", help="Download specific items from playlist (comma-separated indices, e.g. 1,3,5)")
    
    args = parser.parse_args()
    
    # Launch GUI if requested or if no URL is provided
    if args.gui or not args.url:
        root = tk.Tk()
        app = DownloaderGUI(root)
        root.mainloop()
        return
    
    # Command line mode
    downloader = VideoDownloader()
    output_path = args.output if args.output else downloader.download_path
    
    if not downloader.validate_url(args.url):
        print("Invalid URL. Please provide a valid URL.")
        return
    
    # Handle playlist options for command line
    playlist_option = None
    playlist_items = None
    
    if downloader.is_youtube_url(args.url) and downloader.is_playlist(args.url):
        if args.playlist_items:
            playlist_option = "specific"
            playlist_items = [int(i) for i in args.playlist_items.split(',')]
        elif args.playlist_range:
            playlist_option = "range"
            playlist_items = args.playlist_range
    
    downloader.download_video(args.url, args.quality, output_path, 
                            playlist_option=playlist_option, playlist_items=playlist_items)

if __name__ == "__main__":
    main()
