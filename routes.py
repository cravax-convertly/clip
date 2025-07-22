import os
import json
import logging
from datetime import datetime
from flask import render_template, request, jsonify, send_file, abort, flash, redirect, url_for
from werkzeug.utils import secure_filename
from app import app, db
from models import VideoUpload, VideoClip

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main upload page"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard showing processed videos and clips"""
    videos = VideoUpload.query.order_by(VideoUpload.upload_time.desc()).all()
    return render_template('dashboard.html', videos=videos)

@app.route('/upload', methods=['POST'])
def upload_video():
    """Handle video file upload"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload MP4, AVI, MOV, MKV, or WebM files.'}), 400
        
        # Secure the filename
        original_filename = file.filename
        if not original_filename:
            return jsonify({'error': 'No filename provided'}), 400
        filename = secure_filename(original_filename)
        
        # Add timestamp to avoid conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Save file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create database record
        video_upload = VideoUpload()
        video_upload.filename = filename
        video_upload.original_filename = original_filename
        video_upload.file_path = file_path
        video_upload.file_size = file_size
        video_upload.processing_status = 'uploaded'
        
        db.session.add(video_upload)
        db.session.commit()
        
        logger.info(f"Video uploaded successfully: {filename} (ID: {video_upload.id})")
        
        return jsonify({
            'success': True,
            'message': 'Video uploaded successfully',
            'video_id': video_upload.id,
            'filename': original_filename
        })
        
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/process/<int:video_id>', methods=['POST'])
def start_processing(video_id):
    """Start processing a video"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        
        if video.processing_status == 'processing':
            return jsonify({'error': 'Video is already being processed'}), 400
        
        # For now, do basic processing without Celery to make it work
        # Update video record
        video.processing_status = 'processing'
        db.session.commit()
        
        try:
            # Advanced LoL highlight processing with HUD detection + OCR + Audio
            from video_processor import VideoProcessor
            from highlight_detector import SmartLoLHighlightDetector
            
            processor = VideoProcessor()
            smart_detector = SmartLoLHighlightDetector()
            
            # Get basic video info
            video_info = processor.get_video_info(video.file_path)
            video.duration = video_info.get('duration', 0)
            db.session.commit()
            
            logger.info(f"Video duration: {video.duration} seconds")
            
            # Use advanced detection with HUD verification
            if video.duration > 1800:  # 30 minutes - use fast detection
                highlight_moments = smart_detector.detect_highlights_fast(video.file_path)
            else:
                highlight_moments = smart_detector.detect_smart_highlights(video.file_path)
            
            logger.info(f"Found {len(highlight_moments)} verified highlights")
            
            # Create actual working clips with verification
            clips_created = 0
            max_clips = min(3, len(highlight_moments))  # Limit to 3 clips to prevent timeout
            for i, moment in enumerate(highlight_moments[:max_clips]):
                try:
                    # Create a shorter, more manageable clip
                    clip_duration = min(30, moment['duration'])  # Max 30 seconds
                    clip_start = moment['start_time']
                    clip_end = clip_start + clip_duration
                    
                    clip_filename = f"clip_{video_id}_{i+1}_{moment['type']}.mp4"
                    
                    logger.info(f"Creating clip {i+1}: {clip_start:.1f}s - {clip_end:.1f}s ({clip_duration}s)")
                    
                    # Extract the clip now
                    clip_path = processor.extract_clip(
                        video.file_path,
                        clip_start,
                        clip_end,
                        clip_filename
                    )
                    
                    # Verify the clip was created successfully
                    if clip_path and os.path.exists(clip_path) and os.path.getsize(clip_path) > 1000:  # At least 1KB
                        # Create database record for the verified clip
                        video_clip = VideoClip()
                        video_clip.video_upload_id = video_id
                        video_clip.filename = clip_filename
                        video_clip.file_path = clip_path
                        video_clip.start_time = clip_start
                        video_clip.end_time = clip_end
                        video_clip.duration = clip_duration
                        video_clip.audio_spike_score = moment.get('excitement_score', 0.5)
                        video_clip.detection_reason = moment.get('detection_reason', 'Smart detection')
                        video_clip.is_selected = True
                        
                        db.session.add(video_clip)
                        clips_created += 1
                        
                        logger.info(f"Successfully created clip {i+1}: {os.path.getsize(clip_path)} bytes")
                    else:
                        logger.error(f"Clip {i+1} creation failed or file too small")
                        
                except Exception as clip_error:
                    logger.error(f"Failed to create clip {i+1}: {str(clip_error)}")
                    continue
            
            # Update video status
            video.processing_status = 'completed'
            video.processing_progress = 100.0
            video.clips_generated = clips_created
            db.session.commit()
            
            logger.info(f"LoL processing completed for video {video_id}: {clips_created} clips created from {max_clips} attempted")
            
        except Exception as e:
            video.processing_status = 'failed'
            video.error_message = str(e)
            db.session.commit()
            logger.error(f"Processing failed for video {video_id}: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'Processing completed: {video.clips_generated} clips generated',
            'video_id': video_id,
            'clips_generated': video.clips_generated
        })
        
    except Exception as e:
        logger.error(f"Error starting processing: {str(e)}")
        return jsonify({'error': f'Failed to start processing: {str(e)}'}), 500

