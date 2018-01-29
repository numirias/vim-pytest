from collections import Counter
from io import StringIO
import signal

import attr
from attr import attrib, attrs
import pytest
from _pytest.python import Function
from _pytest import terminal


@attrs
class PytestTest:

    outcome = attrib()
    lineno = attrib()


@attrs
class ConnectionWrapper:

    conn = attrib()

    def send(self, *args):
        new_args = tuple(map(self.convert_arg, args))
        self.conn.send(new_args)

    def convert_arg(self, arg):
        if isinstance(arg, Function):
            path, lineno, domain = arg.location
            return {'lineno': lineno, 'nodeid': arg.nodeid}
        if isinstance(arg, list):
            arg = [self.convert_arg(x) for x in arg]
        return arg


class PytestPlugin:

    def __init__(self, conn, stdout, lineno=None):
        self.conn = conn
        self.stdout = stdout
        self.lineno = lineno
        self.config = None
        self.reports = {}
        self.tests = []

    def pytest_configure(self, config):
        self.config = config

    def pytest_collection_modifyitems(self, items):
        if self.lineno is None:
            return
        lineno = lambda item: item.location[1]
        new_items = sorted(items, key=lineno, reverse=True)
        item = next((x for x in new_items if lineno(x) < self.lineno), None)
        if item:
            items[:] = [item]

    def pytest_report_collectionfinish(self, config, startdir, items):
        self.conn.send('collectionfinish', items)

    def pytest_runtest_protocol(self, item, nextitem):
        self.conn.send('protocol', item)

    def pytest_unconfigure(self, config):
        self.conn.send('stdout', self.stdout.getvalue())
        self.conn.send('quit')

    def pytest_runtest_setup(self, item):
        self.conn.send('stage', 'setup', item)

    def pytest_runtest_call(self, item):
        self.conn.send('stage', 'call', item)

    def pytest_runtest_teardown(self, item):
        self.conn.send('stage', 'call', item)

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        self.stdout.truncate(0)
        self.stdout.seek(0)

    def pytest_runtest_logreport(self, report):
        if report.nodeid in self.reports:
            self.reports[report.nodeid].append(report)
        else:
            self.reports[report.nodeid] = [report]
        outcome = self.total_outcome(self.reports[report.nodeid])
        self.conn.send('logreport', report.nodeid, report.when, outcome)

    def pytest_sessionfinish(self, session):
        reports = self.reports.values()
        for group in reports:
            outcome = self.total_outcome(group)
            path, lineno, domain = group[0].location
            self.tests.append(PytestTest(outcome, lineno))

        summary = Counter([self.total_outcome(r) for r in reports])
        self.conn.send('sessionfinish', summary)

    def pytest_internalerror(self, excrepr, excinfo):
        self.conn.send('internalerror', excrepr)

    def total_outcome(self, reports):
        """Return actual test outcome of the group of reports."""
        for report in reports:
            cat = self.config.hook.pytest_report_teststatus(report=report)[0]
            if cat not in ['passed', '']:
                return cat
        return 'passed'


def patch_terminalreporter(new_file):
    reporter = terminal.TerminalReporter
    def wrapper(config, file):
        return reporter(config, new_file)
    terminal.TerminalReporter = wrapper


def sigint_handler(signum, frame):
    raise KeyboardInterrupt


def run_pytest(conn, lineno, pytest_args):
    file = StringIO()
    patch_terminalreporter(file)
    plugin = PytestPlugin(conn, file, lineno)
    pytest.main(pytest_args, plugins=[plugin])


def pytest_process(conn, *args, **kwargs):
    wrapped_conn = ConnectionWrapper(conn)
    signal.signal(signal.SIGINT, sigint_handler)
    try:
        run_pytest(wrapped_conn, *args, **kwargs)
    except:
        import traceback
        wrapped_conn.send('error', traceback.format_exc())
