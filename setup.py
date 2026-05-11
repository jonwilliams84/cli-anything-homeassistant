from setuptools import setup, find_namespace_packages

with open("cli_anything/homeassistant/README.md") as f:
    long_description = f.read()

setup(
    name="cli-anything-homeassistant",
    version="1.15.0",
    description="CLI harness for Home Assistant — control your smart home from the command line",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "requests>=2.28.0",
        "websocket-client>=1.5.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-homeassistant=cli_anything.homeassistant.homeassistant_cli:main",
        ],
    },
    package_data={
        "cli_anything.homeassistant": ["skills/*.md", "README.md"],
    },
    include_package_data=True,
    python_requires=">=3.10",
)
