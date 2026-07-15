def test_app_creation(app):
    """Test that the FastAPI app was created successfully."""
    assert app is not None
    assert app.title == "Leasora API"
    assert app.version == "0.2.0"

