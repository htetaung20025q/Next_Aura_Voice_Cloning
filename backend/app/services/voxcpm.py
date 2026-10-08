import asyncio
import io
import logging
import os
import struct
import tempfile
import time
import uuid
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Set
from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)


class VoiceInferenceProvider(ABC):
    """
    Abstract Base Class for VoxCPM Voice Inference Providers.
    Allows seamlessly swapping Gradio Cloud Demo with self-hosted vLLM/PyTorch inference.
    """

    @abstractmethod
    async def generate_speech(
        self,
        text: str,
        control_instruction: str,
        reference_audio_path: Optional[str],
        ultimate_cloning: bool,
        prompt_text: str,
        cfg_value: float,
        normalize: bool,
        denoise: bool,
    ) -> str:
        """
        Executes voice synthesis and returns the absolute local path to the generated audio file.
        """
        pass


def _extract_audio_result(result: Any) -> str:
    """
    Safely resolves local audio file path from various Gradio return structures:
    - Absolute file path string
    - Remote HTTP/HTTPS audio URL (automatically downloaded to local temp)
    - Dictionary with 'path', 'url', 'value', 'name'
    - Tuple/List containing any of the above
    """
    if result is None:
        raise RuntimeError("VoxCPM inference returned None.")

    # 1. Direct string path or URL
    if isinstance(result, str):
        cleaned = result.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            import urllib.request
            temp_dir = Path(tempfile.gettempdir()) / "vox_gradio_downloads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_dest = temp_dir / f"download_{uuid.uuid4().hex}.wav"
            try:
                urllib.request.urlretrieve(cleaned, str(local_dest))
                if local_dest.exists() and local_dest.stat().st_size > 44:
                    return str(local_dest)
            except Exception as e:
                logger.error("Failed to download audio from remote URL %s: %e", cleaned, e)

        if os.path.exists(cleaned) and os.path.getsize(cleaned) > 44:
            return cleaned

    # 2. Dictionary output
    if isinstance(result, dict):
        for key in ("path", "url", "name", "value", "data"):
            val = result.get(key)
            if val and isinstance(val, str):
                try:
                    res = _extract_audio_result(val)
                    if res:
                        return res
                except Exception:
                    pass

    # 3. Tuple or List output
    if isinstance(result, (tuple, list)):
        for item in result:
            if isinstance(item, (str, dict, list, tuple)):
                try:
                    res = _extract_audio_result(item)
                    if res:
                        return res
                except Exception:
                    pass

    raise RuntimeError(f"VoxCPM inference returned unrecognized or empty output format: {type(result)}")


