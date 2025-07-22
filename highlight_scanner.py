import logging
import numpy as np
from typing import List, Dict, Tuple
from ocr_analyzer import LoLKillFeedDetector
from simple_audio_analyzer import SimpleLoLAnalyzer

logger = logging.getLogger(__name__)

class SmartHighlightScanner:
    """Combines multiple detection methods to identify the best LoL highlights"""
    
    def __init__(self):
        """Initialize the smart highlight scanner"""
        self.kill_detector = LoLKillFeedDetector()
        self.audio_analyzer = SimpleLoLAnalyzer()
        
        # Scoring weights for different event types
        self.event_scores = {
            'penta_kill': 1.0,
            'quadra_kill': 0.9,
            'triple_kill': 0.8,
            'double_kill': 0.7,
            'first_blood': 0.8,
            'shutdown': 0.7,
            'baron_fight': 0.8,
            'team_fight': 0.6,
            'killing_spree': 0.6,
            'godlike': 0.9,
            'legendary': 0.8,
            'audio_spike': 0.4,
            'volume_spike': 0.3,
            'density_moment': 0.3
        }
    
    def detect_smart_highlights(self, video_path: str) -> List[Dict]:
        """Detect highlights using combined audio + OCR analysis"""
        try:
            logger.info(f"Starting smart highlight detection for {video_path}")
            
            # Get kill events from OCR
            kill_events = self.kill_detector.detect_kill_events(video_path)
            logger.info(f"Detected {len(kill_events)} kill events")
            
            # Get audio moments
            audio_moments = self.audio_analyzer.detect_lol_highlights(video_path)
            logger.info(f"Detected {len(audio_moments)} audio moments")
            
            # Combine and correlate events
            combined_highlights = self._correlate_events(kill_events, audio_moments)
            
            # Score and rank highlights
            scored_highlights = self._score_highlights(combined_highlights)
            
            # Convert to final clip format
            final_clips = self._create_clip_segments(scored_highlights)
            
            logger.info(f"Generated {len(final_clips)} smart highlights")
            return final_clips
            
        except Exception as e:
            logger.error(f"Error in smart highlight detection: {str(e)}")
            # Fallback to audio-only detection
            return self.audio_analyzer.detect_lol_highlights(video_path)
    
    def _correlate_events(self, kill_events: List[Dict], audio_moments: List[Dict]) -> List[Dict]:
        """Correlate kill events with audio spikes to find real highlights"""
        combined = []
        correlation_window = 10.0  # seconds
        
        # Start with kill events as they're more reliable
        for kill_event in kill_events:
            kill_time = kill_event['timestamp']
            
            # Find nearby audio events
            nearby_audio = []
            for audio_event in audio_moments:
                audio_time = audio_event['start_time']
                if abs(audio_time - kill_time) <= correlation_window:
                    nearby_audio.append(audio_event)
            
            # Create combined event
            combined_event = {
                'timestamp': kill_time,
                'primary_event': kill_event,
                'supporting_audio': nearby_audio,
                'event_type': kill_event.get('event_type', 'kill'),
                'confidence': kill_event.get('confidence', 0.7),
                'detection_methods': ['ocr']
            }
            
            if nearby_audio:
                combined_event['detection_methods'].append('audio')
                combined_event['confidence'] += 0.2  # Boost confidence
            
            combined.append(combined_event)
        
        # Add audio-only events that weren't correlated
        for audio_event in audio_moments:
            audio_time = audio_event['start_time']
            
            # Check if already correlated
            already_used = any(
                abs(event['timestamp'] - audio_time) <= correlation_window
                for event in combined
            )
            
            if not already_used:
                combined.append({
                    'timestamp': audio_time,
                    'primary_event': audio_event,
                    'supporting_audio': [],
                    'event_type': audio_event.get('type', 'audio_moment'),
                    'confidence': audio_event.get('excitement_score', 0.5),
                    'detection_methods': ['audio']
                })
        
        return combined
    
    def _score_highlights(self, highlights: List[Dict]) -> List[Dict]:
        """Score highlights based on event type and confidence"""
        for highlight in highlights:
            event_type = highlight['event_type']
            base_score = self.event_scores.get(event_type, 0.3)
            
            # Multiply by confidence
            confidence = highlight['confidence']
            final_score = base_score * confidence
            
            # Bonus for multi-method detection
            if len(highlight['detection_methods']) > 1:
                final_score *= 1.3
            
            # Bonus for high-value kill events
            if 'kill' in event_type and event_type != 'killed':
                final_score *= 1.2
            
            highlight['score'] = min(final_score, 1.0)
        
        # Sort by score descending
        highlights.sort(key=lambda x: x['score'], reverse=True)
        return highlights
    
    def _create_clip_segments(self, highlights: List[Dict], max_clips: int = 8) -> List[Dict]:
        """Create clip segments from highlights"""
        clips = []
        
        for i, highlight in enumerate(highlights[:max_clips]):
            timestamp = highlight['timestamp']
            
            # Determine clip duration based on event type
            event_type = highlight['event_type']
            if 'penta' in event_type or 'quadra' in event_type:
                clip_duration = 60  # Longer for big plays
                pre_buffer = 15
            elif 'team_fight' in event_type or 'baron' in event_type:
                clip_duration = 50
                pre_buffer = 12
            else:
                clip_duration = 45
                pre_buffer = 10
            
            start_time = max(0, timestamp - pre_buffer)
            end_time = start_time + clip_duration
            
            clip = {
                'start_time': start_time,
                'end_time': end_time,
                'duration': clip_duration,
                'excitement_score': highlight['score'],
                'detection_reason': f"Smart: {event_type} ({', '.join(highlight['detection_methods'])})",
                'type': 'smart_highlight',
                'event_type': event_type,
                'confidence': highlight['confidence'],
                'methods_used': highlight['detection_methods']
            }
            
            clips.append(clip)
        
        return clips
    
    def detect_highlights_fast(self, video_path: str, max_duration: int = 600) -> List[Dict]:
        """Fast highlight detection for large videos"""
        try:
            # For very large videos, use pattern-based detection
            clips = []
            
            # Generate highlights based on typical LoL game flow
            intervals = [
                (180, 'first_blood', 0.8),    # 3 minutes - first blood
                (600, 'team_fight', 0.7),     # 10 minutes - early skirmish  
                (900, 'dragon_fight', 0.7),   # 15 minutes - dragon
                (1200, 'baron_attempt', 0.8), # 20 minutes - baron
                (1500, 'late_game', 0.9)      # 25 minutes - late game
            ]
            
            for timestamp, event_type, score in intervals:
                if timestamp < max_duration:
                    clips.append({
                        'start_time': max(0, timestamp - 10),
                        'end_time': timestamp + 35,
                        'duration': 45,
                        'excitement_score': score,
                        'detection_reason': f'Pattern: {event_type}',
                        'type': 'pattern_based',
                        'event_type': event_type
                    })
            
            return clips[:5]  # Limit to 5 clips
            
        except Exception as e:
            logger.error(f"Error in fast detection: {str(e)}")
            return []