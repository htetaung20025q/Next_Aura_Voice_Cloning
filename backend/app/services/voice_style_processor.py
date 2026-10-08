"""
Production-grade Voice Style & Character Effects Processor for Next Aura Voice Studio.
High-fidelity, CPU-friendly digital signal processing (DSP) engine with caching,
safe peak limiting, and non-blocking asynchronous execution.
"""

import asyncio
import io
import logging
import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings
from app.services.style_presets import (
    BasePresetEffect,
    StylePresetMeta,
    get_preset_effect,
    get_preset,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audio DSP Building Blocks
# ---------------------------------------------------------------------------

def _biquad_coefficients(filter_type: str, freq: float, sample_rate: float, q: float = 0.707, gain_db: float = 0.0):
    """Calculates Direct Form II Transposed Biquad filter coefficients."""
    w0 = 2.0 * math.pi * min(max(freq, 20.0), sample_rate * 0.49) / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * max(q, 0.05))
    a_linear = 10.0 ** (gain_db / 40.0)

    ft = filter_type.lower()
    if ft == "lowpass":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = (1.0 - cos_w0) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
    elif ft == "highpass":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = (1.0 + cos_w0) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
    elif ft == "bandpass":
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
    elif ft == "peaking" or ft == "bell":
        b0 = 1.0 + alpha * a_linear
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * a_linear
        a0 = 1.0 + alpha / a_linear
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / a_linear
    elif ft == "lowshelf":
        sqrt_a = math.sqrt(max(a_linear, 0.01))
        b0 = a_linear * ((a_linear + 1.0) - (a_linear - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = 2.0 * a_linear * ((a_linear - 1.0) - (a_linear + 1.0) * cos_w0)
        b2 = a_linear * ((a_linear + 1.0) - (a_linear - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a_linear + 1.0) + (a_linear - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = -2.0 * ((a_linear - 1.0) + (a_linear + 1.0) * cos_w0)
        a2 = (a_linear + 1.0) + (a_linear - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    elif ft == "highshelf":
        sqrt_a = math.sqrt(max(a_linear, 0.01))
        b0 = a_linear * ((a_linear + 1.0) + (a_linear - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = -2.0 * a_linear * ((a_linear - 1.0) + (a_linear + 1.0) * cos_w0)
        b2 = a_linear * ((a_linear + 1.0) + (a_linear - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a_linear + 1.0) - (a_linear - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = 2.0 * ((a_linear - 1.0) - (a_linear + 1.0) * cos_w0)
        a2 = (a_linear + 1.0) - (a_linear - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    else:
        return 1.0, 0.0, 0.0, 0.0, 0.0

    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _apply_biquad_filter(samples: List[float], b0: float, b1: float, b2: float, a1: float, a2: float) -> List[float]:
    """Applies a biquad filter in Direct Form II Transposed."""
    out = [0.0] * len(samples)
    d1 = 0.0
    d2 = 0.0
    for i, x in enumerate(samples):
        y = b0 * x + d1
        d1 = b1 * x - a1 * y + d2
        d2 = b2 * x - a2 * y
        out[i] = y
    return out


def _pitch_shift_sola(samples: List[float], sample_rate: int, semitones: float) -> List[float]:
    """
    Time-domain SOLA (Synchronous Overlap-Add) Pitch Shifter.
    Preserves exact audio duration while shifting pitch up or down.
    """
    if abs(semitones) < 0.05 or len(samples) < sample_rate * 0.05:
        return list(samples)

    factor = 2.0 ** (semitones / 12.0)
    orig_len = len(samples)

    # 1. Resample by factor
    resampled_len = int(orig_len / factor)
    if resampled_len < 10:
        return list(samples)

    resampled = [0.0] * resampled_len
    for i in range(resampled_len):
        src_pos = i * factor
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < orig_len:
            resampled[i] = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        elif idx < orig_len:
            resampled[i] = samples[idx]
        else:
            resampled[i] = 0.0

    # 2. SOLA Overlap-Add back to original duration
    win_size = int(sample_rate * 0.04)  # 40 ms window
    if win_size % 2 != 0:
        win_size += 1
    hop_syn = win_size // 4
    hop_ana = int(hop_syn / factor)
    if hop_ana < 1:
        hop_ana = 1

    # Hanning window
    window = [0.5 * (1.0 - math.cos(2.0 * math.pi * n / (win_size - 1))) for n in range(win_size)]

    output = [0.0] * orig_len
    weights = [0.0] * orig_len

    num_hops = int(orig_len / hop_syn)
    max_search = int(win_size * 0.3)

    in_pos = 0
    out_pos = 0

    for hop in range(num_hops):
        if in_pos + win_size >= len(resampled) or out_pos + win_size >= orig_len:
            break

        # Cross-correlation alignment for natural phase matching
        best_offset = 0
        if hop > 0 and in_pos + win_size + max_search < len(resampled):
            max_corr = -1e9
            for offset in range(-max_search // 2, max_search // 2):
                curr_in = in_pos + offset
                if curr_in < 0 or curr_in + win_size >= len(resampled):
                    continue
                # Fast sample correlation
                corr = 0.0
                step = 4
                for k in range(0, win_size, step):
                    corr += resampled[curr_in + k] * output[out_pos + k]
                if corr > max_corr:
                    max_corr = corr
                    best_offset = offset

        aligned_in = max(0, in_pos + best_offset)

        # Overlap add
        for k in range(win_size):
            if out_pos + k < orig_len and aligned_in + k < len(resampled):
                w = window[k]
                output[out_pos + k] += resampled[aligned_in + k] * w
                weights[out_pos + k] += w

        in_pos += hop_ana
        out_pos += hop_syn

    # Normalize window overlap weights
    for i in range(orig_len):
        if weights[i] > 0.01:
            output[i] /= weights[i]

    return output


def _apply_speed_stretch(samples: List[float], speed: float) -> List[float]:
    """Resamples audio to modify playback speed/tempo."""
    if abs(speed - 1.0) < 0.01 or len(samples) < 10:
        return samples
    new_len = int(len(samples) / speed)
    out = [0.0] * new_len
    for i in range(new_len):
        src_pos = i * speed
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(samples):
            out[i] = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        elif idx < len(samples):
            out[i] = samples[idx]
    return out


def _apply_distortion(samples: List[float], config: DistortionConfig, intensity: float) -> List[float]:
    """Applies saturation, asymmetric overdrive, hard clipping, or bitcrushing."""
    drive_lin = 10.0 ** ((config.drive_db * intensity) / 20.0)
    style = config.style.lower()
    out = [0.0] * len(samples)

    if style == "warm":
        # Soft tanh saturation with harmonic warmth
        norm_factor = math.tanh(drive_lin) if drive_lin > 0.01 else 1.0
        for i, x in enumerate(samples):
            out[i] = math.tanh(x * drive_lin) / norm_factor
    elif style == "overdrive":
        # Asymmetric overdrive (creates even + odd harmonics)
        for i, x in enumerate(samples):
            v = x * drive_lin
            if v > 1.0:
                out[i] = 1.0
            elif v < -1.0:
                out[i] = -1.0
            else:
                out[i] = v - 0.25 * (v ** 2) - 0.15 * (v ** 3)
    elif style == "hard":
        # Hard clipping
        for i, x in enumerate(samples):
            out[i] = max(-1.0, min(1.0, x * drive_lin))
    elif style == "bitcrush":
        # Quantize amplitude
        bits = max(4, min(16, int(config.bit_depth - (16 - config.bit_depth) * (intensity - 1.0))))
        levels = 2 ** (bits - 1)
        for i, x in enumerate(samples):
            v = max(-1.0, min(1.0, x * drive_lin))
            out[i] = round(v * levels) / levels
    else:
        out = list(samples)

    return out


def _apply_modulation(samples: List[float], sample_rate: int, config: ModulationConfig, intensity: float) -> List[float]:
    """Applies ring modulation, tremolo, vibrato, or chorus."""
    mod_type = config.mod_type.lower()
    depth = min(1.0, max(0.0, config.depth * intensity))
    rate = config.rate_hz
    n = len(samples)
    out = [0.0] * n

    if mod_type == "ring":
        # Cybernetic ring modulation
        for i, x in enumerate(samples):
            t = i / sample_rate
            carrier = math.cos(2.0 * math.pi * rate * t)
            mod_val = (1.0 - depth) + depth * carrier
            out[i] = x * mod_val
    elif mod_type == "tremolo":
        # Amplitude flutter
        for i, x in enumerate(samples):
            t = i / sample_rate
            mod_val = 1.0 - depth * (0.5 + 0.5 * math.sin(2.0 * math.pi * rate * t))
            out[i] = x * mod_val
    elif mod_type == "vibrato":
        # Pitch modulation via fractional delay
        max_delay_samples = int(sample_rate * 0.005)  # 5ms max
        delay_buf = [0.0] * (n + max_delay_samples + 10)
        delay_buf[:n] = samples
        for i in range(n):
            t = i / sample_rate
            mod_delay = (max_delay_samples / 2.0) * (1.0 + depth * math.sin(2.0 * math.pi * rate * t))
            idx = i + max_delay_samples - mod_delay
            i0 = int(idx)
            frac = idx - i0
            if 0 <= i0 < len(delay_buf) - 1:
                out[i] = delay_buf[i0] * (1.0 - frac) + delay_buf[i0 + 1] * frac
            else:
                out[i] = samples[i]
    elif mod_type == "chorus":
        # Rich multi-voice chorus
        max_delay = int(sample_rate * 0.03)  # 30ms
        delay_buf = [0.0] * (n + max_delay + 10)
        delay_buf[:n] = samples
        for i in range(n):
            t = i / sample_rate
            d1 = int(sample_rate * 0.015) + int(sample_rate * 0.005 * depth * math.sin(2.0 * math.pi * rate * t))
            d2 = int(sample_rate * 0.022) + int(sample_rate * 0.006 * depth * math.cos(2.0 * math.pi * (rate * 1.3) * t))
            v1 = delay_buf[max(0, i - d1)] if i - d1 >= 0 else 0.0
            v2 = delay_buf[max(0, i - d2)] if i - d2 >= 0 else 0.0
            out[i] = samples[i] * (1.0 - depth * 0.5) + (v1 + v2) * (depth * 0.35)
    else:
        out = list(samples)

    return out


def _apply_compressor(samples: List[float], sample_rate: int, config: CompressionConfig, intensity: float) -> List[float]:
    """Feed-forward dynamic range compressor with makeup gain."""
    thresh_db = config.threshold_db * intensity
    ratio = 1.0 + (config.ratio - 1.0) * intensity
    if ratio <= 1.05:
        return samples

    att_coeff = math.exp(-1.0 / (sample_rate * (config.attack_ms / 1000.0)))
    rel_coeff = math.exp(-1.0 / (sample_rate * (config.release_ms / 1000.0)))
    makeup_lin = 10.0 ** ((config.makeup_db * intensity) / 20.0)

    out = [0.0] * len(samples)
    env = 0.0

    for i, x in enumerate(samples):
        abs_x = abs(x)
        if abs_x > env:
            env = att_coeff * env + (1.0 - att_coeff) * abs_x
        else:
            env = rel_coeff * env + (1.0 - rel_coeff) * abs_x

        env_db = 20.0 * math.log10(max(env, 1e-6))
        if env_db > thresh_db:
            gain_db = (thresh_db + (env_db - thresh_db) / ratio) - env_db
        else:
            gain_db = 0.0

        gain_lin = 10.0 ** (gain_db / 20.0)
        out[i] = x * gain_lin * makeup_lin

    return out


def _apply_delay_echo(samples: List[float], sample_rate: int, config: DelayConfig, intensity: float) -> List[float]:
    """Multi-tap feedback delay with lowpass frequency damping."""
    wet = min(1.0, max(0.0, config.wet * intensity))
    if wet < 0.01 or not config.delays_ms:
        return samples

    n = len(samples)
    out = list(samples)

    # Process each delay tap
    for delay_ms, fb in zip(config.delays_ms, config.feedbacks):
        delay_samples = max(1, int((delay_ms / 1000.0) * sample_rate))
        effective_fb = min(0.85, max(0.0, fb * intensity))
        damp_hz = config.damp_hz
        b0, b1, b2, a1, a2 = _biquad_coefficients("lowpass", damp_hz, sample_rate, q=0.707)

        d_buf = [0.0] * (n + delay_samples + 10)
        d1, d2 = 0.0, 0.0

        for i in range(n):
            in_val = samples[i] + (d_buf[i] if i < len(d_buf) else 0.0) * effective_fb
            # Lowpass damp
            filtered = b0 * in_val + d1
            d1 = b1 * in_val - a1 * filtered + d2
            d2 = b2 * in_val - a2 * filtered

            target_idx = i + delay_samples
            if target_idx < len(d_buf):
                d_buf[target_idx] = filtered

            if i < n:
                out[i] += d_buf[i] * wet

    return out


def _apply_reverb(samples: List[float], sample_rate: int, config: ReverbConfig, intensity: float) -> List[float]:
    """
    Schroeder / Moorer / Freeverb Architecture Reverb.
    Uses parallel Lowpass Feedback Comb Filters (LBCF) + series Allpass Diffusers.
    """
    wet = min(1.0, max(0.0, config.wet * intensity))
    dry = max(0.0, 1.0 - (1.0 - config.dry) * intensity)
    if wet < 0.02:
        return samples

    n = len(samples)
    room_size = min(0.95, max(0.2, config.room_size * intensity))
    damp = min(0.9, max(0.1, config.damping))

    # Freeverb Comb filter delay lengths (in samples at 44.1kHz scaled to sample_rate)
    sr_scale = sample_rate / 44100.0
    comb_tunings = [
        int(1116 * sr_scale), int(1188 * sr_scale), int(1277 * sr_scale), int(1356 * sr_scale),
        int(1422 * sr_scale), int(1491 * sr_scale), int(1557 * sr_scale), int(1617 * sr_scale),
    ]
    allpass_tunings = [int(556 * sr_scale), int(441 * sr_scale), int(341 * sr_scale), int(225 * sr_scale)]

    comb_outputs = [0.0] * n

    # 1. Parallel Comb Filters
    for delay_len in comb_tunings:
        if delay_len < 1:
            continue
        c_buf = [0.0] * delay_len
        buf_idx = 0
        filter_store = 0.0

        for i in range(n):
            output = c_buf[buf_idx]
            filter_store = output * (1.0 - damp) + filter_store * damp
            c_buf[buf_idx] = samples[i] + filter_store * room_size
            buf_idx = (buf_idx + 1) % delay_len
            comb_outputs[i] += output

    # 2. Series Allpass Diffusers
    allpass_out = list(comb_outputs)
    for delay_len in allpass_tunings:
        if delay_len < 1:
            continue
        ap_buf = [0.0] * delay_len
        buf_idx = 0
        feedback = 0.5

        for i in range(n):
            buf_out = ap_buf[buf_idx]
            in_val = allpass_out[i]
            ap_buf[buf_idx] = in_val + buf_out * feedback
            allpass_out[i] = -in_val + buf_out * (1.0 - feedback ** 2)
            buf_idx = (buf_idx + 1) % delay_len

    # 3. Mix Dry and Wet
    out = [0.0] * n
    wet_gain = wet * 0.25  # Scale comb accumulation
    for i in range(n):
        out[i] = samples[i] * dry + allpass_out[i] * wet_gain

    return out


def _apply_noise(samples: List[float], sample_rate: int, config: NoiseConfig, intensity: float) -> List[float]:
    """Adds subtle ambient background texture (radio hiss, vinyl crackle, rumble)."""
    level_db = config.level_db - (1.0 - intensity) * 12.0
    level_lin = 10.0 ** (level_db / 20.0)
    noise_type = config.noise_type.lower()
    n = len(samples)
    out = list(samples)

    if noise_type == "radio":
        # Bandpassed analog static
        b0, b1, b2, a1, a2 = _biquad_coefficients("bandpass", 2200.0, sample_rate, q=2.0)
        d1, d2 = 0.0, 0.0
        for i in range(n):
            raw = (random.random() * 2.0 - 1.0) * level_lin
            filtered = b0 * raw + d1
            d1 = b1 * raw - a1 * filtered + d2
            d2 = b2 * raw - a2 * filtered
            out[i] += filtered
    elif noise_type == "rumble":
        # Sub-bass rumble
        b0, b1, b2, a1, a2 = _biquad_coefficients("lowpass", 120.0, sample_rate, q=0.707)
        d1, d2 = 0.0, 0.0
        for i in range(n):
            raw = (random.random() * 2.0 - 1.0) * (level_lin * 1.5)
            filtered = b0 * raw + d1
            d1 = b1 * raw - a1 * filtered + d2
            d2 = b2 * raw - a2 * filtered
            out[i] += filtered
    elif noise_type == "static":
        for i in range(n):
            raw = (random.random() * 2.0 - 1.0) * level_lin
            out[i] += raw

    return out


def _peak_normalize_limiter(samples: List[float], target_db: float = -0.5) -> List[float]:
    """Applies auto-gain scaling and transparent soft-knee limiting to guarantee zero clipping."""
    if not samples:
        return samples

    peak = max(abs(x) for x in samples)
    target_lin = 10.0 ** (target_db / 20.0)

    if peak < 1e-6:
        return list(samples)

    # Scale to target
    scale = target_lin / peak
    # Soft limiter for smooth dynamics
    out = [0.0] * len(samples)
    for i, x in enumerate(samples):
        v = x * scale
        if v > target_lin:
            out[i] = target_lin + (1.0 - target_lin) * math.tanh((v - target_lin) / (1.0 - target_lin))
        elif v < -target_lin:
            out[i] = -target_lin - (1.0 - target_lin) * math.tanh((-v - target_lin) / (1.0 - target_lin))
        else:
            out[i] = v

    return out


# ---------------------------------------------------------------------------
# Core VoiceStyleProcessor Service
# ---------------------------------------------------------------------------

def _convert_to_pcm_wav(input_path: Union[str, Path], output_path: Union[str, Path], target_sr: int = 24000) -> bool:
    """
    Converts any audio file (MP3, AAC, OGG, FLAC, M4A, non-standard WAV) to standard 16-bit PCM WAV.
    Supports ffmpeg, gst-launch-1.0, and graceful fallback.
    """
    inp = str(input_path)
    outp = str(output_path)

    # 1. Try ffmpeg if present
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin, "-y",
            "-i", inp,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(target_sr),
            "-ac", "1",
            outp,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and os.path.exists(outp) and os.path.getsize(outp) > 44:
                return True
        except Exception as e:
            logger.debug(f"ffmpeg conversion failed: {e}")

    # 2. Try GStreamer gst-launch-1.0
    gst_bin = shutil.which("gst-launch-1.0")
    if gst_bin:
        cmd = [
            gst_bin, "-q",
            "filesrc", f"location={inp}",
            "!", "decodebin",
            "!", "audioconvert",
            "!", "audioresample",
            "!", f"audio/x-raw,format=S16LE,channels=1,rate={target_sr}",
            "!", "wavenc",
            "!", "filesink", f"location={outp}",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and os.path.exists(outp) and os.path.getsize(outp) > 44:
                return True
        except Exception as e:
            logger.debug(f"GStreamer conversion failed: {e}")

    return False


class VoiceStyleProcessor:
    """
    Production-grade Voice Style Processor that applies audio effects
    to generated voice audio as a post-processing stage.
    """

    def __init__(self, store_dir: Optional[Union[str, Path]] = None):
        if store_dir:
            self.store_dir = Path(store_dir)
        else:
            # Dedicated workspace storage for generated audio and styled variants
            self.store_dir = Path(tempfile.gettempdir()) / "next_aura_audio_store"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._processing_locks: Dict[str, asyncio.Lock] = {}
        self._lock_mutex = asyncio.Lock()

    def register_audio(self, source_path: Union[str, Path]) -> str:
        """
        Stores original generated audio file in the managed audio store
        and returns a persistent audio_id. Converts any non-WAV / MP3 to 16-bit PCM WAV.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Source audio file not found: {source_path}")

        audio_id = f"audio_{uuid.uuid4().hex}"
        dest_path = self.store_dir / f"{audio_id}.wav"

        is_riff = False
        try:
            with open(src, "rb") as f:
                head = f.read(12)
                is_riff = len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
        except Exception:
            is_riff = False

        if is_riff:
            shutil.copyfile(src, dest_path)
        else:
            converted = _convert_to_pcm_wav(src, dest_path)
            if not converted or not dest_path.exists() or dest_path.stat().st_size <= 44:
                shutil.copyfile(src, dest_path)

        return audio_id

    def get_audio_path(self, audio_id: str, style_id: Optional[str] = None, intensity: float = 0.8) -> Optional[Path]:
        """Resolves path to original or cached styled audio variant."""
        if style_id and style_id.lower() != "normal":
            int_pct = int(round(max(0.0, min(1.0, intensity)) * 100))
            styled_path = self.store_dir / f"{audio_id}_{style_id.lower()}_{int_pct}.wav"
            if styled_path.exists():
                return styled_path
        orig_path = self.store_dir / f"{audio_id}.wav"
        if orig_path.exists():
            return orig_path
        return None

    def _read_audio_wav(self, file_path: Path) -> Tuple[List[float], int, int]:
        """Reads 16-bit PCM WAV into normalized float samples with automatic non-WAV decoding."""
        read_target = file_path
        temp_converted: Optional[Path] = None

        is_riff = False
        try:
            with open(file_path, "rb") as f:
                head = f.read(12)
                is_riff = len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
        except Exception:
            is_riff = False

        if not is_riff:
            temp_converted = self.store_dir / f"conv_{uuid.uuid4().hex}.wav"
            if _convert_to_pcm_wav(file_path, temp_converted):
                read_target = temp_converted

        try:
            with wave.open(str(read_target), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                n_frames = wf.getnframes()

                raw_bytes = wf.readframes(n_frames)
                if sampwidth == 2:
                    num_ints = len(raw_bytes) // 2
                    ints = struct.unpack(f"<{num_ints}h", raw_bytes)
                    raw = [x / 32768.0 for x in ints]
                elif sampwidth == 1:
                    raw = [((b - 128) / 128.0) for b in raw_bytes]
                elif sampwidth == 3:
                    raw = []
                    for k in range(0, len(raw_bytes), 3):
                        val = int.from_bytes(raw_bytes[k:k+3], byteorder="little", signed=True)
                        raw.append(val / 8388608.0)
                elif sampwidth == 4:
                    num_ints = len(raw_bytes) // 4
                    ints = struct.unpack(f"<{num_ints}i", raw_bytes)
                    raw = [x / 2147483648.0 for x in ints]
                else:
                    raw = [0.0] * (n_frames * channels)

            # Convert stereo to mono for processing if needed
            if channels == 2:
                mono = [0.5 * (raw[i * 2] + raw[i * 2 + 1]) for i in range(len(raw) // 2)]
                return mono, sample_rate, 1

            return raw, sample_rate, channels
        finally:
            if temp_converted and temp_converted.exists():
                try:
                    temp_converted.unlink(missing_ok=True)
                except Exception:
                    pass

    def _write_audio_wav(self, file_path: Path, samples: List[float], sample_rate: int, channels: int = 1):
        """Safely writes normalized float samples to 16-bit PCM WAV."""
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)

            # Clamp and convert to 16-bit integer
            clamped = [int(max(-1.0, min(1.0, s)) * 32767.0) for s in samples]
            data = struct.pack(f"<{len(clamped)}h", *clamped)
            wf.writeframes(data)

    def _process_dsp_pipeline(self, samples: List[float], sample_rate: int, preset: Any, intensity: float) -> List[float]:
        """
        Executes the complete DSP transformation pipeline for the chosen preset.
        Safe against clipping, silence, and extreme artifacts.
        """
        if not samples or intensity <= 0.001 or preset.id == "normal":
            return _peak_normalize_limiter(samples, target_db=-0.5)

        if hasattr(preset, "process_effect"):
            return preset.process_effect(samples, sample_rate, intensity)

        # 2. Pitch Shifting (SOLA)
        if abs(preset.pitch_semitones) > 0.05:
            current = _pitch_shift_sola(current, sample_rate, preset.pitch_semitones * intensity)

        # 3. Secondary Voice Harmony (Dual-Voice demon / ghost / possessed layer)
        if preset.secondary_voice:
            sec_cfg = preset.secondary_voice
            sec_semitones = sec_cfg.pitch_semitones * intensity + (sec_cfg.detune_cents * intensity) / 100.0
            sec_layer = _pitch_shift_sola(samples, sample_rate, sec_semitones)
            sec_gain = 10.0 ** ((sec_cfg.gain_db * intensity) / 20.0)

            # Delay offset if configured
            if sec_cfg.delay_ms > 0:
                sec_delay = int((sec_cfg.delay_ms / 1000.0) * sample_rate)
                sec_layer = [0.0] * sec_delay + sec_layer[: len(current) - sec_delay]

            min_len = min(len(current), len(sec_layer))
            for i in range(min_len):
                current[i] += sec_layer[i] * sec_gain

        # 4. EQ Filters
        if preset.highpass_hz:
            b0, b1, b2, a1, a2 = _biquad_coefficients("highpass", preset.highpass_hz, sample_rate, q=0.707)
            current = _apply_biquad_filter(current, b0, b1, b2, a1, a2)

        if preset.lowpass_hz:
            b0, b1, b2, a1, a2 = _biquad_coefficients("lowpass", preset.lowpass_hz, sample_rate, q=0.707)
            current = _apply_biquad_filter(current, b0, b1, b2, a1, a2)

        for eq in preset.eq_bands:
            b0, b1, b2, a1, a2 = _biquad_coefficients(
                eq.filter_type, eq.freq_hz, sample_rate, q=eq.q, gain_db=eq.gain_db * intensity
            )
            current = _apply_biquad_filter(current, b0, b1, b2, a1, a2)

        # 5. Distortion / Saturation
        if preset.distortion:
            current = _apply_distortion(current, preset.distortion, intensity)

        # 6. Modulation (Ring Mod, Tremolo, Vibrato, Chorus)
        if preset.modulation:
            current = _apply_modulation(current, sample_rate, preset.modulation, intensity)

        # 7. Dynamic Range Compression
        if preset.compression:
            current = _apply_compressor(current, sample_rate, preset.compression, intensity)

        # 8. Delay & Echo
        if preset.delay:
            current = _apply_delay_echo(current, sample_rate, preset.delay, intensity)

        # 9. Reverb
        if preset.reverb:
            current = _apply_reverb(current, sample_rate, preset.reverb, intensity)

        # 10. Ambient Noise Texture
        if preset.noise:
            current = _apply_noise(current, sample_rate, preset.noise, intensity)

        # 11. Final Volume Gain & Peak Limiter Normalization
        if abs(preset.volume_gain_db) > 0.01:
            gain_lin = 10.0 ** ((preset.volume_gain_db * intensity) / 20.0)
            current = [x * gain_lin for x in current]

        # 12. Safe peak limiter to prevent digital clipping
        return _peak_normalize_limiter(current, target_db=-0.5)

    async def apply_style(
        self,
        audio_source: Union[str, Path, bytes, UploadFile],
        style_id: str,
        intensity: float = 0.8,
        audio_id: Optional[str] = None,
    ) -> Tuple[Path, Dict[str, Any]]:
        """
        Applies a voice style preset to the given audio.
        Supports caching and concurrent deduplication.
        """
        preset = get_preset(style_id)
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid style preset '{style_id}'. Please select a valid preset.",
            )

        # Intensity bounds validation & normalization (supports 0.0-1.0 and 0-100)
        if intensity > 1.0:
            intensity = intensity / 100.0
        intensity = max(0.0, min(1.0, float(intensity)))
        int_pct = int(round(intensity * 100))

        # Resolve or create audio_id
        orig_file_path: Optional[Path] = None

        if isinstance(audio_source, (str, Path)):
            p = Path(audio_source)
            if p.exists() and p.is_file():
                orig_file_path = p
                if not audio_id:
                    audio_id = p.stem.replace("style_", "").split("_")[0]
            else:
                str_id = str(audio_source).strip()
                if (self.store_dir / f"{str_id}.wav").exists():
                    orig_file_path = self.store_dir / f"{str_id}.wav"
                    if not audio_id:
                        audio_id = str_id
                elif (self.store_dir / str_id).exists():
                    orig_file_path = self.store_dir / str_id
                    if not audio_id:
                        audio_id = Path(str_id).stem
                elif not audio_id:
                    audio_id = str_id
        elif isinstance(audio_source, bytes):
            if not audio_id:
                audio_id = f"audio_{uuid.uuid4().hex}"
            orig_file_path = self.store_dir / f"{audio_id}.wav"
            with open(orig_file_path, "wb") as f:
                f.write(audio_source)
        elif hasattr(audio_source, "read"):
            if not audio_id:
                audio_id = f"audio_{uuid.uuid4().hex}"
            orig_file_path = self.store_dir / f"{audio_id}.wav"
            read_fn = audio_source.read
            import inspect
            if inspect.iscoroutinefunction(read_fn):
                content = await read_fn()
            else:
                content = read_fn()
            with open(orig_file_path, "wb") as f:
                f.write(content)

        if not orig_file_path or not orig_file_path.exists():
            if audio_id:
                cached_orig = self.store_dir / f"{audio_id}.wav"
                if cached_orig.exists():
                    orig_file_path = cached_orig

        if not orig_file_path or not orig_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original audio file not found. Please provide valid audio.",
            )

        if not audio_id:
            audio_id = orig_file_path.stem

        # Cache key for styled variant
        styled_filename = f"{audio_id}_{preset.id}_{int_pct}.wav"
        styled_output_path = self.store_dir / styled_filename

        # Return cached variant if already generated
        if styled_output_path.exists() and styled_output_path.stat().st_size > 44:
            return styled_output_path, {
                "audio_id": audio_id,
                "preset_id": preset.id,
                "preset_name": preset.name,
                "category": preset.category,
                "intensity": intensity,
                "intensity_percent": int_pct,
                "cached": True,
                "processing_time_ms": 0.0,
            }

        # Deduplicate concurrent processing of the exact same audio + style + intensity
        lock_key = f"{audio_id}:{preset.id}:{int_pct}"
        async with self._lock_mutex:
            if lock_key not in self._processing_locks:
                self._processing_locks[lock_key] = asyncio.Lock()
            proc_lock = self._processing_locks[lock_key]

        async with proc_lock:
            # Check cache again inside lock
            if styled_output_path.exists() and styled_output_path.stat().st_size > 44:
                return styled_output_path, {
                    "audio_id": audio_id,
                    "preset_id": preset.id,
                    "preset_name": preset.name,
                    "category": preset.category,
                    "intensity": intensity,
                    "intensity_percent": int_pct,
                    "cached": True,
                    "processing_time_ms": 0.0,
                }

            start_t = time.time()

            # Execute DSP processing in CPU thread pool to never block event loop
            def _execute_processing():
                samples, sample_rate, channels = self._read_audio_wav(orig_file_path)
                styled_samples = self._process_dsp_pipeline(samples, sample_rate, preset, intensity)
                # Write to temp file then rename atomically
                temp_out = self.store_dir / f"tmp_{uuid.uuid4().hex}.wav"
                self._write_audio_wav(temp_out, styled_samples, sample_rate, channels=1)
                shutil.move(temp_out, styled_output_path)
                duration_sec = len(styled_samples) / float(sample_rate) if sample_rate > 0 else 0.0
                return duration_sec, sample_rate

            duration_sec, sample_rate = await asyncio.to_thread(_execute_processing)
            proc_time_ms = round((time.time() - start_t) * 1000.0, 2)

            logger.info(
                "[VoiceStyleProcessor] Applied style '%s' (intensity=%d%%) to %s in %.2fms | Duration=%.2fs",
                preset.id,
                int_pct,
                audio_id,
                proc_time_ms,
                duration_sec,
            )

            # Cleanup lock
            async with self._lock_mutex:
                self._processing_locks.pop(lock_key, None)

            return styled_output_path, {
                "audio_id": audio_id,
                "preset_id": preset.id,
                "preset_name": preset.name,
                "category": preset.category,
                "intensity": intensity,
                "intensity_percent": int_pct,
                "duration_seconds": round(duration_sec, 2),
                "sample_rate": sample_rate,
                "cached": False,
                "processing_time_ms": proc_time_ms,
            }


# Global singleton instance
voice_style_processor = VoiceStyleProcessor()
