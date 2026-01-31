"""Video and audio quality settings optimized for speed and quality"""
from typing import Dict, Any
from core.config import config

class QualitySettings:
    """Manages quality presets optimized for Telegram"""
    
    @staticmethod
    def get_youtube_opts() -> Dict[str, Any]:
        """
        YouTube download options - Optimized for quality + speed
        Uses VP9 codec for better compression and quality
        """
        return {
            # Download best quality available
            'format': 'bestvideo[height<=1080][ext=webm]+bestaudio[ext=webm]/bestvideo[height<=1080]+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                # Video encoding - Fast + High Quality
                '-c:v', 'libx264',
                '-preset', 'fast',  # Fast encoding for speed
                '-crf', '23',  # Balanced quality (23 is good quality, smaller files)
                '-profile:v', 'main',
                '-level', '4.0',
                '-pix_fmt', 'yuv420p',
                # Audio encoding
                '-c:a', 'aac',
                '-b:a', '128k',  # Reduced for smaller files
                '-ar', '44100',
                # Optimization
                '-movflags', '+faststart',
                # Ensure thumbnail/preview works
                '-map_metadata', '0',
                '-map_metadata:s:v', '0:s:v',
                '-map_metadata:s:a', '0:s:a',
            ],
            'prefer_ffmpeg': True,
            'keepvideo': False,
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
    
    @staticmethod
    def get_pinterest_opts() -> Dict[str, Any]:
        """Pinterest download options - Fast and high quality"""
        return {
            'format': 'bestvideo[height<=1080]+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-profile:v', 'main',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
            ],
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
    
    @staticmethod
    def get_instagram_opts() -> Dict[str, Any]:
        """
        Instagram download options - App-like quality
        Optimized to look exactly like Instagram app with fast sending
        """
        return {
            # Get best Instagram quality (usually 1080p)
            'format': 'best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                # Video - Fast encoding, good quality
                '-c:v', 'libx264',
                '-preset', 'veryfast',  # Very fast for quick sending
                '-crf', '26',  # Good quality, smaller files
                '-profile:v', 'baseline',  # Better compatibility
                '-level', '3.1',
                '-pix_fmt', 'yuv420p',
                # Audio
                '-c:a', 'aac',
                '-b:a', '96k',  # Smaller audio for faster sending
                '-ar', '44100',
                # Optimization for Telegram
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '1024',
                # Ensure preview/thumbnail works
                '-map_metadata', '0',
            ],
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
    
    @staticmethod
    def get_audio_opts() -> Dict[str, Any]:
        """Get audio download options with high quality"""
        return {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }, {
                'key': 'FFmpegMetadata',
            }, {
                'key': 'EmbedThumbnail',
            }],
            'writethumbnail': True,
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
        }
    
    @staticmethod
    def get_spotify_audio_opts() -> Dict[str, Any]:
        """Get Spotify/YouTube Music download options"""
        return {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }, {
                'key': 'FFmpegMetadata',
            }, {
                'key': 'EmbedThumbnail',
            }],
            'writethumbnail': True,
            'embedthumbnail': True,
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
        }

# Global quality settings instance
quality_settings = QualitySettings()
