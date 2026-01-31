"""Video and audio quality settings for premium downloads"""
from typing import Dict, Any
from core.config import config

class QualitySettings:
    """Manages quality presets for different platforms"""
    
    @staticmethod
    def get_youtube_opts() -> Dict[str, Any]:
        """Get YouTube download options with ULTRA premium quality"""
        return {
            'format': 'bestvideo[height<=2160][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1920]+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }, {
                'key': 'FFmpegMetadata',
            }],
            'postprocessor_args': [
                '-c:v', 'libx264',
                '-preset', 'veryslow',  # Best quality (slower but much better)
                '-crf', '15',  # Near-lossless quality (15 is extremely high quality)
                '-profile:v', 'high',
                '-level', '4.2',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '320k',
                '-ar', '48000',
                '-movflags', '+faststart',
                '-vf', 'unsharp=7:7:1.5:7:7:0.0,eq=contrast=1.05:brightness=0.02',  # Strong sharpening + slight contrast boost
            ],
            'prefer_ffmpeg': True,
            'keepvideo': False,
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
        }
    
    @staticmethod
    def get_pinterest_opts() -> Dict[str, Any]:
        """Get Pinterest download options with 4K support"""
        return {
            'format': 'bestvideo[height<=2160]+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-crf', '17',  # Even higher quality for Pinterest
                '-c:a', 'aac',
                '-b:a', '256k',
                '-vf', 'unsharp=5:5:1.2:5:5:0.0',  # Stronger sharpening
                '-movflags', '+faststart',
            ],
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
    
    @staticmethod
    def get_instagram_opts() -> Dict[str, Any]:
        """Get Instagram download options with ULTRA premium quality"""
        return {
            'format': 'bestvideo[height<=1920]+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                '-c:v', 'libx264',
                '-preset', 'veryslow',
                '-crf', '15',  # Ultra high quality
                '-profile:v', 'high',
                '-level', '4.2',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '320k',
                '-ar', '48000',
                '-vf', 'unsharp=7:7:1.5:7:7:0.0,eq=contrast=1.05:brightness=0.02',  # Strong sharpening
                '-movflags', '+faststart',
            ],
            'prefer_ffmpeg': True,
            'outtmpl': '%(title)s.%(ext)s',
        }
    
    @staticmethod
    def get_audio_opts() -> Dict[str, Any]:
        """Get audio download options with high quality"""
        return {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',  # Maximum MP3 quality
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
