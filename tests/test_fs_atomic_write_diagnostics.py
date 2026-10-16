"""Host hardening around the unchanged Source atomic publication/ACL policy."""
import errno
import logging
import os
from pathlib import Path
import subprocess
import stat

import pytest

from dsh.cordis.context import Context
from dsh.core.system_prompt import SystemPrompt
from dsh.core.tools import ToolsService
from dsh.fs.fs_local import FsError, FsService, Win32FsError
from dsh.fs.fs_sandbox import SandboxedFileSystem
from dsh.fs.tool_fs import ToolFsPlugin
from dsh.fs.tool_str_replace_editor import StrReplaceEditorPlugin
from dsh.sandbox.sandbox_policy import SandboxPolicyService


def deny(path, syscall="ReplaceFileW", code=5):
    return Win32FsError(syscall, code, str(path))


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [
    "create-parent", "create-staging", "create-temp", "copy-target-acl",
    "write-temp", "sync-temp", "close-temp", "replace-target", "publish-rename", "publish-link",
])
async def test_atomic_failure_identifies_stage_and_retains_original_contract(tmp_path, monkeypatch, stage):
    fs = FsService(cwd=str(tmp_path))
    path = tmp_path / "target.txt"
    if stage not in ("publish-rename", "publish-link"):
        path.write_bytes(b"old")
    target = await fs.resolve("target.txt")
    fs.internals.platform = "win32"
    fs.internals.copyFileDacl = lambda *_args: None
    primary = deny(path)
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(stage)
        raise primary

    if stage == "copy-target-acl":
        fs.internals.copyFileDacl = fail
    elif stage == "replace-target":
        fs.internals.replaceFile = fail
    elif stage == "publish-link":
        fs.internals.linkFile = fail
    elif stage == "close-temp":
        real_close = os.close

        def close_then_fail(descriptor):
            real_close(descriptor)
            fail()

        monkeypatch.setattr(os, "close", close_then_fail)
    elif stage == "create-staging":
        real_mkdir = os.mkdir

        def fail_staging(path, *args, **kwargs):
            if str(path).endswith(".tmpdir"):
                fail()
            return real_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(os, "mkdir", fail_staging)
    else:
        operation = {"create-parent": "makedirs", "create-staging": "mkdir", "create-temp": "open",
                     "write-temp": "write", "sync-temp": "fsync", "publish-rename": "replace"}[stage]
        monkeypatch.setattr(os, operation, fail)

    with pytest.raises((OSError, FsError)) as caught:
        await fs.writeText(target, "new", {"kind": "createIfAbsent"} if stage == "publish-link" else None)
    error = caught.value
    if stage == "publish-link":
        assert isinstance(error, FsError) and error.code == "FS_IO_ERROR" and error.cause is primary
    else:
        assert error is primary and error.code == "EACCES" and error.winerror == 5
    assert error.atomicWrite["stage"] == stage
    assert error.atomicWrite["cleanup"] == ("not-created" if stage in ("create-parent", "create-staging") else "removed")
    assert "stage=" + stage in error.message and "ACL" in error.message
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.tmpdir"))
    assert path.read_bytes() == b"old" if path.exists() else stage in ("publish-rename", "publish-link")


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_both_errors_without_retry_or_acl_changes(tmp_path):
    fs = FsService(cwd=str(tmp_path))
    path = tmp_path / "target.txt"
    path.write_bytes(b"old")
    primary = deny(path, "SetFileSecurityW")
    cleanup = deny(path, "RemoveDirectoryW")

    def fail_copy(*_args):
        raise primary

    def fail_cleanup(*_args):
        raise cleanup

    fs.internals.copyFileDacl = fail_copy
    fs.internals.platform = "win32"
    fs.internals.removeStagingDir = fail_cleanup
    with pytest.raises(FsError) as caught:
        await fs.writeText(await fs.resolve("target.txt"), "new")
    error = caught.value
    assert error.code == "FS_NOT_FOUND" and error.cause is primary
    assert error.atomicWrite["failure"]["winerror"] == 5
    assert error.atomicWrite["cleanupFailure"]["syscall"] == "RemoveDirectoryW"
    assert error.atomicWrite["cleanup"] == "failed"
    assert error.atomicWrite["stagingPath"] in error.message
    assert "Do not retry" in error.message and "temp cleanup failed" in error.message
    assert path.read_bytes() == b"old"
    assert len(list(tmp_path.glob("*.tmpdir"))) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unknown-entry", "directory-identity", "file-identity"])
