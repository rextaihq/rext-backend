import importlib
import warnings


def test_transactional_decorator_import_has_no_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", DeprecationWarning)
        module = importlib.import_module("src.utils.transactional_decorator")
        importlib.reload(module)

    deprecations = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert not deprecations, (
        "transactional_decorator import should not trigger DeprecationWarning; "
        "migrate deprecated logger imports to src.api.lib.logger"
    )
