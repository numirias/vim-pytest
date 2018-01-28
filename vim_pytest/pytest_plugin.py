from collections import Counter
from io import StringIO

from attr import attrib, attrs
import pytest
from _pytest.python import Function


@attrs
class PytestTest:
    outcome = attrib()
    lineno = attrib()


def convert_arg(arg):
    if isinstance(arg, Function):
        path, lineno, domain = arg.location
        return {'lineno': lineno, 'nodeid': arg.nodeid}
    if isinstance(arg, list):
        arg = [convert_arg(x) for x in arg]
    return arg


class PytestPlugin:

    def __init__(self, connection, stdout, lineno=None):
        self.connection = connection
        self.config = None
        self.reports = {}
        self.tests = []
        self.lineno = lineno
        self.stdout = stdout

    def send(self, *args):
        new_args = tuple(map(convert_arg, args))
        self.connection.send(new_args)

    def pytest_configure(self, config):
        self.config = config

    def pytest_collection_modifyitems(self, items):
        if self.lineno is None:
            return
        def lineno(item):
            return item.location[1]
        new_items = sorted(items, key=lineno, reverse=True)
        item = next((x for x in new_items if lineno(x) < self.lineno), None)
        if item:
            items[:] = [item]

    def pytest_report_collectionfinish(self, config, startdir, items):
        self.send('collectionfinish', items)

    def pytest_runtest_protocol(self, item, nextitem):
        self.send('protocol', item)

    def pytest_unconfigure(self, config):
        self.send('stdout', self.stdout.getvalue())
        self.send('quit')

    def pytest_runtest_setup(self, item):
        self.send('stage', 'setup', item)

    def pytest_runtest_call(self, item):
        self.send('stage', 'call', item)

    def pytest_runtest_teardown(self, item):
        self.send('stage', 'call', item)

    def pytest_terminal_summary(self, terminalreporter, exitstatus):
        self.stdout.truncate(0)
        self.stdout.seek(0)

    def pytest_runtest_logreport(self, report):
        if report.nodeid in self.reports:
            self.reports[report.nodeid].append(report)
        else:
            self.reports[report.nodeid] = [report]

        # lineno = report.location[1]
        outcome = self.total_outcome(self.reports[report.nodeid])
        self.send('logreport', report.nodeid, report.when, outcome)

    def pytest_sessionfinish(self, session):
        reports = self.reports.values()
        for group in reports:
            outcome = self.total_outcome(group)
            path, lineno, domain = group[0].location
            self.tests.append(PytestTest(outcome, lineno))

        summary = Counter([self.total_outcome(r) for r in reports])
        self.send('sessionfinish', summary)

    def total_outcome(self, reports):
        """Return actual test outcome of the group of reports."""
        for report in reports:
            cat = self.config.hook.pytest_report_teststatus(report=report)[0]
            if cat not in ['passed', '']:
                return cat
        return 'passed'


def run_pytest(connection, lineno, pytest_args):
    stdout_file = StringIO()
    my_plugin = PytestPlugin(connection, stdout_file, lineno)
    from _pytest import terminal
    reporter = terminal.TerminalReporter
    def wrapper(config, file):
        return reporter(config, stdout_file)
    terminal.TerminalReporter = wrapper
    pytest.main(pytest_args, plugins=[my_plugin])