async def test_cleanup_refuses_foreign_or_changed_objects(tmp_path, change):
    fs = FsService(cwd=str(tmp_path))
    target = tmp_path / "target.txt"
    target.write_bytes(b"old")
    fs.internals.platform = "win32"
    fs.internals.copyFileDacl = lambda *_args: None
    foreign = []

    def fail_publication(_target, temp):
        temp = Path(temp)
        staging = temp.parent
        if change == "unknown-entry":
            path = staging / "foreign.txt"
        elif change == "directory-identity":
            staging.rename(str(staging) + ".saved")
            staging.mkdir()
            path = staging / temp.name
        else:
            temp.rename(tmp_path / "saved-temp.txt")
            path = temp
        path.write_bytes(b"foreign")
        foreign.append(path)
        raise deny(target)

    fs.internals.replaceFile = fail_publication
    with pytest.raises(FsError) as caught:
        await fs.writeText(await fs.resolve("target.txt"), "new")
    assert caught.value.code == "FS_NOT_FOUND"
    assert "cleanup refused" in caught.value.atomicWrite["cleanupFailure"]["message"]
    assert foreign[0].read_bytes() == b"foreign"
    assert target.read_bytes() == b"old"


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction rejection")
@pytest.mark.asyncio
async def test_cleanup_refuses_junction_without_touching_its_destination(tmp_path):
    destination = tmp_path / "foreign"
    destination.mkdir()
    file = destination / "target.txt.tmp"
    file.write_bytes(b"foreign")
    staging = tmp_path / ".target.tmpdir"
    result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(staging), str(destination)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr
    fs = FsService(cwd=str(tmp_path))
    with pytest.raises(OSError, match="cleanup refused"):
        await fs._remove_staging(str(staging), os.lstat(str(staging)), str(staging / file.name), file.stat())
    assert file.read_bytes() == b"foreign" and staging.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [1175, 1176, 1177])
async def test_replace_failure_retains_recoverable_content_only_for_partial_publication(tmp_path, code):
    fs = FsService(cwd=str(tmp_path))
    path = tmp_path / "target.txt"
    path.write_bytes(b"old")
    primary = deny(path, code=code)
    fs.internals.platform = "win32"
    fs.internals.copyFileDacl = lambda *_args: None

    def fail_publication(*_args):
        if code == 1176:
            path.unlink()  # Documented no-backup partial state; the temp is the recovery copy.
        elif code == 1177:
            path.rename(tmp_path / "original-moved.txt")
        raise primary

    fs.internals.replaceFile = fail_publication
    with pytest.raises(Win32FsError) as caught:
        await fs.writeText(await fs.resolve("target.txt"), "new")
    assert caught.value is primary and primary.winerror == code and primary.code == "EIO"
    if code == 1175:
        assert primary.atomicWrite["cleanup"] == "removed"
        assert path.read_bytes() == b"old" and not list(tmp_path.glob("*.tmpdir"))
    else:
        assert primary.atomicWrite["cleanup"] == "preserved-for-recovery"
        assert Path(primary.atomicWrite["tempPath"]).read_bytes() == b"new"
        assert "partially complete" in primary.message


@pytest.mark.asyncio
async def test_successful_commit_stays_successful_when_cleanup_fails_and_reports_residue(tmp_path, caplog):
    fs = FsService(cwd=str(tmp_path))

    def fail_cleanup(path):
        raise deny(path, "RemoveDirectoryW")

    fs.internals.removeStagingDir = fail_cleanup
    with caplog.at_level(logging.WARNING, logger="dsh.fs.fs_local"):
        result = await fs.writeText(await fs.resolve("target.txt"), "committed")
    assert result.operation == "create" and (tmp_path / "target.txt").read_bytes() == b"committed"
    record = next(record for record in caplog.records if hasattr(record, "atomic_write"))
    assert record.atomic_write["stage"] == "cleanup-after-commit"
    assert Path(record.atomic_write["stagingPath"]).is_dir()
    assert "committed; staging cleanup failed" in record.message


@pytest.mark.asyncio
async def test_cleanup_warning_handler_cannot_turn_committed_write_into_failure(tmp_path, monkeypatch):
    fs = FsService(cwd=str(tmp_path))

    def fail_cleanup(*_args, **_kwargs):
        raise RuntimeError("cleanup failed")

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("logging failed")

    fs.internals.removeStagingDir = fail_cleanup
    monkeypatch.setattr(logging.getLogger("dsh.fs.fs_local"), "warning", fail_log)
    outcome = await fs.writeText(await fs.resolve("target.txt"), "committed")
    assert outcome.operation == "create" and (tmp_path / "target.txt").read_bytes() == b"committed"


