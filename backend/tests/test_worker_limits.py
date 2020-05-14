"""
Test classes which inherit from WorkerLimit
"""

from copr_backend.worker_manager import (
    GroupWorkerLimit,
    PredicateWorkerLimit,
    QueueTask,
    StringCounter,
)
from copr_backend.rpm_builds import (
    ArchitectureWorkerLimit,
    BuildQueueTask,
)

TASKS = [{
    "build_id": 7,
    "task_id": "7",
    "project_owner": "cecil",
}, {
    "build_id": 7,
    "task_id": "7-fedora-rawhide-x86_64",
    "project_owner": "cecil",
    "sandbox": "sb1",
}, {
    "build_id": 4,
    "task_id": "7-fedora-32-x86_64",
    "project_owner": "bedrich",
    "sandbox": "sb2",
}, {
    "build_id": 4,
    "task_id": "7-fedora-31-x86_64",
    "project_owner": "bedrich",
    "sandbox": "sb2",
}]

class _QT(QueueTask):
    def __init__(self, _id):
        self._id = _id

    @property
    def id(self):
        return self._id

    @property
    def always_true(self):
        """ this is for predicate tests """
        return True

    @property
    def sometimes_true(self):
        """ this is for predicate tests """
        return bool(int(self._id) % 2)

    @property
    def group(self):
        """ assign task to group_{0,1,2} per modulo operator """
        return "group_{}".format(int(self.id) % 3)

def test_predicate_worker_limit():
    # pylint: disable=protected-access
    wl = PredicateWorkerLimit(lambda x: x.always_true, 3)
    wl.worker_added("1", _QT(1))
    wl.worker_added("2", _QT(2))
    assert wl.check(_QT(3))
    wl.worker_added("3", _QT(3))
    assert wl.check(_QT(4)) is False
    wl.worker_dropped("2")
    assert wl.check(_QT(4))
    # double drop succeeds
    for worker in ["1", "2", "3", "4"]:
        wl.worker_dropped(worker)
    # check memory leaks
    assert wl._refs == {}
    wl.worker_added("3", _QT(3))
    assert set(wl._refs.keys()) == set(["3"])
    wl.clear()
    assert set(wl._refs.keys()) == set([])

def test_predicate_worker_limit_sometimes():
    # pylint: disable=protected-access
    wl = PredicateWorkerLimit(lambda x: x.sometimes_true, 2)
    wl.worker_added("0", _QT(0))
    wl.worker_added("1", _QT(1))
    assert wl.check(_QT(3))
    wl.worker_added("3", _QT(3))
    assert wl.check(_QT(5)) is False

def test_group_worker_limit():
    wl = GroupWorkerLimit(lambda x: x.group, 2)
    for task in [0, 1, 2]:
        wl.worker_added(str(task), _QT(str(task)))

    for task in [3, 4, 5]:
        qt = _QT(str(task))
        assert wl.check(qt)
        wl.worker_added(str(task), qt)

    for task in [6, 7, 8]:
        qt = _QT(str(task))
        assert not wl.check(qt)  # limit raised
        wl.worker_dropped(str(task - 3))
        assert wl.check(qt)  # limit OK again
        wl.worker_added(str(task), qt)

    # pylint: disable=protected-access
    for task in [0, 1, 2, 6, 7, 8]:
        wl.worker_dropped(str(task))

    # check mem leaks
    assert wl._groups._counter == {}
    assert wl._refs == {}

def test_worker_limit_info():
    limits = [
        PredicateWorkerLimit(lambda _: True, 8),
        PredicateWorkerLimit(lambda _: True, 8, name='allmatch'),
        GroupWorkerLimit(lambda x: x.owner, 4),
        GroupWorkerLimit(lambda x: x.sandbox, 2, name='sandbox'),
        ArchitectureWorkerLimit("x86_64", 3),
        ArchitectureWorkerLimit("aarch64", 2),
    ]
    tasks = [BuildQueueTask(t) for t in TASKS]
    for limit in limits:
        for task in tasks:
            limit.worker_added("w:" + str(task.id), task)
    assert ["limit info: " + limit.info() for limit in limits] == [
        "limit info: Unnamed 'PredicateWorkerLimit' limit, matching: w:7, "
        'w:7-fedora-rawhide-x86_64, w:7-fedora-32-x86_64, w:7-fedora-31-x86_64',
        "limit info: 'allmatch', matching: w:7, w:7-fedora-rawhide-x86_64, "
        'w:7-fedora-32-x86_64, w:7-fedora-31-x86_64',
        "limit info: Unnamed 'GroupWorkerLimit' limit, counter: cecil=2, bedrich=2",
        "limit info: 'sandbox', counter: sb1=1, sb2=2",
        "limit info: 'arch_x86_64'",
        "limit info: 'arch_aarch64'",
    ]

def test_string_counter():
    counter = StringCounter()
    counter2 = StringCounter()
    counter.drop(None)
    counter.add(None)
    counter2.add(None)
    assert str(counter) == ""
    counter.add("foo")
    counter.add("bar")
    counter.add("foo")
    counter2.add("baz")
    assert str(counter) == "foo=2, bar=1"
    assert str(counter2) == "baz=1"