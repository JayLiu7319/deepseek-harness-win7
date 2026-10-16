"""Select the last nonempty child message, otherwise its embedded stream text."""
from dsh.llm.assistant_stream import joinAssistantStreamText


class AssistantOutputFold:
    def __init__(self):
        self.message, self.partial = None, []

    def push(self, event):
        if event['type'] == 'assistant/message':
            content = event['data']['message']['content']
            if content:
                self.message = content
        if event['type'] in ('assistant/message', 'assistant/attempt'):
            self.pushText(joinAssistantStreamText(event['data']['stream']))

    def pushText(self, text):
        if text:
            self.partial.append(text)

    def collect(self):
        if self.message is not None:
            return self.message
        text = ''.join(self.partial)
        return [dict(type='text', text=text)] if text else None


def final_assistant_output(events):
    fold = AssistantOutputFold()
    for event in events:
        fold.push(event)
    return fold.collect()


finalAssistantOutput = final_assistant_output