@pytest.mark.asyncio
async def test_write_and_close_double_failure_keeps_primary_cause(tmp_path, monkeypatch):
    fs = FsService(cwd=str(tmp_path))
    primary = OSError(errno.ENOSPC, "disk full")
    real_close = os.close

    def fail_write(*_args):
        raise primary

    def fail_close(descriptor):
        real_close(descriptor)
        raise OSError(errno.EIO, "close failed")

    monkeypatch.setattr(os, "write", fail_write)
    monkeypatch.setattr(os, "close", fail_close)
    with pytest.raises(FsError) as caught:
        await fs.writeText(await fs.resolve("target.txt"), "new")
    assert caught.value.code == "FS_NOT_FOUND" and caught.value.cause is primary
    assert caught.value.atomicWrite["stage"] == "write-temp"
    assert "disk full" in caught.value.message and "close failed" in caught.value.message
    assert not list(tmp_path.glob("*.tmpdir"))


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments", [
    ("write", dict(file_path="target.txt", content="new")),
    ("edit", dict(file_path="target.txt", old_string="old", new_string="new")),
    ("str_replace_editor", dict(command="create", path="target.txt", file_text="new")),
    ("str_replace_editor", dict(command="str_replace", path="target.txt", old_str="old", new_str="new")),
    ("str_replace_editor", dict(command="insert", path="target.txt", insert_line=1, new_str="new")),
])
async def test_atomic_diagnostic_reaches_actual_tool_errors(tmp_path, monkeypatch, name, arguments):
    ctx = Context()
    ctx.set_service("tools", ToolsService(ctx))
    fibers = []
    try:
        fibers.append(await ctx.plugin(SystemPrompt))
        fibers.append(await ctx.plugin(SandboxPolicyService, {"mode": "workspace-write", "workspaceRoot": str(tmp_path)}))
        fibers.append(await ctx.plugin(SandboxedFileSystem, {"cwd": str(tmp_path)}))
        fibers.append(await ctx.plugin(ToolFsPlugin))
        fibers.append(await ctx.plugin(StrReplaceEditorPlugin))
        creating = name == "str_replace_editor" and arguments.get("command") == "create"
        if not creating:
            (tmp_path / "target.txt").write_bytes(b"old")
        fs = ctx.get("fs")
        fs.internals.platform = "win32"

        def fail_copy(*_args):
            raise deny(tmp_path / "target.txt", "SetFileSecurityW")

        fs.internals.copyFileDacl = fail_copy
        if creating:
            real_open = os.open

            def fail_temp(path, *args, **kwargs):
                if str(path).endswith("target.txt.tmp"):
                    raise deny(path, "CreateFileW")
                return real_open(path, *args, **kwargs)

            monkeypatch.setattr(os, "open", fail_temp)
        if name == "str_replace_editor":
            arguments = dict(arguments, path=str(tmp_path / "target.txt"))
        result = await ctx.get("tools").execute(dict(signal=None, callId="atomic-failure", name=name,
                                                     arguments=arguments))
        assert result.is_error is True
        text = "".join(block.get("text", "") for block in result.content)
        assert "stage=" + ("create-temp" if creating else "copy-target-acl") in text
        assert "Win32 5" in text and "ACL" in text
        assert result.error["message"] in text
        if creating:
            assert not (tmp_path / "target.txt").exists()
        else:
            assert (tmp_path / "target.txt").read_bytes() == b"old"
        assert not list(tmp_path.glob("*.tmpdir"))
    finally:
        for fiber in reversed(fibers):
            await fiber.dispose()


