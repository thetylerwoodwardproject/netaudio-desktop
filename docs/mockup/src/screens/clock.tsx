import { PageHeader } from "@/components/page-header"
import { StatusPill } from "@/components/status-pill"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const ROWS = [
  { device: "FOH-Console", role: "Leader", state: "Locked", offset: "0 ns", rate: "48 kHz" },
  { device: "Stagebox-A", role: "Follower", state: "Locked", offset: "+42 ns", rate: "48 kHz" },
  { device: "Monitor-Rack", role: "Follower", state: "Locked", offset: "−61 ns", rate: "48 kHz" },
]

export function ClockPage() {
  return (
    <>
      <PageHeader title="Clock" description="Read-only PTP status per device and which device leads." />
      <Card className="py-2">
        <Table>
          <TableHeader><TableRow>{["Device", "Role", "State", "Offset from leader", "Sample rate"].map((h) => <TableHead key={h} className="px-4">{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {ROWS.map((r) => (
              <TableRow key={r.device}>
                <TableCell className="px-4 font-medium">{r.device}</TableCell>
                <TableCell className="px-4">{r.role === "Leader" ? <StatusPill tone="info" dot={false}>Leader</StatusPill> : r.role}</TableCell>
                <TableCell className="px-4"><StatusPill tone="ok">{r.state}</StatusPill></TableCell>
                <TableCell className="px-4 font-mono text-xs">{r.offset}</TableCell>
                <TableCell className="px-4 font-mono text-xs">{r.rate}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  )
}
