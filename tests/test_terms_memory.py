"""Process-level tests for durable owner memory, never enforcement waivers."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devsift.terms_memory import (
    DecisionHistory, TermsMemoryError, read_history, record_decision,
    repository_identity,
)


class TermsMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.home = self.base / 'home'
        self.git = shutil.which('git')
        self.assertIsNotNone(self.git)
        self.git_command(self.repo, 'init', '-q')

    def git_command(self, root, *args):
        return subprocess.run([self.git, '-C', str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def record(self, **kwargs):
        options = dict(case_id='case-1', fingerprint='1' * 64,
                       evidence_digest='2' * 64, choice='decline', owner='Owner',
                       rationale='Keep blocked pending replacement', home=self.home)
        options.update(kwargs)
        return record_decision(self.repo, **options)

    def directory(self, root=None):
        return (self.home / '.local/share/devsift/terms' /
                repository_identity(root or self.repo))

    def journal(self):
        return self.directory() / 'journal.json'

    def child(self, program, *args):
        return subprocess.Popen([sys.executable, '-c', program,
                                 str(self.repo), str(self.home), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=Path(__file__).resolve().parents[1])

    def test_never_created_history_reads_without_creating_home_or_project_files(self):
        before = sorted(str(p.relative_to(self.repo)) for p in self.repo.rglob('*'))
        history = read_history(self.repo, home=self.home)
        self.assertEqual(history.events, ())
        self.assertEqual(history.revision, '0' * 64)
        self.assertFalse(self.home.exists())
        self.assertEqual(before, sorted(str(p.relative_to(self.repo)) for p in self.repo.rglob('*')))
        with self.assertRaises(TermsMemoryError):
            DecisionHistory(history.repository_id, history.revision, ())
        with self.assertRaises(AttributeError):
            history.repository_id = 'forged'

    def test_restart_and_defensive_copy_preserve_original_event(self):
        event = self.record()
        process = self.child('''
import json, sys
from devsift.terms_memory import read_history
h=read_history(sys.argv[1],home=sys.argv[2])
print(json.dumps(dict(repository_id=h.repository_id,revision=h.revision,events=h.events)))
''')
        out, err = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, err.decode())
        restarted = json.loads(out)
        self.assertEqual(restarted['events'], [event])
        self.assertEqual(restarted['revision'], event['event_hash'])
        history = read_history(self.repo, home=self.home)
        history.events[0]['choice'] = 'resolved'
        event['owner'] = 'Changed after append'
        self.assertEqual(history.events[0]['choice'], 'decline')
        self.assertEqual(history.events[0]['owner'], 'Owner')
        self.assertEqual(read_history(self.repo, home=self.home).events, history.events)

    def test_normalized_origin_persists_across_physical_checkouts(self):
        other = self.base / 'other'
        other.mkdir()
        self.git_command(other, 'init', '-q')
        self.git_command(self.repo, 'remote', 'add', 'origin', 'https://GitHub.com/Owner/Project.git/')
        self.git_command(other, 'remote', 'add', 'origin', 'git@github.com:Owner/Project.git')
        self.assertEqual(repository_identity(self.repo), repository_identity(other))
        first = self.record()
        self.assertEqual(read_history(other, home=self.home).events, (first,))
        self.git_command(other, 'remote', 'set-url', 'origin', 'https://github.com/Owner/Different.git')
        self.assertNotEqual(repository_identity(self.repo), repository_identity(other))
        self.assertEqual(read_history(other, home=self.home).events, ())

    def test_path_fallback_separates_repositories(self):
        other = self.base / 'other'
        other.mkdir()
        self.assertNotEqual(repository_identity(self.repo), repository_identity(other))

    def test_origin_credentials_and_tokens_are_rejected_without_disclosure(self):
        for url in ('https://name:SECRET@github.com/owner/repo',
                    'https://SECRET@github.com/owner/repo',
                    'https://github.com/owner/repo?token=SECRET',
                    'file:///SECRET/repo'):
            self.git_command(self.repo, 'config', 'remote.origin.url', url)
            with self.assertRaises(TermsMemoryError) as error:
                repository_identity(self.repo)
            self.assertNotIn('SECRET', str(error.exception))
            self.assertFalse(self.home.exists())

    def test_concurrent_first_writers_are_serialized_without_lost_events(self):
        program = '''
import sys
from devsift.terms_memory import record_decision
record_decision(sys.argv[1],home=sys.argv[2],case_id='case-'+sys.argv[3],
 fingerprint='1'*64,evidence_digest='2'*64,choice='decline',owner='Owner',
 rationale='Pending replacement')
'''
        processes = [self.child(program, str(i)) for i in range(8)]
        for process in processes:
            out, err = process.communicate(timeout=40)
            self.assertEqual(process.returncode, 0, err.decode())
        history = read_history(self.repo, home=self.home)
        self.assertEqual(len(history.events), 8)
        self.assertEqual({e['case_id'] for e in history.events}, {'case-' + str(i) for i in range(8)})
        previous = '0' * 64
        for event in history.events:
            self.assertEqual(event['previous_hash'], previous)
            previous = event['event_hash']
        self.assertEqual(history.revision, previous)

    def test_explicit_reconsideration_and_supersession_retain_all_events(self):
        first = self.record()
        saved = self.journal().read_bytes()
        with self.assertRaises(TermsMemoryError):
            self.record(choice='reconsider')
        self.assertEqual(saved, self.journal().read_bytes())
        second = self.record(choice='reconsider', supersedes=first['event_id'])
        third = self.record(choice='remediate', supersedes=second['event_id'])
        fourth = self.record(choice='resolved', supersedes=third['event_id'])
        history = read_history(self.repo, home=self.home)
        self.assertEqual(history.events, (first, second, third, fourth))
        before = self.journal().read_bytes()
        for options in (dict(supersedes=first['event_id']),
                        dict(case_id='different', supersedes=fourth['event_id'])):
            with self.assertRaises(TermsMemoryError):
                self.record(**options)
        self.assertEqual(before, self.journal().read_bytes())

    def test_missing_or_corrupt_owned_journal_fails_closed_on_read_and_write(self):
        self.record()
        original = self.journal().read_bytes()
        self.journal().unlink()
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=self.home)
        with self.assertRaises(TermsMemoryError):
            self.record()
        for data in (b'{', b'[]', original.replace(b'"decline"', b'"resolved"')):
            self.journal().write_bytes(data)
            with self.assertRaises(TermsMemoryError):
                read_history(self.repo, home=self.home)
            with self.assertRaises(TermsMemoryError):
                self.record()
            self.assertEqual(self.journal().read_bytes(), data)

    def test_cross_repository_replay_and_missing_marker_are_rejected(self):
        self.record()
        other = self.base / 'other'
        other.mkdir()
        target = self.directory(other)
        target.mkdir()
        for name in ('ownership.json', 'journal.json', 'history.lock'):
            shutil.copyfile(self.directory() / name, target / name)
        with self.assertRaises(TermsMemoryError):
            read_history(other, home=self.home)
        (self.directory() / 'ownership.json').unlink()
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=self.home)
        with self.assertRaises(TermsMemoryError):
            self.record()

    def test_redaction_and_bounded_input_are_persisted_before_hashing(self):
        event = self.record(owner='token=private-value',
                            rationale='Use password=hunter2 until migration')
        raw = self.journal().read_text('utf-8')
        self.assertNotIn('private-value', raw)
        self.assertNotIn('hunter2', raw)
        self.assertIn('[REDACTED]', raw)
        self.assertEqual(read_history(self.repo, home=self.home).events, (event,))
        before = self.journal().read_bytes()
        for bad in (dict(rationale='x' * 8193), dict(owner='a\nb'),
                    dict(fingerprint='bad'), dict(choice='waive'),
                    dict(case_id=''), dict(as_of=datetime(2020, 1, 1))):
            with self.assertRaises(TermsMemoryError):
                self.record(**bad)
        self.assertEqual(before, self.journal().read_bytes())

    def test_backdated_and_reordered_events_fail_closed(self):
        self.record(as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(TermsMemoryError):
            self.record(as_of=datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.record(as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
        data = json.loads(self.journal().read_bytes())
        data['events'].reverse()
        self.journal().write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=self.home)

    def test_journal_and_home_symlinks_rejected_without_touching_destination(self):
        self.record()
        victim = self.base / 'victim'
        victim.write_text('unchanged')
        self.journal().unlink()
        try:
            self.journal().symlink_to(victim)
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=self.home)
        with self.assertRaises(TermsMemoryError):
            self.record()
        self.assertEqual(victim.read_text(), 'unchanged')
        alias = self.base / 'alias'
        alias.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=alias)

    def test_hardlinks_and_project_local_store_are_rejected(self):
        self.record()
        alias = self.base / 'alias'
        os.link(self.journal(), alias)
        with self.assertRaises(TermsMemoryError):
            read_history(self.repo, home=self.home)
        self.assertFalse((self.repo / 'home').exists())
        with self.assertRaises(TermsMemoryError):
            self.record(home=self.repo / 'home')
        self.assertFalse((self.repo / 'home').exists())

    def test_whole_store_rollback_is_explicitly_not_authenticated(self):
        # Demonstrate the documented limit rather than claiming absolute replay
        # protection: a valid older full store needs an independent checkpoint.
        self.record()
        saved = self.journal().read_bytes()
        self.record(case_id='new-case')
        self.journal().write_bytes(saved)
        self.assertEqual(len(read_history(self.repo, home=self.home).events), 1)


if __name__ == '__main__':
    unittest.main()
