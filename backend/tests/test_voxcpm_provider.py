from unittest.mock import MagicMock, patch
import pytest

from app.services.voxcpm import GradioVoxCPMProvider


def test_gradio_provider_initialization_without_token():
    with patch("gradio_client.Client") as mock_client_cls:
        provider = GradioVoxCPMProvider(space="openbmb/VoxCPM-Demo", hf_token=None)
        client = provider._get_client()

        # Verify Client called with space and NO hf_token argument
        mock_client_cls.assert_called_once_with("openbmb/VoxCPM-Demo")


def test_gradio_provider_initialization_with_token():
    with patch("gradio_client.Client") as mock_client_cls:
        provider = GradioVoxCPMProvider(space="openbmb/VoxCPM-Demo", hf_token="hf_test_secret_token_123")
        client = provider._get_client()

        # Verify Client called with token="hf_test_secret_token_123" and NOT hf_token
        mock_client_cls.assert_called_once_with("openbmb/VoxCPM-Demo", token="hf_test_secret_token_123")


def test_gradio_provider_initialization_with_empty_string_token():
    with patch("gradio_client.Client") as mock_client_cls:
        provider = GradioVoxCPMProvider(space="openbmb/VoxCPM-Demo", hf_token="   ")
        client = provider._get_client()

        # Verify whitespace/empty token is omitted
        mock_client_cls.assert_called_once_with("openbmb/VoxCPM-Demo")
