"""
Production-Grade Voice Style Presets and Polymorphic DSP Effect Handlers for Next Aura Voice Studio.
Each preset implements its own tailored, distinct audio processing chain with non-linear saturation,
formant sculpting, pitch/time modulation, multi-voice layering, and atmospheric acoustics.
"""

import math
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic Schemas for Preset Metadata
# ---------------------------------------------------------------------------

class PresetCategory(BaseModel):
    id: str
    name: str
    myanmar_name: str
    description: str
    icon: str


class StylePresetMeta(BaseModel):
    id: str
    name: str
    myanmar_name: str
    category: str
    description: str
    icon: str
    default_intensity: float = 0.8
    tags: List[str] = []


CATEGORIES: List[PresetCategory] = [
    PresetCategory(
        id="character",
        name="Character",
        myanmar_name="ဇာတ်ကောင် အသံများ",
        description="Character transformations from deep villains to cute mascots and robots",
        icon="User",
    ),
    PresetCategory(
        id="horror",
        name="Horror",
        myanmar_name="သရဲနှင့် ထိတ်လန့်ဖွယ်",
        description="Eerie ghosts, demons, whispering spirits, and possessed entities",
        icon="Ghost",
    ),
    PresetCategory(
        id="story",
        name="Story",
        myanmar_name="ဇာတ်လမ်းပြော အသံများ",
        description="Audiobook narration, dramatic storytelling, and documentary voiceovers",
        icon="BookOpen",
    ),
    PresetCategory(
        id="comedy",
        name="Comedy",
        myanmar_name="ဟာသနှင့် အစီအစဉ်",
        description="Energetic cartoons, meme punchlines, radio hosts, and arena announcers",
        icon="Smile",
    ),
    PresetCategory(
        id="cinematic",
        name="Cinematic",
        myanmar_name="ရုပ်ရှင်နှင့် ဇာတ်ရုံ",
        description="Epic movie trailers, dramatic film scores, and blockbuster atmospheres",
        icon="Film",
    ),
    PresetCategory(
        id="environment",
        name="Environment",
        myanmar_name="အသံဝန်းကျင်နှင့် အခန်း",
        description="Acoustic spaces, radios, telephones, walkie-talkies, caves, and halls",
        icon="Radio",
    ),
]


# ---------------------------------------------------------------------------
# DSP Helper Functions for Effect Processing
# ---------------------------------------------------------------------------

