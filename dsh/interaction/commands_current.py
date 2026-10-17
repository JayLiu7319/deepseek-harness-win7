"""rc.3 command attachment descriptor and staged file-receipt admission."""
from dsh.attachment.error import AttachmentError
from dsh.attachment.store_current import decode_upload
from dsh.core.session.json import FrozenDict, FrozenList
from dsh.interaction.commands import CommandRuntime
from dsh.typert.remote import Remote


class CurrentCommandRuntime(CommandRuntime):
    _attachment_field = 'attachments'

    @Remote('execute')
    async def remoteExecute(self, agent, line, submittedAttachments, signal):
        return await super().remoteExecute(agent, line, submittedAttachments, signal)

    def __init__(self, ctx=None, config=None):
        super().__init__(ctx, config)
        self._file_receipts = {'resolver': None}

    def registerFileReceiptResolver(self, resolver):
        if self._file_receipts['resolver'] is not None:
            raise RuntimeError('commands: a file receipt resolver is already registered')
        self._file_receipts['resolver'] = resolver
        def dispose():
            if self._file_receipts['resolver'] is resolver:
                self._file_receipts['resolver'] = None
        return dispose

    def _attachment_rejection(self, name, missing_store=False):
        if missing_store:
            return '/{}: attachments are unavailable because no attachment store is composed'.format(name)
        return '/{} does not accept attachments'.format(name)

    async def _admit_attachments(self, agent, store, submitted):
        files = {}
        resolver = self._file_receipts['resolver']
        # Resolve every file first. Unknown receipts must not start image writes.
        for item in submitted:
            if item['type'] != 'file' or item['receiptId'] in files:
                continue
            ref = resolver(agent, item['receiptId']) if resolver is not None else None
            if ref is None:
                raise AttachmentError('File upload receipt is unknown for this session.', 'ATTACHMENT_NOT_FOUND')
            files[item['receiptId']] = ref
        images = [dict(data=decode_upload(item['data'], image=True), mediaType=item['mediaType'],
                       **({'name': item['name']} if 'name' in item else {})) for item in submitted if item['type'] == 'image']
        refs = iter(await store.saveImages(images)) if images else iter(())
        return FrozenList([FrozenDict(type=item['type'], attachment=next(refs) if item['type'] == 'image' else files[item['receiptId']])
                           for item in submitted])
