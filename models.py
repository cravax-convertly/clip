from datetime import datetime
from app import db
from sqlalchemy import Integer, String, DateTime, Text, Float, Boolean, JSON

class VideoUpload(db.Model):
    id = db.Column(Integer, primary_key=True)
    filename = db.Column(String(255), nullable=False)
    original_filename = db.Column(String(255), nullable=False)
    file_path = db.Column(String(500), nullable=False)
    file_size = db.Column(Integer, nullable=False)
    duration = db.Column(Float)  # Duration in seconds
    upload_time = db.Column(DateTime, default=datetime.utcnow)
    processing_status = db.Column(String(50), default='uploaded')  # uploaded, processing, completed, failed
    error_message = db.Column(Text)
    
    # Processing metadata
    clips_generated = db.Column(Integer, default=0)
    processing_progress = db.Column(Float, default=0.0)
    task_id = db.Column(String(255))  # Celery task ID
    
    # Relationships
    clips = db.relationship('VideoClip', backref='source_video', lazy=True, cascade='all, delete-orphan')

class VideoClip(db.Model):
    id = db.Column(Integer, primary_key=True)
    video_upload_id = db.Column(Integer, db.ForeignKey('video_upload.id'), nullable=False)
    filename = db.Column(String(255), nullable=False)
    file_path = db.Column(String(500), nullable=False)
    
    # Clip metadata
    start_time = db.Column(Float, nullable=False)  # Start time in original video
    end_time = db.Column(Float, nullable=False)    # End time in original video
    duration = db.Column(Float, nullable=False)    # Clip duration
    
    # Detection metadata
    audio_spike_score = db.Column(Float)  # Audio excitement score
    detection_reason = db.Column(String(100))  # Why this clip was created
    
    # Processing metadata
    has_captions = db.Column(Boolean, default=False)
    has_watermark = db.Column(Boolean, default=False)
    transcription = db.Column(Text)
    transcription_data = db.Column(JSON)  # Detailed timing data
    
    # User interaction
    is_selected = db.Column(Boolean, default=True)  # User can deselect clips
    is_downloaded = db.Column(Boolean, default=False)
    
    created_at = db.Column(DateTime, default=datetime.utcnow)

# ProcessingJob model removed - using simplified processing without Celery
