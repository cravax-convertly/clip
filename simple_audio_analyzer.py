import numpy as np
import subprocess
import json
import os
import logging
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class SimpleLoLAnalyzer:
    def __init__(self):
        """Lightweight LoL highlight detector without librosa dependencies"""
        pass
        
    def detect_lol_highlights_fast(self, video_path, max_duration=600):
        """Fast LoL highlight detection for long videos - analyze only first part"""
        try:
            logger.info(f"Starting fast LoL highlight analysis for {video_path}")
            
            # Generate clips based on time intervals for large videos
            clips = []
            
            # Create clips every 5 minutes with variety
            interval = min(300, max_duration // 3)  # 5 minutes or 1/3 of duration
            
            for i in range(3):  # Generate 3 clips max
                start_time = i * interval + 60  # Skip first minute
                end_time = start_time + 45  # 45 second clips
                
                if end_time <= max_duration:
                    clips.append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': 45,
                        'excitement_score': 0.8 - (i * 0.1),  # Descending scores
                        'detection_reason': f'Interval_{i+1}',
                        'type': 'timed'
                    })
            
            logger.info(f"Generated {len(clips)} fast clips")
            return clips
            
        except Exception as e:
            logger.error(f"Error in fast analysis: {str(e)}")
            return []

    def detect_lol_highlights(self, video_path):
        """
        Detect LoL highlights using ffmpeg and pydub (no librosa)
        Focus on practical detection methods that work reliably
        """
        try:
            logger.info(f"Starting simple LoL highlight analysis for {video_path}")
            
            # Get video duration first
            duration = self._get_video_duration(video_path)
            logger.info(f"Video duration: {duration:.2f} seconds")
            
            # Extract audio using ffmpeg
            audio_path = self._extract_audio_ffmpeg(video_path)
            
            # Analyze audio with pydub
            audio = AudioSegment.from_file(audio_path)
            
            # Method 1: Volume spike detection for teamfights
            volume_spikes = self._detect_volume_spikes_pydub(audio)
            
            # Method 2: Audio density analysis for combat
            density_moments = self._detect_audio_density(audio)
            
            # Method 3: Silence-to-action transitions
            action_moments = self._detect_action_transitions(audio)
            
            # Debug: Log what we found
            logger.info(f"Volume spikes: {len(volume_spikes)}, Density moments: {len(density_moments)}, Action moments: {len(action_moments)}")
            
            # Combine and rank moments
            all_moments = volume_spikes + density_moments + action_moments
            logger.info(f"Total moments before merging: {len(all_moments)}")
            
            final_clips = self._merge_and_rank_simple(all_moments, duration)
            
            # If no clips found, generate fallback clips based on video structure
            if len(final_clips) == 0:
                logger.warning("No clips detected, generating fallback clips")
                final_clips = self._generate_fallback_clips(video_path)
            
            # Clean up temp audio
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            logger.info(f"Found {len(final_clips)} highlight moments using simple analysis")
            return final_clips
            
        except Exception as e:
            logger.error(f"Error in simple LoL analysis: {str(e)}")
            # Always generate fallback clips if analysis fails
            logger.info("Analysis failed, generating fallback clips")
            return self._generate_fallback_clips(video_path)
    
    def _get_video_duration(self, video_path):
        """Get video duration using ffprobe"""
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', 
                   '-show_format', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return 1800.0  # Default 30 minutes
    
    def _extract_audio_ffmpeg(self, video_path):
        """Extract audio using ffmpeg"""
        audio_path = os.path.join('temp', f"audio_{os.path.basename(video_path)}.wav")
        
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-ac', '1',  # mono
            '-ar', '22050',  # lower sample rate
            # Remove time limit - analyze the full video
            audio_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        return audio_path
    
    def _detect_volume_spikes_pydub(self, audio):
        """Detect volume spikes using pydub"""
        moments = []
        
        # Analyze in 2-second chunks
        chunk_duration = 2000  # 2 seconds in ms
        
        for i in range(0, len(audio), chunk_duration // 2):  # 50% overlap
            chunk = audio[i:i + chunk_duration]
            if len(chunk) < 1000:  # Skip very short chunks
                continue
                
            # Calculate RMS volume
            rms = chunk.rms
            
            # Get time position
            time_pos = i / 1000.0  # Convert to seconds
            
            # Much lower threshold - LoL gameplay audio varies widely
            if rms > 300:  # Lowered from 1000 to catch more moments
                moments.append({
                    'start_time': time_pos,
                    'end_time': time_pos + 3.0,
                    'type': 'volume_spike',
                    'excitement_score': rms / 500.0,
                    'detection_reason': 'Volume spike detected',
                    'duration': 3.0
                })
        
        return moments
    
    def _detect_audio_density(self, audio):
        """Detect periods of high audio activity"""
        moments = []
        
        # Look for periods with many audio changes
        chunk_duration = 3000  # 3 seconds
        
        for i in range(0, len(audio), chunk_duration):
            chunk = audio[i:i + chunk_duration]
            if len(chunk) < 2000:
                continue
                
            # Calculate how much the audio changes
            changes = 0
            prev_rms = 0
            
            for j in range(0, len(chunk), 100):  # 100ms segments
                segment = chunk[j:j + 100]
                if len(segment) > 0:
                    current_rms = segment.rms
                    if abs(current_rms - prev_rms) > 200:
                        changes += 1
                    prev_rms = current_rms
            
            time_pos = i / 1000.0
            
            # Lower threshold for audio activity
            if changes > 5:  # Lowered from 10 to catch more activity
                moments.append({
                    'start_time': time_pos,
                    'end_time': time_pos + 4.0,
                    'type': 'high_activity',
                    'excitement_score': changes / 5.0,
                    'detection_reason': 'High audio activity',
                    'duration': 4.0
                })
        
        return moments
    
    def _detect_action_transitions(self, audio):
        """Detect transitions from quiet to loud (often indicates action)"""
        moments = []
        
        chunk_duration = 1000  # 1 second chunks
        quiet_threshold = 100  # Much lower - some LoL streams are quiet
        loud_threshold = 400   # Lowered from 800 to catch more action
        
        prev_quiet = False
        
        for i in range(0, len(audio), chunk_duration):
            chunk = audio[i:i + chunk_duration]
            if len(chunk) < 500:
                continue
                
            rms = chunk.rms
            time_pos = i / 1000.0
            
            is_quiet = rms < quiet_threshold
            is_loud = rms > loud_threshold
            
            # Transition from quiet to loud
            if prev_quiet and is_loud:
                moments.append({
                    'start_time': time_pos,
                    'end_time': time_pos + 5.0,
                    'type': 'action_start',
                    'excitement_score': rms / 200.0,
                    'detection_reason': 'Action transition',
                    'duration': 5.0
                })
            
            prev_quiet = is_quiet
        
        return moments
    
    def _merge_and_rank_simple(self, all_moments, video_duration):
        """Simple merging and ranking"""
        if not all_moments:
            return []
        
        # Sort by excitement score
        all_moments.sort(key=lambda x: x['excitement_score'], reverse=True)
        
        # Take top moments and spread them out
        final_clips = []
        used_times = []
        
        for moment in all_moments:
            # Check if this moment is too close to an already selected one
            too_close = False
            for used_time in used_times:
                if abs(moment['start_time'] - used_time) < 20:  # 20 second separation (was 30)
                    too_close = True
                    break
            
            if not too_close and len(final_clips) < 15:  # Max 15 clips for long videos
                # Ensure clip doesn't exceed video duration
                moment['end_time'] = min(moment['end_time'], video_duration)
                moment['duration'] = moment['end_time'] - moment['start_time']
                
                if moment['duration'] >= 2.0:  # At least 2 seconds
                    final_clips.append(moment)
                    used_times.append(moment['start_time'])
        
        return final_clips
    
    def _generate_fallback_clips(self, video_path):
        """Generate some basic clips if analysis fails"""
        try:
            duration = self._get_video_duration(video_path)
            clips = []
            
            # Create clips every 4-5 minutes for a decent spread
            interval = max(240, duration / 12)  # 4 minutes minimum, up to 12 clips max
            
            # Start from different points for variety
            start_offsets = [60, 120, 180]  # 1, 2, 3 minute offsets
            
            for offset in start_offsets:
                for i in range(int(duration / interval)):
                    start_time = offset + (i * interval)
                    if start_time + 12 < duration:  # Ensure 12 seconds available
                        clips.append({
                            'start_time': start_time,
                            'end_time': start_time + 10.0,  # 10 second clips
                            'type': 'periodic',
                            'excitement_score': 2.0 + (i * 0.1),  # Slight score variation
                            'detection_reason': f'Periodic sampling at {offset}s offset',
                            'duration': 10.0
                        })
                        
                        if len(clips) >= 8:  # Generate at least 8 clips for long videos
                            break
                if len(clips) >= 8:
                    break
            
            logger.info(f"Generated {len(clips)} fallback clips for {duration:.1f}s video")
            return clips[:10]  # Return max 10 clips
            
        except Exception as e:
            logger.error(f"Fallback generation failed: {str(e)}")
            return []