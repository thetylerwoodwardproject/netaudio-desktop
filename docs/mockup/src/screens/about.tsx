import { PageHeader } from "@/components/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function AboutPage() {
  return (
    <>
      <PageHeader title="About" description="NetAudio Monitor 2026.11.23 · MIT licence" />
      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader><CardTitle>Credits</CardTitle><CardDescription>Built on open-source work.</CardDescription></CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p><span className="text-foreground">NetAudio</span> (chris-ritsen/network-audio-controller, Unlicense): the bundled <code className="font-mono">netaudio-daemon</code> and the multicast receive code the decoder is ported from.</p>
            <p><span className="text-foreground">Dear ImGui, GLFW, miniaudio, nlohmann/json</span>: UI, windowing, audio output and JSON.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Trademarks</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted-foreground">Dante is a registered trademark of Audinate Pty Ltd. NetAudio Monitor is not affiliated with or endorsed by Audinate.</CardContent>
        </Card>
      </div>
    </>
  )
}
