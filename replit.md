# ClipForge - Stream to Viral Clips Web App

## Overview

ClipForge is a web application that automatically transforms League of Legends stream recordings into TikTok-ready clips. The system analyzes uploaded videos to detect exciting moments, generates clips with captions and branding, and provides a dashboard for managing and downloading the processed content.

## User Preferences

Preferred communication style: Simple, everyday language.
File upload limit: Increased to 2GB to support 3-4 hour League of Legends stream recordings.

## System Architecture

### Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM for database management
- **Task Queue**: Celery with Redis as both broker and result backend for asynchronous video processing
- **Database**: SQLite (development) with PostgreSQL support via environment configuration
- **File Storage**: Local filesystem with organized folder structure (temp/, processed/)

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Flask
- **Styling**: TailwindCSS via CDN for responsive design
- **JavaScript**: Vanilla ES6 with class-based components
- **Icons**: Font Awesome for consistent iconography

### Processing Pipeline
The application uses a multi-stage video processing pipeline:
1. Audio extraction and analysis for excitement detection
2. Video clipping based on detected moments
3. Speech transcription using OpenAI Whisper API
4. Caption overlay and branding application
5. Final clip optimization and storage

## Key Components

### Core Models (`models.py`)
- **VideoUpload**: Tracks uploaded videos with metadata, processing status, and progress
- **VideoClip**: Represents generated clips with timing, detection scores, and transcription data
- Supports cascade deletion and comprehensive metadata tracking

### Video Processing (`video_processor.py`)
- **VideoProcessor**: Handles video metadata extraction, clip cutting using ffmpeg
- Supports multiple video formats (MP4, AVI, MOV, MKV, WebM)
- Implements efficient clip extraction with precise timing

### Audio Analysis (`audio_analyzer.py`)
- **AudioAnalyzer**: Detects excitement moments through volume spike analysis
- Uses librosa for spectral analysis and pydub for audio processing
- Combines multiple detection methods for optimal clip identification

### Background Tasks (`tasks.py`)
- Celery-based asynchronous processing with progress tracking
- Multi-step pipeline with status updates stored in database
- Error handling and recovery mechanisms

### External Services
- **OpenAI Whisper**: Speech-to-text transcription with timing segments
- **Redis**: Task queue management and caching
- **FFmpeg**: Video/audio processing backend

## Data Flow

1. **Upload Phase**: User uploads video → File validation → Database record creation
2. **Processing Phase**: Celery task queued → Audio analysis → Clip detection → Video cutting
3. **Transcription Phase**: Audio extraction → OpenAI Whisper API → Caption generation
4. **Finalization Phase**: Clip assembly → Metadata storage → User notification
5. **Download Phase**: Dashboard access → Clip selection → File delivery

## External Dependencies

### Python Packages
- Flask ecosystem (Flask, SQLAlchemy, Celery)
- Video/Audio processing (moviepy, librosa, pydub)
- AI services (openai for Whisper API)
- System tools (redis, PIL for image processing)

### System Dependencies
- **FFmpeg**: Core video processing engine
- **Redis**: Message broker and result backend
- **Tesseract OCR**: Future implementation for game event detection

### API Dependencies
- **OpenAI API**: Whisper model for transcription (requires API key)
- **Future integrations**: Social media APIs for auto-posting (TikTok, Instagram, YouTube)

## Deployment Strategy

### Development Environment
- Flask development server with debug mode
- SQLite database for rapid development
- Local Redis instance for task queue
- Environment variables for configuration

### Production Considerations
- **Database**: Configurable via DATABASE_URL (supports PostgreSQL)
- **Proxy**: ProxyFix middleware for reverse proxy deployment
- **Security**: Configurable session secrets via environment
- **Scaling**: Celery workers can be distributed across multiple servers

### Configuration Management
- Environment-based configuration for database, Redis, and API keys
- Fallback values for development environment
- Production-ready connection pooling and health checks
- File upload limit: 2GB maximum (updated July 22, 2025)

### File Storage
- Current: Local filesystem with organized directories
- Upload limit: 2GB to support long stream recordings (3-4 hours)
- Future: Could integrate with cloud storage (S3, GCS) for scalability
- Temporary file cleanup and space management built-in

## Recent Changes

### July 22, 2025 - LoL Highlight Detection System
- **Major Feature**: Implemented research-based League of Legends highlight detection system
- **Audio Analysis**: Created SimpleLoLAnalyzer with 4 detection methods:
  - Volume spike detection for teamfights (3x threshold above baseline)
  - Audio density analysis for combat periods using spectral analysis
  - Action transition detection (quiet-to-loud moments)
  - Fallback periodic sampling for reliability
- **Fixed Critical Issues**:
  - Resolved Redis/Celery memory crashes by switching to synchronous processing
  - Fixed automatic processing trigger - now requires manual "Start Processing" button
  - Removed librosa dependency causing worker crashes
  - Fixed dashboard Redis import error
- **Real Clip Generation**: System now creates actual video files using ffmpeg extraction
- **Database Integration**: Clips properly saved with metadata (excitement scores, detection reasons)
- **Performance**: Lightweight analysis (first 60 seconds) to avoid memory issues
- **File Handling**: Increased upload limit to 2GB for long stream recordings
- **User Experience**: Manual processing control, better error handling