@app.route('/status/<int:video_id>')
def get_processing_status(video_id):
    """Get processing status for a video"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        
        result = {
            'video_id': video_id,
            'status': video.processing_status,
            'progress': video.processing_progress,
            'clips_generated': video.clips_generated,
            'error_message': video.error_message
        }
        
        # Processing status is handled directly by video record now
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({'error': f'Failed to get status: {str(e)}'}), 500

@app.route('/clips/<int:video_id>')
def get_clips(video_id):
    """Get clips for a video"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        clips = VideoClip.query.filter_by(video_upload_id=video_id).order_by(VideoClip.start_time).all()
        
        clips_data = []
        for clip in clips:
            clips_data.append({
                'id': clip.id,
                'filename': clip.filename,
                'start_time': clip.start_time,
                'end_time': clip.end_time,
                'duration': clip.duration,
                'audio_spike_score': clip.audio_spike_score,
                'detection_reason': clip.detection_reason,
                'has_captions': clip.has_captions,
                'has_watermark': clip.has_watermark,
                'transcription': clip.transcription,
                'is_selected': clip.is_selected,
                'is_downloaded': clip.is_downloaded
            })
        
        return jsonify({
            'video_id': video_id,
            'clips': clips_data,
            'total_clips': len(clips_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting clips: {str(e)}")
        return jsonify({'error': f'Failed to get clips: {str(e)}'}), 500

@app.route('/clip/<int:clip_id>/toggle', methods=['POST'])
def toggle_clip_selection(clip_id):
    """Toggle clip selection status"""
    try:
        clip = VideoClip.query.get_or_404(clip_id)
        clip.is_selected = not clip.is_selected
        db.session.commit()
        
        return jsonify({
            'success': True,
            'clip_id': clip_id,
            'is_selected': clip.is_selected
        })
        
    except Exception as e:
        logger.error(f"Error toggling clip selection: {str(e)}")
        return jsonify({'error': f'Failed to toggle selection: {str(e)}'}), 500

@app.route('/download/clip/<int:clip_id>')
def download_clip(clip_id):
    """Download a specific clip - extract on demand"""
    try:
        clip = VideoClip.query.get_or_404(clip_id)
        video = VideoUpload.query.get_or_404(clip.video_upload_id)
        
        # Check if clip file already exists
        if not os.path.exists(clip.file_path):
            logger.info(f"Extracting clip {clip_id} on demand")
            
            # Extract the clip now
            from video_processor import VideoProcessor
            processor = VideoProcessor()
            
            try:
                clip_path = processor.extract_clip(
                    video.file_path,
                    clip.start_time,
                    clip.end_time,
                    clip.filename
                )
                
                # Update the clip path in database
                clip.file_path = clip_path
                db.session.commit()
                
            except Exception as extract_error:
                logger.error(f"Failed to extract clip {clip_id}: {str(extract_error)}")
                abort(500, f"Failed to extract clip: {str(extract_error)}")
        
        # Mark as downloaded
        clip.is_downloaded = True
        db.session.commit()
        
        return send_file(
            clip.file_path,
            as_attachment=True,
            download_name=clip.filename
        )
        
    except Exception as e:
        logger.error(f"Error downloading clip: {str(e)}")
        abort(500, f"Download failed: {str(e)}")

@app.route('/download/clip/<int:clip_id>/vertical')
def download_vertical_clip(clip_id):
    """Download a vertical social media ready clip"""
    try:
        clip = VideoClip.query.get_or_404(clip_id)
        video = VideoUpload.query.get_or_404(clip.video_upload_id)
        
        # Create vertical version filename
        vertical_filename = f"vertical_{clip.filename}"
        vertical_path = os.path.join("temp", vertical_filename)
        
        # Check if vertical version exists
        if not os.path.exists(vertical_path):
            logger.info(f"Creating vertical clip {clip_id}")
            
            from video_processor import VideoProcessor
            processor = VideoProcessor()
            
            try:
                # Extract vertical clip directly
                vertical_path = processor.extract_vertical_clip(
                    video.file_path,
                    clip.start_time,
                    clip.end_time,
                    vertical_filename
                )
                
                # Add watermark
                watermarked_filename = f"watermarked_{vertical_filename}"
                watermarked_path = processor.add_watermark(vertical_path, watermarked_filename)
                
                if watermarked_path != vertical_path:
                    vertical_path = watermarked_path
                
            except Exception as create_error:
                logger.error(f"Failed to create vertical clip {clip_id}: {str(create_error)}")
                abort(500, f"Failed to create vertical clip: {str(create_error)}")
        
        return send_file(
            vertical_path,
            as_attachment=True,
            download_name=vertical_filename
        )
        
    except Exception as e:
        logger.error(f"Error downloading vertical clip: {str(e)}")
        abort(500, f"Vertical download failed: {str(e)}")

@app.route('/debug/events/<int:video_id>')
def debug_events(video_id):
    """Debug endpoint to view detected events for a video"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        
        if not os.path.exists(video.file_path):
            return jsonify({'error': 'Video file not found'}), 404
        
        from highlight_detector import SmartLoLHighlightDetector
        detector = SmartLoLHighlightDetector()
        
        # Get all detection components
        gameplay_periods = detector.hud_detector.analyze_gameplay_periods(video.file_path)
        kill_events = detector.kill_detector.detect_kill_events(video.file_path)
        audio_moments = detector.audio_analyzer.detect_lol_highlights(video.file_path)
        
        # Run full smart detection
        highlights = detector.detect_smart_highlights(video.file_path)
        
        debug_info = {
            'video_id': video_id,
            'video_duration': video.duration,
            'gameplay_periods': gameplay_periods,
            'kill_events': kill_events,
            'audio_moments': [
                {
                    'start_time': m['start_time'],
                    'end_time': m['end_time'],
                    'excitement_score': m.get('excitement_score', 0),
                    'type': m.get('type', 'unknown')
                } for m in audio_moments
            ],
            'final_highlights': highlights,
            'processing_summary': {
                'gameplay_periods_found': len(gameplay_periods),
                'kill_events_detected': len(kill_events),
                'audio_moments_detected': len(audio_moments),
                'final_highlights_generated': len(highlights)
            }
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"Error debugging events: {str(e)}")
        return jsonify({'error': f'Debug failed: {str(e)}'}), 500

@app.route('/download/selected/<int:video_id>')
def download_selected_clips(video_id):
    """Download all selected clips as a ZIP file"""
    try:
        import zipfile
        import tempfile
        
        video = VideoUpload.query.get_or_404(video_id)
        selected_clips = VideoClip.query.filter_by(
            video_upload_id=video_id,
            is_selected=True
        ).all()
        
        if not selected_clips:
            return jsonify({'error': 'No clips selected for download'}), 400
        
        # Create temporary ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for clip in selected_clips:
                if os.path.exists(clip.file_path):
                    zipf.write(clip.file_path, clip.filename)
                    clip.is_downloaded = True
        
        db.session.commit()
        
        zip_filename = f"clips_{video.original_filename.split('.')[0]}.zip"
        
        return send_file(
            temp_zip.name,
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        logger.error(f"Error downloading selected clips: {str(e)}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/export/metadata/<int:video_id>')
def export_metadata(video_id):
    """Export metadata for all clips as JSON"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        clips = VideoClip.query.filter_by(video_upload_id=video_id).all()
        
        metadata = {
            'video': {
                'id': video.id,
                'original_filename': video.original_filename,
                'duration': video.duration,
                'upload_time': video.upload_time.isoformat() if video.upload_time else None,
                'processing_status': video.processing_status,
                'clips_generated': video.clips_generated
            },
            'clips': []
        }
        
        for clip in clips:
            clip_data = {
                'id': clip.id,
                'filename': clip.filename,
                'start_time': clip.start_time,
                'end_time': clip.end_time,
                'duration': clip.duration,
                'audio_spike_score': clip.audio_spike_score,
                'detection_reason': clip.detection_reason,
                'transcription': clip.transcription,
                'transcription_data': clip.transcription_data,
                'is_selected': clip.is_selected,
                'created_at': clip.created_at.isoformat() if clip.created_at else None
            }
            metadata['clips'].append(clip_data)
        
        # Create temporary JSON file
        import tempfile
        temp_json = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(metadata, temp_json, indent=2)
        temp_json.close()
        
        json_filename = f"metadata_{video.original_filename.split('.')[0]}.json"
        
        return send_file(
            temp_json.name,
            as_attachment=True,
            download_name=json_filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting metadata: {str(e)}")
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/delete/video/<int:video_id>', methods=['POST'])
def delete_video(video_id):
    """Delete a video and all its clips"""
    try:
        video = VideoUpload.query.get_or_404(video_id)
        
        # Delete all clip files
        clips = VideoClip.query.filter_by(video_upload_id=video_id).all()
        for clip in clips:
            if os.path.exists(clip.file_path):
                os.remove(clip.file_path)
        
        # Delete original video file
        if os.path.exists(video.file_path):
            os.remove(video.file_path)
        
        # Delete database records (clips will be deleted by cascade)
        db.session.delete(video)
        db.session.commit()
        
        logger.info(f"Deleted video {video_id} and all associated clips")
        
        return jsonify({
            'success': True,
            'message': 'Video and clips deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting video: {str(e)}")
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500
