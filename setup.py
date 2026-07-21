"""Compatibility shim for older pip versions that cannot edit-install pyproject projects."""

from setuptools import find_packages, setup


setup(
    name="careerflow-kit",
    version="0.4.0",
    description="Privacy-first end-to-end job application workflow",
    packages=find_packages(),
    package_data={"careerflow": ["prompts/*.md"]},
    include_package_data=True,
    python_requires=">=3.8",
    extras_require={
        "pdf": ["reportlab>=4.0,<4.4"],
        "documents": ["reportlab>=4.0,<4.4", "PyMuPDF>=1.24,<2", "Pillow>=9.0"],
        "dev": ["pytest>=7.0", "reportlab>=4.0,<4.4", "PyMuPDF>=1.24,<2", "Pillow>=9.0"],
    },
    entry_points={"console_scripts": ["careerflow=careerflow.cli:main"]},
)