class GradioVoxCPMProvider(VoiceInferenceProvider):
    """
    Inference provider that connects to Hugging Face Space running VoxCPM.
    """

    def __init__(self, space: str, hf_token: Optional[str] = None):
        self.space = space
        self.hf_token = hf_token
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from gradio_client import Client
            except ImportError as e:
                raise RuntimeError(
                    "gradio_client is not installed in the current Python environment. "
                    "Please install dependencies with: pip install -r requirements.txt "
                    "or set VOXCPM_PROVIDER=mock in .env for local offline testing."
                ) from e

            logger.info("Connecting to VoxCPM Gradio Space: %s", self.space)
            client_kwargs: Dict[str, Any] = {}
            if self.hf_token and str(self.hf_token).strip():
                client_kwargs["token"] = str(self.hf_token).strip()

            self._client = Client(self.space, **client_kwargs)
        return self._client

    async def generate_speech(
        self,
        text: str,
        control_instruction: str,
        reference_audio_path: Optional[str],
        ultimate_cloning: bool,
        prompt_text: str,
        cfg_value: float,
        normalize: bool,
        denoise: bool,
    ) -> str:
        def _call_gradio():
            try:
                from gradio_client import handle_file
            except ImportError as e:
                raise RuntimeError(
                    "gradio_client is not installed in the current Python environment. "
                    "Please run: pip install -r requirements.txt"
                ) from e

            client = self._get_client()
            audio_input = handle_file(reference_audio_path) if reference_audio_path else None
            
            result = None
            last_err = None

            # Strategy 1: Named endpoint '/generate'
            try:
                result = client.predict(
                    text,
                    control_instruction,
                    audio_input,
                    ultimate_cloning,
                    prompt_text,
                    float(cfg_value),
                    bool(normalize),
                    bool(denoise),
                    api_name="/generate",
                )
            except Exception as e1:
                last_err = e1
                logger.warning("Gradio /generate predict attempt failed (%s). Trying /predict endpoint...", e1)
                
                # Strategy 2: Named endpoint '/predict'
                try:
                    result = client.predict(
                        text,
                        control_instruction,
                        audio_input,
                        ultimate_cloning,
                        prompt_text,
                        float(cfg_value),
                        bool(normalize),
                        bool(denoise),
                        api_name="/predict",
                    )
                except Exception as e2:
                    last_err = e2
                    logger.warning("Gradio /predict predict attempt failed (%s). Trying default endpoint...", e2)
                    
                    # Strategy 3: Default root endpoint (no api_name)
                    try:
                        result = client.predict(
                            text,
                            control_instruction,
                            audio_input,
                            ultimate_cloning,
                            prompt_text,
                            float(cfg_value),
                            bool(normalize),
                            bool(denoise),
                        )
                    except Exception as e3:
                        last_err = e3
                        # Strategy 4: Fallback with core positional arguments
                        try:
                            result = client.predict(
                                text,
                                audio_input,
                                prompt_text,
                            )
                        except Exception as e4:
                            logger.error("All Gradio prediction strategies failed: %s", last_err)
                            raise RuntimeError(f"VoxCPM space '{self.space}' error: {str(last_err)}") from last_err

            output_path = _extract_audio_result(result)
            if not output_path or not os.path.exists(str(output_path)):
                raise RuntimeError("VoxCPM inference returned no valid audio output file.")
            return str(output_path)

        # Run synchronous Gradio client in async executor
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call_gradio)


class MockVoiceProvider(VoiceInferenceProvider):
    """
    Mock Voice Provider for testing and local development without Hugging Face / GPU dependencies.
    Generates a valid lightweight audio file.
    """

    async def generate_speech(
        self,
        text: str,
        control_instruction: str,
        reference_audio_path: Optional[str],
        ultimate_cloning: bool,
        prompt_text: str,
        cfg_value: float,
        normalize: bool,
        denoise: bool,
    ) -> str:
        # Create a valid 1-second 44.1kHz silent/sine WAV file
        temp_dir = Path(tempfile.gettempdir()) / "vox_mock_outputs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_path = temp_dir / f"mock_gen_{uuid.uuid4().hex}.wav"

        sample_rate = 24000
        duration_secs = 1
        num_samples = sample_rate * duration_secs

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            # Write 1 second of audio
            data = struct.pack(f"<{num_samples}h", *([0] * num_samples))
            wf.writeframes(data)

        return str(out_path)


