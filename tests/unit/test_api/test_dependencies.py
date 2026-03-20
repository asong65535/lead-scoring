"""Tests for FastAPI dependency functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.api.dependencies import get_model, get_feature_computer
from src.api.exceptions import ModelNotLoadedError


class TestGetModel:
    def test_returns_model_and_version_when_loaded(self):
        request = MagicMock(spec=Request)
        request.app.state.model = MagicMock()
        request.app.state.model_version = "v1.0"

        model, version = get_model(request)

        assert model is request.app.state.model
        assert version == "v1.0"

    def test_raises_when_model_is_none(self):
        request = MagicMock(spec=Request)
        request.app.state.model = None

        with pytest.raises(ModelNotLoadedError):
            get_model(request)


class TestGetFeatureComputer:
    @patch("src.api.dependencies.async_engine")
    @patch("src.api.dependencies.FeatureComputer")
    def test_returns_feature_computer_with_engine(self, mock_fc, mock_engine):
        result = get_feature_computer()

        mock_fc.assert_called_once_with(mock_engine)
        assert result is mock_fc.return_value
