"""Optional Bluetooth and Android integrations; never invoke a local shell."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess


def adb_path():
    configured = os.environ.get('JARVIS_ADB_PATH')
    if configured:
        return configured
    found = shutil.which('adb')
    if found:
        return found
    local = Path.home() / '.local/share/jarvis/platform-tools/adb'
    return str(local) if local.is_file() else None


def _run(argv, timeout=25):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f'Command failed ({result.returncode})').strip())
    return result.stdout.strip()


def android(action, args):
    executable = adb_path()
    if not executable:
        raise RuntimeError('ADB is missing. Install Android platform-tools, or set JARVIS_ADB_PATH to its adb executable.')
    listing = _run([executable, 'devices', '-l'])
    devices = []
    for line in listing.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append({'serial': parts[0], 'state': parts[1], 'details': ' '.join(parts[2:])})
    if action in {'scan', 'list', 'status'}:
        return json.dumps({'devices': devices, 'hint': 'Enable USB debugging and accept the authorization prompt on your phone.'})
    authorized = [device['serial'] for device in devices if device['state'] == 'device']
    serial = args.get('serial')
    if serial is None and len(authorized) == 1:
        serial = authorized[0]
    if serial not in authorized:
        raise ValueError('Select an authorized Android device using args.serial. Connect USB, enable USB debugging, and accept the phone prompt first.')
    if action == 'open_app':
        package = args.get('package', '')
        if not isinstance(package, str) or not re.fullmatch(r'[A-Za-z][\w]*(?:\.[A-Za-z][\w]*)+', package):
            raise ValueError('Provide an Android package name, for example com.android.settings.')
        remote = ['monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1']
        message = 'App launch requested.'
    elif action in {'call', 'dial', 'sms'}:
        number = args.get('number', '')
        if not isinstance(number, str) or not re.fullmatch(r'\+?[0-9][0-9 ()-]{1,30}', number):
            raise ValueError('Provide args.number as a phone number.')
        number = re.sub(r'[ ()-]', '', number)
        if action == 'sms':
            body = args.get('message', '')
            if not isinstance(body, str) or len(body) > 4000 or '\x00' in body:
                raise ValueError('SMS message must be text under 4001 characters, without NUL bytes.')
            remote = ['am', 'start', '-a', 'android.intent.action.SENDTO', '-d', 'smsto:' + number, '--es', 'sms_body', body]
            message = 'SMS composer opened. Review and press Send on your phone; no message was sent automatically.'
        else:
            remote = ['am', 'start', '-a', 'android.intent.action.DIAL', '-d', 'tel:' + number]
            message = 'Dialer opened. Press Call on your phone; no call was placed automatically.'
    else:
        raise ValueError('Android actions: scan, status, open_app, dial/call, sms.')
    # adb shell uses a remote shell even when subprocess has shell=False.
    output = _run([executable, '-s', serial, 'shell', shlex.join(remote)])
    if 'Error:' in output or 'Exception' in output or 'No activities found' in output:
        raise RuntimeError(output)
    return json.dumps({'status': 'requested', 'message': message, 'output': output})


def bluetooth(action, args):
    executable = shutil.which('bluetoothctl')
    if not executable:
        raise RuntimeError('Bluetooth requires BlueZ bluetoothctl on Linux.')
    if action in {'status', 'list'}:
        return _run([executable, 'show']) + '\n' + _run([executable, 'devices'])
    if action == 'scan':
        seconds = args.get('seconds', 8)
        if not isinstance(seconds, int) or not 1 <= seconds <= 30:
            raise ValueError('Scan duration must be 1–30 seconds.')
        output = _run([executable, '--timeout', str(seconds), 'scan', 'on'], timeout=seconds + 5)
        return output + '\n' + _run([executable, 'devices'])
    if action in {'pair', 'connect', 'disconnect', 'info', 'remove'}:
        address = args.get('address', '')
        if not isinstance(address, str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address):
            raise ValueError('Provide args.address as a Bluetooth MAC address.')
        output = _run([executable, '--timeout', '20', action, address])
        if 'Failed' in output or 'not available' in output:
            raise RuntimeError(output)
        return output or 'Bluetooth command completed. Pairing may need confirmation in your desktop Bluetooth settings.'
    raise ValueError('Bluetooth actions: status, list, scan, pair, connect, disconnect, info, remove.')


def connect_device(device_type, action, args=None):
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ValueError('Device args must be an object.')
    if device_type == 'adb':
        return android(action, args)
    if device_type == 'bluetooth':
        return bluetooth(action, args)
    if device_type == 'ios':
        executable = shutil.which('idevice_id')
        if not executable:
            raise RuntimeError('Basic iPhone USB support requires libimobiledevice tools (idevice_id and ideviceinfo). Connect by USB and tap Trust on the phone.')
        identifiers = _run([executable, '-l']).splitlines()
        if action in {'scan', 'list', 'status'}:
            return json.dumps({'devices': identifiers, 'capabilities': ['scan', 'info'], 'hint': 'Connect by USB and tap Trust. Android-style app/call/SMS actions are not supported here.'})
        if action == 'info':
            udid = args.get('udid')
            if udid not in identifiers:
                raise ValueError('args.udid must match a currently connected iPhone from scan.')
            info = shutil.which('ideviceinfo')
            if not info:
                raise RuntimeError('ideviceinfo is missing; install libimobiledevice tools.')
            # Do not request the full device record, which contains personal identifiers.
            return json.dumps({key: _run([info, '-u', udid, '-k', key]) for key in ('ProductType', 'ProductVersion')})
        raise ValueError('iOS supports scan/status/info only; call, SMS and app control are not implemented on iOS.')
    raise ValueError('device_type must be adb, bluetooth or ios.')
