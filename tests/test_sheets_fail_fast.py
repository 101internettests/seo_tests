"""The CLI must fail before crawling when its Google Sheets dependency fails."""
import json
import sys
from unittest.mock import Mock

import httplib2
import pytest
from googleapiclient.errors import HttpError

import multi_site_analyzer as app
from google_sheets_service_account import GoogleSheetsAccessError, GoogleSheetsServiceAccount
from telegram_bot import TelegramBot


def google_error(status):
    return HttpError(httplib2.Response({'status': str(status)}),
                     json.dumps({'error': {'message': 'Access <denied> & unavailable'}}).encode())


@pytest.fixture
def setup_run(monkeypatch, tmp_path):
    config = {
        'sites': {'test': {'name': 'Test', 'description': 'Test',
                           'base_url': 'https://example.test',
                           'urls': ['https://example.test/one', 'https://example.test/two']}},
        'default_settings': {'spreadsheet_id': 'test-sheet-id', 'sheet_name': 'SEO report'},
    }
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['multi_site_analyzer.py', '--config', str(path), '--no-log', '--delay', '0'])
    # Real Sheets methods and Telegram formatting, mocked transports only.
    sheets = GoogleSheetsServiceAccount.__new__(GoogleSheetsServiceAccount)
    sheets.service = Mock()
    values = sheets.service.spreadsheets.return_value.values.return_value
    values.get.return_value.execute.return_value = {}
    values.append.return_value.execute.return_value = {'updates': {'updatedRows': 2}}
    factory = Mock(return_value=sheets)
    monkeypatch.setattr(app, 'GoogleSheetsServiceAccount', factory)
    bot = TelegramBot(bot_token='test-token', chat_id='test-chat')
    monkeypatch.setattr(bot, 'is_configured', lambda: True)
    bot.send_message = Mock(return_value=True)
    monkeypatch.setattr(app, 'TelegramBot', lambda: bot)
    # Prevent any website request unless a test supplies a response.
    crawl = Mock(side_effect=AssertionError('Unexpected website request'))
    monkeypatch.setattr(app.requests.Session, 'get', crawl)
    save = Mock()
    monkeypatch.setattr(app.MultiSiteAnalyzer, 'save_results_locally', save)
    return values, factory, bot, crawl, save


@pytest.mark.parametrize('error', [google_error(400), google_error(401), google_error(403),
                                 google_error(404), google_error(429), google_error(503),
                                 TimeoutError('connection timed out')])
def test_preflight_failure_exits_and_alerts_before_crawling(setup_run, error, capsys):
    values, factory, bot, crawl, save = setup_run
    values.get.return_value.execute.side_effect = error
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    crawl.assert_not_called()
    save.assert_not_called()
    values.append.assert_not_called()
    bot.send_message.assert_called_once()
    message = bot.send_message.call_args.args[0]
    assert '<b>⚠️ ОШИБКА АНАЛИЗА</b>' in message
    assert 'Прогон остановлен' in message
    assert 'https://docs.google.com/spreadsheets/d/test-sheet-id/edit' in message
    assert '<denied>' not in message
    assert 'Анализ завершен успешно' not in capsys.readouterr().out


def test_initialization_failure_still_sends_alert(setup_run):
    values, factory, bot, crawl, save = setup_run
    factory.side_effect = ValueError('Invalid service account configuration')
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    crawl.assert_not_called()
    bot.send_message.assert_called_once()
    assert 'Не удалось подключиться' in bot.send_message.call_args.args[0]


@pytest.mark.parametrize('delivery', [False, RuntimeError('Telegram unavailable')])
def test_alert_delivery_failure_does_not_mask_failed_run(setup_run, delivery):
    values, factory, bot, crawl, save = setup_run
    values.get.return_value.execute.side_effect = google_error(403)
    if isinstance(delivery, Exception):
        bot.send_message.side_effect = delivery
    else:
        bot.send_message.return_value = delivery
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    crawl.assert_not_called()
    bot.send_message.assert_called_once()


def page_response():
    response = Mock(status_code=200, url='https://example.test/one', history=[])
    response.content = b'<html><head><title>Test</title></head><body><h1>Test</h1></body></html>'
    response.text = response.content.decode()
    return response


def test_empty_accessible_sheet_allows_normal_run(setup_run, capsys):
    values, factory, bot, crawl, save = setup_run
    crawl.side_effect = None
    crawl.return_value = page_response()
    app.main()
    assert crawl.call_count >= 2
    assert values.get.call_args_list[0].kwargs == {
        'spreadsheetId': 'test-sheet-id', 'range': "'SEO report'!A1"}
    values.append.assert_called_once()
    save.assert_called_once()
    assert 'Анализ завершен успешно' in capsys.readouterr().out
    assert all('GOOGLE-ТАБЛИЦА НЕДОСТУПНА' not in call.args[0]
               for call in bot.send_message.call_args_list)


def test_access_lost_during_comparison_stops_remaining_urls(setup_run):
    values, factory, bot, crawl, save = setup_run
    values.get.return_value.execute.side_effect = [{}, google_error(403)]
    crawl.side_effect = None
    crawl.return_value = page_response()
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    assert all(call.args[0] != 'https://example.test/two' for call in crawl.call_args_list)
    save.assert_not_called()
    values.append.assert_not_called()
    bot.send_message.assert_called_once()


def test_write_access_failure_exits_without_success_report(setup_run, capsys):
    values, factory, bot, crawl, save = setup_run
    crawl.side_effect = None
    crawl.return_value = page_response()
    values.append.return_value.execute.side_effect = google_error(403)
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    bot.send_message.assert_called_once()
    assert 'Ошибка записи' in bot.send_message.call_args.args[0]
    assert 'Анализ завершен успешно' not in capsys.readouterr().out


def test_no_telegram_flag_suppresses_alert_but_still_fails(setup_run, monkeypatch):
    values, factory, bot, crawl, save = setup_run
    monkeypatch.setattr(sys, 'argv', sys.argv + ['--no-telegram'])
    values.get.return_value.execute.side_effect = google_error(403)
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    bot.send_message.assert_not_called()
    crawl.assert_not_called()


def test_list_sites_does_not_require_google(setup_run, monkeypatch):
    values, factory, bot, crawl, save = setup_run
    monkeypatch.setattr(sys, 'argv', sys.argv + ['--list-sites'])
    app.main()
    factory.assert_not_called()
    crawl.assert_not_called()


def test_no_sheets_still_requires_read_access_for_comparison(setup_run, monkeypatch):
    values, factory, bot, crawl, save = setup_run
    monkeypatch.setattr(sys, 'argv', sys.argv + ['--no-sheets'])
    values.get.return_value.execute.side_effect = google_error(403)
    with pytest.raises(SystemExit) as stopped:
        app.main()
    assert stopped.value.code == 1
    crawl.assert_not_called()
    bot.send_message.assert_called_once()
