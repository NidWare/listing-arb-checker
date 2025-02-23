from setuptools import setup, find_packages

setup(
    name="mexc-sdk",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'requests>=2.25.1',
        'websocket-client>=1.2.1',
        'python-dateutil>=2.8.2'
    ],
    author="MEXC",
    author_email="developer@mexc.com",
    description="MEXC API SDK for Python",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/mxcdevelop/mexc-api-sdk",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
) 