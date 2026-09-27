import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

import actions
import devices
import file_tools
from privacy import redact


class FileTests(unittest.TestCase):
    def test_edit_backups_and_preserves_original_on_ambiguous_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hello.txt'
            path.write_text('hello world')
            file_tools.edit_file(str(path), 'world', 'Jarvis')
            self.assertEqual(path.read_text(), 'hello Jarvis')
            self.assertEqual(path.with_name('hello.txt.jarvis.bak').read_text(), 'hello world')
            with self.assertRaises(ValueError):
                file_tools.edit_file(str(path), 'missing', 'bad')
            self.assertEqual(path.read_text(), 'hello Jarvis')

    def test_credential_files_and_symlinks_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / '.env'
            key.write_text('DO_NOT_READ=secret')
            link = Path(directory) / 'innocent.txt'
            link.symlink_to(key)
            for path in [key, link]:
                with self.assertRaises(ValueError):
                    file_tools.read_file(str(path))

    def test_known_secrets_are_redacted(self):
        with patch.dict(os.environ, {'EXAMPLE_API_KEY': 'test-private-value'}):
            self.assertEqual(redact('output test-private-value'), 'output [REDACTED]')


class DeviceTests(unittest.TestCase):
    def test_android_scan_keeps_unauthorized_state(self):
        with patch('devices.adb_path', return_value='/fake/adb'), patch('devices._run', return_value='List of devices attached\nphone unauthorized\n'):
            result = json.loads(devices.android('scan', {}))
            self.assertEqual(result['devices'][0]['state'], 'unauthorized')

    def test_android_refuses_ambiguous_device(self):
        with patch('devices.adb_path', return_value='/fake/adb'), patch('devices._run', return_value='List of devices attached\none device\ntwo device\n'):
            with self.assertRaises(ValueError):
                devices.android('open_app', {'package': 'com.android.settings'})

    def test_sms_is_quoted_and_only_opens_composer(self):
        body = "hello'; touch /tmp/should-not-exist; echo '"
        with patch('devices.adb_path', return_value='/fake/adb'), patch('devices._run', side_effect=['List of devices attached\nphone device\n', 'Starting: Intent']) as run:
            result = devices.android('sms', {'number': '+123456789', 'message': body})
            command = run.call_args.args[0]
            remote = shlex.split(command[-1])
            self.assertIn('android.intent.action.SENDTO', remote)
            self.assertEqual(remote[-1], body)
            self.assertIn('no message was sent', result)
            self.assertNotIn('service call', command[-1])

    def test_dial_never_uses_call_intent(self):
        with patch('devices.adb_path', return_value='/fake/adb'), patch('devices._run', side_effect=['List of devices attached\nphone device\n', 'Starting']) as run:
            devices.android('call', {'number': '+123456789'})
            self.assertIn('android.intent.action.DIAL', run.call_args.args[0][-1])
            self.assertNotIn('android.intent.action.CALL', run.call_args.args[0][-1])

    def test_bluetooth_rejects_injected_address(self):
        with patch('devices.shutil.which', return_value='/fake/bluetoothctl'), patch('devices._run') as run:
            with self.assertRaises(ValueError):
                devices.bluetooth('connect', {'address': '00:00:00:00:00:00; reboot'})
            run.assert_not_called()

    def test_ios_only_requests_basic_fields(self):
        with patch('devices.shutil.which', side_effect=['idevice_id', 'ideviceinfo']), patch('devices._run', side_effect=['phone-id', 'iPhone', '18']) as run:
            result = json.loads(devices.connect_device('ios', 'info', {'udid': 'phone-id'}))
            self.assertEqual(set(result), {'ProductType', 'ProductVersion'})


class SearchTests(unittest.TestCase):
    def test_search_results_have_sources_and_drop_unsafe_urls(self):
        with patch('ddgs.DDGS') as client:
            client.return_value.text.return_value = [{'title': 'safe', 'href': 'https://example.com', 'body': 'text'}, {'href': 'javascript:bad'}]
            result = json.loads(actions.research('test'))
            self.assertEqual(len(result['results']), 1)
            self.assertEqual(result['results'][0]['url'], 'https://example.com')

    def test_search_failure_is_not_success(self):
        import requests
        with patch('ddgs.DDGS', side_effect=RuntimeError()), patch('web_research.requests.get', side_effect=requests.ConnectionError()):
            self.assertEqual(json.loads(actions.research('test'))['status'], 'unavailable')


class InventoryTests(unittest.TestCase):
    def test_terminal_and_kali_use_requested_timeout(self):
        import subprocess
        with patch('actions.config.TOOL_TIMEOUT', 3830), patch('actions.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            actions.run_terminal('printf hello')
            self.assertEqual(run.call_args.kwargs['timeout'], 3830)
            with patch('actions.shutil.which', return_value='/fake/nmap'):
                actions.kali_tool('nmap', '--version')
                self.assertEqual(run.call_args.kwargs['timeout'], 3830)

    def test_missing_tool_does_not_run(self):
        with patch('actions.shutil.which', return_value=None), patch('actions.subprocess.run') as run:
            self.assertEqual(json.loads(actions.kali_tool('nmap', '--version'))['status'], 'unavailable')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
