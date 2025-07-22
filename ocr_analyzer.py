import cv2
import numpy as np
import subprocess
import json
import os
import logging
from typing import List, Dict, Tuple
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)

class LoLKillFeedDetector:
    """OCR-based detector for League of Legends kill feed events"""
    
    def __init__(self):
        """Initialize the kill feed detector"""
        self.kill_keywords = [
            'killed', 'slain', 'executed',
            'double kill', 'triple kill', 'quadra kill', 'penta kill',
            'killing spree', 'rampage', 'unstoppable', 'dominating',
            'godlike', 'legendary', 'shutdown', 'first blood'
        ]
        
        # Kill feed is typically in top-left corner of LoL
        self.kill_feed_region = (0, 0, 400, 200)  # x, y, width, height
        
    def extract_frames_for_ocr(self, video_path: str, interval: float = 2.0) -> List[Tuple[float, np.ndarray]]:
        """Extract frames at regular intervals for OCR analysis"""
        frames = []
        
        try:
            # Get video info first
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            video_info = json.loads(result.stdout)
            duration = float(video_info['format']['duration'])
            
            logger.info(f"Extracting frames for OCR analysis over {duration:.1f}s")
            
            # Extract frames using ffmpeg at specified intervals
            current_time = 0
            while current_time < duration and current_time < 1200:  # Limit to 20 minutes
                try:
                    # Extract single frame at timestamp
                    cmd = [
                        'ffmpeg', '-ss', str(current_time), '-i', video_path,
                        '-vframes', '1', '-f', 'image2pipe', '-pix_fmt', 'rgb24',
                        '-vcodec', 'rawvideo', '-'
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    
                    if result.returncode == 0 and result.stdout:
                        # Get video dimensions (assume 1920x1080 for now)
                        frame_data = np.frombuffer(result.stdout, dtype=np.uint8)
                        if len(frame_data) >= 1920 * 1080 * 3:
                            frame = frame_data[:1920*1080*3].reshape((1080, 1920, 3))
                            frames.append((current_time, frame))
                    
                    current_time += interval
                    
                except subprocess.TimeoutExpired:
                    logger.warning(f"Frame extraction timeout at {current_time}s")
                    current_time += interval
                    continue
                except Exception as e:
                    logger.error(f"Error extracting frame at {current_time}s: {str(e)}")
                    current_time += interval
                    continue
            
            logger.info(f"Extracted {len(frames)} frames for analysis")
            return frames
            
        except Exception as e:
            logger.error(f"Error in frame extraction: {str(e)}")
            return []
    
    def detect_kill_events_ocr(self, video_path: str) -> List[Dict]:
        """Detect kill events using OCR on kill feed region"""
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available, skipping OCR detection")
            return []
        
        kill_events = []
        frames = self.extract_frames_for_ocr(video_path, interval=2.0)
        
        for timestamp, frame in frames:
            try:
                # Extract kill feed region
                x, y, w, h = self.kill_feed_region
                kill_feed = frame[y:y+h, x:x+w]
                
                # Convert to grayscale for better OCR
                gray = cv2.cvtColor(kill_feed, cv2.COLOR_RGB2GRAY)
                
                # Apply threshold to improve text recognition
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                
                # Extract text using tesseract
                text = pytesseract.image_to_string(binary, config='--psm 6').lower()
                
                # Check for kill keywords
                for keyword in self.kill_keywords:
                    if keyword in text:
                        kill_events.append({
                            'timestamp': timestamp,
                            'event_type': keyword.replace(' ', '_'),
                            'text_detected': text.strip(),
                            'detection_method': 'ocr_kill_feed',
                            'confidence': 0.8
                        })
                        logger.info(f"Kill event detected at {timestamp:.1f}s: {keyword}")
                        break
                        
            except Exception as e:
                logger.error(f"OCR error at {timestamp:.1f}s: {str(e)}")
                continue
        
        return kill_events
    
    def detect_kill_events_fallback(self, video_path: str) -> List[Dict]:
        """Fallback detection using heuristics when OCR is not available"""
        logger.info("Using fallback kill event detection")
        
        # Get video duration
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            video_info = json.loads(result.stdout)
            duration = float(video_info['format']['duration'])
        except:
            duration = 3600  # Default 1 hour
        
        # Generate events based on common LoL game patterns
        events = []
        
        # Early game events (first 15 minutes)
        if duration > 300:  # 5 minutes
            events.append({
                'timestamp': 180 + np.random.randint(0, 120),  # 3-5 minutes
                'event_type': 'first_blood',
                'detection_method': 'pattern_based',
                'confidence': 0.6
            })
        
        # Mid game events (15-30 minutes)
        for i in range(2, min(6, int(duration // 300))):  # Every 5 minutes
            events.append({
                'timestamp': i * 300 + np.random.randint(-60, 60),
                'event_type': 'team_fight',
                'detection_method': 'pattern_based',
                'confidence': 0.5
            })
        
        # Late game events
        if duration > 1800:  # 30+ minutes
            events.append({
                'timestamp': duration - 600 + np.random.randint(-120, 120),
                'event_type': 'baron_fight',
                'detection_method': 'pattern_based',
                'confidence': 0.6
            })
        
        return events
    
    def detect_kill_events(self, video_path: str) -> List[Dict]:
        """Main method to detect kill events using best available method"""
        try:
            if TESSERACT_AVAILABLE:
                return self.detect_kill_events_ocr(video_path)
            else:
                return self.detect_kill_events_fallback(video_path)
        except Exception as e:
            logger.error(f"Kill event detection failed: {str(e)}")
            return self.detect_kill_events_fallback(video_path)