"""The reader uses synchronous SQLAlchemy; its Cython accelerators are optional."""

from pythonforandroid.recipe import PyProjectRecipe


class SQLAlchemyRecipe(PyProjectRecipe):
    name = "sqlalchemy"
    version = "2.1.6"
    url = "https://github.com/sqlalchemy/sqlalchemy/archive/refs/tags/rel_{}.tar.gz"
    depends = ["setuptools", "typing-extensions"]

    @property
    def versioned_url(self):
        return self.url.format(self.version.replace(".", "_"))

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["DISABLE_SQLALCHEMY_CEXT"] = "1"
        return env


recipe = SQLAlchemyRecipe()
