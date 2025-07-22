import os
import logging
import subprocess
from openai import OpenAI

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self):
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
    def transcribe_clip(self, video_path):
        """Transcribe audio from video clip using OpenAI Whisper"""
        try:
            logger.info(f"Transcribing audio from: {video_path}")
            
            # Extract audio from video for transcription
            audio_path = self._extract_audio_for_transcription(video_path)
            
            # Transcribe using OpenAI Whisper
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            # Clean up temporary audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            # Process the response
            transcription_data = {
                'text': transcript.text,
                'language': getattr(transcript, 'language', 'en'),
                'duration': getattr(transcript, 'duration', 0),
                'segments': []
            }
            
            # Process segments with timing information
            if hasattr(transcript, 'segments') and transcript.segments:
                for segment in transcript.segments:
                    segment_data = {
                        'id': segment.id,
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text.strip()
                    }
                    
                    # Only include segments with actual text
                    if segment_data['text']:
                        transcription_data['segments'].append(segment_data)
            
            logger.info(f"Transcription completed. Found {len(transcription_data['segments'])} segments")
            return transcription_data
            
        except Exception as e:
            logger.error(f"Error transcribing clip: {str(e)}")
            # Return empty transcription data on error
            return {
                'text': '',
                'language': 'en',
                'duration': 0,
                'segments': []
            }
    
    def _extract_audio_for_transcription(self, video_path):
        """Extract audio from video for transcription"""
        try:
            
            audio_filename = f"transcribe_{os.path.basename(video_path).split('.')[0]}.mp3"
            audio_path = os.path.join('temp', audio_filename)
            
            # Use ffmpeg to extract audio in format suitable for Whisper
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'mp3',
                '-ar', '16000',  # Sample rate suitable for Whisper
                '-ac', '1',  # Mono
                audio_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            return audio_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error extracting audio for transcription: {e.stderr.decode()}")
            raise Exception(f"Failed to extract audio: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise
    
    def format_subtitles_srt(self, transcription_data):
        """Format transcription data as SRT subtitles"""
        try:
            srt_content = ""
            
            for i, segment in enumerate(transcription_data.get('segments', []), 1):
                start_time = self._seconds_to_srt_time(segment['start'])
                end_time = self._seconds_to_srt_time(segment['end'])
                text = segment['text'].strip()
                
                if text:
                    srt_content += f"{i}\n"
                    srt_content += f"{start_time} --> {end_time}\n"
                    srt_content += f"{text}\n\n"
            
            return srt_content
            
        except Exception as e:
            logger.error(f"Error formatting SRT subtitles: {str(e)}")
            return ""
    
    def _seconds_to_srt_time(self, seconds):
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        try:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            milliseconds = int((seconds % 1) * 1000)
            
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
            
        except Exception as e:
            logger.error(f"Error converting seconds to SRT time: {str(e)}")
            return "00:00:00,000"
