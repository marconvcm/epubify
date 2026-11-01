"""Build modern zeroconf with its supported pure Python implementation."""

from pythonforandroid.recipe import PyProjectRecipe


class ZeroconfRecipe(PyProjectRecipe):
    name = "zeroconf"
    version = "0.152.1"
    url = "https://pypi.python.org/packages/source/z/zeroconf/zeroconf-{version}.tar.gz"
    sha256sum = "2674810a30d6990e4a446857748a875e707d1a0afcc5e103d5bf82c254ac2129"
    depends = ["setuptools", "ifaddr"]

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["SKIP_CYTHON"] = "1"
        return env


recipe = ZeroconfRecipe()
