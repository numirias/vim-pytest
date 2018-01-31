from multiprocessing import Process, Pipe
import os
import signal
import threading

import neovim
import pytest

from .pytest_plugin import pytest_process
from .signs import Signs


# Exit codes from pytest
EXIT_OK = 0
EXIT_TESTSFAILED = 1
EXIT_INTERRUPTED = 2
EXIT_INTERNALERROR = 3
EXIT_USAGEERROR = 4
EXIT_NOTESTSCOLLECTED = 5
WIN_NAME = 'Results.pytest'

class TestSession:

    def __init__(self, vim_plugin, buffer, lineno):
        self.vp = vim_plugin
        self.buffer = buffer
        self.lineno = lineno
        self.num_collected = 0
        self.num_started = 0
        self.stdout = None
        self.exitcode = None
        self.outcomes = None

    def __call__(self):
        path = self.buffer.name
        self.vp.echo('Running pytest on %s' % path)
        thread = threading.Thread(target=self.loop, args=(path, self.lineno))
        thread.start()

    def loop(self, path, lineno):
        conn, other = Pipe()
        proc = Process(target=pytest_process, args=(other, lineno, [path]))
        self.proc = proc
        proc.start()
        while True:
            try:
                obj = conn.recv()
            except EOFError:
                break
            name, *args = obj
            try:
                func = getattr(self, 'msg_%s' % name)
            except AttributeError:
                self.vp.echo('Unhandled event: %s' % name)
            else:
                try:
                    func(*args)
                except:
                    self.handle_exception()
            if name in ['error', 'finish']:
                break
        proc.join()
        self.proc = None

    def handle_exception(self):
        import traceback
        self.vp.vim.async_call(
            self.vp.error,
            'Exception in message thread.\n%s' % traceback.format_exc(),
        )

    def msg_collectionfinish(self, items):
        self.num_collected = len(items)
        for item in items:
            sign = self.vp.signs.add(self.buffer, item['nodeid'], item['lineno'])
            sign.state('collected')

    def msg_test_start(self, item):
        self.num_started += 1
        self.vp.vim.async_call(
            self.vp.echo,
            ('Running test %d/%d' % (self.num_started, self.num_collected))
        )

    def msg_test_stage(self, item, stage):
        self.vp.signs.get(item['nodeid']).state('stage_%s' % stage)

    def msg_test_outcome(self, nodeid, stage, outcome):
        self.vp.signs.get(nodeid).state('outcome_%s' % outcome)

    def msg_finish(self, outcomes, exitcode, stdout):
        self.outcomes = outcomes
        self.exitcode = exitcode
        lines = stdout.split('\n')[:-1]
        self.stdout = lines[1:] if not lines[0] else lines
        self.vp.vim.async_call(self.show_results)

    def msg_error(self, msg):
        self.vp.vim.async_call(
            self.vp.error,
            'Exception in pytest process: %s ' % msg
        )

    def show_results(self, force=False):
        if force or self.exitcode not in [EXIT_OK, EXIT_NOTESTSCOLLECTED]:
            self.vp.split_fill(self.stdout)
        else:
            self.vp.split_delete()
        self.show_summary()

    def show_summary(self):
        total = self.num_started
        outcomes = self.outcomes
        outcomes_text = ', '.join(('%d %s' % (v, k)) for k, v in outcomes.items())
        if len(outcomes) == 1:
            summary = 'All %d tests %s.' % (total, list(outcomes)[0])
        else:
            summary = '%d tests done: %s' % (total, outcomes_text)
        if self.exitcode == EXIT_OK:
            self.vp.echo_good(summary)
        elif self.exitcode in [EXIT_TESTSFAILED, EXIT_INTERRUPTED]:
            if self.exitcode == EXIT_INTERRUPTED:
                if not outcomes:
                    self.vp.echo_bad('Interrupted!')
                else:
                    self.vp.echo_bad('Interrupted! %s' % summary)
            else:
                self.vp.echo_bad(summary)
        elif self.exitcode == EXIT_INTERNALERROR:
            self.vp.echo_okay('Internal error!')
        elif self.exitcode == EXIT_USAGEERROR:
            self.vp.echo_okay('Usage error!')
        elif self.exitcode == EXIT_NOTESTSCOLLECTED:
            self.vp.echo_okay('No tests collected.')


class SplitMixin:

    def __init__(self):
        self.max_split_size = self.vim.eval('g:vp_max_split_size')

    def split_buffer(self):
        return self.vim.buffers[self.split_buffer_id()]

    def split_buffer_id(self):
        return self.vim.eval('buffer_number("%s")' % WIN_NAME)

    def split_fill(self, lines):
        self.vim.command('')
        self.vim.call('VPCreateSplit', len(lines))
        self.split_buffer()[:] = lines

    def split_delete(self):
        self.vim.command('')
        self.vim.call('VPDeleteSplit')


@neovim.plugin
class Plugin(SplitMixin):

    def __init__(self, vim):
        self.vim = vim
        self.signs = Signs(vim)
        self.test_session = None
        self.vim.command('let g:vp_commands = %s' % self.commands())
        super().__init__()

    @classmethod
    def commands(cls):
        return [c[4:] for c in vars(cls).keys() if c.startswith('cmd_')]

    def echo(self, msg):
        escaped = str(msg).replace('"', '\\"')
        self.vim.command('echo "%s"' % escaped)

    def echo_okay(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestWarning', *args, **kwargs)

    def echo_bad(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestError', *args, **kwargs)

    def echo_good(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestSuccess', *args, **kwargs)

    def echo_color(self, msg, hl='Normal', *args, **kwargs):
        self.vim.call('VPEcho', msg, hl, *args, **kwargs)

    def error(self, obj):
        self.vim.err_write('[VP] %s\n' % obj)

    @neovim.command('VP', range='', nargs='+', complete='customlist,VPComplete', sync=False)
    def run(self, args, range):
        try:
            func = getattr(self, 'cmd_%s' % args[0])
        except AttributeError:
            self.error('Subcommand not found: %s' % args[0])
        else:
            func()

    def cmd_file(self):
        self.run_tests()

    def cmd_function(self):
        self.run_tests(self.vim.current.window.cursor[0])

    def cmd_toggle(self):
        if not self.test_session or not self.test_session.stdout:
            self.error('No test results to show.')
            return
        if self.split_buffer_id() > -1:
            self.split_delete()
        else:
            self.test_session.show_results(force=True)

    def cmd_stop(self):
        try:
            pid = self.test_session.proc.pid
        except AttributeError:
            self.error('Pytest isn\'t running.')
            return
        self.echo('Stopping pytest run (PID %d).' % pid)
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            self.error('Pytest isn\'t running.')
            return
        self.test_session.proc.join()
        self.echo('Stopped pytest.')

    def cmd_hidesigns(self):
        self.signs.remove_all()

    def run_tests(self, lineno=None):
        if self.test_session and self.test_session.proc:
            self.vim.async_call(
                self.error, 'Pytest is currently running. (Use "stop" to cancel.)'
            )
            return
        self.signs.remove_all()
        self.test_session = TestSession(self, self.vim.current.buffer, lineno)
        self.test_session()

