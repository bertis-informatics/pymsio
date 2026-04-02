import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--mzml", action="store", default=None, help="Path to an mzML file"
    )
    parser.addoption(
        "--raw", action="store", default=None, help="Path to a Thermo RAW file"
    )
    parser.addoption(
        "--wiff", action="store", default=None, help="Path to a SCIEX WIFF file"
    )


@pytest.fixture
def mzml_path(request):
    path = request.config.getoption("--mzml")
    if path is None:
        pytest.skip("--mzml not provided")
    return path


@pytest.fixture
def raw_path(request):
    path = request.config.getoption("--raw")
    if path is None:
        pytest.skip("--raw not provided")
    return path


@pytest.fixture
def wiff_path(request):
    path = request.config.getoption("--wiff")
    if path is None:
        pytest.skip("--wiff not provided")
    return path
