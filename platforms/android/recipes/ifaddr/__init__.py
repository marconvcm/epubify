"""ifaddr 0.2 on Android API 24+: use Bionic's own getifaddrs.

The upstream p4a recipe patches ifaddr 0.1.7 to load an old-Android shim.
That patch is incompatible with 0.2.0 and unnecessary for our minimum API 28.
https://android.googlesource.com/platform/bionic/+/master/libc/include/ifaddrs.h
"""

from pythonforandroid.recipe import PythonRecipe


class IfaddrRecipe(PythonRecipe):
    name = "ifaddr"
    version = "0.2.0"
    url = "https://pypi.python.org/packages/source/i/ifaddr/ifaddr-{version}.tar.gz"
    sha256sum = "cc0cbfcaabf765d44595825fb96a99bb12c79716b73b44330ea38ee2b0c4aed4"
    depends = ["setuptools"]
    min_ndk_api_support = 24
    call_hostpython_via_targetpython = False
    setup_extra_args = ["--no-deps"]
    patches = []


recipe = IfaddrRecipe()