class VoiceGenerationService:
    """
    Service orchestrating voice synthesis, concurrency management, and resource protection.
    """

    def __init__(self):
        settings = get_settings()
        self._provider: VoiceInferenceProvider
        if settings.VOXCPM_PROVIDER == "mock":
            self._provider = MockVoiceProvider()
        else:
            self._provider = GradioVoxCPMProvider(
                space=settings.VOXCPM_SPACE,
                hf_token=settings.HF_TOKEN,
            )

        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFERENCES)
        self._active_users: Set[str] = set()
        self._user_lock = asyncio.Lock()

    def set_provider(self, provider: VoiceInferenceProvider):
        """Used in automated tests to inject mock providers."""
        self._provider = provider

    async def generate(
        self,
        text: str,
        control_instruction: str,
        reference_audio_path: Optional[str],
        ultimate_cloning: bool,
        prompt_text: str,
        cfg_value: float,
        normalize: bool,
        denoise: bool,
        user_identifier: str,
    ) -> str:
        settings = get_settings()

        # 1. Prevent multiple simultaneous requests from the same user/session
        async with self._user_lock:
            if user_identifier in self._active_users:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="You already have a voice generation in progress. Please wait for it to complete.",
                )
            self._active_users.add(user_identifier)

        try:
            # 2. Acquire global concurrency semaphore
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=15.0)
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Voice generation servers are currently at maximum capacity. Please try again shortly.",
                )

            try:
                # 3. Inspect reference audio metadata safely if available
                ref_duration = 0.0
                ref_sample_rate = 0
                ref_channels = 0
                if reference_audio_path and os.path.exists(reference_audio_path):
                    try:
                        import mutagen
                        m = mutagen.File(reference_audio_path)
                        if m and m.info:
                            ref_duration = round(getattr(m.info, "length", 0.0), 3)
                            ref_sample_rate = getattr(m.info, "sample_rate", 0)
                            ref_channels = getattr(m.info, "channels", 1)
                    except Exception:
                        pass

                logger.info(
                    "[VoxCPM Diagnostic] Starting voice generation | Provider=%s | ModelID=openbmb/VoxCPM2 | "
                    "VoxCPMVersion=VoxCPM2 | CFG=%.1f | InferenceTimesteps=10 | Normalize=%s | Denoise=%s | "
                    "Seed=None | UltimateCloning=%s | TargetTextLen=%d | PromptTextLen=%d | "
                    "RefAudioDuration=%.2fs | RefAudioSampleRate=%dHz | RefAudioChannels=%d",
                    type(self._provider).__name__,
                    float(cfg_value),
                    bool(normalize),
                    bool(denoise),
                    bool(ultimate_cloning),
                    len(text),
                    len(prompt_text),
                    ref_duration,
                    ref_sample_rate,
                    ref_channels,
                )

                # 4. Execute inference with timeout
                start_time = time.time()
                output_path = await asyncio.wait_for(
                    self._provider.generate_speech(
                        text=text,
                        control_instruction=control_instruction,
                        reference_audio_path=reference_audio_path,
                        ultimate_cloning=ultimate_cloning,
                        prompt_text=prompt_text,
                        cfg_value=cfg_value,
                        normalize=normalize,
                        denoise=denoise,
                    ),
                    timeout=settings.INFERENCE_TIMEOUT_SECONDS,
                )
                duration = time.time() - start_time
                logger.info(
                    "[VoxCPM Diagnostic] Voice generation completed successfully in %.2fs | Provider=%s | Output=%s",
                    duration,
                    type(self._provider).__name__,
                    os.path.basename(output_path),
                )
                return output_path

            except asyncio.TimeoutError:
                logger.error("Voice inference timed out after %ds", settings.INFERENCE_TIMEOUT_SECONDS)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Voice synthesis timed out. Please try with a shorter text or try again later.",
                )
            except HTTPException:
                raise
            except Exception as e:
                err_msg = str(e)
                logger.error("Voice inference failed: %s", err_msg, exc_info=True)
                if "429" in err_msg or "busy" in err_msg.lower() or "queue full" in err_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="The voice engine is currently busy. Please try again in a moment.",
                    )
                if "sleeping" in err_msg.lower() or "building" in err_msg.lower() or "waking" in err_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="The voice engine Space is currently starting up on Hugging Face. Please retry in 15 seconds.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Voice generation failed: {err_msg}" if err_msg else "Voice generation failed. Please try again later.",
                )
            finally:
                self._semaphore.release()

        finally:
            async with self._user_lock:
                self._active_users.discard(user_identifier)


# Global singleton instance
voice_service = VoiceGenerationService()