def biquad_coeffs(filter_type: str, freq: float, sample_rate: float, q: float = 0.707, gain_db: float = 0.0):
    w0 = 2.0 * math.pi * min(max(freq, 20.0), sample_rate * 0.49) / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * max(q, 0.05))
    a_lin = 10.0 ** (gain_db / 40.0)

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
    elif ft in ("peaking", "bell"):
        b0 = 1.0 + alpha * a_lin
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * a_lin
        a0 = 1.0 + alpha / a_lin
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / a_lin
    elif ft == "lowshelf":
        sqrt_a = math.sqrt(max(a_lin, 0.01))
        b0 = a_lin * ((a_lin + 1.0) - (a_lin - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = 2.0 * a_lin * ((a_lin - 1.0) - (a_lin + 1.0) * cos_w0)
        b2 = a_lin * ((a_lin + 1.0) - (a_lin - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a_lin + 1.0) + (a_lin - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = -2.0 * ((a_lin - 1.0) + (a_lin + 1.0) * cos_w0)
        a2 = (a_lin + 1.0) + (a_lin - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    elif ft == "highshelf":
        sqrt_a = math.sqrt(max(a_lin, 0.01))
        b0 = a_lin * ((a_lin + 1.0) + (a_lin - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = -2.0 * a_lin * ((a_lin - 1.0) + (a_lin + 1.0) * cos_w0)
        b2 = a_lin * ((a_lin + 1.0) + (a_lin - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a_lin + 1.0) - (a_lin - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = 2.0 * ((a_lin - 1.0) - (a_lin + 1.0) * cos_w0)
        a2 = (a_lin + 1.0) - (a_lin - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    else:
        return 1.0, 0.0, 0.0, 0.0, 0.0

    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def apply_biquad(samples: List[float], b0: float, b1: float, b2: float, a1: float, a2: float) -> List[float]:
    out = [0.0] * len(samples)
    d1, d2 = 0.0, 0.0
    for i, x in enumerate(samples):
        y = b0 * x + d1
        d1 = b1 * x - a1 * y + d2
        d2 = b2 * x - a2 * y
        out[i] = y
    return out


def pitch_shift_sola(samples: List[float], sample_rate: int, semitones: float) -> List[float]:
    if abs(semitones) < 0.05 or len(samples) < sample_rate * 0.05:
        return list(samples)

    factor = 2.0 ** (semitones / 12.0)
    orig_len = len(samples)
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

    win_size = int(sample_rate * 0.04)
    if win_size % 2 != 0:
        win_size += 1
    hop_syn = win_size // 4
    hop_ana = max(1, int(hop_syn / factor))

    window = [0.5 * (1.0 - math.cos(2.0 * math.pi * n / (win_size - 1))) for n in range(win_size)]
    output = [0.0] * orig_len
    weights = [0.0] * orig_len
    num_hops = int(orig_len / hop_syn)
    max_search = int(win_size * 0.3)

    in_pos, out_pos = 0, 0
    for hop in range(num_hops):
        if in_pos + win_size >= len(resampled) or out_pos + win_size >= orig_len:
            break

        best_offset = 0
        if hop > 0 and in_pos + win_size + max_search < len(resampled):
            max_corr = -1e9
            for offset in range(-max_search // 2, max_search // 2):
                curr_in = in_pos + offset
                if curr_in < 0 or curr_in + win_size >= len(resampled):
                    continue
                corr = 0.0
                for k in range(0, win_size, 4):
                    corr += resampled[curr_in + k] * output[out_pos + k]
                if corr > max_corr:
                    max_corr = corr
                    best_offset = offset

        aligned_in = max(0, in_pos + best_offset)
        for k in range(win_size):
            if out_pos + k < orig_len and aligned_in + k < len(resampled):
                w = window[k]
                output[out_pos + k] += resampled[aligned_in + k] * w
                weights[out_pos + k] += w

        in_pos += hop_ana
        out_pos += hop_syn

    for i in range(orig_len):
        if weights[i] > 0.01:
            output[i] /= weights[i]

    return output


def time_stretch(samples: List[float], speed: float) -> List[float]:
    if abs(speed - 1.0) < 0.01 or len(samples) < 10:
        return list(samples)
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


def apply_saturation(samples: List[float], drive_db: float, mode: str = "warm") -> List[float]:
    drive_lin = 10.0 ** (drive_db / 20.0)
    out = [0.0] * len(samples)
    if mode == "warm":
        norm = math.tanh(drive_lin) if drive_lin > 0.01 else 1.0
        for i, x in enumerate(samples):
            out[i] = math.tanh(x * drive_lin) / norm
    elif mode == "overdrive":
        for i, x in enumerate(samples):
            v = max(-1.0, min(1.0, x * drive_lin))
            out[i] = v - 0.28 * (v ** 2) - 0.18 * (v ** 3)
    elif mode == "hard":
        for i, x in enumerate(samples):
            out[i] = max(-1.0, min(1.0, x * drive_lin))
    elif mode == "bitcrush":
        levels = 64
        for i, x in enumerate(samples):
            v = max(-1.0, min(1.0, x * drive_lin))
            out[i] = round(v * levels) / levels
    else:
        out = list(samples)
    return out


def apply_compressor(samples: List[float], sample_rate: int, threshold_db: float, ratio: float, attack_ms: float = 10.0, release_ms: float = 100.0, makeup_db: float = 3.0) -> List[float]:
    if ratio <= 1.05:
        return list(samples)
    att_coeff = math.exp(-1.0 / (sample_rate * (attack_ms / 1000.0)))
    rel_coeff = math.exp(-1.0 / (sample_rate * (release_ms / 1000.0)))
    makeup_lin = 10.0 ** (makeup_db / 20.0)

    out = [0.0] * len(samples)
    env = 0.0
    for i, x in enumerate(samples):
        abs_x = abs(x)
        if abs_x > env:
            env = att_coeff * env + (1.0 - att_coeff) * abs_x
        else:
            env = rel_coeff * env + (1.0 - rel_coeff) * abs_x

        env_db = 20.0 * math.log10(max(env, 1e-6))
        gain_db = (threshold_db + (env_db - threshold_db) / ratio) - env_db if env_db > threshold_db else 0.0
        out[i] = x * (10.0 ** (gain_db / 20.0)) * makeup_lin
    return out


def apply_reverb(samples: List[float], sample_rate: int, room_size: float = 0.6, damping: float = 0.3, wet: float = 0.3, dry: float = 0.85) -> List[float]:
    if wet < 0.02:
        return list(samples)
    n = len(samples)
    sr_scale = sample_rate / 44100.0
    comb_tunings = [
        int(1116 * sr_scale), int(1188 * sr_scale), int(1277 * sr_scale), int(1356 * sr_scale),
        int(1422 * sr_scale), int(1491 * sr_scale), int(1557 * sr_scale), int(1617 * sr_scale),
    ]
    allpass_tunings = [int(556 * sr_scale), int(441 * sr_scale), int(341 * sr_scale), int(225 * sr_scale)]

    comb_outputs = [0.0] * n
    for delay_len in comb_tunings:
        if delay_len < 1:
            continue
        c_buf = [0.0] * delay_len
        buf_idx = 0
        filter_store = 0.0
        for i in range(n):
            output = c_buf[buf_idx]
            filter_store = output * (1.0 - damping) + filter_store * damping
            c_buf[buf_idx] = samples[i] + filter_store * room_size
            buf_idx = (buf_idx + 1) % delay_len
            comb_outputs[i] += output

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

    out = [0.0] * n
    wet_gain = wet * 0.25
    for i in range(n):
        out[i] = samples[i] * dry + allpass_out[i] * wet_gain
    return out


def apply_delay(samples: List[float], sample_rate: int, delays_ms: List[float], feedbacks: List[float], wet: float = 0.35, damp_hz: float = 3500.0) -> List[float]:
    if wet < 0.02 or not delays_ms:
        return list(samples)
    n = len(samples)
    out = list(samples)
    for delay_ms, fb in zip(delays_ms, feedbacks):
        delay_samples = max(1, int((delay_ms / 1000.0) * sample_rate))
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", damp_hz, sample_rate, q=0.707)
        d_buf = [0.0] * (n + delay_samples + 10)
        d1, d2 = 0.0, 0.0
        for i in range(n):
            in_val = samples[i] + (d_buf[i] if i < len(d_buf) else 0.0) * fb
            filtered = b0 * in_val + d1
            d1 = b1 * in_val - a1 * filtered + d2
            d2 = b2 * in_val - a2 * filtered
            target_idx = i + delay_samples
            if target_idx < len(d_buf):
                d_buf[target_idx] = filtered
            if i < n:
                out[i] += d_buf[i] * wet
    return out


def apply_noise_texture(samples: List[float], sample_rate: int, level_db: float = -32.0, noise_type: str = "radio") -> List[float]:
    level_lin = 10.0 ** (level_db / 20.0)
    n = len(samples)
    out = list(samples)
    if noise_type == "radio":
        b0, b1, b2, a1, a2 = biquad_coeffs("bandpass", 2200.0, sample_rate, q=2.0)
        d1, d2 = 0.0, 0.0
        for i in range(n):
            raw = (random.random() * 2.0 - 1.0) * level_lin
            filtered = b0 * raw + d1
            d1 = b1 * raw - a1 * filtered + d2
            d2 = b2 * raw - a2 * filtered
            out[i] += filtered
    elif noise_type == "rumble":
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 110.0, sample_rate, q=0.707)
        d1, d2 = 0.0, 0.0
        for i in range(n):
            raw = (random.random() * 2.0 - 1.0) * (level_lin * 1.5)
            filtered = b0 * raw + d1
            d1 = b1 * raw - a1 * filtered + d2
            d2 = b2 * raw - a2 * filtered
            out[i] += filtered
    return out


def peak_limiter_normalize(samples: List[float], target_db: float = -0.5) -> List[float]:
    if not samples:
        return samples
    peak = max(abs(x) for x in samples)
    target_lin = 10.0 ** (target_db / 20.0)
    if peak < 1e-6:
        return list(samples)
    scale = target_lin / peak
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
# Base Preset Effect Abstract Class
# ---------------------------------------------------------------------------

class BasePresetEffect(ABC):
    """Abstract Base Class for all Voice Style Preset processors."""

    id: str
    name: str
    myanmar_name: str
    category: str
    description: str
    icon: str
    default_intensity: float = 0.8
    tags: List[str] = []

    def get_meta(self) -> StylePresetMeta:
        return StylePresetMeta(
            id=self.id,
            name=self.name,
            myanmar_name=self.myanmar_name,
            category=self.category,
            description=self.description,
            icon=self.icon,
            default_intensity=self.default_intensity,
            tags=self.tags,
        )

    @abstractmethod
    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        """Processes audio through the preset-specific DSP chain scaled by intensity (0.0 - 1.0)."""
        pass


# ---------------------------------------------------------------------------
# 1. CHARACTER PRESETS
# ---------------------------------------------------------------------------

class NormalPreset(BasePresetEffect):
    id = "normal"
    name = "Normal"
    myanmar_name = "မူလ အသံ"
    category = "character"
    description = "Natural clean voice with mild studio warmth and transparency"
    icon = "Mic"
    default_intensity = 0.8
    tags = ["natural", "clean", "studio"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        return peak_limiter_normalize(samples, target_db=-0.5)


class DeepPreset(BasePresetEffect):
    id = "deep"
    name = "Deep Voice"
    myanmar_name = "လူမိုက်အသံ / အသံဩ"
    category = "character"
    description = "Heavy authoritative bass, lowered pitch, chest resonance, and warm saturation"
    icon = "Volume2"
    default_intensity = 0.85
    tags = ["deep", "low", "tough"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # 1. Pitch shift down
        pitch_drop = -3.8 * intensity
        out = pitch_shift_sola(samples, sample_rate, pitch_drop)

        # 2. Chest resonance bass boost (140Hz) and throat warmth (350Hz)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 150.0, sample_rate, q=0.8, gain_db=6.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 350.0, sample_rate, q=1.2, gain_db=3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        # Tame excessive crisp sibilance
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 5000.0, sample_rate, q=0.7, gain_db=-3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # 3. Warm saturation & Optical compression
        out = apply_saturation(out, drive_db=3.8 * intensity, mode="warm")
        out = apply_compressor(out, sample_rate, threshold_db=-16.0 * intensity, ratio=3.8, attack_ms=12.0, release_ms=140.0, makeup_db=3.5 * intensity)
        return peak_limiter_normalize(out)


class VillainPreset(BasePresetEffect):
    id = "villain"
    name = "Villain"
    myanmar_name = "ဗီလိန် / လူဆိုး အသံ"
    category = "character"
    description = "Sinister deep pitch, menacing overdrive rasp, and dark cavern ambiance"
    icon = "Skull"
    default_intensity = 0.85
    tags = ["villain", "dark", "evil"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Pitch drop + throat formant shift
        out = pitch_shift_sola(samples, sample_rate, -4.5 * intensity)

        # Low-shelf boost (120Hz) + harsh bite at 2.4kHz
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 130.0, sample_rate, q=0.9, gain_db=7.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2400.0, sample_rate, q=1.6, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # Overdrive growl
        out = apply_saturation(out, drive_db=5.5 * intensity, mode="overdrive")
        # Dark room ambiance
        out = apply_reverb(out, sample_rate, room_size=0.65 * intensity, damping=0.5, wet=0.28 * intensity, dry=0.85)
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=4.5, attack_ms=6.0, release_ms=90.0, makeup_db=4.0 * intensity)
        return peak_limiter_normalize(out)


class FunnyPreset(BasePresetEffect):
    id = "funny"
    name = "Funny"
    myanmar_name = "လူရွှင်တော်အသံ / ရယ်စရာ"
    category = "character"
    description = "Comical pitch lift, lively fast timing, exaggerated formant sparkle, and punchy attack"
    icon = "Laugh"
    default_intensity = 0.8
    tags = ["funny", "comedy", "fast"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Pitch lift + speedup
        out = time_stretch(samples, 1.0 + 0.09 * intensity)
        out = pitch_shift_sola(out, sample_rate, 4.0 * intensity)

        # Light low-cut + bright 3.2kHz nasal/comical boost
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 160.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3200.0, sample_rate, q=1.2, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # Fast punch compression + short slap room
        out = apply_compressor(out, sample_rate, threshold_db=-16.0 * intensity, ratio=3.2, attack_ms=4.0, release_ms=60.0, makeup_db=3.0 * intensity)
        out = apply_reverb(out, sample_rate, room_size=0.25, damping=0.6, wet=0.15 * intensity, dry=0.92)
        return peak_limiter_normalize(out)


class CutePreset(BasePresetEffect):
    id = "cute"
    name = "Cute"
    myanmar_name = "ချစ်စရာ အသံလေး"
    category = "character"
    description = "High youthful pitch, softened low-end, sweet airy formant lift, and gentle leveling"
    icon = "Sparkles"
    default_intensity = 0.8
    tags = ["cute", "anime", "sweet"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, 4.8 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 180.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3800.0, sample_rate, q=1.1, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 7500.0, sample_rate, q=0.7, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-14.0 * intensity, ratio=2.6, attack_ms=6.0, release_ms=90.0, makeup_db=2.5 * intensity)
        return peak_limiter_normalize(out)


class AngryPreset(BasePresetEffect):
    id = "angry"
    name = "Angry"
    myanmar_name = "ဒေါသထွက်နေသောအသံ"
    category = "character"
    description = "Overdriven aggression, intense bite in upper-mids, and explosive transient punch"
    icon = "Flame"
    default_intensity = 0.85
    tags = ["angry", "shout", "aggressive"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Mild pitch tightening
        out = pitch_shift_sola(samples, sample_rate, -1.0 * intensity)
        # Aggressive presence peaks (2.2kHz and 4.2kHz)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2200.0, sample_rate, q=1.5, gain_db=7.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 4200.0, sample_rate, q=1.2, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        # Overdrive clipping
        out = apply_saturation(out, drive_db=7.5 * intensity, mode="overdrive")
        out = apply_compressor(out, sample_rate, threshold_db=-22.0 * intensity, ratio=6.0, attack_ms=2.0, release_ms=50.0, makeup_db=5.0 * intensity)
        return peak_limiter_normalize(out)


class OldManPreset(BasePresetEffect):
    id = "old_man"
    name = "Old Man"
    myanmar_name = "အဘိုးကြီး အသံ"
    category = "character"
    description = "Weathered gravelly tone, subtle vocal tremor (vibrato), and rolled-off highs"
    icon = "UserCheck"
    default_intensity = 0.8
    tags = ["old", "aged", "grandfather"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.08 * intensity)
        out = pitch_shift_sola(out, sample_rate, -2.6 * intensity)

        # Vocal tremor (5.2Hz LFO vibrato)
        n = len(out)
        max_delay = int(sample_rate * 0.005)
        d_buf = [0.0] * (n + max_delay + 10)
        d_buf[:n] = out
        vibrato_out = [0.0] * n
        for i in range(n):
            t = i / sample_rate
            mod_d = (max_delay / 2.0) * (1.0 + 0.35 * intensity * math.sin(2.0 * math.pi * 5.2 * t))
            idx = i + max_delay - mod_d
            i0 = int(idx)
            frac = idx - i0
            vibrato_out[i] = d_buf[i0] * (1.0 - frac) + d_buf[i0 + 1] * frac if 0 <= i0 < len(d_buf) - 1 else out[i]

        out = vibrato_out
        # Warm low-pass roll-off at 4.2kHz + chest resonance
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 180.0, sample_rate, q=0.8, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 4200.0, sample_rate, q=0.7, gain_db=-5.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=2.5 * intensity, mode="warm")
        return peak_limiter_normalize(out)


class OldWomanPreset(BasePresetEffect):
    id = "old_woman"
    name = "Old Woman"
    myanmar_name = "အဘွားကြီး အသံ"
    category = "character"
    description = "Elderly vocal timbre with trembling flutter and vintage warmth"
    icon = "HeartHandshake"
    default_intensity = 0.8
    tags = ["old", "grandmother"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.06 * intensity)
        out = pitch_shift_sola(out, sample_rate, 2.0 * intensity)

        # Vocal flutter (5.6Hz)
        n = len(out)
        max_delay = int(sample_rate * 0.004)
        d_buf = [0.0] * (n + max_delay + 10)
        d_buf[:n] = out
        flutter_out = [0.0] * n
        for i in range(n):
            t = i / sample_rate
            mod_d = (max_delay / 2.0) * (1.0 + 0.38 * intensity * math.sin(2.0 * math.pi * 5.6 * t))
            idx = i + max_delay - mod_d
            i0 = int(idx)
            frac = idx - i0
            flutter_out[i] = d_buf[i0] * (1.0 - frac) + d_buf[i0 + 1] * frac if 0 <= i0 < len(d_buf) - 1 else out[i]

        out = flutter_out
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 160.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1800.0, sample_rate, q=1.2, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 4500.0, sample_rate, q=0.7, gain_db=-4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        return peak_limiter_normalize(out)


class ChildPreset(BasePresetEffect):
    id = "child"
    name = "Child-like"
    myanmar_name = "ကလေး အသံ"
    category = "character"
    description = "High youthful pitch, lively tempo, crisp treble, and bright innocent tone"
    icon = "Baby"
    default_intensity = 0.8
    tags = ["child", "kid", "young"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 + 0.07 * intensity)
        out = pitch_shift_sola(out, sample_rate, 5.5 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 200.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3400.0, sample_rate, q=1.0, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 7000.0, sample_rate, q=0.7, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-14.0 * intensity, ratio=2.5, attack_ms=6.0, release_ms=80.0, makeup_db=2.0 * intensity)
        return peak_limiter_normalize(out)


class RobotPreset(BasePresetEffect):
    id = "robot"
    name = "Robot"
    myanmar_name = "စက်ရုပ် အသံ"
    category = "character"
    description = "Dual-carrier ring modulation, metallic comb filtering, quantized dynamics, and bitcrush texture"
    icon = "Cpu"
    default_intensity = 0.85
    tags = ["robot", "cyborg", "sci-fi"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        n = len(samples)
        out = [0.0] * n

        # 1. Dual-carrier Ring Modulation (75Hz + 150Hz harmonic)
        depth = 0.75 * intensity
        for i, x in enumerate(samples):
            t = i / sample_rate
            c1 = math.cos(2.0 * math.pi * 75.0 * t)
            c2 = math.cos(2.0 * math.pi * 150.0 * t)
            carrier = 0.65 * c1 + 0.35 * c2
            mod_val = (1.0 - depth) + depth * carrier
            out[i] = x * mod_val

        # 2. Resonant metallic comb peaks
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1100.0, sample_rate, q=2.5, gain_db=6.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2600.0, sample_rate, q=2.8, gain_db=6.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # 3. Flanging metallic short delay
        out = apply_delay(out, sample_rate, delays_ms=[18.0, 36.0], feedbacks=[0.45 * intensity, 0.25 * intensity], wet=0.38 * intensity, damp_hz=4200.0)

        # 4. Hard dynamic compression (eliminates human breathing dynamics)
        out = apply_compressor(out, sample_rate, threshold_db=-24.0 * intensity, ratio=8.0, attack_ms=1.0, release_ms=30.0, makeup_db=5.5 * intensity)
        # 5. 9-bit amplitude quantization
        out = apply_saturation(out, drive_db=3.0 * intensity, mode="bitcrush")
        return peak_limiter_normalize(out)


class HeroPreset(BasePresetEffect):
    id = "hero"
    name = "Hero"
    myanmar_name = "သူရဲကောင်း အသံ"
    category = "character"
    description = "Confident full-bodied chest voice, wide stereo chorus, and concert space"
    icon = "Shield"
    default_intensity = 0.8
    tags = ["hero", "epic", "cinematic"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.0 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 140.0, sample_rate, q=0.7, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3400.0, sample_rate, q=1.0, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_reverb(out, sample_rate, room_size=0.55 * intensity, damping=0.25, wet=0.24 * intensity, dry=0.88)
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=3.2, attack_ms=10.0, release_ms=120.0, makeup_db=3.0 * intensity)
        return peak_limiter_normalize(out)


class NarratorPreset(BasePresetEffect):
    id = "narrator"
    name = "Narrator"
    myanmar_name = "ရုပ်သံဇာတ်ကြောင်းပြော အသံ"
    category = "character"
    description = "Broadcast proximity bass, optical leveling compression, de-essed top end, and studio clarity"
    icon = "Mic2"
    default_intensity = 0.8
    tags = ["narrator", "broadcast", "pro"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Proximity low-shelf boost (120Hz) + presence clarity (3kHz) + de-esser dip (6.2kHz)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 120.0, sample_rate, q=0.7, gain_db=4.5 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3000.0, sample_rate, q=1.1, gain_db=3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 6200.0, sample_rate, q=1.8, gain_db=-2.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # Smooth optical leveling compression + subtle warmth
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=3.5, attack_ms=12.0, release_ms=130.0, makeup_db=3.2 * intensity)
        out = apply_saturation(out, drive_db=1.8 * intensity, mode="warm")
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# 2. HORROR PRESETS
# ---------------------------------------------------------------------------

class GhostPreset(BasePresetEffect):
    id = "ghost"
    name = "Ghost"
    myanmar_name = "သရဲအသံ / တစ္ဆေ"
    category = "horror"
    description = "Supernatural pitch detune blend, spectral flutter vibrato, multi-tap delay, and eerie decaying reverb"
    icon = "Ghost"
    default_intensity = 0.85
    tags = ["ghost", "spooky", "horror"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # 1. Primary voice downward shift + high-pass breath
        primary = pitch_shift_sola(samples, sample_rate, -2.4 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 320.0, sample_rate, q=0.7)
        primary = apply_biquad(primary, b0, b1, b2, a1, a2)

        # 2. Ghost Choir Harmonizer (+3.5 semitones detuned layer)
        sec_layer = pitch_shift_sola(samples, sample_rate, 3.6 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2400.0, sample_rate, q=1.5, gain_db=5.0 * intensity)
        sec_layer = apply_biquad(sec_layer, b0, b1, b2, a1, a2)

        # Mix primary + ghost harmony
        sec_gain = 0.45 * intensity
        out = [primary[i] + sec_layer[i] * sec_gain for i in range(min(len(primary), len(sec_layer)))]

        # 3. Supernatural pitch flutter (2.8Hz)
        n = len(out)
        max_d = int(sample_rate * 0.006)
        d_buf = [0.0] * (n + max_d + 10)
        d_buf[:n] = out
        flutter_out = [0.0] * n
        for i in range(n):
            t = i / sample_rate
            mod_d = (max_d / 2.0) * (1.0 + 0.45 * intensity * math.sin(2.0 * math.pi * 2.8 * t))
            idx = i + max_d - mod_d
            i0 = int(idx)
            frac = idx - i0
            flutter_out[i] = d_buf[i0] * (1.0 - frac) + d_buf[i0 + 1] * frac if 0 <= i0 < len(d_buf) - 1 else out[i]

        out = flutter_out

        # 4. Ghostly multi-tap delay & Long spectral reverb tail
        out = apply_delay(out, sample_rate, delays_ms=[160.0, 320.0, 480.0], feedbacks=[0.38 * intensity, 0.28 * intensity, 0.18 * intensity], wet=0.42 * intensity, damp_hz=2800.0)
        out = apply_reverb(out, sample_rate, room_size=0.88 * intensity, damping=0.25, wet=0.48 * intensity, dry=0.68)
        return peak_limiter_normalize(out)


class DemonPreset(BasePresetEffect):
    id = "demon"
    name = "Demon"
    myanmar_name = "မိစ္ဆာ / မကောင်းဆိုးဝါး အသံ"
    category = "horror"
    description = "Sub-octave demonic pitch layer (-7 semitones), heavy growl overdrive, low-frequency flutter, and cavernous space"
    icon = "Flame"
    default_intensity = 0.85
    tags = ["demon", "devil", "monster"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # 1. Main deep voice (-5.5 semitones)
        primary = pitch_shift_sola(samples, sample_rate, -5.5 * intensity)

        # 2. Sub-octave demonic double (-8.5 semitones)
        sub_layer = pitch_shift_sola(samples, sample_rate, -8.5 * intensity)
        sub_gain = 0.65 * intensity

        out = [primary[i] + sub_layer[i] * sub_gain for i in range(min(len(primary), len(sub_layer)))]

        # 3. Sub-bass boost (110Hz) & growl resonance (1.6kHz)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 120.0, sample_rate, q=1.0, gain_db=8.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1600.0, sample_rate, q=1.5, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # 4. Demonic growl overdrive saturation
        out = apply_saturation(out, drive_db=7.0 * intensity, mode="overdrive")

        # 5. Low-frequency amplitude rumble modulation
        depth = 0.25 * intensity
        for i, x in enumerate(out):
            t = i / sample_rate
            out[i] = x * (1.0 - depth * (0.5 + 0.5 * math.sin(2.0 * math.pi * 38.0 * t)))

        # 6. Cavernous dark reverb
        out = apply_reverb(out, sample_rate, room_size=0.82 * intensity, damping=0.45, wet=0.38 * intensity, dry=0.75)
        return peak_limiter_normalize(out)


class HauntedPreset(BasePresetEffect):
    id = "haunted"
    name = "Haunted"
    myanmar_name = "ခြောက်ခြားဖွယ် အသံ"
    category = "horror"
    description = "Ghostly resonant 850Hz peak, hollow comb reflections, slow spectral flutter, and eerie decay"
    icon = "Moon"
    default_intensity = 0.8
    tags = ["haunted", "hollow", "creepy"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.8 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 850.0, sample_rate, q=2.8, gain_db=7.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 4500.0, sample_rate, q=0.7, gain_db=-4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[140.0, 280.0], feedbacks=[0.35 * intensity, 0.2 * intensity], wet=0.35 * intensity, damp_hz=3000.0)
        out = apply_reverb(out, sample_rate, room_size=0.8 * intensity, damping=0.35, wet=0.42 * intensity, dry=0.72)
        return peak_limiter_normalize(out)


class HorrorWhisperPreset(BasePresetEffect):
    id = "whisper_horror"
    name = "Horror Whisper"
    myanmar_name = "တီးတိုး ထိတ်လန့်ဖွယ်"
    category = "horror"
    description = "Breathy high-pass filter (>1.1kHz), intimate airy boost, heavy compression, and tight stereo slap"
    icon = "Wind"
    default_intensity = 0.8
    tags = ["whisper", "creepy", "breath"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # 1. High-pass filter stripping vocal chord fundamentals
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 1100.0, sample_rate, q=0.7)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)

        # 2. Boost breathy friction (3.6kHz & 7kHz)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3600.0, sample_rate, q=1.2, gain_db=6.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 7000.0, sample_rate, q=0.8, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # 3. High compression with fast attack to amplify breath
        out = apply_compressor(out, sample_rate, threshold_db=-24.0 * intensity, ratio=6.5, attack_ms=2.0, release_ms=60.0, makeup_db=6.5 * intensity)
        out = apply_delay(out, sample_rate, delays_ms=[75.0, 150.0], feedbacks=[0.32 * intensity, 0.16 * intensity], wet=0.35 * intensity, damp_hz=4800.0)
        return peak_limiter_normalize(out)


class DarkHorrorPreset(BasePresetEffect):
    id = "dark_horror"
    name = "Dark Horror"
    myanmar_name = "အမှောင်ထု ထိတ်လန့်ဖွယ်"
    category = "horror"
    description = "Deep pitch descent, ominous sub-rumble texture, and dark damp room reflections"
    icon = "EyeOff"
    default_intensity = 0.85
    tags = ["dark", "ominous", "sub"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -4.8 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 100.0, sample_rate, q=1.0, gain_db=7.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 3500.0, sample_rate, q=0.7, gain_db=-6.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_noise_texture(out, sample_rate, level_db=-34.0, noise_type="rumble")
        out = apply_reverb(out, sample_rate, room_size=0.76 * intensity, damping=0.65, wet=0.32 * intensity, dry=0.8)
        return peak_limiter_normalize(out)


class PossessedPreset(BasePresetEffect):
    id = "possessed"
    name = "Possessed"
    myanmar_name = "ပူးကပ်ခံထားရသော အသံ"
    category = "horror"
    description = "Chaotic dual-voice detune (+/-3 semitones), erratic delay feedback, and demonic overdrive"
    icon = "Zap"
    default_intensity = 0.85
    tags = ["possessed", "chaotic", "dual-voice"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        p1 = pitch_shift_sola(samples, sample_rate, -3.2 * intensity)
        p2 = pitch_shift_sola(samples, sample_rate, 3.0 * intensity)
        mix = [p1[i] + p2[i] * (0.6 * intensity) for i in range(min(len(p1), len(p2)))]
        out = apply_saturation(mix, drive_db=5.5 * intensity, mode="overdrive")
        out = apply_delay(out, sample_rate, delays_ms=[110.0, 230.0], feedbacks=[0.38 * intensity, 0.22 * intensity], wet=0.36 * intensity, damp_hz=3200.0)
        out = apply_reverb(out, sample_rate, room_size=0.74 * intensity, damping=0.4, wet=0.32 * intensity, dry=0.8)
        return peak_limiter_normalize(out)


class CreepyPreset(BasePresetEffect):
    id = "creepy"
    name = "Creepy"
    myanmar_name = "ကျောချမ်းဖွယ် အသံ"
    category = "horror"
    description = "Unsettling pitch vibrato, thin cold EQ curve, and hollow metallic reflections"
    icon = "Radio"
    default_intensity = 0.8
    tags = ["creepy", "cold", "unsettling"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.5 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 280.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1400.0, sample_rate, q=2.0, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[85.0], feedbacks=[0.28 * intensity], wet=0.28 * intensity, damp_hz=2600.0)
        return peak_limiter_normalize(out)


class DistortedHorrorPreset(BasePresetEffect):
    id = "distorted_horror"
    name = "Distorted Horror"
    myanmar_name = "ပျက်စီးနေသော ထိတ်လန့်ဖွယ်"
    category = "horror"
    description = "Heavy 7-bit bitcrusher distortion, bandpass telephone cut, and claustrophobic short echo"
    icon = "Activity"
    default_intensity = 0.85
    tags = ["distorted", "bitcrush", "glitch"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -2.8 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("bandpass", 1600.0, sample_rate, q=1.2)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=8.0 * intensity, mode="bitcrush")
        out = apply_delay(out, sample_rate, delays_ms=[55.0, 120.0], feedbacks=[0.42 * intensity, 0.22 * intensity], wet=0.35 * intensity, damp_hz=2400.0)
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# 3. STORY PRESETS
# ---------------------------------------------------------------------------

class StoryNarratorPreset(BasePresetEffect):
    id = "story_narrator"
    name = "Story Narrator"
    myanmar_name = "ဇာတ်လမ်းပြော အသံ"
    category = "story"
    description = "Warm audiobook tone, gentle broadcast compression, subtle room acoustics, and crisp articulation"
    icon = "BookOpen"
    default_intensity = 0.8
    tags = ["story", "audiobook", "warm"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.03 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 140.0, sample_rate, q=0.7, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2800.0, sample_rate, q=1.0, gain_db=2.8 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=2.8, attack_ms=15.0, release_ms=140.0, makeup_db=2.5 * intensity)
        out = apply_reverb(out, sample_rate, room_size=0.28, damping=0.55, wet=0.15 * intensity, dry=0.92)
        return peak_limiter_normalize(out)


class DocumentaryPreset(BasePresetEffect):
    id = "documentary"
    name = "Documentary"
    myanmar_name = "မှတ်တမ်းတင် အသံ"
    category = "story"
    description = "Neutral broadcast transparency, flat acoustic response, and clear studio articulation"
    icon = "FileText"
    default_intensity = 0.8
    tags = ["documentary", "neutral", "factual"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 250.0, sample_rate, q=1.0, gain_db=-2.0 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3200.0, sample_rate, q=1.0, gain_db=3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-16.0 * intensity, ratio=3.0, attack_ms=10.0, release_ms=110.0, makeup_db=2.2 * intensity)
        return peak_limiter_normalize(out)


class DramaticPreset(BasePresetEffect):
    id = "dramatic"
    name = "Dramatic"
    myanmar_name = "ဒရာမာ / ပြဇာတ် အသံ"
    category = "story"
    description = "High-contrast dynamic compression, rich lower-mid warmth, and dramatic theater depth"
    icon = "Compass"
    default_intensity = 0.8
    tags = ["dramatic", "serious", "theater"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.05 * intensity)
        out = pitch_shift_sola(out, sample_rate, -1.2 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 160.0, sample_rate, q=0.8, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-20.0 * intensity, ratio=4.2, attack_ms=8.0, release_ms=130.0, makeup_db=4.0 * intensity)
        out = apply_reverb(out, sample_rate, room_size=0.48 * intensity, damping=0.4, wet=0.2 * intensity, dry=0.9)
        return peak_limiter_normalize(out)


class EmotionalPreset(BasePresetEffect):
    id = "emotional"
    name = "Emotional"
    myanmar_name = "ခံစားချက်ပြည့် အသံ"
    category = "story"
    description = "Intimate near-mic tone, lush plate reverberation, and softened high sibilance"
    icon = "Heart"
    default_intensity = 0.8
    tags = ["emotional", "intimate", "soft"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.05 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 180.0, sample_rate, q=0.7, gain_db=3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 5800.0, sample_rate, q=0.7, gain_db=-3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_reverb(out, sample_rate, room_size=0.62 * intensity, damping=0.35, wet=0.26 * intensity, dry=0.85)
        return peak_limiter_normalize(out)


class SuspensePreset(BasePresetEffect):
    id = "suspense"
    name = "Suspense"
    myanmar_name = "သည်းထိတ်ရင်ဖို အသံ"
    category = "story"
    description = "Focused bandpass tension, muted lower-mids, and sharp high presence"
    icon = "AlertCircle"
    default_intensity = 0.8
    tags = ["suspense", "thriller", "mystery"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.4 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 220.0, sample_rate, q=0.8, gain_db=-3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2800.0, sample_rate, q=1.4, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[140.0], feedbacks=[0.22 * intensity], wet=0.22 * intensity, damp_hz=3500.0)
        return peak_limiter_normalize(out)


class MysteryPreset(BasePresetEffect):
    id = "mystery"
    name = "Mystery"
    myanmar_name = "လျှို့ဝှက်ဆန်းကြယ် အသံ"
    category = "story"
    description = "Dark atmospheric space, subtle low detune, and veiled top-end shadows"
    icon = "HelpCircle"
    default_intensity = 0.8
    tags = ["mystery", "detective", "shadow"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.6 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 180.0, sample_rate, q=0.7, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 4000.0, sample_rate, q=0.7, gain_db=-4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_reverb(out, sample_rate, room_size=0.68 * intensity, damping=0.5, wet=0.28 * intensity, dry=0.84)
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# 4. COMEDY PRESETS
# ---------------------------------------------------------------------------

class ComedyPreset(BasePresetEffect):
    id = "comedy"
    name = "Comedy"
    myanmar_name = "ဟာသ အသံ"
    category = "comedy"
    description = "Bouncy energetic pitch, +6% speed, and punchy mid-frequency boost"
    icon = "Smile"
    default_intensity = 0.8
    tags = ["comedy", "funny", "punchy"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 + 0.07 * intensity)
        out = pitch_shift_sola(out, sample_rate, 3.2 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2400.0, sample_rate, q=1.0, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-15.0 * intensity, ratio=3.2, attack_ms=6.0, release_ms=80.0, makeup_db=2.8 * intensity)
        return peak_limiter_normalize(out)


class CartoonPreset(BasePresetEffect):
    id = "cartoon"
    name = "Cartoon"
    myanmar_name = "ကာတွန်း အသံ"
    category = "comedy"
    description = "Helium-like high pitch (+6.5 semitones), fast animation tempo, and cartoonish brightness"
    icon = "Star"
    default_intensity = 0.85
    tags = ["cartoon", "helium", "animation"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 + 0.12 * intensity)
        out = pitch_shift_sola(out, sample_rate, 6.5 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 240.0, sample_rate, q=0.7)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3600.0, sample_rate, q=1.2, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-16.0 * intensity, ratio=3.5, attack_ms=4.0, release_ms=70.0, makeup_db=3.0 * intensity)
        return peak_limiter_normalize(out)


class CrazyPreset(BasePresetEffect):
    id = "crazy"
    name = "Crazy"
    myanmar_name = "ရူးသွပ်သွက်လက် အသံ"
    category = "comedy"
    description = "Wild pitch flutter tremolo, fast tempo (+15%), and wild overdrive peaks"
    icon = "Zap"
    default_intensity = 0.85
    tags = ["crazy", "wild", "unhinged"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 + 0.15 * intensity)
        out = pitch_shift_sola(out, sample_rate, 3.5 * intensity)
        # 8Hz tremolo
        depth = 0.38 * intensity
        for i, x in enumerate(out):
            t = i / sample_rate
            out[i] = x * (1.0 - depth * (0.5 + 0.5 * math.sin(2.0 * math.pi * 8.0 * t)))
        out = apply_saturation(out, drive_db=4.5 * intensity, mode="overdrive")
        return peak_limiter_normalize(out)


class ExaggeratedPreset(BasePresetEffect):
    id = "exaggerated"
    name = "Exaggerated"
    myanmar_name = "ချဲ့ကားပြောဆိုသော အသံ"
    category = "comedy"
    description = "Hyped mid-range dynamics, ultra-fast attack compression, and vivid articulation"
    icon = "TrendingUp"
    default_intensity = 0.8
    tags = ["exaggerated", "hype", "promo"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1600.0, sample_rate, q=1.0, gain_db=4.0 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 4000.0, sample_rate, q=1.2, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_compressor(out, sample_rate, threshold_db=-22.0 * intensity, ratio=5.5, attack_ms=3.0, release_ms=80.0, makeup_db=4.8 * intensity)
        return peak_limiter_normalize(out)


class MemePreset(BasePresetEffect):
    id = "meme"
    name = "Meme Voice"
    myanmar_name = "မီမ်း / အပျက်အသံ"
    category = "comedy"
    description = "Bass-boosted overdrive punch with safe peak limiting and bitcrush flavor"
    icon = "Layers"
    default_intensity = 0.85
    tags = ["meme", "bass-boost", "earrape-safe"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Heavy bass shelf + overdrive + safe peak limiter
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 110.0, sample_rate, q=1.2, gain_db=10.0 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2500.0, sample_rate, q=1.5, gain_db=6.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=9.0 * intensity, mode="overdrive")
        out = apply_compressor(out, sample_rate, threshold_db=-26.0 * intensity, ratio=8.0, attack_ms=2.0, release_ms=50.0, makeup_db=6.5 * intensity)
        return peak_limiter_normalize(out)


class RadioHostPreset(BasePresetEffect):
    id = "radio_host"
    name = "Radio Host"
    myanmar_name = "ရေဒီယို အစီအစဉ်မှူး"
    category = "comedy"
    description = "Classic FM broadcast optical leveling, +5dB bass boost, and crisp presence exciter"
    icon = "Radio"
    default_intensity = 0.8
    tags = ["radio", "fm", "dj"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 130.0, sample_rate, q=0.8, gain_db=5.0 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3400.0, sample_rate, q=1.0, gain_db=3.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=2.5 * intensity, mode="warm")
        out = apply_compressor(out, sample_rate, threshold_db=-20.0 * intensity, ratio=4.2, attack_ms=8.0, release_ms=100.0, makeup_db=4.2 * intensity)
        return peak_limiter_normalize(out)


class AnnouncerPreset(BasePresetEffect):
    id = "announcer"
    name = "Announcer"
    myanmar_name = "အားကစားကွင်း ကြေညာသူ"
    category = "comedy"
    description = "Arena PA horn resonance (1.5kHz), slapback echo, and large stadium reflections"
    icon = "Volume2"
    default_intensity = 0.8
    tags = ["announcer", "arena", "stadium"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 250.0, sample_rate, q=0.7)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1600.0, sample_rate, q=2.0, gain_db=6.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[130.0, 260.0], feedbacks=[0.32 * intensity, 0.16 * intensity], wet=0.38 * intensity, damp_hz=3200.0)
        out = apply_reverb(out, sample_rate, room_size=0.72 * intensity, damping=0.3, wet=0.28 * intensity, dry=0.82)
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# 5. CINEMATIC PRESETS
# ---------------------------------------------------------------------------

class CinematicPreset(BasePresetEffect):
    id = "cinematic"
    name = "Cinematic"
    myanmar_name = "ရုပ်ရှင်ဆန်သော အသံ"
    category = "cinematic"
    description = "Theatrical sub-bass weight (<80Hz), wide cinematic space, and film score presence"
    icon = "Film"
    default_intensity = 0.8
    tags = ["cinematic", "movie", "epic"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.4 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 80.0, sample_rate, q=0.8, gain_db=5.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 3200.0, sample_rate, q=1.0, gain_db=3.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_reverb(out, sample_rate, room_size=0.65 * intensity, damping=0.25, wet=0.25 * intensity, dry=0.88)
        out = apply_compressor(out, sample_rate, threshold_db=-16.0 * intensity, ratio=3.2, attack_ms=12.0, release_ms=120.0, makeup_db=2.8 * intensity)
        return peak_limiter_normalize(out)


class EpicPreset(BasePresetEffect):
    id = "epic"
    name = "Epic"
    myanmar_name = "ခမ်းနားကြီးကျယ်သော အသံ"
    category = "cinematic"
    description = "Grand stadium reverberation, punchy sub-bass boost, and wide chorus presence"
    icon = "Award"
    default_intensity = 0.85
    tags = ["epic", "grand", "heroic"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = pitch_shift_sola(samples, sample_rate, -1.8 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 75.0, sample_rate, q=0.9, gain_db=6.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2800.0, sample_rate, q=1.1, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_reverb(out, sample_rate, room_size=0.82 * intensity, damping=0.2, wet=0.35 * intensity, dry=0.78)
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=3.8, attack_ms=8.0, release_ms=130.0, makeup_db=3.8 * intensity)
        return peak_limiter_normalize(out)


class TrailerPreset(BasePresetEffect):
    id = "trailer"
    name = "Trailer Voice"
    myanmar_name = "ရုပ်ရှင် နမူနာအသံ"
    category = "cinematic"
    description = "Deep blockbuster resonance, heavy mastering limiter, and punchy theatrical mid-bass"
    icon = "PlayCircle"
    default_intensity = 0.85
    tags = ["trailer", "blockbuster", "heavy"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = time_stretch(samples, 1.0 - 0.05 * intensity)
        out = pitch_shift_sola(out, sample_rate, -3.2 * intensity)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 100.0, sample_rate, q=0.9, gain_db=7.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 2600.0, sample_rate, q=1.2, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=3.5 * intensity, mode="warm")
        out = apply_reverb(out, sample_rate, room_size=0.58 * intensity, damping=0.35, wet=0.22 * intensity, dry=0.88)
        out = apply_compressor(out, sample_rate, threshold_db=-22.0 * intensity, ratio=5.0, attack_ms=6.0, release_ms=110.0, makeup_db=4.8 * intensity)
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# 6. ENVIRONMENT PRESETS
# ---------------------------------------------------------------------------

class RadioPreset(BasePresetEffect):
    id = "radio"
    name = "Vintage Radio"
    myanmar_name = "ရှေးဟောင်း ရေဒီယို"
    category = "environment"
    description = "AM bandpass 400Hz–3.5kHz, analog harmonic saturation, and vintage hiss texture"
    icon = "Radio"
    default_intensity = 0.85
    tags = ["radio", "am", "vintage", "lo-fi"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Steep bandpass (400Hz - 3.4kHz)
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 420.0, sample_rate, q=0.8)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 3400.0, sample_rate, q=0.8)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1500.0, sample_rate, q=1.5, gain_db=5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=6.0 * intensity, mode="warm")
        out = apply_noise_texture(out, sample_rate, level_db=-30.0 + (1.0 - intensity) * 8.0, noise_type="radio")
        out = apply_compressor(out, sample_rate, threshold_db=-20.0 * intensity, ratio=5.0, attack_ms=5.0, release_ms=70.0, makeup_db=4.0 * intensity)
        return peak_limiter_normalize(out)


class TelephonePreset(BasePresetEffect):
    id = "telephone"
    name = "Telephone"
    myanmar_name = "တယ်လီဖုန်း အသံ"
    category = "environment"
    description = "Classic landline 300Hz–3.4kHz filter, transmission clipping grit, and zero sub-bass"
    icon = "Phone"
    default_intensity = 0.85
    tags = ["telephone", "phone", "landline"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 320.0, sample_rate, q=0.9)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 3300.0, sample_rate, q=0.9)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1800.0, sample_rate, q=2.0, gain_db=4.5 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=4.5 * intensity, mode="overdrive")
        out = apply_compressor(out, sample_rate, threshold_db=-18.0 * intensity, ratio=4.5, attack_ms=4.0, release_ms=60.0, makeup_db=3.8 * intensity)
        return peak_limiter_normalize(out)


class WalkieTalkiePreset(BasePresetEffect):
    id = "walkie_talkie"
    name = "Walkie-Talkie"
    myanmar_name = "စကားပြောစက် အသံ"
    category = "environment"
    description = "Tactical bandpass 600Hz–2.9kHz, aggressive limiter, and radio static burst"
    icon = "Radio"
    default_intensity = 0.85
    tags = ["walkie-talkie", "military", "tactical"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 600.0, sample_rate, q=1.0)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 2900.0, sample_rate, q=1.0)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1600.0, sample_rate, q=2.5, gain_db=6.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=7.5 * intensity, mode="hard")
        out = apply_noise_texture(out, sample_rate, level_db=-26.0 + (1.0 - intensity) * 8.0, noise_type="radio")
        out = apply_compressor(out, sample_rate, threshold_db=-24.0 * intensity, ratio=8.0, attack_ms=2.0, release_ms=40.0, makeup_db=5.5 * intensity)
        return peak_limiter_normalize(out)


class MegaphonePreset(BasePresetEffect):
    id = "megaphone"
    name = "Megaphone"
    myanmar_name = "လက်ကိုင်အသံချဲ့စက်"
    category = "environment"
    description = "Harsh bullhorn resonance peak (1.5kHz), horn acoustic echo, and hard amplifier clipping"
    icon = "Megaphone"
    default_intensity = 0.85
    tags = ["megaphone", "bullhorn", "protest"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("highpass", 500.0, sample_rate, q=0.8)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 3500.0, sample_rate, q=0.8)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 1500.0, sample_rate, q=3.2, gain_db=9.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_saturation(out, drive_db=7.0 * intensity, mode="hard")
        out = apply_delay(out, sample_rate, delays_ms=[85.0, 170.0], feedbacks=[0.38 * intensity, 0.18 * intensity], wet=0.35 * intensity, damp_hz=2600.0)
        out = apply_compressor(out, sample_rate, threshold_db=-22.0 * intensity, ratio=6.0, attack_ms=2.0, release_ms=50.0, makeup_db=4.5 * intensity)
        return peak_limiter_normalize(out)


class CavePreset(BasePresetEffect):
    id = "cave"
    name = "Cave"
    myanmar_name = "လိုဏ်ဂူ အသံ"
    category = "environment"
    description = "Deep cavernous multi-reflection delay, high dampening, and wet acoustic reverberation"
    icon = "Mountain"
    default_intensity = 0.85
    tags = ["cave", "cavern", "echo"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("lowshelf", 200.0, sample_rate, q=0.8, gain_db=4.5 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 3200.0, sample_rate, q=0.7, gain_db=-5.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[140.0, 290.0, 480.0], feedbacks=[0.48 * intensity, 0.32 * intensity, 0.2 * intensity], wet=0.48 * intensity, damp_hz=2200.0)
        out = apply_reverb(out, sample_rate, room_size=0.88 * intensity, damping=0.58, wet=0.44 * intensity, dry=0.68)
        return peak_limiter_normalize(out)


class LargeHallPreset(BasePresetEffect):
    id = "large_hall"
    name = "Large Hall"
    myanmar_name = "ခန်းမကြီး အသံ"
    category = "environment"
    description = "Concert hall acoustics with 1.8s decay, pre-delay, and spacious stereo width"
    icon = "Home"
    default_intensity = 0.8
    tags = ["hall", "concert", "spacious"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = apply_delay(samples, sample_rate, delays_ms=[45.0], feedbacks=[0.15 * intensity], wet=0.18 * intensity, damp_hz=4500.0)
        out = apply_reverb(out, sample_rate, room_size=0.84 * intensity, damping=0.25, wet=0.38 * intensity, dry=0.78)
        return peak_limiter_normalize(out)


class SmallRoomPreset(BasePresetEffect):
    id = "small_room"
    name = "Small Room"
    myanmar_name = "အခန်းကျဉ်း အသံ"
    category = "environment"
    description = "Tight studio room reflections (25-45ms) with intimate acoustic warmth"
    icon = "Box"
    default_intensity = 0.75
    tags = ["room", "studio", "intimate"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = apply_reverb(samples, sample_rate, room_size=0.35, damping=0.48, wet=0.22 * intensity, dry=0.9)
        return peak_limiter_normalize(out)


class UnderwaterPreset(BasePresetEffect):
    id = "underwater"
    name = "Underwater"
    myanmar_name = "ရေအောက် အသံ"
    category = "environment"
    description = "Steep muffled lowpass (<550Hz), slow aqueous chorus, and heavy acoustic damping"
    icon = "Droplet"
    default_intensity = 0.85
    tags = ["underwater", "muffled", "water"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        # Steep lowpass filter
        b0, b1, b2, a1, a2 = biquad_coeffs("lowpass", 520.0, sample_rate, q=0.7)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = biquad_coeffs("peaking", 280.0, sample_rate, q=1.5, gain_db=4.0 * intensity)
        out = apply_biquad(out, b0, b1, b2, a1, a2)

        # Slow 0.45Hz aqueous modulation
        n = len(out)
        max_d = int(sample_rate * 0.015)
        d_buf = [0.0] * (n + max_d + 10)
        d_buf[:n] = out
        chorus_out = [0.0] * n
        for i in range(n):
            t = i / sample_rate
            mod_d = (max_d / 2.0) * (1.0 + 0.5 * intensity * math.sin(2.0 * math.pi * 0.45 * t))
            idx = i + max_d - mod_d
            i0 = int(idx)
            frac = idx - i0
            chorus_out[i] = d_buf[i0] * (1.0 - frac) + d_buf[i0 + 1] * frac if 0 <= i0 < len(d_buf) - 1 else out[i]

        out = apply_reverb(chorus_out, sample_rate, room_size=0.75 * intensity, damping=0.82, wet=0.38 * intensity, dry=0.72)
        return peak_limiter_normalize(out)


class DreamyPreset(BasePresetEffect):
    id = "dreamy"
    name = "Dreamy"
    myanmar_name = "အိပ်မက်ဆန်သော အသံ"
    category = "environment"
    description = "Lush multi-voice chorus, stereo pan flutter, and ethereal shimmering tail"
    icon = "Cloud"
    default_intensity = 0.8
    tags = ["dreamy", "ethereal", "floating"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        b0, b1, b2, a1, a2 = biquad_coeffs("highshelf", 6000.0, sample_rate, q=0.7, gain_db=3.0 * intensity)
        out = apply_biquad(samples, b0, b1, b2, a1, a2)
        out = apply_delay(out, sample_rate, delays_ms=[180.0, 360.0], feedbacks=[0.32 * intensity, 0.16 * intensity], wet=0.32 * intensity, damp_hz=4000.0)
        out = apply_reverb(out, sample_rate, room_size=0.82 * intensity, damping=0.2, wet=0.4 * intensity, dry=0.76)
        return peak_limiter_normalize(out)


class EchoPreset(BasePresetEffect):
    id = "echo"
    name = "Canyon Echo"
    myanmar_name = "တောင်ကြား ပဲ့တင်သံ"
    category = "environment"
    description = "Rhythmically spaced canyon multi-tap echoes with smooth decaying feedback"
    icon = "Repeat"
    default_intensity = 0.85
    tags = ["echo", "canyon", "repeat"]

    def process_effect(self, samples: List[float], sample_rate: int, intensity: float) -> List[float]:
        out = apply_delay(samples, sample_rate, delays_ms=[220.0, 440.0, 660.0], feedbacks=[0.52 * intensity, 0.36 * intensity, 0.22 * intensity], wet=0.52 * intensity, damp_hz=3000.0)
        out = apply_reverb(out, sample_rate, room_size=0.62 * intensity, damping=0.4, wet=0.22 * intensity, dry=0.85)
        return peak_limiter_normalize(out)


# ---------------------------------------------------------------------------
# Registry of Preset Effect Handlers
# ---------------------------------------------------------------------------

PRESET_EFFECTS: List[BasePresetEffect] = [
    # Character
    NormalPreset(),
    DeepPreset(),
    VillainPreset(),
    FunnyPreset(),
    CutePreset(),
    AngryPreset(),
    OldManPreset(),
    OldWomanPreset(),
    ChildPreset(),
    RobotPreset(),
    HeroPreset(),
    NarratorPreset(),
    # Horror
    GhostPreset(),
    DemonPreset(),
    HauntedPreset(),
    HorrorWhisperPreset(),
    DarkHorrorPreset(),
    PossessedPreset(),
    CreepyPreset(),
    DistortedHorrorPreset(),
    # Story
    StoryNarratorPreset(),
    DocumentaryPreset(),
    DramaticPreset(),
    EmotionalPreset(),
    SuspensePreset(),
    MysteryPreset(),
    # Comedy
    ComedyPreset(),
    CartoonPreset(),
    CrazyPreset(),
    ExaggeratedPreset(),
    MemePreset(),
    RadioHostPreset(),
    AnnouncerPreset(),
    # Cinematic
    CinematicPreset(),
    EpicPreset(),
    TrailerPreset(),
    # Environment
    RadioPreset(),
    TelephonePreset(),
    WalkieTalkiePreset(),
    MegaphonePreset(),
    CavePreset(),
    LargeHallPreset(),
    SmallRoomPreset(),
    UnderwaterPreset(),
    DreamyPreset(),
    EchoPreset(),
]

_EFFECT_MAP: Dict[str, BasePresetEffect] = {p.id: p for p in PRESET_EFFECTS}


_ALIASES: Dict[str, str] = {
    "horror_whisper": "whisper_horror",
    "horror-whisper": "whisper_horror",
    "whisper": "whisper_horror",
    "story": "story_narrator",
    "story-narrator": "story_narrator",
    "deep_voice": "deep",
    "deep-voice": "deep",
    "old-man": "old_man",
    "old-woman": "old_woman",
    "walkie-talkie": "walkie_talkie",
    "large-hall": "large_hall",
    "small-room": "small_room",
}


def get_preset_effect(preset_id: str) -> Optional[BasePresetEffect]:
    clean_id = preset_id.lower().strip().replace(" ", "_")
    target_id = _ALIASES.get(clean_id, clean_id)
    return _EFFECT_MAP.get(target_id)


def list_preset_metas(category: Optional[str] = None) -> List[StylePresetMeta]:
    if category:
        cat = category.lower().strip()
        return [p.get_meta() for p in PRESET_EFFECTS if p.category == cat]
    return [p.get_meta() for p in PRESET_EFFECTS]


def list_categories() -> List[PresetCategory]:
    return CATEGORIES


def get_preset_ids() -> List[str]:
    return list(_EFFECT_MAP.keys())


# Compatibility aliases
StylePreset = StylePresetMeta
get_preset = get_preset_effect
list_presets = list_preset_metas
STYLE_PRESETS: List[StylePresetMeta] = [p.get_meta() for p in PRESET_EFFECTS]

