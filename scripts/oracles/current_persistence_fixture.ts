/** Controlled read/fault callbacks behind the current read-only handle protocol. */
export function readFixture(listHeaders: (signal?: AbortSignal) => Promise<any[]>, readLog?: (id: string, signal?: AbortSignal) => Promise<any>) {
  return {
    list: async (options?: {signal?: AbortSignal}) => (await listHeaders(options?.signal)).map(header => ({header, revision: 'controlled'})),
    open: async (id: string, mode: string, options?: {signal?: AbortSignal}) => {
      if (mode !== 'read') throw Error('observer only allows cold reads')
      const loaded = await readLog!(id, options?.signal)
      let closed = false
      return {header: loaded.meta, inheritedEventCount: loaded.inheritedEventCount,
        read: async (start = 0) => {if(closed)throw Error('closed fixture handle');return {events:loaded.events.slice(start),eventState:'detached'}},
        close: async () => {closed = true},
      }
    },
  }
}
