export type FlowKind = "multicast" | "aes67" | "unicast"
export type Level = { db: number | null; peak: number | null; clip?: boolean }
/** One row per flow: a stereo pair (two channels in one flow) has `r`, the right channel's level. */
export type Channel = {
  n: number | string
  name: string
  dir: "tx" | "rx"
  flow: FlowKind
  group?: string
  source?: string
  db: number | null
  peak: number | null
  clip?: boolean
  muted?: boolean
  r?: Level
}
export type Device = { name: string; model: string; ip: string; format: string; clock: "leader" | "locked" | "unlocked"; channels: Channel[] }

export const DEVICES: Device[] = [
  {
    name: "Stagebox-A", model: "Yamaha Rio3224-D2", ip: "192.168.10.21", format: "48 kHz · 24-bit", clock: "locked",
    channels: [
      { n: 1, name: "Vox Lead", dir: "tx", flow: "multicast", group: "239.255.12.6", db: -18.5, peak: -11.0 },
      { n: 2, name: "Vox Backing", dir: "tx", flow: "multicast", group: "239.255.12.7", db: -24.0, peak: -16.5 },
      { n: 3, name: "Kick", dir: "tx", flow: "unicast", db: 0, peak: 0, clip: true },
      { n: 4, name: "Snare", dir: "tx", flow: "unicast", db: -9.5, peak: -4.0 },
      { n: 5, name: "Bass DI", dir: "tx", flow: "unicast", db: -14.0, peak: -8.5 },
      { n: 6, name: "Spare", dir: "tx", flow: "unicast", db: null, peak: null },
    ],
  },
  {
    name: "FOH-Console", model: "Yamaha CL5", ip: "192.168.10.30", format: "48 kHz · 24-bit", clock: "leader",
    channels: [
      { n: "1–2", name: "Stage Mix", dir: "tx", flow: "multicast", group: "239.255.12.4", db: -6.5, peak: -2.5, r: { db: -7.0, peak: -3.0 } },
      { n: "3–4", name: "AES67 Program", dir: "tx", flow: "aes67", group: "239.69.83.67", db: -16.0, peak: -10.0, r: { db: -16.5, peak: -10.5 } },
      { n: 1, name: "From Stagebox: Kick", dir: "rx", flow: "unicast", source: "Stagebox-A · 3 Kick · unicast", db: 0, peak: 0, clip: true },
      { n: 2, name: "From Stagebox: Bass DI", dir: "rx", flow: "unicast", source: "Stagebox-A · 5 Bass DI · unicast", db: -14.0, peak: -8.5 },
      { n: 3, name: "Spare in", dir: "rx", flow: "unicast", db: null, peak: null },
    ],
  },
  {
    name: "Monitor-Rack", model: "Allen & Heath DX168", ip: "192.168.10.44", format: "48 kHz · 24-bit", clock: "locked",
    channels: [
      { n: "1–2", name: "Wedge mix", dir: "rx", flow: "multicast", group: "239.255.12.4", source: "FOH-Console · 1–2 Stage Mix · multicast", db: -19.5, peak: -12.0, r: { db: -20.5, peak: -13.0 } },
      { n: "3–4", name: "IEM", dir: "rx", flow: "aes67", group: "239.69.83.67", source: "FOH-Console · 3–4 AES67 Program · AES67", db: -22.0, peak: -15.0, muted: true, r: { db: -23.0, peak: -16.0 } },
    ],
  },
]

/** Channels in a row (a stereo pair counts as two). */
export const chCount = (c: Channel) => (c.r ? 2 : 1)
export const maxDb = (c: Channel) => Math.max(c.db ?? -99, c.r?.db ?? -99)

export const FLOWS = [
  { source: "FOH-Console", channels: "1–2 Stage Mix (stereo)", type: "Multicast", dest: "239.255.12.4:5004", format: "48 kHz · 24-bit · 2 ch", listen: true },
  { source: "FOH-Console", channels: "3–4 AES67 Program (stereo)", type: "AES67", dest: "239.69.83.67:5004", format: "48 kHz · L24 · 2 ch", listen: true },
  { source: "Stagebox-A", channels: "1 Vox Lead", type: "Multicast", dest: "239.255.12.6:5004", format: "48 kHz · 24-bit · 1 ch", listen: true },
  { source: "Stagebox-A", channels: "2 Vox Backing", type: "Multicast", dest: "239.255.12.7:5004", format: "48 kHz · 24-bit · 1 ch", listen: true },
  { source: "Stagebox-A", channels: "3–5 Drums, Bass", type: "Unicast", dest: "FOH-Console", format: "48 kHz · 24-bit · 3 ch", listen: false },
  { source: "Stagebox-A", channels: "1", type: "Unicast", dest: "Monitor-Rack", format: "48 kHz · 24-bit · 1 ch", listen: false },
]
