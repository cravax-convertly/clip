import os
import subprocess
import json
import logging
try:
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("MoviePy not available - using ffmpeg only for basic operations")

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL not available - watermark features disabled")

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.temp_folder = 'temp'
        self.processed_folder = 'processed'
        
    def get_video_info(self, video_path):
        """Get video metadata using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next(
                (stream for stream in data['streams'] if stream['codec_type'] == 'video'),
                None
            )
            
            return {
                'duration': float(data['format']['duration']),
                'width': int(video_stream['width']) if video_stream else 0,
                'height': int(video_stream['height']) if video_stream else 0,
                'fps': eval(video_stream['r_frame_rate']) if video_stream else 30
            }
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return {'duration': 0, 'width': 0, 'height': 0, 'fps': 30}
    
    def extract_clip(self, video_path, start_time, end_time, output_filename):
        """Extract a clip from the video using ffmpeg with timeout"""
        try:
            output_path = os.path.join(self.temp_folder, output_filename)
            duration = end_time - start_time
            
            # Use the working ffmpeg pattern with input seeking for speed
            duration = min(duration, 15)  # Max 15 seconds to prevent timeout
            cmd = [
                'ffmpeg', '-y',  # Overwrite output files
                '-ss', str(start_time),  # Seek first (faster)
                '-i', video_path,
                '-t', str(duration),
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, timeout=8)
            logger.info(f"Extracted clip: {output_filename}")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout extracting clip: {output_filename}")
            raise Exception(f"Clip extraction timed out after 20 seconds")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error extracting clip: {e.stderr.decode() if e.stderr else str(e)}")
            raise Exception(f"Failed to extract clip: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error extracting clip: {str(e)}")
            raise Exception(f"Failed to extract clip: {str(e)}")
    
    def extract_vertical_clip(self, video_path, start_time, end_time, output_filename):
        """Extract and convert clip to vertical 9:16 format for social media"""
        try:
            output_path = os.path.join(self.temp_folder, output_filename)
            duration = end_time - start_time
            
            # Use ffmpeg to create vertical clip with proper scaling
            cmd = [
                'ffmpeg', '-y',  # Overwrite output files
                '-i', video_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'fast',
                '-crf', '23',
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            logger.info(f"Created vertical clip: {output_filename}")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout creating vertical clip: {output_filename}")
            raise Exception(f"Vertical clip creation timed out")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating vertical clip: {e.stderr.decode() if e.stderr else str(e)}")
            raise Exception(f"Failed to create vertical clip: {str(e)}")
    
    def add_watermark(self, video_path, output_filename, watermark_text="ClipForge"):
        """Add watermark to video"""
        try:
            output_path = os.path.join(self.temp_folder, output_filename)
            
            # Use ffmpeg to add text watermark
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x=10:y=10:alpha=0.7",
                '-c:a', 'copy',
                '-preset', 'fast',
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            logger.info(f"Added watermark to: {output_filename}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error adding watermark: {str(e)}")
            # Return original path if watermark fails
            return video_path

    def convert_to_vertical(self, video_path):
        """Convert video to vertical 9:16 format for social media"""
        try:
            output_filename = f"vertical_{os.path.basename(video_path)}"
            output_path = os.path.join(self.temp_folder, output_filename)
            
            if MOVIEPY_AVAILABLE:
                # Use MoviePy for advanced video processing
                with VideoFileClip(video_path) as clip:
                    # Get original dimensions
                    original_width, original_height = clip.size
                    
                    # Calculate new dimensions for 9:16 aspect ratio
                    target_width = 1080
                    target_height = 1920
                    
                    # Calculate scaling to fit the video in the frame
                    scale_w = target_width / original_width
                    scale_h = target_height / original_height
                    scale = min(scale_w, scale_h)
                    
                    # Resize the clip
                    resized_clip = clip.resize(scale)
                    
                    # Center the clip in the vertical frame
                    final_clip = resized_clip.set_position('center')
                    
                    # Create the final video with black bars if needed
                    final_clip = CompositeVideoClip([final_clip], size=(target_width, target_height))
                    
                    # Write the video
                    final_clip.write_videofile(
                        output_path,
                        codec='libx264',
                        audio_codec='aac',
                        temp_audiofile='temp-audio.m4a',
                        remove_temp=True,
                        verbose=False,
                        logger=None
                    )
            else:
                # Use ffmpeg for basic vertical conversion
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',
                    '-c:a', 'copy',
                    output_path
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            
            logger.info(f"Converted to vertical format: {output_filename}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error converting to vertical: {str(e)}")
            raise Exception(f"Failed to convert to vertical format: {str(e)}")
    
    def add_captions(self, video_path, transcription_data):
        """Add captions to video based on transcription data"""
        try:
            output_filename = f"captioned_{os.path.basename(video_path)}"
            output_path = os.path.join(self.temp_folder, output_filename)
            
            if MOVIEPY_AVAILABLE and 'segments' in transcription_data and transcription_data['segments']:
                # Use MoviePy for advanced caption overlay
                with VideoFileClip(video_path) as clip:
                    # Create text clips for each segment
                    text_clips = []
                    
                    for segment in transcription_data['segments']:
                        text = segment['text'].strip()
                        if text:
                            txt_clip = TextClip(
                                text,
                                fontsize=50,
                                color='white',
                                font='Arial-Bold',
                                stroke_color='black',
                                stroke_width=3
                            ).set_position(('center', 'bottom')).set_duration(
                                segment['end'] - segment['start']
                            ).set_start(segment['start'])
                            
                            text_clips.append(txt_clip)
                    
                    # Composite video with captions
                    if text_clips:
                        final_clip = CompositeVideoClip([clip] + text_clips)
                    else:
                        final_clip = clip
                    
                    final_clip.write_videofile(
                        output_path,
                        codec='libx264',
                        audio_codec='aac',
                        temp_audiofile='temp-audio.m4a',
                        remove_temp=True,
                        verbose=False,
                        logger=None
                    )
            else:
                # For now, just copy the video (captions will be added in future version)
                cmd = ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', output_path]
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info("Captions will be added in a future version - copied video as-is")
            
            logger.info(f"Processed captions: {output_filename}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error adding captions: {str(e)}")
            raise Exception(f"Failed to add captions: {str(e)}")
    
    def add_watermark(self, video_path):
        """Add watermark/logo to video"""
        try:
            output_filename = f"final_{os.path.basename(video_path)}"
            output_path = os.path.join(self.processed_folder, output_filename)
            
            if MOVIEPY_AVAILABLE:
                # Use MoviePy for advanced watermark overlay
                with VideoFileClip(video_path) as clip:
                    # Create a simple text watermark (you can replace with logo image)
                    watermark = TextClip(
                        "ClipForge",
                        fontsize=30,
                        color='white',
                        font='Arial-Bold',
                        stroke_color='black',
                        stroke_width=2
                    ).set_position(('right', 'top')).set_duration(clip.duration).set_opacity(0.7)
                    
                    # Composite the final video
                    final_clip = CompositeVideoClip([clip, watermark])
                    
                    final_clip.write_videofile(
                        output_path,
                        codec='libx264',
                        audio_codec='aac',
                        temp_audiofile='temp-audio.m4a',
                        remove_temp=True,
                        verbose=False,
                        logger=None
                    )
            else:
                # Use ffmpeg for simple text overlay
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-vf', 'drawtext=text=ClipForge:fontcolor=white:fontsize=30:x=w-tw-10:y=10',
                    '-c:a', 'copy',
                    output_path
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info("Added simple text watermark using ffmpeg")
            
            logger.info(f"Added watermark: {output_filename}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error adding watermark: {str(e)}")
            raise Exception(f"Failed to add watermark: {str(e)}")
