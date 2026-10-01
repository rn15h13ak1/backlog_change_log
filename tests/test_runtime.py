from change_log.runtime import check_runtime


def _ok(name):
    return object()


def test_runtime_ok():
    assert check_runtime((3, 10, 0), _ok) == []


def test_old_python_is_reported_before_packages():
    def broken(name):
        raise AssertionError("版が足りないときは import を試さない")
    problems = check_runtime((3, 9, 6), broken)
    assert "Python 3.10 以上が必要です（実行中: 3.9.6）。" in problems


def test_missing_package_shows_pip_name():
    def no_yaml(name):
        raise ModuleNotFoundError(name=name)
    problems = check_runtime((3, 12, 0), no_yaml)
    assert problems[0] == "必要なライブラリが入っていません: pyyaml"
    assert problems[-1].endswith("-m pip install pyyaml")
