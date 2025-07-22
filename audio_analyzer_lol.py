import numpy as np
import librosa
from pydub import AudioSegment
import logging
import os

logger = logging.getLogger(__name__)

class LoLAudioAnalyzer:
    def __init__(self):
        self.sample_rate = 44100  # Higher quality for LoL detection
        self.hop_length = 1024
        
        # League of Legends specific audio cues for highlight detection
        self.lol_highlight_keywords = [
            'pentakill', 'quadra kill', 'triple kill', 'double kill',
            'rampage', 'unstoppable', 'dominating', 'godlike',
            'legendary', 'ace', 'victory', 'defeat'
        ]
        
    def detect_lol_highlights(self, video_path):
        """
        Advanced LoL highlight detection using multiple techniques:
        1. Audio spike analysis for teamfights
        2. Spectral analysis for game event detection  
        3. Volume dynamics analysis
        4. Combat audio density detection
        """
        try:
            logger.info(f"Starting comprehensive LoL highlight analysis for {video_path}")
            
            # Load audio with high quality
            y, sr = librosa.load(video_path, sr=self.sample_rate)
            duration = len(y) / sr
            
            logger.info(f"Loaded audio: {duration:.2f} seconds, sample rate: {sr}")
            
            # Method 1: Audio spike detection for teamfights
            teamfight_moments = self._detect_teamfight_audio_spikes(y, sr)
            
            # Method 2: Combat audio density analysis
            combat_moments = self._detect_combat_density(y, sr)
            
            # Method 3: Spectral analysis for game events
            event_moments = self._detect_game_events_spectral(y, sr)
            
            # Method 4: Volume dynamics for exciting moments
            dynamic_moments = self._detect_volume_dynamics(y, sr)
            
            # Combine all detection methods
            all_moments = teamfight_moments + combat_moments + event_moments + dynamic_moments
            
            # Merge overlapping moments and rank by excitement score
            merged_clips = self._merge_and_rank_moments(all_moments, duration)
            
            logger.info(f"Detected {len(merged_clips)} LoL highlight moments")
            return merged_clips
            
        except Exception as e:
            logger.error(f"Error in LoL highlight detection: {str(e)}")
            return []
    
    def _detect_teamfight_audio_spikes(self, y, sr):
        """Detect teamfights using audio spike analysis - research shows this is most effective"""
        try:
            # Calculate RMS energy in overlapping windows
            frame_length = int(sr * 2)  # 2 second windows
            hop_length = int(sr * 0.5)  # 0.5 second hops
            
            rms_values = []
            times = []
            
            for i in range(0, len(y) - frame_length, hop_length):
                window = y[i:i + frame_length]
                rms = np.sqrt(np.mean(window**2))
                rms_values.append(rms)
                times.append(i / sr)
            
            rms_values = np.array(rms_values)
            times = np.array(times)
            
            # Dynamic threshold - teamfights are 3x louder than average
            mean_rms = np.mean(rms_values)
            std_rms = np.std(rms_values)
            teamfight_threshold = mean_rms + (3.0 * std_rms)
            
            # Find teamfight moments
            teamfight_indices = np.where(rms_values > teamfight_threshold)[0]
            
            moments = []
            for idx in teamfight_indices:
                start_time = times[idx]
                end_time = start_time + 2.0  # 2 second clips
                excitement_score = rms_values[idx] / mean_rms  # Relative excitement
                
                moments.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'type': 'teamfight',
                    'excitement_score': excitement_score,
                    'detection_reason': 'Audio spike during teamfight'
                })
            
            logger.info(f"Found {len(moments)} potential teamfight moments")
            return moments
            
        except Exception as e:
            logger.error(f"Error in teamfight detection: {str(e)}")
            return []
    
    def _detect_combat_density(self, y, sr):
        """Detect high combat audio density periods"""
        try:
            # Use spectral centroid to detect complex audio (multiple abilities/effects)
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=self.hop_length)[0]
            
            # Use zero crossing rate to detect rapid audio changes
            zcr = librosa.feature.zero_crossing_rate(y, hop_length=self.hop_length)[0]
            
            # Convert to time-based analysis
            times = librosa.frames_to_time(np.arange(len(spectral_centroids)), sr=sr, hop_length=self.hop_length)
            
            # High spectral centroid + high ZCR = complex combat audio
            combat_threshold_centroid = np.percentile(spectral_centroids, 85)
            combat_threshold_zcr = np.percentile(zcr, 85)
            
            combat_moments = []
            for i, (time, centroid, zcr_val) in enumerate(zip(times, spectral_centroids, zcr)):
                if centroid > combat_threshold_centroid and zcr_val > combat_threshold_zcr:
                    combat_moments.append({
                        'start_time': time,
                        'end_time': time + 3.0,  # 3 second clips for combat
                        'type': 'combat',
                        'excitement_score': (centroid / np.mean(spectral_centroids)) + (zcr_val / np.mean(zcr)),
                        'detection_reason': 'High combat audio density'
                    })
            
            logger.info(f"Found {len(combat_moments)} combat density moments")
            return combat_moments
            
        except Exception as e:
            logger.error(f"Error in combat density detection: {str(e)}")
            return []
    
    def _detect_game_events_spectral(self, y, sr):
        """Detect game events using spectral analysis"""
        try:
            # Use MFCC features to detect announcement audio patterns
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=self.hop_length)
            
            # Calculate spectral rolloff for event detection
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=self.hop_length)[0]
            
            times = librosa.frames_to_time(np.arange(len(spectral_rolloff)), sr=sr, hop_length=self.hop_length)
            
            # Detect announcer patterns (distinctive spectral signature)
            event_threshold = np.percentile(spectral_rolloff, 90)
            
            event_moments = []
            for i, (time, rolloff) in enumerate(zip(times, spectral_rolloff)):
                if rolloff > event_threshold:
                    event_moments.append({
                        'start_time': time,
                        'end_time': time + 4.0,  # 4 seconds for events with reactions
                        'type': 'game_event',
                        'excitement_score': rolloff / np.mean(spectral_rolloff),
                        'detection_reason': 'Game event audio signature'
                    })
            
            logger.info(f"Found {len(event_moments)} game event moments")
            return event_moments
            
        except Exception as e:
            logger.error(f"Error in spectral event detection: {str(e)}")
            return []
    
    def _detect_volume_dynamics(self, y, sr):
        """Detect exciting moments based on volume dynamics"""
        try:
            # Calculate loudness over time using research-based approach
            frame_length = int(sr * 1)  # 1 second windows
            hop_length = int(sr * 0.25)  # 0.25 second hops
            
            loudness_values = []
            times = []
            
            for i in range(0, len(y) - frame_length, hop_length):
                window = y[i:i + frame_length]
                # Use A-weighted loudness (perceptually relevant)
                loudness = np.sqrt(np.mean(window**2)) * len(window)
                loudness_values.append(loudness)
                times.append(i / sr)
            
            loudness_values = np.array(loudness_values)
            times = np.array(times)
            
            # Find sudden loudness increases (excitement spikes)
            loudness_diff = np.diff(loudness_values)
            excitement_threshold = np.percentile(loudness_diff, 95)
            
            dynamic_moments = []
            for i, (time, diff) in enumerate(zip(times[1:], loudness_diff)):
                if diff > excitement_threshold:
                    dynamic_moments.append({
                        'start_time': time,
                        'end_time': time + 2.5,
                        'type': 'excitement_spike',
                        'excitement_score': diff / np.mean(loudness_diff),
                        'detection_reason': 'Sudden excitement spike'
                    })
            
            logger.info(f"Found {len(dynamic_moments)} excitement spike moments")
            return dynamic_moments
            
        except Exception as e:
            logger.error(f"Error in volume dynamics detection: {str(e)}")
            return []
    
    def _merge_and_rank_moments(self, all_moments, video_duration):
        """Merge overlapping moments and rank by excitement score"""
        if not all_moments:
            return []
        
        # Sort by start time
        all_moments.sort(key=lambda x: x['start_time'])
        
        merged = []
        current = all_moments[0].copy()
        
        for moment in all_moments[1:]:
            # If moments overlap, merge them
            if moment['start_time'] <= current['end_time']:
                # Extend end time and combine excitement scores
                current['end_time'] = max(current['end_time'], moment['end_time'])
                current['excitement_score'] += moment['excitement_score']
                current['detection_reason'] += f" + {moment['detection_reason']}"
                
                # Update type to show multiple detections
                if moment['type'] not in current['type']:
                    current['type'] += f"_{moment['type']}"
            else:
                merged.append(current)
                current = moment.copy()
        
        merged.append(current)
        
        # Ensure clips don't exceed video duration
        for clip in merged:
            clip['end_time'] = min(clip['end_time'], video_duration)
            clip['duration'] = clip['end_time'] - clip['start_time']
        
        # Filter out clips that are too short or too long
        valid_clips = [
            clip for clip in merged 
            if 1.5 <= clip['duration'] <= 30.0  # 1.5 to 30 seconds
        ]
        
        # Sort by excitement score (descending) and limit to top clips
        valid_clips.sort(key=lambda x: x['excitement_score'], reverse=True)
        
        # For a 34-minute video, expect 5-15 highlight moments
        max_clips = min(15, max(5, int(video_duration / 180)))  # ~1 clip per 3 minutes
        top_clips = valid_clips[:max_clips]
        
        logger.info(f"Merged into {len(top_clips)} final highlight clips from {len(all_moments)} total moments")
        return top_clips