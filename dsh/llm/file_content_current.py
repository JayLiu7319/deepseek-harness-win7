"""rc.3 transient file handles; durable messages retain their file blocks."""
from dsh.cordis.json_text import stringify_json
from dsh.cordis.utils import js_to_string


def content_has_file(content):
    return any(block['type'] == 'file' or
               (block['type'] == 'tool-result' and content_has_file(block['content'])) for block in content)


def file_handle_text(ref, readonly_path=None):
    digest = js_to_string(ref.get('attachmentId'))[7:15]
    identity = 'File {} ({} bytes, sha256:{})'.format(stringify_json(ref['name']), js_to_string(ref['bytes']), digest)
    if readonly_path is None:
        return ('[' + identity + ' was uploaded, but the current execution environment cannot access a readable path. '
                'Report that limitation if its contents are needed; do not claim to have read it.]')
    return ('[' + identity + ': verbatim read-only copy saved at ' + stringify_json(readonly_path) +
            '. Read that path with your file tools when its contents are needed; copy it to a writable location before modifying it. '
            'When delegating file work, include this saved path in the delegation prompt; only subagents sharing this execution environment can read it.]')


def replace_files(blocks, resolve_path):
    result = None
    for index, block in enumerate(blocks):
        if block['type'] == 'file':
            if result is None:
                result = list(blocks[:index])
            result.append(dict(type='text', text=file_handle_text(block['attachment'], resolve_path(block['attachment']))))
            continue
        if block['type'] == 'tool-result':
            content = replace_files(block['content'], resolve_path)
            if content is not block['content']:
                if result is None:
                    result = list(blocks[:index])
                result.append(dict(block, content=content))
                continue
        if result is not None:
            result.append(block)
    return blocks if result is None else result


def project_files_to_text(messages, resolve_path):
    if not any(content_has_file(message['content']) for message in messages):
        return messages
    result = []
    for message in messages:
        content = replace_files(message['content'], resolve_path)
        result.append(message if content is message['content'] else dict(message, content=content))
    return result
