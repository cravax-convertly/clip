import cv2
import numpy as np
import subprocess
import json
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

class LoLHUDDetector:
    """Detects League of Legends in-game HUD elements to determine if gameplay is active"""
    
    def __init__(self):
        """Initialize the HUD detector with known LoL interface patterns"""
        # Define HUD regions for detection (normalized coordinates 0-1)
        self.hud_regions = {
            'kill_feed': (0.0, 0.0, 0.25, 0.15),      # Top-left kill feed
            'minimap': (0.75, 0.75, 1.0, 1.0),        # Bottom-right minimap
            'abilities': (0.35, 0.85, 0.65, 1.0),     # Bottom center abilities
            'health_bar': (0.0, 0.85, 0.35, 1.0),     # Bottom-left health/mana
        }
        
        # Color ranges for LoL UI elements (HSV)
        self.ui_colors = {
            'blue_team': ([100, 50, 50], [130, 255, 255]),    # Blue UI elements
            'red_team': ([0, 50, 50], [10, 255, 255]),        # Red UI elements
            'gold_ui': ([20, 100, 100], [30, 255, 255]),      # Gold/yellow UI
            'health_green': ([40, 50, 50], [80, 255, 255]),   # Health bars
        }
    
    def extract_sample_frames(self, video_path: str, sample_count: int = 10) -> List[Tuple[float, np.ndarray]]:
        """Extract sample frames throughout the video for HUD analysis"""
        frames = []
        
        try:
            # Get video duration
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            video_info = json.loads(result.stdout)
            duration = float(video_info['format']['duration'])
            
            # Sample frames at regular intervals
            interval = duration / (sample_count + 1)
            
            for i in range(1, sample_count + 1):
                timestamp = i * interval
                try:
                    # Extract frame using ffmpeg
                    cmd = [
                        'ffmpeg', '-ss', str(timestamp), '-i', video_path,
                        '-vframes', '1', '-f', 'image2pipe', '-pix_fmt', 'rgb24',
                        '-vcodec', 'rawvideo', '-'
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    
                    if result.returncode == 0 and result.stdout:
                        # Assume 1920x1080 frame size
                        frame_data = np.frombuffer(result.stdout, dtype=np.uint8)
                        if len(frame_data) >= 1920 * 1080 * 3:
                            frame = frame_data[:1920*1080*3].reshape((1080, 1920, 3))
                            frames.append((timestamp, frame))
                            
                except subprocess.TimeoutExpired:
                    logger.warning(f"Frame extraction timeout at {timestamp:.1f}s")
                    continue
                except Exception as e:
                    logger.error(f"Error extracting frame at {timestamp:.1f}s: {str(e)}")
                    continue
            
            logger.info(f"Extracted {len(frames)} sample frames")
            return frames
            
        except Exception as e:
            logger.error(f"Error in frame extraction: {str(e)}")
            return []
    
    def detect_hud_elements(self, frame: np.ndarray) -> Dict[str, bool]:
        """Detect presence of LoL HUD elements in a frame"""
        height, width = frame.shape[:2]
        hud_detected = {}
        
        try:
            # Convert to HSV for better color detection
            hsv_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            
            for region_name, (x1, y1, x2, y2) in self.hud_regions.items():
                # Convert normalized coordinates to pixels
                x1_px, y1_px = int(x1 * width), int(y1 * height)
                x2_px, y2_px = int(x2 * width), int(y2 * height)
                
                # Extract region
                region = hsv_frame[y1_px:y2_px, x1_px:x2_px]
                
                # Check for UI colors in this region
                ui_pixels = 0
                total_pixels = region.shape[0] * region.shape[1] if region.size > 0 else 1
                
                for color_name, (lower, upper) in self.ui_colors.items():
                    lower_bound = np.array(lower)
                    upper_bound = np.array(upper)
                    mask = cv2.inRange(region, lower_bound, upper_bound)
                    ui_pixels += np.sum(mask > 0)
                
                # Consider HUD present if >5% of region contains UI colors
                hud_detected[region_name] = (ui_pixels / total_pixels) > 0.05
            
            return hud_detected
            
        except Exception as e:
            logger.error(f"Error detecting HUD elements: {str(e)}")
            return {region: False for region in self.hud_regions.keys()}
    
    def analyze_gameplay_periods(self, video_path: str) -> List[Dict]:
        """Analyze video to identify in-game periods"""
        try:
            logger.info(f"Analyzing gameplay periods for {video_path}")
            
            # Extract sample frames
            frames = self.extract_sample_frames(video_path, sample_count=15)
            
            gameplay_periods = []
            current_period = None
            
            for timestamp, frame in frames:
                hud_elements = self.detect_hud_elements(frame)
                
                # Consider in-game if we detect at least 2 key HUD elements
                key_elements = ['minimap', 'abilities', 'health_bar']
                in_game_score = sum(1 for elem in key_elements if hud_elements.get(elem, False))
                is_in_game = in_game_score >= 2
                
                if is_in_game and current_period is None:
                    # Start new gameplay period
                    current_period = {
                        'start_time': timestamp,
                        'end_time': timestamp,
                        'confidence': in_game_score / len(key_elements)
                    }
                elif is_in_game and current_period is not None:
                    # Extend current period
                    current_period['end_time'] = timestamp
                    current_period['confidence'] = max(
                        current_period['confidence'],
                        in_game_score / len(key_elements)
                    )
                elif not is_in_game and current_period is not None:
                    # End current period
                    if current_period['end_time'] - current_period['start_time'] > 60:  # At least 1 minute
                        gameplay_periods.append(current_period)
                    current_period = None
            
            # Close final period if exists
            if current_period is not None:
                if current_period['end_time'] - current_period['start_time'] > 60:
                    gameplay_periods.append(current_period)
            
            logger.info(f"Detected {len(gameplay_periods)} gameplay periods")
            return gameplay_periods
            
        except Exception as e:
            logger.error(f"Error analyzing gameplay periods: {str(e)}")
            return []
    
    def is_timestamp_in_game(self, timestamp: float, gameplay_periods: List[Dict]) -> bool:
        """Check if a specific timestamp falls within a detected gameplay period"""
        for period in gameplay_periods:
            if period['start_time'] <= timestamp <= period['end_time']:
                return True
        return False
    
    def get_gameplay_periods_fallback(self, video_path: str) -> List[Dict]:
        """Fallback method using heuristics when HUD detection fails"""
        try:
            # Get video duration
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            video_info = json.loads(result.stdout)
            duration = float(video_info['format']['duration'])
            
            # Assume most of a long video is gameplay, skip first/last 5%
            skip_duration = duration * 0.05
            
            return [{
                'start_time': skip_duration,
                'end_time': duration - skip_duration,
                'confidence': 0.6,
                'method': 'fallback'
            }]
            
        except Exception as e:
            logger.error(f"Error in fallback detection: {str(e)}")
            return []