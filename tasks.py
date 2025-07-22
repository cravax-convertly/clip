import os
import logging
from datetime import datetime
from celery import current_task
from app import celery, db
from models import VideoUpload, VideoClip, ProcessingJob
from video_processor import VideoProcessor
from audio_analyzer import AudioAnalyzer
from transcription_service import TranscriptionService

logger = logging.getLogger(__name__)

@celery.task(bind=True)
def process_video_task(self, video_upload_id):
    """Main task to process uploaded video and generate clips"""
    logger.info(f"Starting video processing for upload ID: {video_upload_id}")
    
    try:
        # Get video upload record
        video_upload = VideoUpload.query.get(video_upload_id)
        if not video_upload:
            raise Exception(f"Video upload {video_upload_id} not found")
        
        # Update status
        video_upload.processing_status = 'processing'
        video_upload.task_id = self.request.id
        db.session.commit()
        
        # Create processing job record
        job = ProcessingJob(
            video_upload_id=video_upload_id,
            task_id=self.request.id,
            status='running',
            current_step='Initializing'
        )
        db.session.add(job)
        db.session.commit()
        
        # Initialize processors
        video_processor = VideoProcessor()
        audio_analyzer = AudioAnalyzer()
        transcription_service = TranscriptionService()
        
        # Step 1: Analyze video metadata
        self.update_state(state='PROGRESS', meta={'progress': 10, 'step': 'Analyzing video'})
        job.progress = 10
        job.current_step = 'Analyzing video metadata'
        db.session.commit()
        
        video_info = video_processor.get_video_info(video_upload.file_path)
        video_upload.duration = video_info.get('duration', 0)
        
        # Step 2: Detect audio spikes for exciting moments
        self.update_state(state='PROGRESS', meta={'progress': 30, 'step': 'Detecting exciting moments'})
        job.progress = 30
        job.current_step = 'Analyzing audio for exciting moments'
        db.session.commit()
        
        audio_spikes = audio_analyzer.detect_excitement_moments(video_upload.file_path)
        logger.info(f"Found {len(audio_spikes)} potential exciting moments")
        
        # Step 3: Generate clips from detected moments
        self.update_state(state='PROGRESS', meta={'progress': 50, 'step': 'Generating clips'})
        job.progress = 50
        job.current_step = 'Extracting video clips'
        job.total_clips_found = len(audio_spikes)
        db.session.commit()
        
        clips_created = 0
        for i, spike in enumerate(audio_spikes):
            try:
                # Extract clip
                clip_filename = f"clip_{video_upload_id}_{i+1}.mp4"
                clip_path = video_processor.extract_clip(
                    video_upload.file_path,
                    spike['start_time'],
                    spike['end_time'],
                    clip_filename
                )
                
                # Convert to vertical format
                vertical_clip_path = video_processor.convert_to_vertical(clip_path)
                
                # Create clip record
                clip = VideoClip(
                    video_upload_id=video_upload_id,
                    filename=os.path.basename(vertical_clip_path),
                    file_path=vertical_clip_path,
                    start_time=spike['start_time'],
                    end_time=spike['end_time'],
                    duration=spike['end_time'] - spike['start_time'],
                    audio_spike_score=spike['score'],
                    detection_reason='audio_spike'
                )
                db.session.add(clip)
                clips_created += 1
                
                # Update progress
                progress = 50 + (i + 1) / len(audio_spikes) * 30
                self.update_state(state='PROGRESS', meta={'progress': progress, 'step': f'Generated clip {i+1}/{len(audio_spikes)}'})
                job.progress = progress
                job.clips_processed = i + 1
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error processing clip {i+1}: {str(e)}")
                continue
        
        # Step 4: Process transcriptions and captions
        self.update_state(state='PROGRESS', meta={'progress': 80, 'step': 'Adding captions'})
        job.progress = 80
        job.current_step = 'Generating transcriptions and captions'
        db.session.commit()
        
        clips = VideoClip.query.filter_by(video_upload_id=video_upload_id).all()
        for i, clip in enumerate(clips):
            try:
                # Transcribe audio
                transcription_data = transcription_service.transcribe_clip(clip.file_path)
                clip.transcription = transcription_data['text']
                clip.transcription_data = transcription_data
                
                # Add captions to video
                captioned_path = video_processor.add_captions(
                    clip.file_path,
                    transcription_data
                )
                
                # Add watermark/logo
                final_path = video_processor.add_watermark(captioned_path)
                
                # Update clip record
                clip.file_path = final_path
                clip.has_captions = True
                clip.has_watermark = True
                
                progress = 80 + (i + 1) / len(clips) * 15
                self.update_state(state='PROGRESS', meta={'progress': progress, 'step': f'Captioned {i+1}/{len(clips)} clips'})
                
            except Exception as e:
                logger.error(f"Error adding captions to clip {clip.id}: {str(e)}")
                continue
        
        # Final step: Complete processing
        self.update_state(state='PROGRESS', meta={'progress': 100, 'step': 'Completed'})
        video_upload.processing_status = 'completed'
        video_upload.clips_generated = clips_created
        video_upload.processing_progress = 100.0
        
        job.status = 'completed'
        job.progress = 100.0
        job.current_step = 'Processing completed'
        job.completed_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(f"Video processing completed. Generated {clips_created} clips.")
        return {
            'status': 'completed',
            'clips_generated': clips_created,
            'message': f'Successfully generated {clips_created} clips'
        }
        
    except Exception as e:
        logger.error(f"Video processing failed: {str(e)}")
        
        # Update records with error
        if 'video_upload' in locals():
            video_upload.processing_status = 'failed'
            video_upload.error_message = str(e)
        
        if 'job' in locals():
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
        
        db.session.commit()
        
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise Exception(f"Video processing failed: {str(e)}")
