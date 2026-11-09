from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import connection_runtime


def test_sessions_refresh_once_then_pick_up_a_new_source(tmp_path):
    source = tmp_path/'synthetic_client.py'
    source.write_text('first', encoding='utf-8')
    client = SimpleNamespace(__name__='synthetic_client', __file__=str(source))
    importer = Mock()
    importer.reload.side_effect = lambda module: module
    connection_runtime._REFRESHED.clear()
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: connection_runtime.refresh_client(client, importer=importer), range(32)))
    assert all(result is client for result in results)
    assert importer.reload.call_count == 1
    source.write_text('second revision', encoding='utf-8')
    connection_runtime.refresh_client(client, importer=importer)
    assert importer.reload.call_count == 2


def test_evicted_client_is_refreshed_even_if_source_has_not_changed(tmp_path):
    source = tmp_path/'synthetic_eviction.py'
    source.write_text('same source', encoding='utf-8')
    importer = Mock()
    importer.reload.side_effect = lambda module: module
    connection_runtime._REFRESHED.clear()
    for _ in range(2):
        client = SimpleNamespace(__name__='synthetic_eviction', __file__=str(source))
        assert connection_runtime.refresh_client(client, importer=importer) is client
    assert importer.reload.call_count == 2