@pytest.fixture
def native_acl(tmp_path):
    """Install ACLs only on this freshly allocated fixture, restoring before pytest cleanup."""
    if os.name != "nt":
        pytest.skip("actual Windows ACL inheritance")
    import ctypes as c
    from dsh.sandbox.windows_acl import WinApi, SidAttributes

    api = WinApi()
    adv = api.advapi
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [c.c_wchar_p, c.c_uint32, c.c_void_p, c.c_void_p]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = c.c_int
    adv.SetFileSecurityW.argtypes = [c.c_wchar_p, c.c_uint32, c.c_void_p]
    adv.SetFileSecurityW.restype = c.c_int
    adv.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.c_void_p]
    adv.ConvertSidToStringSidW.restype = c.c_int
    token = c.c_void_p()
    api.check(api.OpenProcessToken(api.GetCurrentProcess(), 8, c.byref(token)), "OpenProcessToken")
    try:
        user = api.token_info(token, 1)
        value = c.c_void_p()
        api.check(adv.ConvertSidToStringSidW(SidAttributes.from_buffer(user).sid, c.byref(value)), "format fixture SID")
        try:
            account = c.wstring_at(value)
        finally:
            api.LocalFree(value)
    finally:
        api.CloseHandle(token)

    def install(path, sddl):
        descriptor = c.c_void_p()
        api.check(adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl.replace("CURRENT_USER", account), 1, c.byref(descriptor), None), "parse fixture DACL")
        try:
            api.check(adv.SetFileSecurityW(str(path), 0x80000004, descriptor), "set fixture DACL")
        finally:
            api.LocalFree(descriptor)

    folder = tmp_path / "owned-acl-fixture"
    folder.mkdir()
    try:
        yield folder, install
    finally:
        # This fixture never creates links; refuse them rather than changing any destination ACL.
        for directory, dirs, files in os.walk(str(folder)):
            for path in [Path(directory)] + [Path(directory) / name for name in files]:
                assert not path.lstat().st_file_attributes & 0x400
                install(path, "D:P(A;OICI;FA;;;CURRENT_USER)")
                if path.is_file():
                    path.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction,existing_stage,new_stage", [
    ("D:P(A;;0x1f01bf;;;CURRENT_USER)(A;OICIIO;FR;;;CURRENT_USER)", "create-temp", "create-temp"),
    ("D:P(A;OICI;0x1e01bf;;;CURRENT_USER)", "replace-target", "publish-rename"),
])
async def test_actual_inherited_acl_failures_identify_stage_and_distinct_residue(native_acl, restriction,
                                                                                existing_stage, new_stage):
    folder, install = native_acl
    path = folder / "existing.txt"
    path.write_bytes(b"original")
    install(folder, restriction)
    fs = FsService(cwd=str(folder))
    residues = []
    for filename, stage in [("existing.txt", existing_stage), ("probe.txt", new_stage), ("existing.txt", existing_stage)]:
        with pytest.raises(FsError) as caught:
            await fs.writeText(await fs.resolve(filename), "new")
        error = caught.value
        assert error.code == "FS_NOT_FOUND"
        assert error.atomicWrite["stage"] == stage and error.atomicWrite["cleanup"] == "failed"
        assert error.atomicWrite["cleanupFailure"]["winerror"] == 5
        residues.append(error.atomicWrite["stagingPath"])
        assert Path(residues[-1]).is_dir()
        assert "ACL" in error.message and "WinError 5" in error.message
    assert len(set(residues)) == 3
    assert path.read_bytes() == b"original" and not (folder / "probe.txt").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction,winerror", [("readonly", 5), ("held-reader", 32)])
async def test_actual_readonly_and_sharing_errors_do_not_poison_directory(native_acl, restriction, winerror):
    folder, _install = native_acl
    path = folder / "existing.txt"
    path.write_bytes(b"original")
    fs = FsService(cwd=str(folder))
    reader = None
    if restriction == "readonly":
        path.chmod(stat.S_IREAD)
    else:
        reader = path.open("rb")
    try:
        with pytest.raises(Win32FsError) as caught:
            await fs.writeText(await fs.resolve("existing.txt"), "new")
        assert caught.value.winerror == winerror
        assert caught.value.atomicWrite["stage"] == "replace-target"
        assert caught.value.atomicWrite["cleanup"] == "removed"
        assert "file handle" in caught.value.message if winerror == 32 else "read-only" in caught.value.message
        assert path.read_bytes() == b"original" and not list(folder.glob("*.tmpdir"))
        assert (await fs.writeText(await fs.resolve("probe.txt"), "probe")).operation == "create"
    finally:
        if reader:
            reader.close()
        path.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.asyncio
async def test_actual_replacement_preserves_restricted_dacl_before_and_after_content(native_acl):
    import ctypes as c
    import re
    folder, install = native_acl
    path = folder / "protected.txt"
    path.write_bytes(b"original")
    install(path, "D:P(A;;0x12019f;;;CURRENT_USER)")
    adv = c.WinDLL("advapi32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    adv.GetFileSecurityW.argtypes = [c.c_wchar_p, c.c_uint32, c.c_void_p, c.c_uint32, c.c_void_p]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32, c.c_void_p, c.c_void_p]
    kernel.LocalFree.argtypes = [c.c_void_p]

    def policy(filename):
        size = c.c_uint32()
        adv.GetFileSecurityW(str(filename), 4, None, 0, c.byref(size))
        assert size.value
        descriptor = c.create_string_buffer(size.value)
        assert adv.GetFileSecurityW(str(filename), 4, descriptor, size.value, c.byref(size))
        value = c.c_void_p()
        assert adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4, c.byref(value), None)
        try:
            # ReplaceFileW may duplicate equivalent ACEs while preserving access policy.
            return list(dict.fromkeys(re.findall(r"\([^()]+\)", c.wstring_at(value))))
        finally:
            kernel.LocalFree(value)

    expected = policy(path)
    fs = FsService(cwd=str(folder))
    seen = []

    def inspect_staged(paths):
        seen.append(policy(paths["tempPath"]))
        assert Path(paths["tempPath"]).read_bytes() == b"new"

    fs.internals.inspectTemp = inspect_staged
    outcome = await fs.writeText(await fs.resolve("protected.txt"), "new")
    assert outcome.operation == "update" and path.read_bytes() == b"new"
    assert seen == [expected] and policy(path) == expected
    assert not list(folder.glob("*.tmpdir"))
