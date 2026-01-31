"""Clean error handling and user-facing messages"""
from typing import Optional
from utils.logger import logger

class ErrorHandler:
    """Handles errors and provides clean user messages"""
    
    @staticmethod
    def get_user_message(error_type: str, platform: str = "download") -> str:
        """
        Get clean user-facing error message
        
        Args:
            error_type: Type of error (network, format, blocked, etc.)
            platform: Platform name (youtube, spotify, instagram, etc.)
        
        Returns:
            Clean error message for user
        """
        messages = {
            'network': f"⚠️ Network issue while downloading from {platform}. Please try again.",
            'format': f"⚠️ This {platform} link format is not supported. Please check the URL.",
            'unavailable': f"⚠️ This {platform} content is unavailable or private.",
            'blocked': "🚫 You blocked the bot while it was processing, so downloads are disabled for 1 hour. Try again later.",
            'rate_limit': f"⚠️ Too many requests to {platform}. Please wait a moment and try again.",
            'file_too_large': "⚠️ File is too large to send via Telegram (max 50MB).",
            'processing': f"⚠️ Error processing {platform} file. Please try a different link.",
            'cookies': f"⚠️ Authentication issue with {platform}. Our team has been notified.",
            'timeout': f"⚠️ Download timed out. The {platform} server may be slow. Try again.",
            'unknown': f"⚠️ Download failed. Please try again or use a different link.",
        }
        
        return messages.get(error_type, messages['unknown'])
    
    @staticmethod
    def log_and_notify(error: Exception, context: str, user_id: int) -> str:
        """
        Log error internally and return clean user message
        
        Args:
            error: The exception that occurred
            context: Context string (e.g., "youtube_download", "spotify_track")
            user_id: User ID for logging
        
        Returns:
            Clean error message for user
        """
        # Log full error internally
        logger.error(f"[{context}] User {user_id}: {type(error).__name__}: {str(error)}")
        
        # Determine error type and return clean message
        error_str = str(error).lower()
        
        if 'network' in error_str or 'connection' in error_str:
            return ErrorHandler.get_user_message('network', context.split('_')[0])
        elif 'format' in error_str or 'unsupported' in error_str:
            return ErrorHandler.get_user_message('format', context.split('_')[0])
        elif 'unavailable' in error_str or 'private' in error_str or '404' in error_str:
            return ErrorHandler.get_user_message('unavailable', context.split('_')[0])
        elif 'rate' in error_str or 'limit' in error_str or '429' in error_str:
            return ErrorHandler.get_user_message('rate_limit', context.split('_')[0])
        elif 'size' in error_str or 'too large' in error_str:
            return ErrorHandler.get_user_message('file_too_large')
        elif 'cookie' in error_str or 'auth' in error_str or '401' in error_str or '403' in error_str:
            return ErrorHandler.get_user_message('cookies', context.split('_')[0])
        elif 'timeout' in error_str:
            return ErrorHandler.get_user_message('timeout', context.split('_')[0])
        else:
            return ErrorHandler.get_user_message('unknown')
    
    @staticmethod
    def format_spotify_error(track_title: str, error: str) -> str:
        """Format Spotify track error message"""
        return f"⚠️ {track_title}\n   └ Failed to download"
    
    @staticmethod
    def format_success_summary(total: int, successful: int, failed: int) -> str:
        """Format download summary message"""
        if failed == 0:
            return f"✅ All {total} items downloaded successfully!"
        elif successful == 0:
            return f"❌ All {total} items failed to download. Please try again."
        else:
            return f"✅ Downloaded {successful}/{total} items\n⚠️ {failed} failed"

# Global error handler instance
error_handler = ErrorHandler()
