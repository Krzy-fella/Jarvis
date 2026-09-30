import builtins
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import terminal_ui

ROOT = Path(__file__).resolve().parents[1]


class InputHistoryTests(unittest.TestCase):
    def setUp(self):
        self.saved = list(terminal_ui._message_history)
        terminal_ui._message_history.clear()
        self.addCleanup(lambda:terminal_ui._message_history.__setitem__(slice(None),self.saved))

    def test_only_chat_input_is_recalled_and_readline_history_is_restored(self):
        try: import readline
        except ImportError: self.skipTest('This Python build has no readline')
        previous = [readline.get_history_item(i+1) for i in range(readline.get_current_history_length())]
        def restore():
            readline.clear_history()
            for item in previous: readline.add_history(item)
        self.addCleanup(restore)
        readline.clear_history(); readline.add_history('menu choice not a chat')
        with patch.object(terminal_ui.console,'input',return_value='first message'):
            self.assertEqual(terminal_ui.read_message(),'first message')
        def read(prompt):
            self.assertEqual(readline.get_current_history_length(),1)
            self.assertEqual(readline.get_history_item(1),'first message')
            return 'second message'
        with patch.object(terminal_ui.console,'input',side_effect=read): terminal_ui.read_message()
        self.assertEqual(readline.get_history_item(1),'menu choice not a chat')
        self.assertEqual(terminal_ui._message_history,['first message','second message'])

    def test_history_is_bounded_redacted_and_forget_clears_it(self):
        try: import readline
        except ImportError: self.skipTest('This Python build has no readline')
        terminal_ui._message_history[:] = [str(i) for i in range(100)]
        with patch.object(terminal_ui.console,'input',return_value='sensitive text'), patch('terminal_ui.redact',return_value='[REDACTED]'):
            self.assertEqual(terminal_ui.read_message(),'sensitive text')
        self.assertEqual(len(terminal_ui._message_history),100)
        self.assertEqual(terminal_ui._message_history[-1],'[REDACTED]')
        with patch.object(terminal_ui.console,'input',return_value='/forget all'): terminal_ui.read_message()
        self.assertEqual(terminal_ui._message_history,[])

    def test_no_readline_keeps_plain_text_working(self):
        original = builtins.__import__
        def importing(name,*args,**kwargs):
            if name == 'readline': raise ImportError('unavailable')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=importing), patch.object(terminal_ui.console,'input',return_value=' hello '):
            self.assertEqual(terminal_ui.read_message(),'hello')

    @unittest.skipUnless(shutil.which('node'),'Node is development-only for web keyboard tests')
    def test_web_history_navigation_and_draft_restoration(self):
        result = subprocess.run(['node',str(ROOT/'tests/input_history_test.js')],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(sys.platform.startswith('linux'),'PTY keyboard integration uses Linux readline')
    def test_real_terminal_arrow_keys_recall_and_restore_draft(self):
        import os, pty, select, time
        master,slave = pty.openpty()
        script = "import terminal_ui; [(print('RECEIVED:'+terminal_ui.read_message(),flush=True)) for _ in range(4)]"
        process = subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,stdin=slave,stdout=slave,stderr=slave)
        os.close(slave)
        buffer = bytearray()
        def read_until(text):
            deadline = time.monotonic()+5
            while text not in buffer and time.monotonic()<deadline:
                if select.select([master],[],[],.1)[0]: buffer.extend(os.read(master,8192))
            self.assertIn(text,buffer)
            buffer.clear()
        try:
            read_until('You'.encode()); os.write(master,b'first message\n'); read_until(b'RECEIVED:first message')
            os.write(master,b'second message\n'); read_until(b'RECEIVED:second message')
            os.write(master,b'\x1b[A\n'); read_until(b'RECEIVED:second message')
            os.write(master,b'draft\x1b[A\x1b[B\n'); read_until(b'RECEIVED:draft')
            self.assertEqual(process.wait(timeout=5),0)
        finally:
            if process.poll() is None: process.kill(); process.wait()
            os.close(master)
