"""Packaging for Petra, with a build-time hook that sets up a machine for it.

`pip install git+https://github.com/At1a8/Petra` (or `pip install .` in a checkout) runs the
bootstrap in petra/bootstrap.py while building the wheel: clone the checkout and install the
Claude Code CLI.

The metadata lives here rather than in a pyproject [project] table on purpose: Ubuntu 22.04's
system pip (22.0.2) can build with the system setuptools 59 even in an isolated build, and that
setuptools ignores [project], producing an UNKNOWN-0.0.0 wheel that never runs build_py, so the
hook would be skipped silently.

The hook runs on a real wheel build only; a cached wheel skips it, so use
`pip install --no-cache-dir --force-reinstall ...` to run it again, or `python3 -m petra.bootstrap`.
pip hides build output unless you pass -v. Set PETRA_SKIP_BOOTSTRAP=1 to install without side effects.
"""
import os
import re
import sys

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
        return f.read()


VERSION = re.search(r'^__version__ = "([^"]+)"', read("petra", "__init__.py"), re.M).group(1)


def run_bootstrap():
    # Best-effort: a network hiccup must never fail the install.
    if os.environ.get("PETRA_SKIP_BOOTSTRAP"):
        return
    try:
        sys.path.insert(0, HERE)
        from petra.bootstrap import main as bootstrap_main

        bootstrap_main([])
    except Exception as exc:
        sys.stderr.write("[petra-bootstrap WARN] bootstrap failed: %r\n" % (exc,))
        sys.stderr.write("[petra-bootstrap WARN] run `python3 -m petra.bootstrap` after the install, "
                         "or see https://github.com/At1a8/Petra#install\n")


class BuildPyWithBootstrap(build_py):
    """Runs at wheel-build time, which for `pip install git+...` is the user's machine."""

    def run(self):
        super().run()
        run_bootstrap()


setup(
    name="petra",
    version=VERSION,
    description="Petra: framework agent for AMD GPUs in open-source LLM inference frameworks. "
                "Installing it clones the checkout and the Claude Code CLI its workflow runs inside.",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/At1a8/Petra",
    license="Apache-2.0",
    python_requires=">=3.9",
    packages=["petra"],
    install_requires=[],
    cmdclass={"build_py": BuildPyWithBootstrap},
)
