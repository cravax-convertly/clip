import os
import numpy as np
import logging
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import librosa

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    def __init__(self):
        self.min_clip_duration = 30  # Minimum clip duration in seconds
        self.max_clip_duration = 60  # Maximum clip duration in seconds
        self.excitement_threshold = 0.7  # Threshold for excitement detection
        
    def detect_excitement_moments(self, video_path):
        """Detect exciting moments in video based on audio analysis"""
        try:
            logger.info(f"Analyzing audio for exciting moments: {video_path}")
            
            # Extract audio from video
            audio_path = self._extract_audio(video_path)
            
            # Load audio with librosa for analysis
            y, sr = librosa.load(audio_path)
            
            # Detect volume spikes
            volume_spikes = self._detect_volume_spikes(y, sr)
            
            # Detect spectral changes (indicating excitement)
            spectral_changes = self._detect_spectral_changes(y, sr)
            
            # Combine detection methods
            excitement_moments = self._combine_detections(volume_spikes, spectral_changes)
            
            # Filter and optimize clip boundaries
            optimized_clips = self._optimize_clip_boundaries(excitement_moments, len(y) / sr)
            
            # Clean up temporary audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            logger.info(f"Found {len(optimized_clips)} exciting moments")
            return optimized_clips
            
        except Exception as e:
            logger.error(f"Error detecting excitement moments: {str(e)}")
            return []
    
    def _extract_audio(self, video_path):
        """Extract audio from video file"""
        try:
            audio_path = os.path.join('temp', f"audio_{os.path.basename(video_path)}.wav")
            
            # Use pydub to extract audio
            audio = AudioSegment.from_file(video_path)
            audio.export(audio_path, format="wav")
            
            return audio_path
            
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise
    
    def _detect_volume_spikes(self, y, sr):
        """Detect sudden volume increases that might indicate exciting moments"""
        try:
            # Calculate RMS energy in sliding windows
            hop_length = sr // 2  # 0.5 second windows
            rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
            
            # Convert to dB
            rms_db = librosa.amplitude_to_db(rms)
            
            # Calculate moving average and standard deviation
            window_size = 10  # 5 seconds
            moving_avg = np.convolve(rms_db, np.ones(window_size)/window_size, mode='same')
            moving_std = np.array([
                np.std(rms_db[max(0, i-window_size//2):min(len(rms_db), i+window_size//2)])
                for i in range(len(rms_db))
            ])
            
            # Detect spikes (values significantly above moving average)
            spike_threshold = moving_avg + 1.5 * moving_std
            spikes = rms_db > spike_threshold
            
            # Convert frame indices to time
            spike_times = []
            for i, is_spike in enumerate(spikes):
                if is_spike:
                    time = i * hop_length / sr
                    score = (rms_db[i] - moving_avg[i]) / (moving_std[i] + 1e-6)
                    spike_times.append({'time': time, 'score': score, 'type': 'volume'})
            
            return spike_times
            
        except Exception as e:
            logger.error(f"Error detecting volume spikes: {str(e)}")
            return []
    
    def _detect_spectral_changes(self, y, sr):
        """Detect spectral changes that might indicate excitement (shouting, music changes)"""
        try:
            # Calculate spectral centroid (brightness of sound)
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            
            # Calculate spectral rolloff (where most energy is concentrated)
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            
            # Calculate zero crossing rate (roughness of sound)
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            
            # Detect sudden changes in spectral features
            hop_length = 512
            frame_duration = hop_length / sr
            
            changes = []
            for i in range(1, len(spectral_centroids)):
                # Calculate relative changes
                centroid_change = abs(spectral_centroids[i] - spectral_centroids[i-1]) / (spectral_centroids[i-1] + 1e-6)
                rolloff_change = abs(spectral_rolloff[i] - spectral_rolloff[i-1]) / (spectral_rolloff[i-1] + 1e-6)
                zcr_change = abs(zcr[i] - zcr[i-1]) / (zcr[i-1] + 1e-6)
                
                # Combined spectral change score
                change_score = centroid_change + rolloff_change + zcr_change
                
                if change_score > 0.5:  # Threshold for significant change
                    time = i * frame_duration
                    changes.append({'time': time, 'score': change_score, 'type': 'spectral'})
            
            return changes
            
        except Exception as e:
            logger.error(f"Error detecting spectral changes: {str(e)}")
            return []
    
    def _combine_detections(self, volume_spikes, spectral_changes):
        """Combine different detection methods to find the best moments"""
        try:
            all_moments = volume_spikes + spectral_changes
            
            # Sort by time
            all_moments.sort(key=lambda x: x['time'])
            
            # Merge nearby moments and calculate combined scores
            merged_moments = []
            current_moment = None
            merge_window = 5.0  # Merge moments within 5 seconds
            
            for moment in all_moments:
                if current_moment is None:
                    current_moment = moment.copy()
                elif moment['time'] - current_moment['time'] <= merge_window:
                    # Merge with current moment
                    current_moment['score'] = max(current_moment['score'], moment['score'])
                    current_moment['time'] = (current_moment['time'] + moment['time']) / 2
                else:
                    # Start new moment
                    if current_moment['score'] >= self.excitement_threshold:
                        merged_moments.append(current_moment)
                    current_moment = moment.copy()
            
            # Don't forget the last moment
            if current_moment and current_moment['score'] >= self.excitement_threshold:
                merged_moments.append(current_moment)
            
            return merged_moments
            
        except Exception as e:
            logger.error(f"Error combining detections: {str(e)}")
            return []
    
    def _optimize_clip_boundaries(self, excitement_moments, total_duration):
        """Optimize clip start and end times for better viewing experience"""
        try:
            optimized_clips = []
            
            for moment in excitement_moments:
                excitement_time = moment['time']
                
                # Calculate clip boundaries
                # Put excitement moment in the middle-to-end of clip for buildup
                clip_duration = min(self.max_clip_duration, 
                                  max(self.min_clip_duration, 45))  # Default 45 seconds
                
                # Place excitement 2/3 through the clip
                pre_excitement = clip_duration * 0.6
                post_excitement = clip_duration * 0.4
                
                start_time = max(0, excitement_time - pre_excitement)
                end_time = min(total_duration, excitement_time + post_excitement)
                
                # Adjust if we hit boundaries
                actual_duration = end_time - start_time
                if actual_duration < self.min_clip_duration:
                    if start_time == 0:
                        end_time = min(total_duration, start_time + self.min_clip_duration)
                    elif end_time == total_duration:
                        start_time = max(0, end_time - self.min_clip_duration)
                
                clip = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time,
                    'excitement_time': excitement_time,
                    'score': moment['score']
                }
                
                optimized_clips.append(clip)
            
            # Remove overlapping clips, keeping the highest scoring ones
            optimized_clips = self._remove_overlaps(optimized_clips)
            
            return optimized_clips
            
        except Exception as e:
            logger.error(f"Error optimizing clip boundaries: {str(e)}")
            return []
    
    def _remove_overlaps(self, clips):
        """Remove overlapping clips, keeping the highest scoring ones"""
        try:
            if not clips:
                return []
            
            # Sort by score (descending)
            clips.sort(key=lambda x: x['score'], reverse=True)
            
            non_overlapping = []
            for clip in clips:
                # Check if this clip overlaps with any already selected clip
                overlaps = False
                for selected in non_overlapping:
                    if (clip['start_time'] < selected['end_time'] and 
                        clip['end_time'] > selected['start_time']):
                        overlaps = True
                        break
                
                if not overlaps:
                    non_overlapping.append(clip)
            
            # Sort by start time for final output
            non_overlapping.sort(key=lambda x: x['start_time'])
            
            return non_overlapping
            
        except Exception as e:
            logger.error(f"Error removing overlaps: {str(e)}")
            return clips
