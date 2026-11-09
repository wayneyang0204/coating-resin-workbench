import os
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import techdb_client


@pytest.mark.parametrize('base', ['http://127.0.0.1:8765', 'http://localhost:8765', 'http://[::1]:8765', 'http://0.0.0.0:8765'])
def test_cloud_loopback_is_explicitly_unavailable_without_network(monkeypatch, base):
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT', 'cloud')
    monkeypatch.setenv('TECH_DB_API_BASE', base)
    with patch('urllib.request.urlopen') as request:
        health = techdb_client.health()
        assert health['availability'] == 'local_only' and not health['ok']
        assert health['error'] is None
        with pytest.raises(RuntimeError, match='公司本機版'):
            techdb_client.search_materials('synthetic')
        request.assert_not_called()


def test_local_connection_still_requests_health_and_statistics(monkeypatch):
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT', 'local')
    with patch.object(techdb_client, '_request', side_effect=[{'status':'ok','database_ready':True},{'materials':3,'documents':4}]) as request:
        result = techdb_client.health()
        assert result['ok'] and result['materials'] == 3
        assert [c.args[0] for c in request.call_args_list] == ['/api/health','/api/stats']


def test_remote_failure_is_not_hidden_by_cloud_mode(monkeypatch):
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT','cloud')
    monkeypatch.setenv('TECH_DB_API_BASE','https://configured.example.test')
    with patch.object(techdb_client,'_request',side_effect=RuntimeError('configured API failed')):
        result=techdb_client.health()
        assert not result['ok'] and result['error']=='configured API failed'
        assert 'availability' not in result


def test_auto_cloud_mount_and_explicit_local_override(monkeypatch):
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT','auto')
    monkeypatch.setenv('TECH_DB_API_BASE','http://127.0.0.1:8765')
    monkeypatch.setattr(techdb_client,'__file__','/mount/src/workbench/techdb_client.py')
    with patch.object(techdb_client,'Path') as path:
        path.side_effect=lambda value: (PurePosixPath(value) if value=='/mount/src'
                                       else SimpleNamespace(resolve=lambda:PurePosixPath(value)))
        assert techdb_client.local_only_deployment()
        monkeypatch.setenv('WORKBENCH_DEPLOYMENT','local')
        assert not techdb_client.local_only_deployment()


def test_cloud_login_page_reports_mode_instead_of_connection_failure(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT','cloud')
    monkeypatch.setenv('TECH_DB_API_BASE','http://127.0.0.1:8765')
    monkeypatch.setenv('RECIPE_DB_PATH',str(tmp_path/'synthetic.db'))
    with patch('urllib.request.urlopen') as request:
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
        assert not at.exception
        assert any('雲端版提供實驗筆記與紀錄' in e.value for e in at.info)
        assert not at.warning and not at.error
        request.assert_not_called()


def test_cloud_notes_remain_available_and_material_controls_are_disabled(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    import backend
    monkeypatch.setenv('WORKBENCH_DEPLOYMENT','cloud')
    monkeypatch.setenv('TECH_DB_API_BASE','http://127.0.0.1:8765')
    monkeypatch.setenv('RECIPE_DB_PATH',str(tmp_path/'synthetic.db'))
    monkeypatch.setattr(backend,'DB_PATH',tmp_path/'synthetic.db')
    with patch.object(backend,'list_notes',return_value=[]), patch.object(backend,'search_logs',return_value=[]):
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'))
        at.session_state['auth_user']={'name':'Synthetic','role':'user'}
        at.session_state['auth_token']='synthetic-fixture-only'
        at.run()
        assert not at.exception
        assert next(b for b in at.button if b.label=='搜尋').disabled
        assert at.chat_input[0].disabled
        assert not next(b for b in at.button if b.label=='以目前帳號存檔').disabled
