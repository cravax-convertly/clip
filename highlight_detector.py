import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from hud_detector import LoLHUDDetector
from ocr_analyzer import LoLKillFeedDetector
from simple_audio_analyzer import SimpleLoLAnalyzer

logger = logging.getLogger(__name__)

class SmartLoLHighlightDetector:
    """Advanced LoL highlight detector that combines multiple signals for accurate detection"""
    
    def __init__(self):
        """Initialize the smart highlight detector"""
        self.hud_detector = LoLHUDDetector()
        self.kill_detector = LoLKillFeedDetector()
        self.audio_analyzer = SimpleLoLAnalyzer()
        
        # Event scoring system
        self.event_scores = {
            'penta_kill': 10,
            'quadra_kill': 8,
            'triple_kill': 6,
            'double_kill': 4,
            'first_blood': 5,
            'shutdown': 4,
            'baron': 6,
            'dragon': 5,
            'turret': 3,
            'teamfight': 7,
            'single_kill': 2,
            'audio_spike': 1
        }
        
        # Correlation settings
        self.correlation_window = 8.0  # seconds
        self.min_highlight_gap = 30.0  # minimum seconds between highlights
    
    def detect_smart_highlights(self, video_path: str) -> List[Dict]:
        """Main detection method combining all signals"""
        try:
            logger.info(f"Starting smart LoL highlight detection for {video_path}")
            
            # Step 1: Detect gameplay periods
            gameplay_periods = self.hud_detector.analyze_gameplay_periods(video_path)
            if not gameplay_periods:
                logger.warning("No gameplay periods detected, using fallback")
                gameplay_periods = self.hud_detector.get_gameplay_periods_fallback(video_path)
            
            # Step 2: Get kill feed events (only during gameplay)
            kill_events = self.kill_detector.detect_kill_events(video_path)
            filtered_kills = [
                event for event in kill_events
                if self.hud_detector.is_timestamp_in_game(event['timestamp'], gameplay_periods)
            ]
            
            logger.info(f"Filtered {len(kill_events)} kill events to {len(filtered_kills)} in-game events")
            
            # Step 3: Get audio spikes (only during gameplay)
            audio_moments = self.audio_analyzer.detect_lol_highlights(video_path)
            filtered_audio = []
            for moment in audio_moments:
                if self.hud_detector.is_timestamp_in_game(moment['start_time'], gameplay_periods):
                    filtered_audio.append(moment)
            
            logger.info(f"Filtered audio moments to {len(filtered_audio)} in-game moments")
            
            # Step 4: Correlate events
            correlated_highlights = self._correlate_events(filtered_kills, filtered_audio, gameplay_periods)
            
            # Step 5: Score and rank
            scored_highlights = self._score_and_rank(correlated_highlights)
            
            # Step 6: Generate final clips
            final_clips = self._generate_clips(scored_highlights)
            
            logger.info(f"Generated {len(final_clips)} smart highlights")
            return final_clips
            
        except Exception as e:
            logger.error(f"Error in smart highlight detection: {str(e)}")
            # Fallback to pattern-based detection
            return self._pattern_based_fallback(video_path)
    
    def _correlate_events(self, kill_events: List[Dict], audio_moments: List[Dict], 
                         gameplay_periods: List[Dict]) -> List[Dict]:
        """Correlate kill events with audio spikes for better accuracy"""
        correlated = []
        
        # Start with kill events (highest confidence)
        for kill_event in kill_events:
            kill_time = kill_event['timestamp']
            
            # Find nearby audio events within correlation window
            nearby_audio = []
            for audio_event in audio_moments:
                audio_time = audio_event['start_time']
                if abs(audio_time - kill_time) <= self.correlation_window:
                    nearby_audio.append(audio_event)
            
            # Create correlated event
            highlight = {
                'timestamp': kill_time,
                'primary_event': kill_event,
                'supporting_audio': nearby_audio,
                'event_type': kill_event.get('event_type', 'kill'),
                'confidence': kill_event.get('confidence', 0.7),
                'detection_methods': ['ocr', 'hud'],
                'in_game': True
            }
            
            # Boost confidence if we have supporting audio
            if nearby_audio:
                highlight['detection_methods'].append('audio')
                highlight['confidence'] = min(1.0, highlight['confidence'] + 0.2)
                # Use best audio score
                best_audio_score = max(a.get('excitement_score', 0.3) for a in nearby_audio)
                highlight['audio_boost'] = best_audio_score
            
            correlated.append(highlight)
        
        # Add high-confidence audio events that weren't correlated
        for audio_event in audio_moments:
            audio_time = audio_event['start_time']
            
            # Check if already used in correlation
            already_used = any(
                abs(h['timestamp'] - audio_time) <= self.correlation_window
                for h in correlated
            )
            
            # Only add if high excitement score and not already used
            if not already_used and audio_event.get('excitement_score', 0) > 0.7:
                correlated.append({
                    'timestamp': audio_time,
                    'primary_event': audio_event,
                    'supporting_audio': [],
                    'event_type': 'audio_highlight',
                    'confidence': audio_event.get('excitement_score', 0.7),
                    'detection_methods': ['audio', 'hud'],
                    'in_game': True
                })
        
        return correlated
    
    def _score_and_rank(self, highlights: List[Dict]) -> List[Dict]:
        """Score highlights based on event type, confidence, and methods used"""
        for highlight in highlights:
            event_type = highlight['event_type']
            
            # Base score from event type
            base_score = self.event_scores.get(event_type, 1)
            
            # Apply confidence multiplier
            confidence_mult = highlight['confidence']
            
            # Multi-method bonus
            method_bonus = 1.0
            if len(highlight['detection_methods']) > 2:
                method_bonus = 1.4
            elif len(highlight['detection_methods']) > 1:
                method_bonus = 1.2
            
            # Audio boost bonus
            audio_bonus = 1.0 + highlight.get('audio_boost', 0) * 0.3
            
            # Calculate final score
            final_score = base_score * confidence_mult * method_bonus * audio_bonus
            highlight['score'] = min(final_score, 10.0)  # Cap at 10
        
        # Sort by score descending
        highlights.sort(key=lambda x: x['score'], reverse=True)
        return highlights
    
    def _generate_clips(self, highlights: List[Dict], max_clips: int = 8) -> List[Dict]:
        """Generate clip segments from highlights with proper spacing"""
        clips = []
        last_clip_time = -999
        
        for highlight in highlights[:max_clips * 2]:  # Check more than needed
            timestamp = highlight['timestamp']
            
            # Ensure minimum gap between clips
            if timestamp - last_clip_time < self.min_highlight_gap:
                continue
            
            # Determine clip parameters based on event type
            event_type = highlight['event_type']
            
            if 'penta' in event_type or 'quadra' in event_type:
                duration = 60
                pre_buffer = 15
            elif 'teamfight' in event_type or 'baron' in event_type:
                duration = 45
                pre_buffer = 10
            elif 'triple' in event_type or 'double' in event_type:
                duration = 40
                pre_buffer = 8
            else:
                duration = 35
                pre_buffer = 6
            
            start_time = max(0, timestamp - pre_buffer)
            end_time = start_time + duration
            
            clip = {
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'excitement_score': highlight['score'],
                'detection_reason': f"Smart: {event_type} ({', '.join(highlight['detection_methods'])})",
                'type': 'smart_highlight',
                'event_type': event_type,
                'confidence': highlight['confidence'],
                'methods_used': highlight['detection_methods'],
                'in_game_verified': True
            }
            
            clips.append(clip)
            last_clip_time = timestamp
            
            if len(clips) >= max_clips:
                break
        
        return clips
    
    def _pattern_based_fallback(self, video_path: str) -> List[Dict]:
        """Fallback pattern-based detection when other methods fail"""
        logger.info("Using pattern-based fallback detection")
        
        try:
            # Get video duration
            import subprocess
            import json
            
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            video_info = json.loads(result.stdout)
            duration = float(video_info['format']['duration'])
        except:
            duration = 3600  # Default 1 hour
        
        clips = []
        
        # Skip first 2 minutes (loading/champion select)
        start_offset = 120
        
        # Generate clips at strategic intervals
        intervals = [
            (300, 'early_game', 0.6),      # 5 minutes
            (600, 'first_objective', 0.7), # 10 minutes
            (900, 'mid_game', 0.8),        # 15 minutes
            (1200, 'team_fights', 0.9),    # 20 minutes
            (1500, 'late_game', 0.8),      # 25 minutes
        ]
        
        for timestamp, event_type, score in intervals:
            if timestamp > start_offset and timestamp + 45 < duration:
                clips.append({
                    'start_time': timestamp - 10,
                    'end_time': timestamp + 35,
                    'duration': 45,
                    'excitement_score': score,
                    'detection_reason': f'Pattern: {event_type}',
                    'type': 'pattern_fallback',
                    'event_type': event_type,
                    'confidence': 0.6,
                    'methods_used': ['pattern'],
                    'in_game_verified': False
                })
        
        return clips[:5]  # Return top 5
    
    def detect_highlights_fast(self, video_path: str) -> List[Dict]:
        """Fast detection for large videos"""
        logger.info("Using fast highlight detection")
        return self._pattern_based_fallback(video_path)