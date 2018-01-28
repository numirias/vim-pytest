from multiprocessing import Process, Pipe

import neovim
import pytest

from .pytest_plugin import run_pytest
from .signs import Signs


WIN_NAME = 'Results.pytest'

class TestSession:

    def __init__(self, vim_plugin):
        self.vp = vim_plugin
        self.num_collected = 0
        self.num_started = 0
        self.stdout = None

    def __call__(self, path, lineno):
        self.vp.echo('Running pytest on %s' % path)
        conn, other_conn = Pipe()
        proc = Process(target=run_pytest, args=(other_conn, lineno, [path]))
        proc.start()
        while True:
            obj = conn.recv()
            name, *args = obj
            if name == 'quit':
                break
            try:
                func = getattr(self, 'msg_%s' % name)
            except AttributeError:
                self.vp.echo('Unhandled event: %s' % str(obj))
            else:
                func(*args)
        proc.join()

    def msg_protocol(self, item):
        self.num_started += 1
        self.vp.echo('Running test %d/%d' %
                     (self.num_started, self.num_collected))

    def msg_collectionfinish(self, items):
        self.num_collected = len(items)
        for item in items:
            sign = self.vp.signs.add(item['nodeid'], item['lineno'])
            sign.state('collected')

    def msg_stage(self, stage, item):
        self.vp.signs.get(item['nodeid']).state('stage_%s' % stage)

    def msg_logreport(self, nodeid, stage, outcome):
        self.vp.signs.get(nodeid).state('outcome_%s' % outcome)

    def msg_sessionfinish(self, outcomes):
        self.outcomes = outcomes

    def msg_stdout(self, stdout):
        self.stdout = stdout
        if self.bad_outcomes:
            self.vp.split_fill()
        else:
            self.vp.split_delete()
        self.vp.show_summary()

    @property
    def bad_outcomes(self):
        return set(self.outcomes) - {'passed', 'skipped', 'xfailed', 'xpassed'}


class SplitMixin:

    def __init__(self):
        self.split_buffer = None
        self.max_split_size = self.vim.eval('g:vp_max_split_size')

    def split_content(self):
        return self.test_session.stdout.split('\n')[1:-1]

    def split_buffer_id(self):
        return self.vim.eval('buffer_number("%s")' % WIN_NAME)

    def split_fill(self):
        if self.split_buffer_id() > -1:
            self.split_update_size()
        else:
            self.split_create()
        self.split_buffer[:] = self.split_content()

    def split_create(self):
        new_size = min(
            self.max_split_size,
            len(self.split_content()),
            self.vim.eval('winheight("%") / 2'),
        )
        self.vim.command('botright %d new %s' % (new_size, WIN_NAME))
        self.split_buffer = self.vim.current.buffer
        self.vim.command('call VPSetupWindow()')
        self.vim.command('wincmd p')

    def split_update_size(self):
        new_size = min(
            self.max_split_size,
            len(self.split_content()),
            self.vim.eval('(winheight("%%") + winheight("%s")) / 2 + 1' % WIN_NAME),
        )
        self.vim.command('exe %d "resize %d"' %
                         (self.split_buffer_id(), new_size))

    def split_delete(self):
        self.vim.command('silent! exe "bdelete" buffer_number("%s")' % WIN_NAME)

    def split_toggle(self):
        if self.split_buffer_id() > -1:
            self.split_delete()
        else:
            self.split_fill()
            self.show_summary()


@neovim.plugin
class Plugin(SplitMixin):

    def __init__(self, vim):
        self.vim = vim
        self.signs = Signs(vim)
        self.test_session = None
        super().__init__()

    def echo(self, msg): # TODO
        msg = str(msg).replace('"', '\\"')
        self.vim.command('echo ' + '"' + str(msg) + '"')

    def echo_okay(self, msg):
        self.vim.call('VPEcho', msg, 'pytestWarning')

    def echo_bad(self, msg):
        self.vim.call('VPEcho', msg, 'pytestError')

    def echo_good(self, msg):
        self.vim.call('VPEcho', msg, 'pytestSuccess')

    @neovim.command('VP', range='', nargs='*', sync=False)
    def cmd_run(self, args, range):
        try:
            func = getattr(self, 'cmd_%s' % args[0])
        except AttributeError:
            self.echo('Pytest command %s not found.' % args[0])
        else:
            func()

    def cmd_file(self):
        self.run_tests()

    def cmd_function(self):
        self.run_tests(self.vim.current.window.cursor[0])

    def cmd_toggle(self):
        if not self.test_session or not self.test_session.stdout:
            self.echo_bad('No test failures to show.')
            return
        self.split_toggle()

    def cmd_nosigns(self):
        self.signs.remove_all()

    def run_tests(self, lineno=None):
        self.signs.remove_all()
        filename = self.vim.current.buffer.name
        self.test_session = TestSession(self)
        self.test_session(filename, lineno)

    def show_summary(self):
        total = self.test_session.num_started
        outcomes = self.test_session.outcomes
        if total:
            if all(o == 'passed' for o in outcomes):
                func = self.echo_good
            elif not self.test_session.bad_outcomes:
                func = self.echo_okay
            else:
                func = self.echo_bad
            text = ', '.join(('%d %s' % (v, k)) for k, v in outcomes.items())
            func('%d tests done: %s' % (total, text))
        else:
            self.echo_okay('No tests found.')
