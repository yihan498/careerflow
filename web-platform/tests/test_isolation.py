from pathlib import Path


def test_web_platform_is_self_contained():
    root = Path(__file__).resolve().parents[1]
    expected = {"frontend", "api", "document-worker", "shared", "migrations", "deploy", "tests"}
    assert expected.issubset({item.name for item in root.iterdir()})

