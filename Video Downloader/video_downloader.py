import os
import sys
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yt_dlp
import requests
# tqdm is used by the _progress_hook for yt-dlp and directly for web downloads
# from tqdm import tqdm # tqdm is not directly used, yt-dlp hook provides percentage
import urllib.parse # Changed from from urllib.parse import urlparse
import argparse
import threading
import colorama
import imageio_ffmpeg

colorama.init()

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
            "highest": "best"
        }
        self.ffmpeg_path = None
        try:
            self.ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            print(f"[WARN] Could not get FFmpeg path from imageio-ffmpeg: {e}")
            print("[WARN] yt-dlp will try to find FFmpeg in system PATH. Merging high-quality streams might fail if not found.")

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

    def download_video(self, url, quality="best", output_path=None, progress_callback=None):
        """Download video from YouTube or web."""
        if not output_path:
            output_path = self.download_path
            
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        if self.is_youtube_url(url):
            if self.is_playlist(url):
                return self.download_youtube_playlist(url, quality, output_path, progress_callback)
            else:
                return self.download_youtube_video(url, quality, output_path, progress_callback)
        else:
            return self.download_web_video(url, output_path, progress_callback)

    def download_youtube_video(self, url, quality="best", output_path=None, progress_callback=None):
        """Download a YouTube video with selected quality, attempting to merge audio and video."""
        try:
            q_val = self.quality_options.get(quality, "best")
            
            if q_val == "best":
                format_selector = 'bestvideo+bestaudio/best' # Best video + best audio, fallback to best overall
            else:
                format_selector = f'bestvideo[height<={q_val}]+bestaudio/best[height<={q_val}]' # Best video up to q_val + best audio, fallback to best pre-muxed at q_val

            ydl_opts = {
                'format': format_selector,
                'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4', # Attempt to merge into MP4
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
                    
                    ydl.download([url])
                    
                    if progress_callback:
                        progress_callback(100, "Download complete")
                    print(f"Downloaded successfully to {output_path}")
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube video: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False

    def download_youtube_playlist(self, url, quality="best", output_path=None, progress_callback=None):
        """Download all videos in a YouTube playlist, attempting to merge audio and video."""
        try:
            q_val = self.quality_options.get(quality, "best")

            if q_val == "best":
                format_selector = 'bestvideo+bestaudio/best'
            else:
                format_selector = f'bestvideo[height<={q_val}]+bestaudio/best[height<={q_val}]'

            ydl_opts = {
                'format': format_selector,
                'outtmpl': os.path.join(output_path, '%(playlist_title)s/%(title)s.%(ext)s'),
                'progress_hooks': [lambda d: self._progress_hook(d, progress_callback)],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'merge_output_format': 'mp4',
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
                    
                    ydl.download([url])
                    
                    if progress_callback:
                        progress_callback(100, "Playlist download complete")
                    
                    print(f"Downloaded playlist successfully to {output_path}")
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error downloading YouTube playlist: {str(e)}")
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
            
            with open(file_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            progress = int(downloaded * 100 / total_size)
                            progress_callback(progress, f"Downloading: {progress}%")
            
            if progress_callback:
                progress_callback(100, "Download complete")
            
            print(f"Downloaded successfully to {file_path}")
            return True
            
        except Exception as e:
            print(f"Error downloading web video: {str(e)}")
            if progress_callback:
                progress_callback(0, f"Error: {str(e)}")
            return False
    
    def _progress_hook(self, d, progress_callback):
        if not progress_callback:
            return
            
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').strip()
            try:
                progress = int(float(p.replace('%', '')))
                progress_callback(progress, f"Downloading: {p}")
            except:
                progress_callback(0, f"Downloading...")
        elif d['status'] == 'finished':
            progress_callback(100, "Processing file...")


class DownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader")
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        
        self.downloader = VideoDownloader()
        
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
        ttk.Entry(url_frame, textvariable=self.url_var, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Quality selection
        quality_frame = ttk.Frame(main_frame)
        quality_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(quality_frame, text="Video Quality:").pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="highest")
        quality_combo = ttk.Combobox(
            quality_frame, 
            textvariable=self.quality_var,
            values=["2160p", "1440p", "1080p", "720p", "480p", "360p", "highest"],
            state="readonly",
            width=10
        )
        quality_combo.pack(side=tk.LEFT, padx=5)
        
        # Output path
        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(path_frame, text="Save to:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self.downloader.download_path)
        ttk.Entry(path_frame, textvariable=self.path_var, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Browse", command=self.browse_path).pack(side=tk.LEFT, padx=5)
        
        # Download button
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        self.download_btn = ttk.Button(button_frame, text="Download", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar and status
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.status_var).pack(fill=tk.X, padx=5)
    
    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)
    
    def update_progress(self, progress, status):
        self.progress_var.set(progress)
        self.status_var.set(status)
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
            
        self.download_btn.config(state=tk.DISABLED)
        self.status_var.set("Preparing download...")
        self.progress_var.set(0)
        
        # Run download in a separate thread to prevent UI freeze
        download_thread = threading.Thread(
            target=self._download_thread,
            args=(url, quality, output_path)
        )
        download_thread.daemon = True
        download_thread.start()
    
    def _download_thread(self, url, quality, output_path):
        success = self.downloader.download_video(
            url, 
            quality, 
            output_path,
            progress_callback=lambda p, s: self.root.after(0, self.update_progress, p, s)
        )
        
        def finish():
            self.download_btn.config(state=tk.NORMAL)
            if success:
                messagebox.showinfo("Success", "Download completed successfully!")
            else:
                messagebox.showerror("Error", "Failed to download. See console for details.")
        
        self.root.after(0, finish)


def main():
    parser = argparse.ArgumentParser(description="Video Downloader for YouTube and Web")
    parser.add_argument("url", nargs="?", help="URL of the video or playlist to download")
    parser.add_argument("-q", "--quality", 
                        choices=["2160p", "1440p", "1080p", "720p", "480p", "360p", "highest"], 
                        default="highest", 
                        help="Preferred video quality (default: highest)")
    parser.add_argument("-o", "--output", help="Output directory (default: Downloads folder)")
    parser.add_argument("-g", "--gui", action="store_true", help="Launch the GUI interface")
    
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
    
    downloader.download_video(args.url, args.quality, output_path)

if __name__ == "__main__":
    main()
