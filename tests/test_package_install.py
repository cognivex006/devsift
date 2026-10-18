"""Opt-in actual offline wheel/sdist installs and explicit synthetic rollback."""
import base64
import csv
from email.parser import BytesParser
import hashlib
from importlib import metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_PACKAGE_INSTALL") == "1", "explicit actual offline install/rollback opt-in")
class PackageInstallTests(unittest.TestCase):
    def run_command(self, command, *, cwd=None, stdin=None, timeout=120, setup_git=False):
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}
                       and not key.upper().startswith(("GIT_", "PIP_"))}
        environment.update(PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1",
                           PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1",
                           GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0",
                           GIT_LITERAL_PATHSPECS="1", GIT_TERMINAL_PROMPT="0", SOURCE_DATE_EPOCH="1700000000",
                           PIP_CONFIG_FILE=os.devnull)
        if setup_git:
            environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                               GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
        run = subprocess.run(command, cwd=cwd, input=stdin, capture_output=True, env=environment, timeout=timeout)
        self.assertEqual(run.returncode, 0, (run.stdout + run.stderr).decode("utf-8", errors="replace")[-5000:])
        self.assertLessEqual(len(run.stdout), 64_000_000)
        return run.stdout

    def git(self, root, *args, setup=False, stdin=None):
        from devsift.git_runtime import git_executable
        return self.run_command([git_executable(root), "--no-optional-locks", "--no-replace-objects",
                                 "-c", "core.fsmonitor=false", "-C", str(root), *args],
                                stdin=stdin, setup_git=setup, timeout=30)

    def snapshot(self, root, names):
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}

    def commit_inputs(self):
        settings = self.git(ROOT, "config", "--includes", "--null", "--list").lower().split(b"\0")
        keys = [item.split(b"\n", 1)[0] for item in settings]
        self.assertFalse(any(key == b"extensions.partialclone" or key.endswith(b".promisor") for key in keys))
        self.assertEqual(self.git(ROOT, "rev-parse", "--is-shallow-repository").strip(), b"false")
        sha = self.git(ROOT, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        self.assertRegex(sha, r"^[a-f0-9]{40}$")
        manifest_raw = self.git(ROOT, "cat-file", "blob", sha + ":packaging/manifest.json")
        self.assertLessEqual(len(manifest_raw), 200_000)
        manifest = json.loads(manifest_raw)
        names = sorted({name for component in manifest["components"].values() for name in component["required"]}
                       | {"packaging/manifest.json"})
        self.assertLessEqual(len(names), 256)
        for name in names:
            self.assertFalse(name.startswith("/"))
            self.assertNotIn("..", PurePosixPath(name).parts)
            self.assertNotIn("\\", name)
            self.assertNotIn(":", name)
        tree = self.git(ROOT, "ls-tree", "-z", sha, "--", *names)
        entries = {}
        for item in tree.split(b"\0"):
            if item:
                info, name = item.split(b"\t", 1)
                mode, kind, oid = info.split(b" ")
                self.assertIn(mode, (b"100644", b"100755"))
                self.assertEqual(kind, b"blob")
                entries[name.decode()] = oid
        self.assertEqual(set(entries), set(names))
        # Bound object sizes before batch-reading contents. No filters/archive
        # substitution, broad workspace copy or consumer build hooks are involved.
        oids = [entries[name] for name in names]
        sizes = self.git(ROOT, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                         stdin=b"\n".join(oids) + b"\n").splitlines()
        self.assertEqual(len(sizes), len(names))
        total = 0
        for oid, row in zip(oids, sizes):
            actual, kind, length = row.split()
            self.assertEqual((actual, kind), (oid, b"blob"))
            self.assertLessEqual(int(length), 8_000_000)
            total += int(length)
        self.assertLessEqual(total, 32_000_000)
        batch = io.BytesIO(self.git(ROOT, "cat-file", "--batch", stdin=b"\n".join(oids) + b"\n"))
        data = {}
        for name, oid in zip(names, oids):
            actual, kind, length = batch.readline().split()
            self.assertEqual((actual, kind), (oid, b"blob"))
            data[name] = batch.read(int(length))
            self.assertEqual(batch.read(1), b"\n")
        self.assertEqual(batch.read(), b"")
        self.assertEqual(data["packaging/manifest.json"], manifest_raw)
        return sha, manifest, data

    def build(self, stage, output, *, sdist=False):
        output.mkdir()
        backend = str(Path(metadata.distribution("setuptools").locate_file("")).resolve())
        code = "import sys;sys.path.insert(0,sys.argv[2]);from setuptools.build_meta import build_wheel,build_sdist;destination=sys.argv[1];build_wheel(destination);"
        if sdist:
            code += "build_sdist(destination);"
        self.run_command([sys.executable, "-I", "-B", "-c", code, str(output), backend], cwd=stage)
        return next(output.glob("*.whl")), next(output.glob("*.tar.gz")) if sdist else None

    def wheel_sources(self, wheel, expected):
        with zipfile.ZipFile(wheel) as archive:
            files = {name for name in archive.namelist() if ".dist-info/" not in name}
            self.assertEqual(files, set(expected))
            for name, raw in expected.items():
                self.assertEqual(archive.read(name), raw, name)
            info = next(name.split("/")[0] for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            headers = BytesParser().parsebytes(archive.read(info + "/METADATA"))
            self.assertEqual(headers["Name"], "devsift")
            self.assertEqual(headers["Version"], PROJECT_VERSION)
            self.assertNotIn(b"Requires-Dist:", archive.read(info + "/METADATA"))
            self.assertIn(b"Wheel-Version: 1.0", archive.read(info + "/WHEEL"))
            self.assertIn(b"devsift = devsift.cli:main", archive.read(info + "/entry_points.txt"))
            rows = {row[0]: row for row in csv.reader(io.StringIO(archive.read(info + "/RECORD").decode()))}
            for name, raw in expected.items():
                digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
                self.assertEqual(rows[name][1:], ["sha256=" + digest, str(len(raw))])

    def venv(self, destination):
        self.run_command([sys.executable, "-I", "-B", "-m", "venv", str(destination)])
        return destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def install(self, python, wheel, expected_digest, *, cwd):
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), expected_digest)
        self.run_command([str(python), "-I", "-B", "-m", "pip", "install", "--no-index", "--no-deps",
                          "--no-cache-dir", "--no-compile", "--force-reinstall", str(wheel)], cwd=cwd)

    def installed(self, python, expected, *, cwd):
        code = """import base64,csv,hashlib,importlib,importlib.metadata as m,io,json,sys
expected=json.load(sys.stdin);dist=m.distribution('devsift');files={str(p).replace('\\\\','/') for p in dist.files}
assert {p for p in files if p.startswith('devsift/')}==set(expected)
rows={r[0]:r for r in csv.reader(io.StringIO(dist.read_text('RECORD')))}
actual={}
for name,digest in expected.items():
    path=dist.locate_file(name);raw=path.read_bytes();actual[name]=hashlib.sha256(raw).hexdigest()
    assert actual[name]==digest
    encoded=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
    assert rows[name][1:]==['sha256='+encoded,str(len(raw))]
    if name.endswith('.py') and not name.endswith('/__main__.py'):
        module=name[:-3].replace('/','.').removesuffix('.__init__');importlib.import_module(module)
assert not any(p.startswith(('tools/','plan/','templates/','native/','skills/','tests/','worktrees/')) for p in files)
assert not dist.locate_file('devsift/verification_plan.py').exists() or 'devsift/verification_plan.py' in expected
print(json.dumps(actual,sort_keys=True))
"""
        hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in expected.items()}
        observed = json.loads(self.run_command([str(python), "-I", "-B", "-c", code], cwd=cwd,
                                               stdin=json.dumps(hashes).encode()))
        self.assertEqual(observed, hashes)

    def cli(self, python, consumer):
        record = json.loads(self.run_command([str(python), "-I", "-B", "-m", "devsift", "scan", "--all", "--security"], cwd=consumer))
        self.assertEqual(record["command"], "scan")
        self.assertEqual(record["data"]["counts"]["executed"], 3)
        console = python.parent / ("devsift.exe" if os.name == "nt" else "devsift")
        output = self.run_command([str(console), "--help"], cwd=consumer)
        self.assertIn(b"usage:", output)

    def test_actual_offline_install_sdist_and_explicit_synthetic_rollback(self):
        self.assertEqual(metadata.version("setuptools"), "83.0.0", "Provision the pinned backend explicitly before opt-in")
        source_sha, manifest, data = self.commit_inputs()
        current = {name: data[name] for name in manifest["components"]["core-wheel"]["required"]}
        self.assertEqual(len(current), 42)
        self.assertTrue(all(name.startswith("devsift/") and name.endswith(".py") for name in current))
        original = self.snapshot(ROOT, sorted(data))
        index = Path(self.git(ROOT, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
        index_before = index.read_bytes()
        with tempfile.TemporaryDirectory(prefix="devsift-offline-install-") as directory:
            parent = Path(directory)
            stage = parent / "trusted-stage"
            stage.mkdir()
            for name, raw in data.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            for args in (("init", "--quiet"), ("config", "core.autocrlf", "false"),
                         ("config", "core.hooksPath", str(parent / "no-hooks")), ("add", "--all"),
                         ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                          "-c", "commit.gpgSign=false", "commit", "--quiet", "-m", "trusted extracted input fixture")):
                self.git(stage, *args, setup=True)
            fixture_sha = self.git(stage, "rev-parse", "HEAD", setup=True).decode().strip()
            from tools.build_package import build_package, verify_bundle
            bundle = parent / "source-bundles"
            artifacts = build_package(stage, bundle, source_sha=fixture_sha)
            integrity = next(item.sha256 for item in artifacts if item.name == "integrity.json")
            self.assertEqual(verify_bundle(bundle, expected_integrity_sha256=integrity, expected_source_sha=fixture_sha), artifacts)
            with zipfile.ZipFile(bundle / "devsift-consumer-skill.zip") as archive:
                self.assertEqual(archive.namelist(), manifest["components"]["consumer-skill"]["required"])
                self.assertIn(b"CONSUMER-SCOPE.md", archive.read("skills/devsift/SKILL.md"))
            with zipfile.ZipFile(bundle / "devsift-source-assets.zip") as archive:
                self.assertEqual(archive.namelist(), manifest["components"]["source-assets"]["required"])
                self.assertFalse(any(PurePosixPath(name).suffix.lower() in {".exe", ".dll", ".so", ".dylib", ".whl"} for name in archive.namelist()))
            wheel, sdist = self.build(stage, parent / "current", sdist=True)
            self.wheel_sources(wheel, current)
            # Review every tar member before individually copying regular files.
            # No extractall, links, devices or traversal are accepted.
            extracted = parent / "verified-sdist"
            extracted.mkdir()
            with tarfile.open(sdist) as archive:
                members = archive.getmembers()
                self.assertLessEqual(len(members), 256)
                self.assertLessEqual(sum(member.size for member in members), 32_000_000)
                tar_modules = {}
                for member in members:
                    parts = PurePosixPath(member.name).parts
                    self.assertTrue(parts and parts[0] == f"devsift-{PROJECT_VERSION}")
                    self.assertNotIn("..", parts)
                    self.assertNotIn("\\", member.name)
                    self.assertNotIn(":", member.name)
                    self.assertTrue(member.isdir() or member.isfile())
                    if member.isdir():
                        continue
                    name = "/".join(parts[1:])
                    self.assertFalse(name.startswith(("plan/", "tests/", "templates/", "worktrees/", "native/", "skills/")))
                    raw = archive.extractfile(member).read()
                    if name.startswith("devsift/"):
                        tar_modules[name] = raw
                    if name == "PKG-INFO":
                        self.assertEqual(BytesParser().parsebytes(raw)["Name"], "devsift")
                    target = extracted / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write(raw)
                self.assertEqual(tar_modules, current)
            recovered_wheel, _ = self.build(extracted, parent / "sdist-wheel")
            self.wheel_sources(recovered_wheel, current)
            prior_stage = parent / "synthetic-prior"
            prior_stage.mkdir()
            prior = dict(current)
            del prior["devsift/verification_plan.py"]
            prior["devsift/__init__.py"] += b"\n# Explicit synthetic prior-artifact rollback fixture.\n"
            for name in manifest["components"]["core-sdist"]["required"]:
                if name == "devsift/verification_plan.py":
                    continue
                raw = prior.get(name, data[name])
                if name == "pyproject.toml":
                    raw = raw.replace(b'    "devsift.verification_plan",\n', b"")
                target = prior_stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            prior_wheel, _ = self.build(prior_stage, parent / "prior")
            self.wheel_sources(prior_wheel, prior)
            trusted_artifacts = {artifact: hashlib.sha256(artifact.read_bytes()).hexdigest()
                                 for artifact in (prior_wheel, wheel, recovered_wheel)}
            consumer = parent / "consumer"
            consumer.mkdir()
            (consumer / "sample.py").write_bytes(b"value = 1\n")
            (consumer / "devsift.py").write_bytes(b"raise RuntimeError('consumer must not execute')\n")
            (consumer / "setup.py").write_bytes(b"raise RuntimeError('consumer build hook must not execute')\n")
            for args in (("init", "--quiet"), ("config", "core.autocrlf", "false"), ("add", "--all"),
                         ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                          "-c", "commit.gpgSign=false", "commit", "--quiet", "-m", "consumer")):
                self.git(consumer, *args, setup=True)
            consumer_names = [path.relative_to(consumer).as_posix() for path in consumer.rglob("*") if path.is_file()]
            consumer_before = self.snapshot(consumer, consumer_names)
            python = self.venv(parent / "venv")
            for artifact, expected in ((prior_wheel, prior), (wheel, current), (prior_wheel, prior)):
                self.install(python, artifact, trusted_artifacts[artifact], cwd=consumer)
                self.installed(python, expected, cwd=consumer)
                self.cli(python, consumer)
            sdist_python = self.venv(parent / "sdist-venv")
            self.install(sdist_python, recovered_wheel, trusted_artifacts[recovered_wheel], cwd=consumer)
            self.installed(sdist_python, current, cwd=consumer)
            self.cli(sdist_python, consumer)
            self.assertEqual(self.snapshot(consumer, consumer_names), consumer_before)
            self.assertEqual({path.relative_to(consumer).as_posix() for path in consumer.rglob("*") if path.is_file()}, set(consumer_names))
            self.assertEqual(self.snapshot(stage, sorted(data)), {name: hashlib.sha256(raw).hexdigest() for name, raw in data.items()})
        self.assertEqual(self.snapshot(ROOT, sorted(data)), original)
        self.assertEqual(index.read_bytes(), index_before)
        self.assertEqual(self.git(ROOT, "rev-parse", "HEAD").decode().strip(), source_sha)


if __name__ == "__main__":
    unittest.main()
