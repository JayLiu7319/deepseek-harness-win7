"""Run the same owned-filesystem generation journeys as the real Source actor."""
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from dsh.session.generation import (prepareJsonlMigration, verifyJsonlCurrentGeneration, default_format_adapter)
from dsh.session.jsonl_current import generationLogFilename
from dsh.session.jsonl_zstd import compress_frame, decompress_frame, scan_frames


async def generation_case(test):
    with tempfile.TemporaryDirectory(prefix='dsh-generation-pair-') as directory:
        root=Path(directory)
        source=root/generationLogFilename(test['version'],test['compression'])
        current=root/generationLogFilename(3,test['compression'])
        def encode(raw):
            data=raw.encode('utf-8')
            return data if test['compression']=='none' else compress_frame(data)
        raw=test['raw']
        end=raw.find('\n')+1
        data=encode(raw) if test['compression']=='none' else encode(raw[:end])+(encode(raw[end:]) if raw[end:] else b'')
        if test.get('tornFrame'):data+=encode('tail\n')[:6]
        if test.get('combinedFrame'):data=encode(raw)
        source.write_bytes(data)
        validation_calls,verification_calls=0,0
        async def validate(header):
            nonlocal validation_calls
            await asyncio.sleep(0)
            validation_calls+=1
            if test.get('failHeader'):raise ValueError('historical header rejected')
        async def verify(*args):
            nonlocal verification_calls
            verification_calls+=1
            result=await verifyJsonlCurrentGeneration(*args)
            if test.get('badDigest'):result['digest']='0'*64
            return result
        options=dict(sourcePath=str(source),currentPath=str(current),sourceVersion=test['version'],compression=test['compression'],
                     validateHistoricalHeader=validate,verifyCurrentFile=verify)
        if test['operation']=='verify':
            result=await verifyJsonlCurrentGeneration(str(source),test['compression'],test.get('expectedId','generation'),test.get('count',0),test.get('prefix'))
            return dict(bytes=result['bytes'],digest=result['digest'])
        try:
            prepared=await prepareJsonlMigration(options)
            if test.get('changedSource'):source.write_bytes(data+b'changed')
            if test.get('target')=='different':current.write_bytes(b'different')
            if test.get('target')=='same':
                first=await prepareJsonlMigration(options)
                await first.publish()
                if test.get('appendWinner'):current.write_bytes(current.read_bytes()+encode('unvalidated append tail'))
            if test.get('publish'):await asyncio.gather(prepared.publish(),prepared.publish())
            current_header=None
            if current.exists():
                physical=current.read_bytes()
                if test['compression']=='zstd':
                    frame=scan_frames(physical)['frames'][0]
                    physical=decompress_frame(physical[:frame['end']])
                current_header=physical.decode('utf-8').split('\n')[0]
            return dict(artifact=prepared.artifact,validationCalls=validation_calls,verificationCalls=verification_calls,
                sourceUnchanged=source.read_bytes()==data,files=sorted(os.listdir(root)),currentHeader=current_header)
        except Exception as error:
            failure=dict(name=getattr(error,'name','Error'),message=str(error).replace(directory,'<root>'))
            if hasattr(error,'cause'):
                if isinstance(error.cause,json.JSONDecodeError):
                    print(json.dumps(dict(case=test['case'],jsonParserCause=str(error.cause))))
                    failure['cause']='$native-json-parser-error'
                else:failure['cause']=str(error.cause).replace(directory,'<root>')
            return dict(failure=failure,validationCalls=validation_calls,verificationCalls=verification_calls,
                        sourceUnchanged=source.read_bytes()==data,files=sorted(os.listdir(root)))


def execute(test):
    return asyncio.run(generation_case(test))
