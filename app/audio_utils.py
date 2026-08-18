# app/audio_utils.py
import numpy as np
import librosa
from pydub import AudioSegment

def extract_audio_metrics(file_path: str) -> dict:
    # 1. Basic Metadata via Pydub
    audio = AudioSegment.from_file(file_path)
    duration_sec = round(len(audio) / 1000.0, 2)
    sample_rate_hz = audio.frame_rate
    bitrate_kbps = round((audio.frame_rate * audio.sample_width * 8 * audio.channels) / 1000.0, 2)
    loudness_db = round(audio.dBFS, 2)

    # 2. Signal-to-Noise Ratio (SNR) via Librosa
    y, sr = librosa.load(file_path, sr=None)
    signal_power = np.mean(y ** 2)
    
    # Estimate noise power from quietest 10% frames
    frame_len = int(sr * 0.05)
    frames = librosa.util.frame(y, frame_length=frame_len, hop_length=frame_len // 2)
    frame_powers = np.mean(frames ** 2, axis=0)
    noise_power = np.mean(np.sort(frame_powers)[:max(1, len(frame_powers) // 10)])
    
    snr_db = round(10 * np.log10(signal_power / (noise_power + 1e-10)), 2)
    
    if snr_db > 20: quality_label = "Clean / High Quality"
    elif snr_db > 10: quality_label = "Moderate Noise"
    else: quality_label = "High Background Noise"

    return {
        "duration_seconds": duration_sec,
        "sample_rate_hz": sample_rate_hz,
        "bitrate_kbps": bitrate_kbps,
        "loudness_db": loudness_db,
        "snr_db": snr_db,
        "quality_label": quality_label
    }
