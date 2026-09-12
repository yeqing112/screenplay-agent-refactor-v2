import json

import pytest

from core.script_ir import resolve_script_payload


class _Query:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None

    def order_by(self, *args):
        return self


class _Session:
    def query(self, _model):
        return _Query()


class _Script:
    book_id = 1
    episode = 1
    current_script_ir_version_id = None
    content = json.dumps({"scenes": [{"name": "门厅"}]}, ensure_ascii=False)


def test_production_runtime_is_fail_closed_without_script_ir():
    with pytest.raises(Exception, match="qualified ScriptIR"):
        resolve_script_payload(_Session(), _Script(), workflow_profile="production")

